# CloudsineAI Scanner

A web app that lets you upload a file, scans it with the VirusTotal API, shows the verdict and per-engine breakdown, and can explain the result in plain English using Google Gemini.

- **Live demo:** http://13.213.0.0

---

## What it does

1. User uploads a file through the web interface
2. The backend streams it to VirusTotal's `POST /files` endpoint and polls for the scan result
3. The React frontend displays the verdict (`clean` / `suspicious` / `malicious`), per-engine breakdown, and aggregate stats as soon as the scan completes
4. The user can click "Explain this scan to me" to get a plain-English explanation from Gemini, and ask follow-up questions in a chat that persists across page refreshes
5. Previously scanned files are deduplicated by SHA-256, so re-uploading returns the cached result

---

## Stack

| Layer | Technology |
| --- | --- |
| Backend | Python 3.12, FastAPI, Uvicorn, SQLAlchemy, Alembic, Pydantic, tenacity |
| Frontend | React 18, TypeScript, Vite, Tailwind (CDN), react-markdown |
| Database | PostgreSQL |
| External APIs | VirusTotal v3, Google Gemini (`gemini-3.1-flash-lite-preview` primary, `gemini-3-flash-preview` fallback) |
| Runtime | Docker + Docker Compose on Ubuntu 24.04 (t2.micro) |
| Web server | Nginx (serves the SPA and reverse-proxies `/api/*`) |
| Dev tooling | Ruff, pytest, TypeScript, ESLint-free (tsc --noEmit) |

---

## How to run it

### Option 1. Visit the live demo

Open **http://13.213.0.0** in a browser. No setup required.

### Option 2. Run locally with Docker Compose

You'll need Docker Desktop, and your own VirusTotal + Gemini API keys.

```bash
git clone https://github.com/jovitaeliana/cloudsine-assignment.git
cd cloudsine-assignment

# Copy the template and fill in your keys
cp .env.example .env
# Open .env and set VIRUSTOTAL_API_KEY, GEMINI_API_KEY, POSTGRES_PASSWORD

# Start the full stack (frontend, backend, Postgres)
docker compose up --build

# App will be available at http://localhost
```

### Option 3. Run the backend only, against local Postgres (for development)

```bash
# Start just Postgres
docker compose up -d db

# Set up Python environment
cd backend
python3.12 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"

# Run the app with auto-reload
uvicorn app.main:app --reload --port 8000
```

Frontend (separate terminal):

```bash
cd frontend
npm install
npm run dev
# Open http://localhost:5173
```

### Running tests

```bash
# Backend (requires Postgres running on localhost)
cd backend
source .venv/bin/activate
pytest -v

# Frontend (type check + build)
cd frontend
npm run lint && npm run build
```

---

# Documentation

## Build process

The project was built in four rough phases: backend, frontend, containerisation, then deployment. After the first working version, a fifth phase added polish (chat persistence, markdown, UI fixes).

### Backend

Built bottom-up so every layer could be tested before the next was added.

1. Scaffolding. FastAPI app, `Settings` loader from `.env`, SQLAlchemy engine, and a `/api/healthz` endpoint. Just enough to confirm the dev loop worked.
2. Data layer. Defined the `Scan` ORM model and wrote the initial Alembic migration. Migrations auto-run on container startup, so any environment ends up on the right schema.
3. Schemas. Pydantic request and response DTOs in `schemas.py`. Every endpoint declares a `response_model` so raw VirusTotal and Gemini payloads are filtered before reaching the browser.
4. Utilities. Streaming SHA-256 hasher and upload validation. Files stream through memory into the hasher and out to VirusTotal, never touching disk.
5. External clients. One module per external dependency: `virustotal.py` and `gemini.py`. If an upstream API changes, only one file needs edits.
6. Business logic. `scan_service.py` orchestrates hashing, cache lookup, VT upload, polling, and verdict computation. Routers stay thin: they parse input, call one service function, and return a DTO.
7. Tests. Unit tests for each pure-logic module, plus an integration test suite that runs the full FastAPI app against a real Postgres with VT and Gemini mocked.

### Frontend

Chose to use a simple Vite + React + TypeScript scaffold. 

- Components each own the data they display: `UploadZone`, `VerdictCard`, `VendorTable`, `RecentScans`, `ChatThread`.
- Hooks own the async concerns: `useScanPoll` drives the active scan, `useRecentScans` loads the sidebar.
- A single `api/client.ts` with typed fetch wrappers, and a `types.ts` that mirrors the backend schemas.


### Containerisation

Multi-stage Dockerfiles for both services with `dev` and `prod` targets. The frontend prod target uses `node:20-alpine` to build, then copies only the static assets into `nginx:alpine`, so the runtime image is about 22 MB.

Docker Compose runs three services: `frontend`, `backend`, `db`. Per-container memory limits keep the full stack under 768 MB, which fits on the t2.micro. A dev override file adds hot-reload and exposed ports.

### Deployment

I launched a t2.micro in `ap-southeast-1` running Ubuntu 24.04 LTS (free tier eligible), and attached an Elastic IP so the public address survives reboots. The security group opens port 22 (SSH) and port 80 (HTTP).

After SSHing in with the PEM key, I ran `scripts/provision.sh` once. The script installs Docker Engine, adds a 2 GB swap file, adds the `ubuntu` user to the `docker` group, and creates `/opt/cloudsine`. It is idempotent.

Nginx is the web server. I picked it over Apache because the `nginx:alpine` image is small and its reverse-proxy + static-file config is simple for a single-page app. Nginx serves the built React assets and proxies `/api/*` to the FastAPI container, so the SPA and API share the same origin and CORS is not needed in production.

