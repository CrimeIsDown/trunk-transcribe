from sqlalchemy import Column, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlmodel import SQLModel, Session, Field

from app.geocoding.types import GeoResponse
from .metadata import Metadata
from .transcript import RawTranscript


class Base(SQLModel):
    pass


class CallBase(Base):
    raw_metadata: Metadata = Field(sa_column=Column(JSONB))
    raw_audio_url: str
    raw_transcript: RawTranscript | None = Field(
        default=None, sa_column=Column(JSONB, nullable=True)
    )
    geo: GeoResponse | None = Field(
        default=None, sa_column=Column(JSONB, nullable=True)
    )


class Call(CallBase, table=True):
    __tablename__ = "calls"
    id: int | None = Field(default=None, primary_key=True)


class CallCreate(CallBase):
    pass


class CallUpdate(Base):
    raw_metadata: Metadata | None = None
    raw_audio_url: str | None = None
    raw_transcript: RawTranscript | None = None
    geo: GeoResponse | None = None


class CallPublic(CallBase):
    id: int


class CallsPublic(Base):
    data: list[CallPublic]
    count: int


def create_call(db: Session, call: CallCreate) -> Call:
    db_call = Call.model_validate(call)
    db.add(db_call)
    db.commit()
    db.refresh(db_call)
    return db_call


def update_call(db: Session, call: CallUpdate, db_call: Call) -> Call:
    call_data = call.model_dump(exclude_unset=True)
    db_call.sqlmodel_update(call_data)
    db.add(db_call)
    db.commit()
    db.refresh(db_call)
    return db_call


def get_talkgroups(db: Session, table_name: str) -> list[dict]:
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
