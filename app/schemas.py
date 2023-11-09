from typing import Tuple
from pydantic import BaseModel

from .geocoding import GeoResponse


class CallBase(BaseModel):
    pass


class CallCreate(CallBase):
    raw_metadata: dict
    raw_audio_url: str


class CallUpdate(CallBase):
    raw_transcript: list[Tuple]
    geo: GeoResponse | None


class Call(CallBase):
    id: int
    raw_metadata: dict
    raw_audio_url: str
    raw_transcript: list[Tuple] | None
    geo: GeoResponse | None

    class Config:
        orm_mode = True
