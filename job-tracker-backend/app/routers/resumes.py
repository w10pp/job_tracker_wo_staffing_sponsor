from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app import models, schemas
from app.database import get_db

router = APIRouter(prefix="/resumes", tags=["resumes"])


@router.post("", response_model=schemas.Resume)
def create_resume(payload: schemas.ResumeCreate, db: Session = Depends(get_db)):
    resume = models.Resume(**payload.model_dump())
    db.add(resume)
    db.commit()
    db.refresh(resume)
    return resume


@router.get("", response_model=list[schemas.Resume])
def list_resumes(db: Session = Depends(get_db)):
    return db.query(models.Resume).order_by(models.Resume.created_at.desc()).all()
