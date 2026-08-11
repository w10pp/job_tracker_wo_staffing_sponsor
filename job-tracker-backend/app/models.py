"""
SQLAlchemy ORM models.

Core flow:
  job_postings  -> (AI + rule based screening: staffing? sponsorship?)
                -> user decision (apply / skip)
                -> applications (only postings the user actually applied to)
                -> status_history (tracks the funnel over time)

Supporting tables:
  resumes                    -> versioned resumes, linked to applications
  staffing_companies_blocklist -> growing list of known staffing/agency companies
  h1b_sponsors                -> imported DOL H1B disclosure data, used as a
                                  factual signal for sponsorship likelihood
"""

import enum
import uuid

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    JSON,
    func,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from app.database import Base


def gen_uuid():
    return str(uuid.uuid4())


class ApplicationStatus(str, enum.Enum):
    applied = "applied"
    oa = "oa"  # online assessment
    interview = "interview"
    offer = "offer"
    rejected = "rejected"
    withdrawn = "withdrawn"


class PostingDecision(str, enum.Enum):
    pending = "pending"
    apply = "apply"
    skip = "skip"


class SkipReason(str, enum.Enum):
    staffing = "staffing"
    no_sponsorship = "no_sponsorship"
    manual = "manual"
    other = "other"


class SponsorshipStatus(str, enum.Enum):
    sponsors = "sponsors"
    citizen_pr_only = "citizen_pr_only"
    unclear = "unclear"


class Resume(Base):
    __tablename__ = "resumes"

    id = Column(UUID(as_uuid=False), primary_key=True, default=gen_uuid)
    version_name = Column(String, nullable=False)  # e.g. "SWE-focused-v2"
    file_url = Column(String, nullable=True)
    notes = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    applications = relationship("Application", back_populates="resume")


class JobPosting(Base):
    __tablename__ = "job_postings"

    id = Column(UUID(as_uuid=False), primary_key=True, default=gen_uuid)
    company_name = Column(String, nullable=False, index=True)
    position_title = Column(String, nullable=False)
    job_description = Column(Text, nullable=False)
    job_url = Column(String, nullable=True)
    source = Column(String, nullable=True)  # LinkedIn / Indeed / company site

    # --- staffing screening ---
    is_staffing = Column(Boolean, nullable=True)
    staffing_confidence = Column(Float, nullable=True)
    staffing_reason = Column(Text, nullable=True)

    # --- sponsorship screening (multi-signal) ---
    sponsorship_status = Column(Enum(SponsorshipStatus), nullable=True)
    sponsorship_confidence = Column(Float, nullable=True)
    sponsorship_reason = Column(Text, nullable=True)
    h1b_sponsor_match = Column(Boolean, nullable=True)
    h1b_match_confidence = Column(Float, nullable=True)
    h1b_recent_years = Column(JSON, nullable=True)  # e.g. [2023, 2024]

    # --- user decision ---
    decision = Column(
        Enum(PostingDecision), nullable=False, default=PostingDecision.pending
    )
    skip_reason = Column(Enum(SkipReason), nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    analyzed_at = Column(DateTime(timezone=True), nullable=True)

    application = relationship(
        "Application", back_populates="job_posting", uselist=False
    )


class Application(Base):
    __tablename__ = "applications"

    id = Column(UUID(as_uuid=False), primary_key=True, default=gen_uuid)
    job_posting_id = Column(
        UUID(as_uuid=False), ForeignKey("job_postings.id"), nullable=False
    )
    resume_id = Column(UUID(as_uuid=False), ForeignKey("resumes.id"), nullable=True)

    status = Column(
        Enum(ApplicationStatus), nullable=False, default=ApplicationStatus.applied
    )
    applied_date = Column(DateTime(timezone=True), server_default=func.now())
    last_updated = Column(DateTime(timezone=True), onupdate=func.now())
    follow_up_date = Column(DateTime(timezone=True), nullable=True)
    notes = Column(Text, nullable=True)

    job_posting = relationship("JobPosting", back_populates="application")
    resume = relationship("Resume", back_populates="applications")
    status_history = relationship("StatusHistory", back_populates="application")


class StatusHistory(Base):
    __tablename__ = "status_history"

    id = Column(UUID(as_uuid=False), primary_key=True, default=gen_uuid)
    application_id = Column(
        UUID(as_uuid=False), ForeignKey("applications.id"), nullable=False
    )
    status = Column(Enum(ApplicationStatus), nullable=False)
    changed_at = Column(DateTime(timezone=True), server_default=func.now())

    application = relationship("Application", back_populates="status_history")


class StaffingCompanyBlocklist(Base):
    __tablename__ = "staffing_companies_blocklist"

    id = Column(UUID(as_uuid=False), primary_key=True, default=gen_uuid)
    company_name = Column(String, nullable=False, unique=True, index=True)
    added_by = Column(String, nullable=False, default="manual")  # manual | ai_detected
    notes = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class H1BSponsor(Base):
    """
    Imported from DOL LCA disclosure data. See app/data/import_h1b.py.
    Company names are stored both raw and normalized for fuzzy matching.
    """

    __tablename__ = "h1b_sponsors"

    id = Column(UUID(as_uuid=False), primary_key=True, default=gen_uuid)
    company_name = Column(String, nullable=False, index=True)  # normalized
    company_name_raw = Column(String, nullable=False)
    fiscal_year = Column(Integer, nullable=False)
    total_applications = Column(Integer, nullable=True)
    approved_applications = Column(Integer, nullable=True)
    job_title_sample = Column(Text, nullable=True)
