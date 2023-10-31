from sqlalchemy import Column, Integer, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.hybrid import hybrid_property
from sqlalchemy.ext.mutable import MutableDict, MutableList
from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    pass


class Call(Base):
    __tablename__ = "calls"

    id = Column(Integer, primary_key=True, index=True)
    raw_metadata = Column(MutableDict.as_mutable(JSONB))  # type: ignore
    raw_audio_url = Column(String)
    raw_transcript = Column(MutableList.as_mutable(JSONB), nullable=True)  # type: ignore
    geo = Column(MutableDict.as_mutable(JSONB), nullable=True)  # type: ignore

    # @hybrid_property
    # def length(self) -> int:
    #     return self.end - self.start
