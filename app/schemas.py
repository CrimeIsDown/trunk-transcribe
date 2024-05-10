from typing_extensions import List, Tuple, Optional
from pydantic import BaseModel

from .geocoding import GeoResponse


class CallBase(BaseModel):
    pass


class CallCreate(CallBase):
    raw_metadata: dict
    raw_audio_url: str


class CallUpdate(CallBase):
    raw_transcript: List[Tuple]
    geo: Optional[GeoResponse] = None


class Call(CallBase):
    id: int
    raw_metadata: dict
    raw_audio_url: str
    raw_transcript: Optional[List[Tuple]] = None
    geo: Optional[GeoResponse] = None

    class Config:
        from_attributes = True
