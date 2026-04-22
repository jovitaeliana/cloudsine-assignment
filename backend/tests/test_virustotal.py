from io import BytesIO

import httpx
import pytest
import respx

from app.services.virustotal import VirusTotalClient, VirusTotalError

BASE_URL = "https://vt.test/api/v3"


@pytest.fixture
def client():
    return VirusTotalClient(api_key="test-key", base_url=BASE_URL)


@respx.mock
async def test_upload_file_returns_analysis_id(client: VirusTotalClient):
    route = respx.post(f"{BASE_URL}/files").mock(
        return_value=httpx.Response(200, json={"data": {"id": "abc123", "type": "analysis"}})
    )

    analysis_id = await client.upload_file(filename="x.js", buffer=BytesIO(b"hello"))

    assert analysis_id == "abc123"
    assert route.called
    assert route.calls.last.request.headers["x-apikey"] == "test-key"


@respx.mock
async def test_get_analysis_status_returns_completed(client: VirusTotalClient):
    respx.get(f"{BASE_URL}/analyses/abc123").mock(
        return_value=httpx.Response(
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
    )

    status = await client.get_analysis_status("abc123")

    assert status.status == "completed"
    assert status.sha256 == "deadbeef"
    assert status.stats["malicious"] == 5


@respx.mock
async def test_get_file_report_returns_full_report(client: VirusTotalClient):
    respx.get(f"{BASE_URL}/files/deadbeef").mock(
        return_value=httpx.Response(
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
    )

    report = await client.get_file_report("deadbeef")

    assert report.stats["malicious"] == 5
    assert report.vendor_results["EngineA"]["category"] == "malicious"


@respx.mock
async def test_upload_file_raises_on_api_error(client: VirusTotalClient):
    respx.post(f"{BASE_URL}/files").mock(
        return_value=httpx.Response(429, json={"error": {"code": "QuotaExceeded"}})
    )

    with pytest.raises(VirusTotalError, match="429"):
        await client.upload_file(filename="x.js", buffer=BytesIO(b"hi"))


@respx.mock
async def test_get_analysis_status_pending(client: VirusTotalClient):
    respx.get(f"{BASE_URL}/analyses/p1").mock(
        return_value=httpx.Response(
            200,
            json={"data": {"attributes": {"status": "queued"}, "meta": {}}},
        )
    )

    status = await client.get_analysis_status("p1")

    assert status.status == "queued"
    assert status.sha256 is None
    assert status.stats is None
