from io import BytesIO

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Scan
from app.services.virustotal import VirusTotalClient

MALICIOUS_THRESHOLD = 3


def compute_verdict(stats: dict) -> str:
    malicious = int(stats.get("malicious") or 0)
    suspicious = int(stats.get("suspicious") or 0)
    if malicious >= MALICIOUS_THRESHOLD:
        return "malicious"
    if malicious >= 1 or suspicious >= 1:
        return "suspicious"
    return "clean"


def find_cached_complete_scan(db: Session, sha256: str) -> Scan | None:
    stmt = (
        select(Scan)
        .where(Scan.sha256 == sha256, Scan.status == "complete")
        .order_by(Scan.created_at.desc())
        .limit(1)
    )
    return db.execute(stmt).scalar_one_or_none()


async def create_scan(
    db: Session,
    *,
    vt: VirusTotalClient,
    sha256: str,
    filename: str,
    size_bytes: int,
    mime_type: str | None,
    buffer: BytesIO,
) -> Scan:
    analysis_id = await vt.upload_file(filename=filename, buffer=buffer)
    scan = Scan(
        sha256=sha256,
        filename=filename,
        size_bytes=size_bytes,
        mime_type=mime_type,
        vt_analysis_id=analysis_id,
        status="pending",
    )
    db.add(scan)
    db.commit()
    db.refresh(scan)
    return scan


async def advance_scan(db: Session, *, vt: VirusTotalClient, scan: Scan) -> Scan:
    """Poll VT once and update the scan row. Only acts on pending rows.

    Uses the locally-computed sha256 to fetch the file report. The local
    hash is authoritative because it is deterministic from the bytes the
    user uploaded, which is also what VT received.
    """
    if scan.status != "pending" or not scan.vt_analysis_id:
        return scan

    analysis = await vt.get_analysis_status(scan.vt_analysis_id)
    if analysis.status != "completed":
        return scan

    report = await vt.get_file_report(scan.sha256)
    scan.status = "complete"
    scan.stats = report.stats
    scan.vendor_results = report.vendor_results
    scan.verdict = compute_verdict(report.stats)
    db.commit()
    db.refresh(scan)
    return scan


def mark_failed(db: Session, scan: Scan, message: str) -> Scan:
    scan.status = "failed"
    scan.error_message = message
    db.commit()
    db.refresh(scan)
    return scan
