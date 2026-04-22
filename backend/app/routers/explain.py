from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps import get_gemini_client
from app.models import Scan
from app.schemas import ExplanationResponse
from app.services.gemini import GeminiClient

router = APIRouter(prefix="/api", tags=["explain"])


@router.post("/explain/{scan_id}", response_model=ExplanationResponse)
def explain(
    scan_id: UUID,
    db: Session = Depends(get_db),
    gemini: GeminiClient = Depends(get_gemini_client),
):
    scan = db.get(Scan, scan_id)
    if not scan:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="scan not found")
    if scan.status != "complete":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="scan is not complete yet",
        )

    if scan.ai_explanation:
        return ExplanationResponse(explanation=scan.ai_explanation)

    explanation = gemini.explain(
        filename=scan.filename,
        verdict=scan.verdict or "unknown",
        stats=scan.stats or {},
        vendor_results=scan.vendor_results or {},
    )
    scan.ai_explanation = explanation
    db.commit()
    return ExplanationResponse(explanation=explanation)
