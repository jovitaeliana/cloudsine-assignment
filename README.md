# CloudsineAI Scanner

A web app that lets you upload a file, scans it with the VirusTotal API, shows the verdict and per-engine breakdown, and can explain the result in plain English using Google Gemini.

- **Live demo:** http://13.213.0.0
- **Repo:** https://github.com/jovitaeliana/cloudsine-assignment

This is my submission for the Cloudsine WebTest take-home assignment ([requirements.md](requirements.md)).

---

## Table of contents

- [What it does](#what-it-does)
- [Stack](#stack)
- [How to run it](#how-to-run-it)
- [Architecture](#architecture)
- [How the assignment requirements are met](#how-the-assignment-requirements-are-met)
- [Setting up the EC2 instance](#setting-up-the-ec2-instance)
- [Challenges I faced](#challenges-i-faced)
- [Why this stack](#why-this-stack)
- [Project structure](#project-structure)
- [Testing](#testing)
- [Manual acceptance script](#manual-acceptance-script)
- [What I'd do next](#what-id-do-next)

---

## What it does

1. User uploads a file through the web interface
2. The backend streams it to VirusTotal's `POST /files` endpoint and polls for the scan result
3. The React frontend displays the verdict (`clean` / `suspicious` / `malicious`), per-engine breakdown, and aggregate stats as soon as the scan completes
4. The user can click "Explain this scan to me" to get a plain-English explanation from Gemini, and ask follow-up questions in a chat that persists across page refreshes
5. Previously scanned files are deduplicated by SHA-256, so re-uploading returns the cached result in under 500 ms

## Stack

| Layer | Technology |
| --- | --- |
| Backend | Python 3.12, FastAPI, Uvicorn, SQLAlchemy 2, Alembic, Pydantic v2, tenacity |
| Frontend | React 18, TypeScript, Vite, Tailwind (CDN), react-markdown |
| Database | PostgreSQL 16 |
| External APIs | VirusTotal v3, Google Gemini (`gemini-3.1-flash-lite-preview` primary, `gemini-3-flash-preview` fallback) |
| Runtime | Docker + Docker Compose on Ubuntu 24.04 (t2.micro) |
| Web server | Nginx (serves the SPA and reverse-proxies `/api/*`) |
| CI/CD | GitHub Actions → GHCR → SSH deploy to EC2 |
| Dev tooling | Ruff, pytest, TypeScript, ESLint-free (tsc --noEmit) |

---

## How to run it

### Option 1 — Just visit the live demo

Open **http://13.213.0.0** in a browser. No setup required.

### Option 2 — Run locally with Docker Compose

You'll need Docker Desktop, and your own VirusTotal + Gemini API keys.

```bash
git clone https://github.com/jovitaeliana/cloudsine-assignment.git
cd cloudsine-assignment

# Copy the template and fill in your keys
cp .env.example .env
# Open .env and set VIRUSTOTAL_API_KEY, GEMINI_API_KEY, POSTGRES_PASSWORD

# Start the full stack — frontend, backend, Postgres
docker compose up --build

# App will be available at http://localhost
```

### Option 3 — Run the backend only, against local Postgres (for development)

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

## Architecture

Single EC2 instance. Three containers on a private Docker network. Only Nginx is exposed to the public internet.

```
 Browser ──:80──►  Nginx (alpine)  ──►  FastAPI + Uvicorn  ──►  Postgres 16
                   serves SPA +                │
                   proxies /api/*              ├──►  VirusTotal v3 API
                                               └──►  Google Gemini API
```

**Key design decisions:**

- **Nginx fronts FastAPI** so the browser talks to a single origin (`http://13.213.0.0`). The SPA and the API share the same origin, which avoids CORS in production and lets the frontend use relative URLs like `/api/scan`.
- **Postgres runs in Docker**, not RDS. On a free-tier budget, containerized Postgres is simpler and cheaper. The `db` service has no exposed port, so it's only reachable from the backend container on the private Docker network.
- **Images are built in CI**, never on the EC2 instance. The t2.micro only has 1 GB of RAM, and a `docker build` would OOM during `npm install`. GitHub Actions builds the images on its x86-64 runners and pushes them to GHCR; the instance just pulls.
- **Per-container memory limits** in [docker-compose.yml](docker-compose.yml): backend 384 MB, frontend 128 MB, Postgres 256 MB. Total fits in 1 GB RAM with headroom for the kernel and a 2 GB swap file configured in [scripts/provision.sh](scripts/provision.sh).

---

## How the assignment requirements are met

### Step 1 — EC2 hosted web server ✅

- t2.micro in `ap-southeast-1`, Ubuntu 24.04 LTS
- Security group opens port 22 (SSH) and port 80 (HTTP)
- Nginx is the web server, running inside a container

(See [Setting up the EC2 instance](#setting-up-the-ec2-instance) below for the full walkthrough.)

### Step 2 — Core functionality

#### File upload with basic validation ✅

**Client side** — [frontend/src/components/UploadZone.tsx](frontend/src/components/UploadZone.tsx) supports drag-and-drop and click-to-pick. Before sending to the server it checks:
- File is not empty
- File is ≤ 32 MB

**Server side** — [backend/app/utils/validation.py](backend/app/utils/validation.py) re-validates the same two rules before doing anything else. The client check is a UX hint; the server check is the real gate. Failures return `400 Bad Request` (empty) or `413 Payload Too Large` (oversize) with a descriptive message.

**Streaming hash** — [backend/app/utils/hashing.py](backend/app/utils/hashing.py) reads the upload in 64 KB chunks into an in-memory buffer while computing SHA-256 on the fly. No temp files, no disk writes.

**Deduplication** — if the same SHA-256 hash already has a completed scan in the database, we return that immediately with `cached: true`. Saves VirusTotal quota and gives sub-500 ms responses for repeat uploads.

#### VirusTotal integration ✅

[backend/app/services/virustotal.py](backend/app/services/virustotal.py) wraps VirusTotal's v3 API:

1. `POST /files` — upload the bytes, get back an `analysis_id`
2. `GET /analyses/{id}` — poll until status is `completed`
3. `GET /files/{sha256}` — fetch the full file report once analysis finishes

All three endpoints are called via `httpx` with an `x-apikey` header. The API key is read from environment (`VIRUSTOTAL_API_KEY`) and never logged or returned to the frontend.

#### Dynamic result display ✅

The SPA polls `GET /api/scan/{scan_id}` every 3 seconds after upload. When the backend returns `status: complete`, the frontend swaps the "Scanning..." placeholder for three components:

- `VerdictCard` — big color-coded verdict box (red/yellow/green)
- `VendorTable` — per-engine results, severity-sorted, filter toggle defaults to "show only flagged"
- `ChatThread` — the Gemini explanation chat

The **Recent Scans sidebar** also auto-refreshes every 5 seconds while any scan in the list is pending, so verdicts appear without user action.

#### GenAI explanation ✅

"Explain this scan to me" button → calls `POST /api/chat/{scan_id}` with a preset opener. [backend/app/services/gemini.py](backend/app/services/gemini.py) sends the scan context (filename, verdict, stats, top flagged engines) as a `system_instruction` plus the message history, and returns the model's response.

The user can then ask **follow-up questions** — both free-text input and verdict-specific suggested chips (e.g., for a malicious verdict: "How do I safely remove it?"). All messages persist in the `scan_messages` table, so refreshing the page reloads the conversation.

#### Preferred language ✅

Python 3.12 for the backend. The assignment said Python or Go were preferred; I chose Python because I'm more experienced with it and FastAPI's ergonomics around typed request/response models fit the problem well.

### Step 2 — Security considerations

#### Handle file uploads securely to prevent malicious file execution ✅

The core principle: **the backend never interprets, executes, or persists uploaded files**. It treats every upload as an opaque byte stream that flows through to VirusTotal's sandboxed infrastructure.

Concrete defenses:

- **No disk writes.** Files stream through memory into a `BytesIO`, through a SHA-256 hasher, and straight out to VirusTotal's upload endpoint. After the request finishes the buffer is garbage-collected. Only scan metadata (filename, size, verdict, stats) is persisted to Postgres — never the file bytes.
- **No interpretation.** We don't parse, deserialize, or run the file in any way. No `subprocess`, no `exec`, no `pickle`, no dispatching on `Content-Type`.
- **Size and emptiness validation** on both client and server, as described above. An attacker can't DOS our VirusTotal quota by spamming huge payloads.
- **Filename escaping.** React automatically escapes the filename when rendering (prevents XSS), and SQLAlchemy's parameterized queries prevent SQL injection when the filename is stored.
- **Network isolation.** The `db` service has no published port, so Postgres is only reachable from the `backend` container on the Docker network. Even if someone compromised the upload path, they couldn't pivot to the database from the public internet.
- **Least privilege container.** The backend container creates a non-root `appuser` and runs as that user ([backend/Dockerfile](backend/Dockerfile)).

#### Sanitize API requests and responses ✅

**Requests** — every request body is validated by a Pydantic model. FastAPI automatically returns `422 Unprocessable Entity` on schema violations:

- `POST /api/scan` — file type enforced by `UploadFile`; size/empty checks via `validate_upload()`
- `POST /api/chat/{id}` — `ChatRequest` with `message: str = Field(..., min_length=1, max_length=2000)` rejects empty or overly long inputs
- `GET /api/scans?limit=N` — the handler clamps `limit` to the range 1–100
- Path params like `{scan_id}` are typed as `UUID`, so non-UUID strings fail parsing before reaching the handler

**Responses** — every route declares a `response_model` pointing at an explicit Pydantic class. Raw payloads from VirusTotal and Gemini are filtered through our schemas before reaching the browser:

- `ScanDetail` — whitelist of scan columns, no raw VT payload
- `ChatResponse` — just the user + assistant message rows
- `MessageDTO` — exactly the fields we want exposed

This prevents upstream API changes from accidentally leaking internal fields to the client. An attacker can't sniff VirusTotal's response headers or internal status codes through our API.

Other cross-cutting protections:

- **CORS** locked to `CORS_ALLOWED_ORIGINS` (just the production origin in prod)
- **Error messages** are sanitized — `ServerError` from Gemini becomes `"AI service is temporarily busy. Please try again in a moment."`, never a raw traceback
- **Secrets** stay server-side and are loaded from `.env`. They're read into a single `Settings` object at startup and injected via dependency injection; they never appear in a response

### Step 3 — Test with sample files ✅

Five sample files in [files/](files/) are used as the manual acceptance set:

| File | Expected verdict |
| --- | --- |
| `forbes_magecart_skimmer.js` | malicious |
| `newegg_magecart_skimmer.js` | malicious |
| `obfuscated_cryptomine.js` | malicious or suspicious |
| `jquery-3.5.1.min.js` | clean |
| `moment.min.js` | clean |

All verdicts have been verified against the live deployment.

### Bonus — Dockerization ✅

- **Separate dev and prod Dockerfiles** as multi-stage builds ([backend/Dockerfile](backend/Dockerfile), [frontend/Dockerfile](frontend/Dockerfile))
- **Docker Compose** with three services: `frontend`, `backend`, `db` ([docker-compose.yml](docker-compose.yml))
- **Dev overrides** in [docker-compose.dev.yml](docker-compose.dev.yml) add hot-reload, bind mounts, and exposed ports for frontend/backend

**Image size optimizations:**

- `python:3.12-slim` and `node:20-alpine` / `nginx:alpine` as base images
- Multi-stage build for the frontend: `node:20-alpine` builds `dist/`, then only the static files are copied into the final `nginx:alpine` container — no Node or npm in the runtime image
- `pip install --no-cache-dir` skips pip's local cache
- Layer ordering: `COPY pyproject.toml` and `pip install` happen **before** `COPY app ./app`, so source-only changes reuse the cached dependency layer
- Dev dependencies (pytest, ruff, respx) are not installed in the `prod` stage

### Bonus — CI/CD pipeline ✅

Two GitHub Actions workflows:

**[.github/workflows/ci.yml](.github/workflows/ci.yml)** — runs on every PR and non-main push:
- Backend job: Postgres service container → `pip install -e ".[dev]"` → `ruff check` → `pytest` (26 unit + 10 integration tests)
- Frontend job: `npm ci` → `npm run lint` (TypeScript `--noEmit`) → `npm run build` (Vite production build catches type errors)

**[.github/workflows/deploy.yml](.github/workflows/deploy.yml)** — runs only on push to `main`:
1. `build-and-push`: Buildx builds both images for `linux/amd64`, tags them with `latest` and the commit SHA, pushes to GHCR, uses GHA cache for fast rebuilds
2. `deploy`: SSH into EC2 via `appleboy/ssh-action`, write `.env` from GitHub Secrets, `git pull`, `docker compose pull && up -d`, poll `/api/healthz` until it returns 200

### Bonus — Integration tests ✅

[backend/tests/test_scan_integration.py](backend/tests/test_scan_integration.py) runs the FastAPI app through `TestClient` against a real Postgres test database, with VirusTotal and Gemini mocked:

- `test_upload_then_poll_returns_complete` — full scan lifecycle
- `test_second_upload_hits_cache` — SHA-256 deduplication
- `test_chat_post_persists_both_messages_and_returns_them` — chat round-trip
- `test_chat_get_returns_history_in_order` — multi-turn history
- `test_chat_preserves_user_message_on_gemini_server_error` — resilience on upstream failure
- …and 5 more covering validation, 404s, 409s, and message-length limits

Tests auto-skip when Postgres isn't reachable, so `pytest` in a bare environment still passes cleanly.

### Bonus — Secure secret management ✅

- `.env` is **gitignored** ([.gitignore](.gitignore)) and only exists on developer machines and the EC2 host
- `.env.example` is committed, but has empty values — it documents the contract without the data
- In production, the deploy workflow writes `.env` on the EC2 instance from **GitHub Secrets** every deploy. Secrets never live in the repo or in Docker image layers
- All secrets are read through a single `Settings` class in [backend/app/config.py](backend/app/config.py), so migrating to AWS Secrets Manager in the future would be a one-file change

AWS Secrets Manager was considered but left out of scope — it adds IAM setup and cost (~$0.40 per secret per month) without meaningful security benefit for a single-host demo. For a production multi-service system, the central-rotation and audit-log benefits would make it worthwhile.

---

## Setting up the EC2 instance

This section walks through how I set up the AWS EC2 instance from scratch, and why I made the choices I did.

### Instance type: t2.micro

Chosen because:
- It's **free tier eligible** — 750 hours per month
- 1 GB RAM is enough when I don't build images on the instance (CI does the builds; the instance just pulls)
- For a demo with one user at a time, 1 vCPU is fine

Trade-off: 1 GB RAM is tight. I compensated with a 2 GB swap file (see [scripts/provision.sh](scripts/provision.sh)), per-container memory limits in Compose, and pre-built images from CI.

### Operating system: Ubuntu 24.04 LTS

Ubuntu over Amazon Linux because:
- Docker's official apt repo has first-class Ubuntu support — `apt-get install docker-ce` just works
- More community tutorials and answered Stack Overflow threads reference Ubuntu, which helped when I was debugging
- Trade-off: Amazon Linux is marginally more optimized for EC2, but for this workload the difference is negligible

### Region: ap-southeast-1 (Singapore)

Lowest latency for me (Southeast Asia). Any region works since the assignment reviewer can be anywhere.

### Security group rules

| Port | Source | Why |
|---|---|---|
| 22 (SSH) | 0.0.0.0/0 | For me to SSH in. I initially restricted to "My IP", but changing networks (cafe → home) kept breaking my connection. Since SSH is key-only (no password auth) and the `.pem` is 2048-bit RSA, opening to the world is still secure — bots scanning port 22 can't brute-force a cryptographic key. |
| 80 (HTTP) | 0.0.0.0/0 | Required so any reviewer can reach the app |
| All other inbound | Blocked | Default deny — nothing else is exposed |

Port 5432 (Postgres) is **deliberately not opened**. Postgres is only reachable from inside the Docker network via the service name `db`, so there's no attack surface from the public internet.

### Web server: Nginx

Nginx over Apache because:
- Lower memory footprint — runs comfortably in 128 MB
- The `nginx:alpine` image is ~22 MB, which matters on a tight RAM budget
- Its reverse-proxy + static-file-serving config is simpler for a single-page app than Apache's module system

Role in this stack: Nginx serves the React build output (`dist/index.html` + JS/CSS assets) and reverse-proxies everything under `/api/*` to the FastAPI container. This means:
- The SPA and API share the same origin (`http://13.213.0.0`), so no CORS in production
- Static assets are served directly by Nginx (efficient)
- The FastAPI container is never directly exposed — Nginx is the only public-facing process

Config is at [frontend/nginx.conf](frontend/nginx.conf).

### How the app is reachable

1. The EC2 instance has an **Elastic IP** (`13.213.0.0`) — a static public address that survives reboots
2. The security group allows inbound port 80
3. Docker maps port 80 on the host to port 80 in the frontend (Nginx) container
4. Nginx routes static requests to the SPA and `/api/*` requests to the backend

Anyone can open http://13.213.0.0 from any browser, and the app loads.

### Provisioning script

[scripts/provision.sh](scripts/provision.sh) is idempotent — safe to run multiple times. On a fresh instance it:

1. Installs Docker Engine and the Compose plugin from Docker's official Ubuntu repo
2. Creates a 2 GB swap file at `/swapfile` (critical for 1 GB RAM)
3. Adds the `ubuntu` user to the `docker` group (so `docker` works without `sudo`)
4. Creates `/opt/cloudsine` with the right ownership

After running it once, a fresh SSH session has everything needed to pull images and run `docker compose up -d`.

---

## Challenges I faced

### 1. Setting up AWS from scratch

This was my **first time using AWS**. Creating the account, understanding billing (free tier limits, when you leave it), and navigating the console was a lot of clicking around. I accidentally almost picked Amazon Linux for the AMI because it was the default Quick Start option, and only caught the mistake after my provisioning script errored out on `apt-get update` (Amazon Linux uses `dnf`). Now I double-check the AMI selection.

### 2. First time hosting a website on EC2

Previously I'd only run web apps locally or on Vercel/Netlify. EC2 is much more hands-on — you manage the OS, the web server, the firewall (security group), the domain, the TLS, the deploy mechanism, all of it. The mental shift was realizing that "hosting on EC2" isn't one decision, it's a dozen: which AMI, which instance type, which region, which security group rules, how to SSH, how to get code onto the box, how to update it.

### 3. Never used Nginx before

I picked Nginx because it was one of the options the assignment mentioned. Debugging its config was humbling — my first attempt had the `proxy_pass` target wrong and the SPA couldn't reach the API. The fix was learning that inside a Docker Compose network, services address each other by service name (`http://backend:8000`), not `localhost`. See [frontend/nginx.conf](frontend/nginx.conf) for the final config.

### 4. Apple Silicon vs EC2 architecture mismatch

My MacBook is ARM64; EC2 t2.micro is x86-64 (amd64). When I first built images locally and pushed them, the EC2 instance errored on `docker compose pull` with "no matching manifest for linux/amd64". Fixed by passing `--platform linux/amd64` to `docker build`, which emulates via Rosetta. This was also the motivation to move all builds into GitHub Actions (whose runners are x86-64 by default).

### 5. t2.micro's 1 GB of RAM

Building images on the t2.micro itself didn't work — `npm install` alone OOM'd the instance during the frontend build. The fix was moving all builds to CI and treating the instance as purely a runtime. Plus a 2 GB swap file for margin, and explicit per-container memory limits in Compose.

### 6. Gemini 503 overloads

Mid-demo testing, clicking "Explain this to me" started returning a 500 on the frontend. Looking at container logs, the underlying error was a `google.genai.errors.ServerError: 503 UNAVAILABLE` — the default `gemini-2.5-flash` model was temporarily overloaded on Google's side. Three fixes:
1. Moved to `gemini-3.1-flash-lite-preview` (faster, less contended pool)
2. Added tenacity-based retries with exponential backoff (3 attempts: 2s, 4s, 8s)
3. Added `gemini-3-flash-preview` as a fallback model — different backend pool = independent availability

Now transient 503s are absorbed silently, and only persistent failures show a friendly "Gemini is busy, try again shortly" banner.

### 7. Auto-refresh on scan completion

The first version had exponential backoff polling (3s → 4s → 5s → ... → 15s), which meant if VirusTotal finished scanning at the 10-second mark but the next poll was scheduled for 15 seconds, the user stared at "Scanning..." for 5 more seconds of dead air. I switched to a fixed 3-second interval for the active scan and added background polling on the Recent Scans sidebar so pending scans update without user action.

---

## Why this stack

### Python + FastAPI

- The assignment prefers Python or Go
- FastAPI gives me automatic request/response validation via Pydantic, OpenAPI docs for free, and async support for httpx calls to VirusTotal
- Strong typing without feeling like Java — Pydantic catches most shape bugs at the boundary

### React + TypeScript + Vite

- React is the most common choice for SPAs, with the largest library ecosystem
- TypeScript catches the class of bugs where the frontend and backend disagree on a field name
- Vite builds in milliseconds; the whole dev cycle feels instant

### Tailwind CDN

- I didn't want to set up PostCSS or Tailwind's build pipeline for a small SPA
- The CDN version is one `<script>` tag in `index.html`. Good enough for this scope.

### Nginx

- Small memory footprint (`nginx:alpine` is 22 MB)
- The reverse-proxy + static-file config is dead simple
- Gives me one place to add rate limiting, TLS, or CDN integration later

### PostgreSQL 16

- Postgres is the default "serious" database for almost any new project
- JSONB columns are useful for the `stats` and `vendor_results` fields where the shape comes from VirusTotal and normalizing them further would be pointless
- Alembic integrates cleanly with SQLAlchemy for migrations
- `postgres:16-alpine` is a small image

### Docker + Docker Compose

- Declarative, reproducible setup — any reviewer can `docker compose up` from a clean checkout and get the same stack I'm running
- Network isolation between services without firewall rules
- Per-container memory limits enforceable in YAML

### GitHub Actions over alternatives

- Free for public repos
- Runners are x86-64, matching the EC2 architecture
- The workflow files live next to the code, so changes are PR-reviewed together with related application changes

---

## Project structure

```
cloudsine-assignment/
├── README.md                          # this file
├── requirements.md                    # original assignment brief
├── docker-compose.yml                 # production stack
├── docker-compose.dev.yml             # dev overrides (hot reload, exposed ports)
├── .env.example                       # template for secrets (committed, empty values)
├── .gitignore                         # excludes .env, node_modules, etc.
│
├── .github/workflows/
│   ├── ci.yml                         # lint + test on every PR
│   └── deploy.yml                     # build, push to GHCR, deploy to EC2 on main
│
├── backend/
│   ├── Dockerfile                     # multi-stage: dev | prod
│   ├── pyproject.toml                 # deps + ruff + pytest config
│   ├── alembic.ini
│   ├── alembic/versions/
│   │   ├── 0001_initial.py            # scans table
│   │   └── 0002_scan_messages.py      # chat messages table
│   ├── app/
│   │   ├── main.py                    # FastAPI app, middleware, router wiring
│   │   ├── config.py                  # pydantic-settings, reads .env
│   │   ├── database.py                # SQLAlchemy engine, session, get_db
│   │   ├── models.py                  # Scan, ScanMessage ORM models
│   │   ├── schemas.py                 # request/response DTOs
│   │   ├── deps.py                    # DI for VT and Gemini clients
│   │   ├── routers/
│   │   │   ├── scans.py
│   │   │   └── chat.py
│   │   ├── services/
│   │   │   ├── virustotal.py
│   │   │   ├── gemini.py              # multi-turn + retry + fallback
│   │   │   └── scan_service.py
│   │   └── utils/
│   │       ├── hashing.py             # streaming SHA-256
│   │       └── validation.py          # size, emptiness checks
│   └── tests/
│       ├── test_hashing.py
│       ├── test_validation.py
│       ├── test_virustotal.py
│       ├── test_gemini.py             # retry, fallback, multi-turn
│       ├── test_scan_service.py
│       ├── test_scan_integration.py   # real DB, mocked external APIs
│       └── test_health.py
│
├── frontend/
│   ├── Dockerfile                     # node build → nginx serve
│   ├── nginx.conf                     # static + /api/* proxy
│   ├── package.json
│   ├── vite.config.ts
│   ├── tsconfig.json
│   ├── index.html
│   └── src/
│       ├── main.tsx
│       ├── App.tsx                    # layout: upload + result + sidebar
│       ├── api/client.ts              # typed fetch wrappers
│       ├── components/
│       │   ├── UploadZone.tsx
│       │   ├── VerdictCard.tsx
│       │   ├── VendorTable.tsx        # filter, severity sort, badges
│       │   ├── ChatThread.tsx         # multi-turn Gemini chat
│       │   ├── MessageBubble.tsx      # markdown-rendered assistant replies
│       │   └── RecentScans.tsx
│       ├── hooks/
│       │   ├── useScanPoll.ts         # polling with fixed 3s interval
│       │   └── useRecentScans.ts      # auto-polls while any scan is pending
│       └── types.ts
│
├── files/                             # sample files for manual acceptance
├── scripts/
│   └── provision.sh                   # idempotent EC2 provisioning
└── docs/
    └── specs.md                       # design spec
```

---

## Testing

### Automated

36 tests total:

- **26 unit tests** covering streaming hashing, validation edge cases, VirusTotal client HTTP handling, Gemini client (multi-turn, retry, fallback, error handling), and verdict computation
- **10 integration tests** that spin up the FastAPI app through `TestClient` against a real Postgres database with VirusTotal and Gemini mocked

Run all: `pytest -v` in `backend/` (requires local Postgres on port 5432 for integration tests; unit tests always run).

Frontend: `npm run build` in `frontend/` catches TypeScript errors.

CI runs all of the above on every PR via [.github/workflows/ci.yml](.github/workflows/ci.yml).

### Manual acceptance script

```
1. Upload files/jquery-3.5.1.min.js
   → verdict "clean" appears within ~15s without clicking

2. Upload files/forbes_magecart_skimmer.js
   → verdict "malicious"
   → vendor table shows flagged engines at the top, defaults to
     "Show only flagged"

3. Click "Explain this scan to me"
   → plain-English 2-3 paragraph explanation renders with markdown

4. Click chip "How do I safely remove it?"
   → contextual response considers the prior explanation

5. Type a follow-up: "How did I get this file?"
   → response addresses the question in context

6. Reload the page (Cmd+R)
   → click the same scan in the sidebar
   → full chat history reloads

7. Upload the same file again
   → second response returns in <500 ms with cached=true

8. Click a different scan in the sidebar
   → that scan's own chat history loads (not the previous scan's)
```

---

## What I'd do next

If I had more time:

- **HTTPS with a custom domain** — use DuckDNS or a cheap domain + Let's Encrypt via certbot
- **Full AWS Secrets Manager integration** — replace `.env` on the EC2 host with IAM-role-based secrets fetching
- **Authentication** — optional per-user scoping so the reviewer's scans don't pollute other users' sidebars
- **Download scan as PDF or JSON** — useful for real-world workflows where someone wants to share a scan with a colleague
- **Rate limiting** via slowapi to protect the VirusTotal quota
- **Observability** — Prometheus metrics for scan latency, CloudWatch for container-level logs

Some of these are flagged in [docs/specs.md](docs/specs.md) as deliberately out of scope for the assignment window.
