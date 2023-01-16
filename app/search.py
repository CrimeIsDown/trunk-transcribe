import datetime
import json
import logging
import os
from hashlib import sha256

from meilisearch import Client
from meilisearch.errors import MeiliSearchApiError
from meilisearch.index import Index
from meilisearch.models.task import TaskInfo

from app.conversion import convert_to_mp3
from app.digital import parse_radio_id
from app.storage import upload_file


index = None


def get_client() -> Client:
    url = os.getenv("MEILI_URL", "http://127.0.0.1:7700")
    api_key = os.getenv("MEILI_MASTER_KEY")
    return Client(url=url, api_key=api_key)


def get_index() -> Index:
    global index
    if not index:
        client = get_client()
        index_name = os.getenv("MEILI_INDEX", "calls")
        index = client.index(index_name)
        try:
            index.fetch_info()
        except MeiliSearchApiError:
            index = create_index(client, index_name)

    return index


def index_call(metadata: dict, audio_file: str, transcript: str) -> TaskInfo:
    srcList = [
        src["tag"]
        if len(src["tag"])
        else parse_radio_id(str(src["src"]), metadata["short_name"])[0]
        for src in metadata["srcList"]
    ]

    start_time = datetime.datetime.fromtimestamp(metadata["start_time"])
    uploaded_audio_path = (
        start_time.strftime("%Y/%m/%d/%H/%Y%m%d_%H%M%S")
        + f"_{metadata['short_name']}_{metadata['talkgroup']}.mp3"
    )
    raw_metadata = json.dumps(metadata)
    raw_audio_url = upload_file(convert_to_mp3(audio_file), uploaded_audio_path)
    id = sha256(raw_metadata.encode("utf-8")).hexdigest()

    doc = {
        "freq": metadata["freq"],
        "start_time": metadata["start_time"],
        "stop_time": metadata["stop_time"],
        "call_length": metadata["call_length"],
        "talkgroup": metadata["talkgroup"],
        "talkgroup_tag": metadata["talkgroup_tag"],
        "talkgroup_description": metadata["talkgroup_description"].split("|")[0],
        "talkgroup_group_tag": metadata["talkgroup_group_tag"],
        "talkgroup_group": metadata["talkgroup_group"],
        "audio_type": metadata["audio_type"],
        "short_name": metadata["short_name"],
        "srcList": srcList,
        "transcript": transcript,
        "raw_metadata": raw_metadata,
        "raw_audio_url": raw_audio_url,
        "id": id,
    }

    logging.debug(f"Sending document to be indexed: {str(doc)}")

    return get_index().add_documents([doc])


def create_index(client: Client, index_name: str) -> Index:
    client.create_index(index_name)
    index = client.index(index_name)

    index.update_settings(
        {
            "searchableAttributes": [
                "transcript",
                "srcList",
            ],
            "filterableAttributes": [
                "start_time",
                "talkgroup",
                "talkgroup_tag",
                "talkgroup_description",
                "talkgroup_group_tag",
                "talkgroup_group",
                "audio_type",
                "short_name",
                "srcList",
            ],
            "sortableAttributes": [
                "start_time",
            ],
            "rankingRules": [
                "sort",
                "words",
                "typo",
                "proximity",
                "attribute",
                "exactness",
            ],
        }
    )

    return index
