import datetime
from typing import Any, Generator
from itertools import chain, starmap
from urllib.parse import urlencode

from app.core.config import settings
from app.models.metadata import SearchableMetadata


class Document(SearchableMetadata):
    units: list[str]
    radios: list[str]
    srcList: list[str]
    transcript: str
    transcript_plaintext: str
    raw_transcript: str
    raw_metadata: str
    raw_audio_url: str
    id: str
    _geo: dict[str, float]
    geo_formatted_address: str


def get_default_index_name(
    time: datetime.datetime | None = None,
) -> str:  # pragma: no cover
    index_name = settings.MEILI_INDEX
    if settings.MEILI_INDEX_SPLIT_BY_MONTH:
        if not time:
            time = datetime.datetime.now()
        index_name += time.strftime("_%Y_%m")
    return index_name


def flatten_dict(dictionary: dict[Any, Any]) -> dict[Any, Any]:
    """Flatten a nested dictionary structure"""

    def unpack(
        parent_key: Any, parent_value: Any
    ) -> Generator[tuple[Any, Any], None, None]:
        """Unpack one level of nesting in a dictionary"""
        try:
            items = parent_value.items()
        except AttributeError:
            # parent_value was not a dict, no need to flatten
            yield (parent_key, parent_value)
        else:
            for key, value in items:
                if type(value) is list:
                    for k, v in enumerate(value):
                        yield (parent_key + "[" + key + "]" + "[" + str(k) + "]", v)
                else:
                    yield (parent_key + "[" + key + "]", value)

    while True:
        # Keep unpacking the dictionary until all value's are not dictionary's
        dictionary = dict(chain.from_iterable(starmap(unpack, dictionary.items())))
        if not any(isinstance(value, dict) for value in dictionary.values()):
            break
    return dictionary


def encode_params(params: dict):
    return urlencode(flatten_dict(params))


def get_default_engine() -> str:
    if settings.has_meilisearch:
        return "meilisearch"
    elif settings.has_typesense:
        return "typesense"
    else:
        raise ValueError("Invalid search adapter")
