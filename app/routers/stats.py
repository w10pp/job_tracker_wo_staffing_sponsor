from fastapi import APIRouter, Depends
from sqlalchemy import func, Integer
from sqlalchemy.orm import Session

from app import models, schemas
from app.database import get_db

router = APIRouter(prefix="/stats", tags=["stats"])


@router.get("/summary", response_model=schemas.SummaryStats)
def summary(db: Session = Depends(get_db)):
    total_postings = db.query(func.count(models.JobPosting.id)).scalar()
    total_filtered_out = (
        db.query(func.count(models.JobPosting.id))
        .filter(models.JobPosting.decision == models.PostingDecision.skip)
        .scalar()
    )
    total_applications = db.query(func.count(models.Application.id)).scalar()
    total_offers = (
        db.query(func.count(models.Application.id))
        .filter(models.Application.status == models.ApplicationStatus.offer)
        .scalar()
    )

    return schemas.SummaryStats(
        total_postings=total_postings or 0,
        total_filtered_out=total_filtered_out or 0,
        total_applications=total_applications or 0,
        total_offers=total_offers or 0,
    )


@router.get("/skip-breakdown", response_model=schemas.SkipBreakdown)
def skip_breakdown(db: Session = Depends(get_db)):
    rows = (
        db.query(models.JobPosting.skip_reason, func.count(models.JobPosting.id))
        .filter(models.JobPosting.decision == models.PostingDecision.skip)
        .group_by(models.JobPosting.skip_reason)
        .all()
    )
    counts = {reason.value if reason else "other": count for reason, count in rows}
    return schemas.SkipBreakdown(
        staffing=counts.get("staffing", 0),
        no_sponsorship=counts.get("no_sponsorship", 0),
        manual=counts.get("manual", 0),
        other=counts.get("other", 0),
    )


@router.get("/conversion")
def conversion_funnel(db: Session = Depends(get_db)):
    """Count of applications currently at each status (a simple funnel view)."""
    rows = (
        db.query(models.Application.status, func.count(models.Application.id))
        .group_by(models.Application.status)
        .all()
    )
    return {status.value: count for status, count in rows}


@router.get("/by-resume")
def stats_by_resume(db: Session = Depends(get_db)):
    """
    Compares application volume and offer/interview rate across resume
    versions -- the core "which resume version actually works" insight.
    """
    rows = (
        db.query(
            models.Resume.version_name,
            func.count(models.Application.id).label("total"),
            func.sum(
                (models.Application.status == models.ApplicationStatus.interview).cast(
                    Integer
                )
            ).label("interviews"),
            func.sum(
                (models.Application.status == models.ApplicationStatus.offer).cast(
                    Integer
                )
            ).label("offers"),
        )
        .join(models.Application, models.Application.resume_id == models.Resume.id)
        .group_by(models.Resume.version_name)
        .all()
    )
    return [
        {
            "resume_version": r.version_name,
            "total_applications": r.total,
            "interviews": r.interviews or 0,
            "offers": r.offers or 0,
        }
        for r in rows
    ]
