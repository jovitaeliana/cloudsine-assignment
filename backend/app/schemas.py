from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

ScanStatus = Literal["pending", "complete", "failed"]
Verdict = Literal["clean", "suspicious", "malicious"]


class ScanCreateResponse(BaseModel):
    scan_id: UUID
    status: ScanStatus
    cached: bool


class ScanSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    filename: str
    sha256: str
    size_bytes: int
    status: ScanStatus
    verdict: Verdict | None = None
    created_at: datetime


class ScanDetail(ScanSummary):
    mime_type: str | None = None
    stats: dict | None = None
    vendor_results: dict | None = None
    ai_explanation: str | None = None
    error_message: str | None = None
    updated_at: datetime


class ScanList(BaseModel):
    items: list[ScanSummary]


class ExplanationResponse(BaseModel):
    explanation: str = Field(..., min_length=1)
