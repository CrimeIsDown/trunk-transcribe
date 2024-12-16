import os
from unittest import TestCase

import meilisearch
import typesense
from dotenv import load_dotenv

from app.geocoding.geocoding import GeoResponse
from app.models.metadata import Metadata
from app.models.transcript import Transcript
from app.search.adapters import MeilisearchAdapter, TypesenseAdapter
from app.search.helpers import get_default_index_name

load_dotenv()

original_s3_public_url = os.getenv("S3_PUBLIC_URL")

load_dotenv(".env.testing.local", override=True)


class TestMeilisearchAdapter(TestCase):
    @classmethod
    def setUpClass(cls):
        adapter = MeilisearchAdapter()
        adapter.delete_index(get_default_index_name())

    def test_get_client(self):
        adapter = MeilisearchAdapter()
        self.assertIsInstance(adapter.client, meilisearch.Client)

    def test_build_document(self):
        metadata = Metadata(
            freq=12345,
            start_time=1609459200,
            stop_time=1609459260,
            call_length=60,
            talkgroup=1,
            talkgroup_tag="Tag1",
            talkgroup_description="Description1",
            talkgroup_group_tag="GroupTag1",
            talkgroup_group="Group1",
            short_name="ShortName1",
            audio_type="analog",
            emergency=0,
            encrypted=0,
            freqList=[{"freq": 12345, "time": 1609459200, "pos": 0.0, "len": 60}],
            srcList=[
                {
                    "src": -1,
                    "time": 1609459200,
                    "pos": 0.0,
                    "emergency": 0,
                    "signal_system": "",
                    "tag": "",
                    "transcript_prompt": "",
                }
            ],
        )
        raw_audio_url = "http://example.com/audio.mp3"
        transcript = Transcript(transcript=[(None, "test")])
        geo = GeoResponse(
            geo={"lat": 40.7128, "lng": -74.0060}, geo_formatted_address="New York, NY"
        )

        adapter = MeilisearchAdapter()
        document = adapter.build_document("1", metadata, raw_audio_url, transcript, geo)
        self.assertEqual(document["id"], "1")
        self.assertEqual(document["transcript"], "test")

    def test_index_call(self):
        metadata = Metadata(
            freq=12345,
            start_time=1609459200,
            stop_time=1609459260,
            call_length=60,
            talkgroup=1,
            talkgroup_tag="Tag1",
            talkgroup_description="Description1",
            talkgroup_group_tag="GroupTag1",
            talkgroup_group="Group1",
            short_name="ShortName1",
            audio_type="analog",
            emergency=0,
            encrypted=0,
            freqList=[{"freq": 12345, "time": 1609459200, "pos": 0.0, "len": 60}],
            srcList=[
                {
                    "src": -1,
                    "time": 1609459200,
                    "pos": 0.0,
                    "emergency": 0,
                    "signal_system": "",
                    "tag": "",
                    "transcript_prompt": "",
                }
            ],
        )
        raw_audio_url = "http://example.com/audio.mp3"
        transcript = Transcript(transcript=[(None, "test")])
        geo = GeoResponse(
            geo={"lat": 40.7128, "lng": -74.0060}, geo_formatted_address="New York, NY"
        )

        adapter = MeilisearchAdapter()
        url = adapter.index_call("1", metadata, raw_audio_url, transcript, geo)
        self.assertIn("Tag1", url)

    def test_create_or_update_index(self):
        adapter = MeilisearchAdapter()
        adapter.create_or_update_index("calls")
        index = adapter.client.get_index("calls")
        self.assertIsNotNone(index)


class TestTypesenseAdapter(TestCase):
    @classmethod
    def setUpClass(cls):
        adapter = TypesenseAdapter()
        adapter.delete_index(get_default_index_name())

    def test_get_client(self):
        adapter = TypesenseAdapter()
        self.assertIsInstance(adapter.client, typesense.Client)

    def test_build_document(self):
        metadata = Metadata(
            freq=12345,
            start_time=1609459200,
            stop_time=1609459260,
            call_length=60,
            talkgroup=1,
            talkgroup_tag="Tag1",
            talkgroup_description="Description1",
            talkgroup_group_tag="GroupTag1",
            talkgroup_group="Group1",
            short_name="ShortName1",
            audio_type="analog",
            emergency=0,
            encrypted=0,
            freqList=[{"freq": 12345, "time": 1609459200, "pos": 0.0, "len": 60}],
            srcList=[
                {
                    "src": -1,
                    "time": 1609459200,
                    "pos": 0.0,
                    "emergency": 0,
                    "signal_system": "",
                    "tag": "",
                    "transcript_prompt": "",
                }
            ],
        )
        raw_audio_url = "http://example.com/audio.mp3"
        transcript = Transcript(transcript=[(None, "test")])
        geo = GeoResponse(
            geo={"lat": 40.7128, "lng": -74.0060}, geo_formatted_address="New York, NY"
        )

        adapter = TypesenseAdapter()
        document = adapter.build_document("1", metadata, raw_audio_url, transcript, geo)
        self.assertEqual(document["id"], "1")
        self.assertEqual(document["transcript"], "test")

    def test_index_call(self):
        metadata = Metadata(
            freq=12345,
            start_time=1609459200,
            stop_time=1609459260,
            call_length=60,
            talkgroup=1,
            talkgroup_tag="Tag1",
            talkgroup_description="Description1",
            talkgroup_group_tag="GroupTag1",
            talkgroup_group="Group1",
            short_name="ShortName1",
            audio_type="analog",
            emergency=0,
            encrypted=0,
            freqList=[{"freq": 12345, "time": 1609459200, "pos": 0.0, "len": 60}],
            srcList=[
                {
                    "src": -1,
                    "time": 1609459200,
                    "pos": 0.0,
                    "emergency": 0,
                    "signal_system": "",
                    "tag": "",
                    "transcript_prompt": "",
                }
            ],
        )
        raw_audio_url = "http://example.com/audio.mp3"
        transcript = Transcript(transcript=[(None, "test")])
        geo = GeoResponse(
            geo={"lat": 40.7128, "lng": -74.0060}, geo_formatted_address="New York, NY"
        )

        adapter = TypesenseAdapter()
        url = adapter.index_call("1", metadata, raw_audio_url, transcript, geo)
        self.assertIn("Tag1", url)

    def test_create_or_update_index(self):
        adapter = TypesenseAdapter()
        adapter.create_or_update_index("calls")
        collection = adapter.client.collections["calls"].retrieve()  # type: ignore
        self.assertIsNotNone(collection)
