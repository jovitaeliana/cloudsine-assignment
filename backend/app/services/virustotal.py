from dataclasses import dataclass
from io import BytesIO

import httpx


class VirusTotalError(RuntimeError):
    pass


@dataclass
class AnalysisStatus:
    status: str  # "queued" | "in-progress" | "completed"
    sha256: str | None
    stats: dict | None


@dataclass
class FileReport:
    stats: dict
    vendor_results: dict


class VirusTotalClient:
    """Thin async wrapper over the VirusTotal v3 API.

    A single httpx.AsyncClient is reused across calls. Tests inject a
    MockTransport to avoid real network I/O.
    """

    def __init__(
        self,
        *,
        api_key: str,
        base_url: str,
        timeout: float = 30.0,
        transport: httpx.AsyncBaseTransport | None = None,
    ):
        self._client = httpx.AsyncClient(
            base_url=base_url.rstrip("/"),
            headers={"x-apikey": api_key},
            timeout=timeout,
            transport=transport,
        )

    async def aclose(self) -> None:
        await self._client.aclose()

    async def upload_file(self, *, filename: str, buffer: BytesIO) -> str:
        buffer.seek(0)
        r = await self._client.post("/files", files={"file": (filename, buffer)})
        if r.status_code >= 400:
            raise VirusTotalError(f"upload failed ({r.status_code}): {r.text[:200]}")
        data = r.json().get("data", {})
        analysis_id = data.get("id")
        if not analysis_id:
            raise VirusTotalError(f"upload missing analysis id: {r.text[:200]}")
        return analysis_id

    async def get_analysis_status(self, analysis_id: str) -> AnalysisStatus:
        r = await self._client.get(f"/analyses/{analysis_id}")
        if r.status_code >= 400:
            raise VirusTotalError(
                f"analysis fetch failed ({r.status_code}): {r.text[:200]}"
            )
        payload = r.json().get("data", {})
        attrs = payload.get("attributes", {})
        meta = payload.get("meta", {}).get("file_info", {})
        return AnalysisStatus(
            status=attrs.get("status", "queued"),
            sha256=meta.get("sha256"),
            stats=attrs.get("stats"),
        )

    async def get_file_report(self, sha256: str) -> FileReport:
        r = await self._client.get(f"/files/{sha256}")
        if r.status_code >= 400:
            raise VirusTotalError(
                f"report fetch failed ({r.status_code}): {r.text[:200]}"
            )
        attrs = r.json().get("data", {}).get("attributes", {})
        return FileReport(
            stats=attrs.get("last_analysis_stats", {}),
            vendor_results=attrs.get("last_analysis_results", {}),
        )
