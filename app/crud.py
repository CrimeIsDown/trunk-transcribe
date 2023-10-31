from sqlalchemy.orm import Session

from . import models, schemas


def get_call(db: Session, call_id: int):
    return db.query(models.Call).filter(models.Call.id == call_id).first()


def get_calls(db: Session, skip: int = 0, limit: int = 100):
    return db.query(models.Call).offset(skip).limit(limit).all()


def create_call(db: Session, call: schemas.CallCreate):
    db_call = models.Call(
        raw_metadata=call.raw_metadata, raw_audio_url=call.raw_audio_url
    )
    db.add(db_call)
    db.commit()
    db.refresh(db_call)
    return db_call


def update_call(db: Session, call: schemas.CallUpdate, db_call: models.Call):
    db_call.raw_transcript = call.raw_transcript  # type: ignore
    db_call.geo = call.geo  # type: ignore
    db.commit()
    db.refresh(db_call)
    return db_call
