from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app import models, schemas
from app.database import get_db

router = APIRouter(prefix="/blocklist", tags=["blocklist"])


@router.get("", response_model=list[schemas.BlocklistEntry])
def list_blocklist(db: Session = Depends(get_db)):
    return (
        db.query(models.StaffingCompanyBlocklist)
        .order_by(models.StaffingCompanyBlocklist.company_name)
        .all()
    )


@router.post("", response_model=schemas.BlocklistEntry)
def add_to_blocklist(payload: schemas.BlocklistEntryCreate, db: Session = Depends(get_db)):
    entry = models.StaffingCompanyBlocklist(
        company_name=payload.company_name.strip().lower(),
        notes=payload.notes,
        added_by="manual",
    )
    db.add(entry)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="Company already on blocklist")
    db.refresh(entry)
    return entry


@router.delete("/{entry_id}", status_code=204)
def remove_from_blocklist(entry_id: str, db: Session = Depends(get_db)):
    entry = db.get(models.StaffingCompanyBlocklist, entry_id)
    if not entry:
        raise HTTPException(status_code=404, detail="Entry not found")
    db.delete(entry)
    db.commit()
