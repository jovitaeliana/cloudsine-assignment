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
import os
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
            c.execute(text("TRUNCATE TABLE scans, scan_messages RESTART IDENTITY CASCADE"))


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
    g.chat.return_value = "This file appears to be malicious. You should not open it."
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


def test_list_scans_returns_recent(client):
    for name in ["a.js", "b.js", "c.js"]:
        client.post("/api/scan", files={"file": (name, io.BytesIO(b"x"), "text/plain")})

    r = client.get("/api/scans?limit=10")
    assert r.status_code == 200
    items = r.json()["items"]
    assert len(items) >= 1
    assert items[0]["created_at"] >= items[-1]["created_at"]


def test_chat_post_persists_both_messages_and_returns_them(client, db):
    from app.models import Scan

    scan = Scan(
        sha256="a" * 64,
        filename="evil.js",
        size_bytes=100,
        status="complete",
        verdict="malicious",
        stats={"malicious": 5, "suspicious": 0, "harmless": 50, "undetected": 10},
        vendor_results={"EngineA": {"category": "malicious", "result": "Trojan.X"}},
    )
    db.add(scan)
    db.commit()

    r = client.post(f"/api/chat/{scan.id}", json={"message": "Explain this"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["user_message"]["content"] == "Explain this"
    assert body["user_message"]["role"] == "user"
    assert body["assistant_message"]["role"] == "assistant"
    # Default fake_gemini returns the mocked chat text
    assert body["assistant_message"]["content"]


def test_chat_get_returns_history_in_order(client, db):
    from app.models import Scan

    scan = Scan(
        sha256="b" * 64,
        filename="chatty.js",
        size_bytes=100,
        status="complete",
        verdict="clean",
    )
    db.add(scan)
    db.commit()

    client.post(f"/api/chat/{scan.id}", json={"message": "First question"})
    client.post(f"/api/chat/{scan.id}", json={"message": "Second question"})

    r = client.get(f"/api/chat/{scan.id}")
    assert r.status_code == 200
    msgs = r.json()["messages"]
    # Two user + two assistant = 4 messages, in chronological order
    assert len(msgs) == 4
    assert msgs[0]["role"] == "user"
    assert msgs[0]["content"] == "First question"
    assert msgs[1]["role"] == "assistant"
    assert msgs[2]["role"] == "user"
    assert msgs[2]["content"] == "Second question"
    assert msgs[3]["role"] == "assistant"


def test_chat_returns_empty_history_for_scan_with_no_messages(client, db):
    from app.models import Scan

    scan = Scan(
        sha256="c" * 64,
        filename="quiet.js",
        size_bytes=50,
        status="complete",
        verdict="clean",
    )
    db.add(scan)
    db.commit()

    r = client.get(f"/api/chat/{scan.id}")
    assert r.status_code == 200
    assert r.json() == {"messages": []}


def test_chat_rejects_pending_scan(client, db):
    from app.models import Scan

    scan = Scan(
        sha256="d" * 64,
        filename="pending.js",
        size_bytes=50,
        status="pending",
    )
    db.add(scan)
    db.commit()

    r = client.post(f"/api/chat/{scan.id}", json={"message": "Explain"})
    assert r.status_code == 409


def test_chat_post_404_for_missing_scan(client):
    from uuid import uuid4
    r = client.post(f"/api/chat/{uuid4()}", json={"message": "Explain"})
    assert r.status_code == 404


def test_chat_preserves_user_message_on_gemini_server_error(client, db):
    from unittest.mock import MagicMock

    from google.genai.errors import ServerError

    from app import deps
    from app.models import Scan

    scan = Scan(
        sha256="e" * 64,
        filename="unlucky.js",
        size_bytes=50,
        status="complete",
        verdict="malicious",
    )
    db.add(scan)
    db.commit()

    busted_gemini = MagicMock()
    fake_resp = MagicMock()
    fake_resp.status_code = 503
    fake_resp.json.return_value = {"error": {"code": 503, "message": "overloaded"}}
    busted_gemini.chat.side_effect = ServerError(503, fake_resp)

    app.dependency_overrides[deps.get_gemini_client] = lambda: busted_gemini
    try:
        r = client.post(f"/api/chat/{scan.id}", json={"message": "Explain"})
        assert r.status_code == 503
        # User message should still be persisted
        r2 = client.get(f"/api/chat/{scan.id}")
        msgs = r2.json()["messages"]
        assert len(msgs) == 1
        assert msgs[0]["role"] == "user"
        assert msgs[0]["content"] == "Explain"
    finally:
        app.dependency_overrides.pop(deps.get_gemini_client, None)


def test_chat_validates_message_length(client, db):
    from app.models import Scan

    scan = Scan(
        sha256="f" * 64,
        filename="test.js",
        size_bytes=50,
        status="complete",
        verdict="clean",
    )
    db.add(scan)
    db.commit()

    # Empty message
    r = client.post(f"/api/chat/{scan.id}", json={"message": ""})
    assert r.status_code == 422

    # Too long (> 2000 chars)
    r = client.post(f"/api/chat/{scan.id}", json={"message": "x" * 2001})
    assert r.status_code == 422
