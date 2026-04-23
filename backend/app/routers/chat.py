import logging
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException, status
from google.genai.errors import ClientError, ServerError
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps import get_gemini_client
from app.models import Scan, ScanMessage
from app.schemas import ChatHistory, ChatRequest, ChatResponse, MessageDTO
from app.services.gemini import GeminiClient, _top_flagged

log = logging.getLogger(__name__)

router = APIRouter(prefix="/api/chat", tags=["chat"])


@router.get("/{scan_id}", response_model=ChatHistory)
def get_chat_history(scan_id: UUID, db: Session = Depends(get_db)) -> ChatHistory:
    scan = db.get(Scan, scan_id)
    if not scan:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="scan not found")

    rows = (
        db.query(ScanMessage)
        .filter(ScanMessage.scan_id == scan_id)
        .order_by(ScanMessage.created_at.asc())
        .all()
    )
    return ChatHistory(messages=[MessageDTO.model_validate(r) for r in rows])


@router.post("/{scan_id}", response_model=ChatResponse)
def post_chat_message(
    scan_id: UUID,
    body: ChatRequest,
    db: Session = Depends(get_db),
    gemini: GeminiClient = Depends(get_gemini_client),
) -> ChatResponse:
    scan = db.get(Scan, scan_id)
    if not scan:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="scan not found")
    if scan.status != "complete":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="scan is not complete yet",
        )

    prior = (
        db.query(ScanMessage)
        .filter(ScanMessage.scan_id == scan_id)
        .order_by(ScanMessage.created_at.asc())
        .all()
    )

    # Persist user message before calling Gemini. On Gemini failure the user
    # message stays so the user can retry without retyping.
    user_row = ScanMessage(
        id=uuid4(),
        scan_id=scan_id,
        role="user",
        content=body.message,
    )
    db.add(user_row)
    db.flush()

    history = [{"role": m.role, "content": m.content} for m in prior] + [
        {"role": "user", "content": body.message}
    ]

    scan_summary = {
        "filename": scan.filename,
        "verdict": scan.verdict or "unknown",
        "stats": scan.stats or {},
        "flagged_engines": _top_flagged(scan.vendor_results or {}),
    }

    try:
        assistant_text = gemini.chat(history=history, scan_summary=scan_summary)
    except ServerError as e:
        log.warning("Gemini unavailable for chat on scan %s: %s", scan_id, e)
        db.commit()
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="AI service is temporarily busy. Please try again in a moment.",
        ) from e
    except ClientError as e:
        log.warning("Gemini client error for chat on scan %s: %s", scan_id, e)
        db.commit()
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="AI service returned an error.",
        ) from e

    if not assistant_text:
        db.commit()
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="AI service returned an empty response.",
        )

    assistant_row = ScanMessage(
        id=uuid4(),
        scan_id=scan_id,
        role="assistant",
        content=assistant_text,
    )
    db.add(assistant_row)
    db.commit()
    db.refresh(user_row)
    db.refresh(assistant_row)

    return ChatResponse(
        user_message=MessageDTO.model_validate(user_row),
        assistant_message=MessageDTO.model_validate(assistant_row),
    )