Images are built on my laptop with `--platform linux/amd64` and pushed to GHCR. The instance only pulls and runs; it never builds. This avoids out-of-memory errors on a 1 GB instance. Deploys are currently manual: SSH in, `git pull`, `docker compose pull`, `docker compose up -d`. Automating this with GitHub Actions is described under [Future improvements](#future-improvements).

### Iteration

The first version worked but felt rough. A second pass added:

- Fixed-interval polling on the active scan plus background polling on the sidebar, so verdicts appear without clicking.
- A persistent multi-turn chat backed by a new `scan_messages` table, replacing the one-shot explanation button.
- Tenacity retries plus a fallback model on the Gemini client, so transient 503s do not surface as errors.
- Upload spinner, severity-sorted vendor table with a "show only flagged" toggle, and markdown rendering for assistant messages.

## Challenges and solutions

### 1. First time hosting a website on EC2

I usually deploy with Railway or Vercel, which hide the complexity of setting up a server. EC2 exposed all of that at once: AMI, instance type, region, security group rules, SSH keys, and the deploy mechanism. It took a while to understand which settings mattered and how they fit together.

**Solution.** I used AI assistance to confirm that the settings I picked (instance type, AMI, security group rules) were appropriate, and to guide me through the options based on the project's requirements.

### 2. Testing on Apple Silicon vs deploying on x86

My MacBook is ARM64 and the t2.micro is x86-64. Images I built and tested locally failed on EC2 with "no matching manifest for linux/amd64".

**Solution.** I added `--platform linux/amd64` to the docker build commands to force amd64 output. This works but emulation is slow on ARM; moving builds to GitHub Actions (where the runners are already x86-64) is a planned improvement.

### 3. t2.micro's 1 GB of RAM

Building the frontend image on the t2.micro ran out of memory during `npm install`.

**Solution.** I stopped building on the instance. I build images on my laptop (forcing `linux/amd64`) and push to GHCR; the instance only pulls. I also added a 2 GB swap file and explicit per-container memory limits in [docker-compose.yml](docker-compose.yml) so no single container can starve the others.

### 4. Gemini 503 errors during testing

The "Explain this to me" button started returning a 500. Container logs showed a `google.genai.errors.ServerError: 503 UNAVAILABLE` from Gemini itself. The default `gemini-2.5-flash` model was temporarily overloaded on Google's side.

**Solution.** Four layers of defence so a transient upstream failure stops surfacing as a user-visible error:

1. Tenacity retries with exponential backoff (2s, 4s, 8s) on `ServerError`. Only 5xx is retried; 4xx errors propagate immediately because a retry would not help.
2. A fallback model (`gemini-3-flash-preview`). If the primary exhausts its retries, the client falls back to the secondary model once. Different model, different backend pool, independent failure mode.
3. Router-level graceful failure. [backend/app/routers/chat.py](backend/app/routers/chat.py) catches `ServerError`, commits the user's message anyway (so they don't have to retype on retry), and returns a 503 with the detail `"AI service is temporarily busy. Please try again in a moment."`. A separate `ClientError` branch maps to 502 with a different message, so transient overloads are distinguishable from auth or bad-request issues.
4. Frontend retry UX. [frontend/src/components/ChatThread.tsx](frontend/src/components/ChatThread.tsx) detects the 503 and shows a friendly amber banner ("Gemini is busy right now. Try again in a moment.") with a Retry button. Because the user's message is already persisted server-side, Retry just asks the LLM again against the same history, no retyping required.

## Future improvements

### CI/CD pipeline

Today the deploy loop is manual: build locally, push to GHCR, SSH to EC2, pull, restart. This is fine for a solo project but is the first thing I would automate next. Draft workflow files exist under [.github/workflows/](.github/workflows/) as a design sketch; they have not been exercised end-to-end yet.

The plan is two workflows:

- **`ci.yml`** — triggered on every pull request and every push to a non-`main` branch. Runs two jobs in parallel. The backend job spins up a Postgres service container, installs dependencies, and runs `ruff check` plus `pytest` (unit and integration). The frontend job runs `tsc --noEmit` and `vite build` to catch type errors and broken builds. The PR is blocked from merging if either job fails.
- **`deploy.yml`** — triggered only on push to `main`. Uses Docker Buildx on x86-64 runners to build both images for `linux/amd64`, tags them with `latest` and the commit SHA, and pushes to GHCR. Then SSHes into the EC2 instance, writes a fresh `.env` from GitHub Secrets, runs `docker compose pull && docker compose up -d`, and polls `/api/healthz` for up to 60 seconds. If the health check does not return 200, the job fails red and the backend logs are surfaced.

Before treating the pipeline as production-ready I would:

1. Configure the ten required GitHub Secrets (`EC2_HOST`, `EC2_USER`, `EC2_SSH_KEY`, `VIRUSTOTAL_API_KEY`, `GEMINI_API_KEY`, `POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_DB`, `CORS_ALLOWED_ORIGINS`, `ENVIRONMENT`) so the workflows can authenticate to EC2 and regenerate the server `.env`.
2. Push to a feature branch first to prove `ci.yml` goes green without touching production.
3. Push to `main` to prove `deploy.yml` builds, pushes to GHCR, deploys, and passes the health check — then independently confirm with `curl http://<ip>/api/healthz` from outside the box.
4. Deliberately break a lint rule and a health check on throwaway branches to confirm the pipeline fails red when it should. A pipeline that only goes green is not actually protecting anything.