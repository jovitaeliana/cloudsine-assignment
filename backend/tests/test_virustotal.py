from io import BytesIO

import httpx
import pytest

from app.services.virustotal import VirusTotalClient, VirusTotalError

BASE_URL = "https://vt.test/api/v3"


def _client(handler):
    transport = httpx.MockTransport(handler)
    return VirusTotalClient(api_key="test-key", base_url=BASE_URL, transport=transport)


async def test_upload_file_returns_analysis_id():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "POST"
        assert request.url.path == "/api/v3/files"
        assert request.headers["x-apikey"] == "test-key"
        return httpx.Response(200, json={"data": {"id": "abc123", "type": "analysis"}})

    c = _client(handler)
    try:
        analysis_id = await c.upload_file(filename="x.js", buffer=BytesIO(b"hello"))
        assert analysis_id == "abc123"
    finally:
        await c.aclose()


async def test_get_analysis_status_returns_completed():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/v3/analyses/abc123"
        return httpx.Response(
            200,
            json={
                "data": {
                    "attributes": {
                        "status": "completed",
                        "stats": {
                            "malicious": 5,
                            "suspicious": 0,
                            "harmless": 60,
                            "undetected": 10,
                        },
                    },
                    "meta": {"file_info": {"sha256": "deadbeef"}},
                }
            },
        )

    c = _client(handler)
    try:
        s = await c.get_analysis_status("abc123")
        assert s.status == "completed"
        assert s.sha256 == "deadbeef"
        assert s.stats["malicious"] == 5
    finally:
        await c.aclose()


async def test_get_file_report_returns_full_report():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/v3/files/deadbeef"
        return httpx.Response(
            200,
            json={
                "data": {
                    "attributes": {
                        "last_analysis_stats": {
                            "malicious": 5,
                            "harmless": 60,
                            "suspicious": 0,
                            "undetected": 10,
                        },
                        "last_analysis_results": {
                            "EngineA": {"category": "malicious", "result": "Trojan.X"},
                            "EngineB": {"category": "harmless", "result": None},
                        },
                    }
                }
            },
        )

    c = _client(handler)
    try:
        report = await c.get_file_report("deadbeef")
        assert report.stats["malicious"] == 5
        assert report.vendor_results["EngineA"]["category"] == "malicious"
    finally:
        await c.aclose()


async def test_upload_file_raises_on_api_error():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(429, json={"error": {"code": "QuotaExceeded"}})

    c = _client(handler)
    try:
        with pytest.raises(VirusTotalError, match="429"):
            await c.upload_file(filename="x.js", buffer=BytesIO(b"hi"))
    finally:
        await c.aclose()


async def test_get_analysis_status_pending():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={"data": {"attributes": {"status": "queued"}, "meta": {}}},
        )

    c = _client(handler)
    try:
        s = await c.get_analysis_status("p1")
        assert s.status == "queued"
        assert s.sha256 is None
        assert s.stats is None
    finally:
        await c.aclose()
