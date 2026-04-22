"""End-to-end integration tests.

Requires a reachable Postgres. Skipped automatically when one is not
available (unit tests in sibling files cover the pure logic). In CI a
Postgres service container is provisioned; locally you can run

    docker run -d --name pg-dev \\
        -e POSTGRES_USER=cloudsine \\
        -e POSTGRES_PASSWORD=change_me_in_prod \\
        -e POSTGRES_DB=cloudsine \\
        -p 5432:5432 postgres:16-alpine

before invoking pytest.
"""
import io
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import sessionmaker

from app import deps
from app.database import Base, get_db
from app.main import app
from app.services.gemini import GeminiClient
from app.services.virustotal import AnalysisStatus, FileReport, VirusTotalClient

import os

_PG_HOST = os.getenv("TEST_PG_HOST", "localhost")
_PG_PORT = os.getenv("TEST_PG_PORT", "5432")
_PG_USER = os.getenv("TEST_PG_USER", "cloudsine")
_PG_PASSWORD = os.getenv("TEST_PG_PASSWORD", "change_me_in_prod")

TEST_DB_URL = (
    f"postgresql+psycopg://{_PG_USER}:{_PG_PASSWORD}@{_PG_HOST}:{_PG_PORT}/cloudsine_test"
)
ADMIN_DB_URL = (
    f"postgresql+psycopg://{_PG_USER}:{_PG_PASSWORD}@{_PG_HOST}:{_PG_PORT}/postgres"
)


def _postgres_reachable() -> bool:
    try:
        eng = create_engine(ADMIN_DB_URL, connect_args={"connect_timeout": 2})
        with eng.connect():
            pass
        eng.dispose()
        return True
    except OperationalError:
        return False


pytestmark = pytest.mark.skipif(
    not _postgres_reachable(),
    reason="Postgres not reachable on localhost:5432 (integration tests skipped).",
)


@pytest.fixture(scope="module")
def engine():
    admin = create_engine(ADMIN_DB_URL, isolation_level="AUTOCOMMIT")
    with admin.connect() as c:
        c.execute(text("DROP DATABASE IF EXISTS cloudsine_test"))
        c.execute(text("CREATE DATABASE cloudsine_test"))
    admin.dispose()

    eng = create_engine(TEST_DB_URL)
    Base.metadata.create_all(eng)
    yield eng
    eng.dispose()


@pytest.fixture
def db(engine):
    Session = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    session = Session()
    try:
        yield session
    finally:
        session.rollback()
        session.close()
        with engine.begin() as c:
            c.execute(text("TRUNCATE TABLE scans RESTART IDENTITY"))


@pytest.fixture
def fake_vt():
    vt = MagicMock(spec=VirusTotalClient)

    async def upload(filename, buffer):
        return "analysis-test-1"

    async def analysis_status(analysis_id):
        return AnalysisStatus(
            status="completed",
            sha256="f" * 64,
            stats={"malicious": 5, "suspicious": 0, "harmless": 40, "undetected": 5},
        )

    async def file_report(sha256):
        return FileReport(
            stats={"malicious": 5, "suspicious": 0, "harmless": 40, "undetected": 5},
            vendor_results={"EngineA": {"category": "malicious", "result": "Trojan.X"}},
        )

    vt.upload_file.side_effect = upload
    vt.get_analysis_status.side_effect = analysis_status
    vt.get_file_report.side_effect = file_report
    return vt


@pytest.fixture
def fake_gemini():
    g = MagicMock(spec=GeminiClient)
    g.explain.return_value = "This file appears to be malicious. You should not open it."
    return g


@pytest.fixture
def client(db, fake_vt, fake_gemini):
    def _get_db():
        yield db

    app.dependency_overrides[get_db] = _get_db
    app.dependency_overrides[deps.get_virustotal_client] = lambda: fake_vt
    app.dependency_overrides[deps.get_gemini_client] = lambda: fake_gemini
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


def test_upload_then_poll_returns_complete(client):
    files = {"file": ("test.js", io.BytesIO(b"alert(1)"), "application/javascript")}

    r = client.post("/api/scan", files=files)
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["status"] == "pending"
    assert body["cached"] is False
    scan_id = body["scan_id"]

    r = client.get(f"/api/scan/{scan_id}")
    assert r.status_code == 200
    detail = r.json()
    assert detail["status"] == "complete"
    assert detail["verdict"] == "malicious"
    assert detail["vendor_results"]["EngineA"]["category"] == "malicious"


def test_second_upload_hits_cache(client):
    payload = b"same bytes"
    files1 = {"file": ("a.js", io.BytesIO(payload), "application/javascript")}
    r1 = client.post("/api/scan", files=files1)
    sid = r1.json()["scan_id"]
    client.get(f"/api/scan/{sid}")  # advance to complete

    files2 = {"file": ("renamed.js", io.BytesIO(payload), "application/javascript")}
    r2 = client.post("/api/scan", files=files2)
    assert r2.status_code == 201
    body = r2.json()
    assert body["cached"] is True
    assert body["status"] == "complete"


def test_explain_caches_result(client):
    files = {"file": ("x.js", io.BytesIO(b"abc"), "application/javascript")}
    sid = client.post("/api/scan", files=files).json()["scan_id"]
    client.get(f"/api/scan/{sid}")

    r1 = client.post(f"/api/explain/{sid}")
    assert r1.status_code == 200
    text1 = r1.json()["explanation"]
    assert "malicious" in text1.lower() or "open it" in text1.lower()

    r2 = client.post(f"/api/explain/{sid}")
    assert r2.json()["explanation"] == text1


def test_list_scans_returns_recent(client):
    for name in ["a.js", "b.js", "c.js"]:
        client.post("/api/scan", files={"file": (name, io.BytesIO(b"x"), "text/plain")})

    r = client.get("/api/scans?limit=10")
    assert r.status_code == 200
    items = r.json()["items"]
    assert len(items) >= 1
    assert items[0]["created_at"] >= items[-1]["created_at"]


def test_explain_returns_404_for_missing_scan(client):
    from uuid import uuid4

    r = client.post(f"/api/explain/{uuid4()}")
    assert r.status_code == 404


def test_explain_returns_409_when_scan_not_complete(client, db):
    from app.models import Scan

    row = Scan(
        sha256="a" * 64,
        filename="p.js",
        size_bytes=10,
        status="pending",
        vt_analysis_id="wait",
    )
    db.add(row)
    db.commit()

    r = client.post(f"/api/explain/{row.id}")
    assert r.status_code == 409
