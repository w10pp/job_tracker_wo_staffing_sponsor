from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app import models, schemas
from app.database import get_db

router = APIRouter(prefix="/applications", tags=["applications"])


@router.post("", response_model=schemas.Application)
def create_application(payload: schemas.ApplicationCreate, db: Session = Depends(get_db)):
    posting = db.get(models.JobPosting, payload.job_posting_id)
    if not posting:
        raise HTTPException(status_code=404, detail="Job posting not found")

    application = models.Application(
        job_posting_id=payload.job_posting_id,
        resume_id=payload.resume_id,
        notes=payload.notes,
    )
    db.add(application)

    # Mark the source posting as "apply" so it drops out of the pending pool.
    posting.decision = models.PostingDecision.apply

    db.flush()
    db.add(
        models.StatusHistory(
            application_id=application.id, status=models.ApplicationStatus.applied
        )
    )
    db.commit()
    db.refresh(application)
    return application


@router.get("", response_model=list[schemas.Application])
def list_applications(
    status: models.ApplicationStatus | None = None, db: Session = Depends(get_db)
):
    query = db.query(models.Application)
    if status is not None:
        query = query.filter(models.Application.status == status)
    return query.order_by(models.Application.applied_date.desc()).all()


@router.get("/{application_id}", response_model=schemas.Application)
def get_application(application_id: str, db: Session = Depends(get_db)):
    application = db.get(models.Application, application_id)
    if not application:
        raise HTTPException(status_code=404, detail="Application not found")
    return application


@router.patch("/{application_id}", response_model=schemas.Application)
def update_application(
    application_id: str, payload: schemas.ApplicationUpdate, db: Session = Depends(get_db)
):
    application = db.get(models.Application, application_id)
    if not application:
        raise HTTPException(status_code=404, detail="Application not found")

    update_data = payload.model_dump(exclude_unset=True)
    status_changed = "status" in update_data and update_data["status"] != application.status

    for field, value in update_data.items():
        setattr(application, field, value)

    if status_changed:
        db.add(
            models.StatusHistory(
                application_id=application.id, status=application.status
            )
        )

    db.commit()
    db.refresh(application)
    return application


@router.delete("/{application_id}", status_code=204)
def delete_application(application_id: str, db: Session = Depends(get_db)):
    application = db.get(models.Application, application_id)
    if not application:
        raise HTTPException(status_code=404, detail="Application not found")
    db.delete(application)
    db.commit()
