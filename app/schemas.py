"""
Pydantic schemas. Naming convention:
  XCreate  -> what the client sends to create X
  XUpdate  -> partial update payload
  X        -> what the API returns
"""

from datetime import datetime
from typing import Optional, List, Any

from pydantic import BaseModel, ConfigDict

from app.models import (
    ApplicationStatus,
    PostingDecision,
    SkipReason,
    SponsorshipStatus,
)


# ---------- Resume ----------

class ResumeCreate(BaseModel):
    version_name: str
    file_url: Optional[str] = None
    notes: Optional[str] = None


class Resume(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    version_name: str
    file_url: Optional[str] = None
    notes: Optional[str] = None
    created_at: datetime


# ---------- Job Posting ----------

class JobPostingCreate(BaseModel):
    company_name: str
    position_title: str
    job_description: str
    job_url: Optional[str] = None
    source: Optional[str] = None


class JobPostingDecisionUpdate(BaseModel):
    decision: PostingDecision
    skip_reason: Optional[SkipReason] = None


class JobPosting(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    company_name: str
    position_title: str
    job_description: str
    job_url: Optional[str] = None
    source: Optional[str] = None

    is_staffing: Optional[bool] = None
    staffing_confidence: Optional[float] = None
    staffing_reason: Optional[str] = None

    sponsorship_status: Optional[SponsorshipStatus] = None
    sponsorship_confidence: Optional[float] = None
    sponsorship_reason: Optional[str] = None
    h1b_sponsor_match: Optional[bool] = None
    h1b_match_confidence: Optional[float] = None
    h1b_recent_years: Optional[List[int]] = None

    decision: PostingDecision
    skip_reason: Optional[SkipReason] = None

    created_at: datetime
    analyzed_at: Optional[datetime] = None


class AnalysisResult(BaseModel):
    """Response shape returned by the /analyze endpoint."""

    is_staffing: bool
    staffing_confidence: float
    staffing_reason: str

    sponsorship_status: SponsorshipStatus
    sponsorship_confidence: float
    sponsorship_reason: str
    h1b_sponsor_match: bool
    h1b_match_confidence: float
    h1b_recent_years: List[int]

    signals: dict[str, Any]


# ---------- Application ----------

class ApplicationCreate(BaseModel):
    job_posting_id: str
    resume_id: Optional[str] = None
    notes: Optional[str] = None


class ApplicationUpdate(BaseModel):
    status: Optional[ApplicationStatus] = None
    resume_id: Optional[str] = None
    follow_up_date: Optional[datetime] = None
    notes: Optional[str] = None


class Application(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    job_posting_id: str
    resume_id: Optional[str] = None
    status: ApplicationStatus
    applied_date: datetime
    last_updated: Optional[datetime] = None
    follow_up_date: Optional[datetime] = None
    notes: Optional[str] = None


# ---------- Blocklist ----------

class BlocklistEntryCreate(BaseModel):
    company_name: str
    notes: Optional[str] = None


class BlocklistEntry(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    company_name: str
    added_by: str
    notes: Optional[str] = None
    created_at: datetime


# ---------- Stats ----------

class SummaryStats(BaseModel):
    total_postings: int
    total_filtered_out: int
    total_applications: int
    total_offers: int


class SkipBreakdown(BaseModel):
    staffing: int
    no_sponsorship: int
    manual: int
    other: int
