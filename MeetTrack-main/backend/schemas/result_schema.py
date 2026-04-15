# schemas/result_schema.py
from datetime import datetime
from pydantic import BaseModel, Field
from typing import Optional, List


# ---------------------------------------------------------------------------
# Structured meeting intelligence output
# ---------------------------------------------------------------------------

class ActionItemOut(BaseModel):
    task: str
    assignee: str = "Unassigned"
    deadline: Optional[str] = None          # YYYY-MM-DD or null
    confidence_score: float = Field(default=0.8, ge=0.0, le=1.0)


class StructuredMeetingOutput(BaseModel):
    """
    The canonical structured output produced by the AI pipeline.
    Stored as JSON in Result.summary.
    """
    summary: str
    decisions: List[str] = []
    action_items: List[ActionItemOut] = []


# ---------------------------------------------------------------------------
# DB-level schemas
# ---------------------------------------------------------------------------

class ResultCreate(BaseModel):
    meeting_id: int
    summary: str                            # JSON string of StructuredMeetingOutput
    key_points: Optional[str] = None


class ResultResponse(BaseModel):
    id: int
    meeting_id: int
    summary: str
    key_points: Optional[str] = None

    class Config:
        from_attributes = True


# ---------------------------------------------------------------------------
# Convenience response that parses the JSON summary for API consumers
# ---------------------------------------------------------------------------

class RichResultResponse(BaseModel):
    id: int
    meeting_id: int
    structured: StructuredMeetingOutput
    key_points: Optional[str] = None

    class Config:
        from_attributes = True


# ---------------------------------------------------------------------------
# Legacy / approval schemas
# ---------------------------------------------------------------------------

class SummaryResponse(BaseModel):
    meeting_id: int
    summary: str


class SummaryApproval(BaseModel):
    meeting_id: int
    approved: bool
