from uuid import UUID

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import Settings, get_settings
from app.database import get_db
from app.deps import get_virustotal_client
from app.models import Scan
from app.schemas import ScanCreateResponse, ScanDetail, ScanList, ScanSummary
from app.services import scan_service
from app.services.virustotal import VirusTotalClient, VirusTotalError
from app.utils.hashing import hash_and_buffer
from app.utils.validation import ValidationError, validate_upload

router = APIRouter(prefix="/api", tags=["scans"])


@router.post("/scan", response_model=ScanCreateResponse, status_code=status.HTTP_201_CREATED)
async def create_scan(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    vt: VirusTotalClient = Depends(get_virustotal_client),
    settings: Settings = Depends(get_settings),
):
    sha256, buffer = await hash_and_buffer(file)
    size_bytes = buffer.getbuffer().nbytes

    try:
        validate_upload(
            filename=file.filename or "",
            size_bytes=size_bytes,
            max_bytes=settings.max_upload_bytes,
        )
    except ValidationError as e:
        code = (
            status.HTTP_413_REQUEST_ENTITY_TOO_LARGE
            if "size" in str(e)
            else status.HTTP_400_BAD_REQUEST
        )
        raise HTTPException(status_code=code, detail=str(e)) from e

    cached = scan_service.find_cached_complete_scan(db, sha256)
    if cached:
        return ScanCreateResponse(scan_id=cached.id, status=cached.status, cached=True)

    try:
        scan = await scan_service.create_scan(
            db,
            vt=vt,
            sha256=sha256,
            filename=file.filename or "unnamed",
            size_bytes=size_bytes,
            mime_type=file.content_type,
            buffer=buffer,
        )
    except VirusTotalError as e:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY, detail=str(e)
        ) from e

    return ScanCreateResponse(scan_id=scan.id, status=scan.status, cached=False)


@router.get("/scan/{scan_id}", response_model=ScanDetail)
async def get_scan(
    scan_id: UUID,
    db: Session = Depends(get_db),
    vt: VirusTotalClient = Depends(get_virustotal_client),
):
    scan = db.get(Scan, scan_id)
    if not scan:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="scan not found")

    if scan.status == "pending":
        try:
            scan = await scan_service.advance_scan(db, vt=vt, scan=scan)
        except VirusTotalError as e:
            scan = scan_service.mark_failed(db, scan, f"virustotal error: {e}")

    return scan


@router.get("/scans", response_model=ScanList)
def list_scans(limit: int = 20, db: Session = Depends(get_db)):
    limit = max(1, min(limit, 100))
    stmt = select(Scan).order_by(Scan.created_at.desc()).limit(limit)
    rows = db.execute(stmt).scalars().all()
    return ScanList(items=[ScanSummary.model_validate(r) for r in rows])
