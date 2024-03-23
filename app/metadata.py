from typing_extensions import Literal, TypedDict


class FreqListItem(TypedDict):
    freq: int
    time: int
    pos: float
    len: float
    error_count: int
    spike_count: int


class SrcListItem(TypedDict):
    src: int
    time: int
    pos: float
    emergency: Literal[0, 1]
    signal_system: str
    tag: str
    transcript_prompt: str


class SearchableMetadata(TypedDict):
    freq: int
    start_time: int
    stop_time: int
    call_length: float
    talkgroup: int
    talkgroup_tag: str
    talkgroup_description: str
    talkgroup_group_tag: str
    talkgroup_group: str
    audio_type: Literal["analog", "digital", "digital tdma"]
    short_name: str


class Metadata(SearchableMetadata):
    emergency: Literal[0, 1]
    encrypted: Literal[0, 1]
    freqList: list[FreqListItem]
    srcList: list[SrcListItem]
