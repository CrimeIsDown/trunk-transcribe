from datetime import datetime
from sqlalchemy import TIMESTAMP, Column, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlmodel import SQLModel, Session, Field

from app.geocoding.types import GeoResponse
from .metadata import Metadata
from .transcript import RawTranscript


CALLS_TABLE_NAME = "calls"
TALKGROUP_SEARCH_MATERIALIZED_VIEW_NAME = "talkgroup_search"


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
    start_time: datetime = Field(
        sa_column=Column(
            TIMESTAMP(timezone=True), nullable=False, server_default=text("now()")
        )
    )
    transcript_plaintext: str | None = Field(default=None)


class Call(CallBase, table=True):
    __tablename__ = CALLS_TABLE_NAME
    id: int | None = Field(default=None, primary_key=True)


class CallCreate(CallBase):
    pass


class CallUpdate(Base):
    raw_metadata: Metadata | None = None
    raw_audio_url: str | None = None
    raw_transcript: RawTranscript | None = None
    geo: GeoResponse | None = None
    start_time: datetime | None = None
    transcript_plaintext: str | None = None


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


def get_talkgroups(
    db: Session,
    *,
    radio_system: str | None = None,
    start_datetime: datetime | None = None,
    end_datetime: datetime | None = None,
    search_query: str | None = None,
    limit: int | None = None,
) -> list[dict]:
    where_clauses = ["1 = 1"]
    params: dict[str, object] = {}

    if radio_system:
        where_clauses.append("short_name = :radio_system")
        params["radio_system"] = radio_system

    if start_datetime:
        where_clauses.append("active_hour >= date_trunc('hour', :start_datetime)")
        params["start_datetime"] = start_datetime

    if end_datetime:
        where_clauses.append("active_hour <= date_trunc('hour', :end_datetime)")
        params["end_datetime"] = end_datetime

    if search_query:
        where_clauses.append(
            "search_vector @@ websearch_to_tsquery('simple', :search_query)"
        )
        params["search_query"] = search_query

    query = f"""
        SELECT
            short_name,
            talkgroup_group,
            talkgroup_tag,
            talkgroup_description,
            talkgroup
        FROM
            {TALKGROUP_SEARCH_MATERIALIZED_VIEW_NAME}
        WHERE
            {" AND ".join(where_clauses)}
        GROUP BY
            short_name, talkgroup_group, talkgroup_tag, talkgroup_description, talkgroup
        ORDER BY
            short_name,
            talkgroup_group,
            talkgroup_description,
            talkgroup_tag,
            talkgroup
    """

    if limit is not None:
        query += "\n        LIMIT :limit"
        params["limit"] = limit

    result = db.execute(text(query), params).fetchall()
    return [dict(row._mapping) for row in result]


def refresh_talkgroup_search_materialized_view(*, concurrently: bool = True) -> None:
    from app.models.database import engine

    refresh_mode = "CONCURRENTLY " if concurrently else ""
    statement = text(
        f"REFRESH MATERIALIZED VIEW {refresh_mode}{TALKGROUP_SEARCH_MATERIALIZED_VIEW_NAME}"
    )

    if concurrently:
        with engine.connect().execution_options(isolation_level="AUTOCOMMIT") as conn:
            conn.execute(statement)
        return

    with Session(engine) as db:
        db.execute(statement)
        db.commit()
