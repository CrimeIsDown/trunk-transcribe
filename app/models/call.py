from typing import List, Optional, Tuple

from pydantic import BaseModel
from sqlalchemy import Column, Integer, String, text
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


def get_call(db: Session, call_id: int) -> Call | None:
    return db.query(Call).filter(Call.id == call_id).first()


def get_calls(db: Session, skip: int = 0, limit: int = 100) -> List[Call]:
    return db.query(Call).offset(skip).limit(limit).all()


def create_call(db: Session, call: CallCreateSchema) -> Call:
    db_call = Call(raw_metadata=call.raw_metadata, raw_audio_url=call.raw_audio_url)
    db.add(db_call)
    db.commit()
    db.refresh(db_call)
    return db_call


def update_call(db: Session, call: CallUpdateSchema, db_call: Call) -> Call:
    db_call.raw_transcript = call.raw_transcript  # type: ignore
    db_call.geo = call.geo  # type: ignore
    db.commit()
    db.refresh(db_call)
    return db_call


def get_talkgroups(db: Session, table_name: str) -> List[dict]:
    query = f"""
        SELECT
            raw_metadata::jsonb ->> 'short_name' AS short_name,
            raw_metadata::jsonb ->> 'talkgroup_group' AS talkgroup_group,
            raw_metadata::jsonb ->> 'talkgroup_tag' AS talkgroup_tag,
            raw_metadata::jsonb ->> 'talkgroup' AS talkgroup
        FROM
            {table_name}
        WHERE
            raw_metadata::jsonb ->> 'talkgroup_tag' != ''
        GROUP BY
            short_name, talkgroup_group, talkgroup_tag, talkgroup
    """

    result = db.execute(text(query)).fetchall()
    return [dict(row._mapping) for row in result]
