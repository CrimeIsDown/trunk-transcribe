from pydantic import BaseModel

from .geocoding import GeoResponse
from .transcript import RawTranscript


class CallBase(BaseModel):
    pass


class CallCreate(CallBase):
    raw_metadata: dict
    raw_audio_url: str


class CallUpdate(CallBase):
    raw_transcript: RawTranscript
    geo: GeoResponse | None


class Call(CallBase):
    id: int
    raw_metadata: dict
    raw_audio_url: str
    raw_transcript: RawTranscript | None
    geo: GeoResponse | None

    class Config:
        orm_mode = True
