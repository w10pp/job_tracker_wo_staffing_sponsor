from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app import models, schemas
from app.database import get_db
from app.services.ai_classifier import screen_posting

router = APIRouter(prefix="/job-postings", tags=["job-postings"])


@router.post("", response_model=schemas.JobPosting)
def create_posting(payload: schemas.JobPostingCreate, db: Session = Depends(get_db)):
    posting = models.JobPosting(**payload.model_dump())
    db.add(posting)
    db.commit()
    db.refresh(posting)
    return posting


@router.get("", response_model=list[schemas.JobPosting])
def list_postings(
    decision: models.PostingDecision | None = None,
    is_staffing: bool | None = None,
    db: Session = Depends(get_db),
):
    query = db.query(models.JobPosting)
    if decision is not None:
        query = query.filter(models.JobPosting.decision == decision)
    if is_staffing is not None:
        query = query.filter(models.JobPosting.is_staffing == is_staffing)
    return query.order_by(models.JobPosting.created_at.desc()).all()


@router.get("/{posting_id}", response_model=schemas.JobPosting)
def get_posting(posting_id: str, db: Session = Depends(get_db)):
    posting = db.get(models.JobPosting, posting_id)
    if not posting:
        raise HTTPException(status_code=404, detail="Job posting not found")
    return posting


@router.post("/{posting_id}/analyze", response_model=schemas.AnalysisResult)
def analyze_posting(posting_id: str, db: Session = Depends(get_db)):
    posting = db.get(models.JobPosting, posting_id)
    if not posting:
        raise HTTPException(status_code=404, detail="Job posting not found")

    blocklist_names = {
        row.company_name.strip().lower()
        for row in db.query(models.StaffingCompanyBlocklist.company_name).all()
    }

    result = screen_posting(
        db=db,
        company_name=posting.company_name,
        position_title=posting.position_title,
        job_description=posting.job_description,
        blocklist_names=blocklist_names,
    )

    posting.is_staffing = result.is_staffing
    posting.staffing_confidence = result.staffing_confidence
    posting.staffing_reason = result.staffing_reason
    posting.sponsorship_status = result.sponsorship_status
    posting.sponsorship_confidence = result.sponsorship_confidence
    posting.sponsorship_reason = result.sponsorship_reason
    posting.h1b_sponsor_match = result.h1b_sponsor_match
    posting.h1b_match_confidence = result.h1b_match_confidence
    posting.h1b_recent_years = result.h1b_recent_years
    posting.analyzed_at = datetime.now(timezone.utc)

    db.commit()

    return schemas.AnalysisResult(
        is_staffing=result.is_staffing,
        staffing_confidence=result.staffing_confidence,
        staffing_reason=result.staffing_reason,
        sponsorship_status=result.sponsorship_status,
        sponsorship_confidence=result.sponsorship_confidence,
        sponsorship_reason=result.sponsorship_reason,
        h1b_sponsor_match=result.h1b_sponsor_match,
        h1b_match_confidence=result.h1b_match_confidence,
        h1b_recent_years=result.h1b_recent_years,
        signals=result.signals,
    )


@router.patch("/{posting_id}/decision", response_model=schemas.JobPosting)
def update_decision(
    posting_id: str,
    payload: schemas.JobPostingDecisionUpdate,
    db: Session = Depends(get_db),
):
    posting = db.get(models.JobPosting, posting_id)
    if not posting:
        raise HTTPException(status_code=404, detail="Job posting not found")

    posting.decision = payload.decision
    posting.skip_reason = payload.skip_reason

    # If the user is manually overriding an AI staffing call to "skip", and
    # the company wasn't already flagged, offer it up for the blocklist so
    # the rule layer improves over time. (Left as an explicit follow-up
    # action for the frontend to call POST /blocklist — we don't want to
    # silently blocklist a company the user might reconsider.)

    db.commit()
    db.refresh(posting)
    return posting
