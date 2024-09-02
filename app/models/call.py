from typing import List, Optional, Tuple
from pydantic import BaseModel
from sqlalchemy import Column, Integer, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.mutable import MutableDict, MutableList
from sqlalchemy.orm import Session

from app.geocoding.geocoding import GeoResponse

from .base import Base


class Call(Base):
    __tablename__ = "calls"

    id = Column(Integer, primary_key=True, index=True)
    raw_metadata = Column(MutableDict.as_mutable(JSONB))  # type: ignore
    raw_audio_url = Column(String)
    raw_transcript = Column(MutableList.as_mutable(JSONB), nullable=True)  # type: ignore
    geo = Column(MutableDict.as_mutable(JSONB), nullable=True)  # type: ignore


class CallBaseSchema(BaseModel):
    pass


class CallCreateSchema(CallBaseSchema):
    raw_metadata: dict
    raw_audio_url: str


class CallUpdateSchema(CallBaseSchema):
    raw_transcript: List[Tuple]
    geo: Optional[GeoResponse] = None


class CallSchema(CallBaseSchema):
    id: int
    raw_metadata: dict
    raw_audio_url: str
    raw_transcript: Optional[List[Tuple]] = None
    geo: Optional[GeoResponse] = None

    class Config:
        from_attributes = True


def get_call(db: Session, call_id: int):
    return db.query(Call).filter(Call.id == call_id).first()


def get_calls(db: Session, skip: int = 0, limit: int = 100):
    return db.query(Call).offset(skip).limit(limit).all()


def create_call(db: Session, call: CallCreateSchema):
    db_call = Call(raw_metadata=call.raw_metadata, raw_audio_url=call.raw_audio_url)
    db.add(db_call)
    db.commit()
    db.refresh(db_call)
    return db_call


def update_call(db: Session, call: CallUpdateSchema, db_call: Call):
    db_call.raw_transcript = call.raw_transcript  # type: ignore
    db_call.geo = call.geo  # type: ignore
    db.commit()
    db.refresh(db_call)
    return db_call
