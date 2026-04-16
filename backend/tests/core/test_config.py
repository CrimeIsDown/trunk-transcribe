import unittest

from app.core.config import parse_csv_list
from app.core.transcription_profiles import (
    REMOTE_VENDOR_QUEUE,
    build_pool_profile,
    build_vendor_profile,
    resolve_transcription_profile,
    slug_token,
)


class TestParseCsvList(unittest.TestCase):
    def test_returns_empty_list_for_none(self):
        self.assertEqual([], parse_csv_list(None))

    def test_returns_empty_list_for_empty_string(self):
        self.assertEqual([], parse_csv_list(""))

    def test_parses_single_item(self):
        self.assertEqual(["whisper"], parse_csv_list("whisper"))

    def test_parses_multiple_items(self):
        self.assertEqual(["a", "b", "c"], parse_csv_list("a,b,c"))

    def test_strips_whitespace(self):
        self.assertEqual(["a", "b"], parse_csv_list("  a , b  "))

    def test_skips_empty_items_after_split(self):
        self.assertEqual(["a", "b"], parse_csv_list("a,,b"))

    def test_passes_through_list(self):
        self.assertEqual(["x", "y"], parse_csv_list(["x", "y"]))

    def test_raises_on_unexpected_type(self):
        with self.assertRaises(ValueError):
            parse_csv_list(42)


class TestTranscriptionProfiles(unittest.TestCase):
    def test_vendor_profile_routes_to_vendor_queue(self):
        profile = resolve_transcription_profile(
            build_vendor_profile("openai", "whisper-1")
        )
        self.assertEqual("vendor", profile.kind)
        self.assertEqual("openai", profile.provider)
        self.assertEqual("whisper-1", profile.model)
        self.assertEqual("vendor.openai", profile.endpoint_target)
        self.assertEqual(REMOTE_VENDOR_QUEUE, profile.queue_name)
        self.assertIsNone(profile.asr_pool)

    def test_pool_profile_routes_to_pool_queue(self):
        profile = resolve_transcription_profile(
            build_pool_profile(
                platform="vast",
                family="whisper",
                variant="large-v3",
                provider="speaches",
                model="Systran/faster-whisper-large-v3",
            )
        )
        self.assertEqual("pool", profile.kind)
        self.assertEqual("pool.vast.whisper.large-v3", profile.endpoint_target)
        self.assertEqual("vast.whisper.large-v3", profile.asr_pool)
        self.assertEqual(
            "transcribe.remote.pool.vast.whisper.large-v3", profile.queue_name
        )

    def test_pool_profile_requires_platform_family_variant(self):
        with self.assertRaisesRegex(
            ValueError,
            "Pool transcription profiles must include platform, family, and variant fields",
        ):
            resolve_transcription_profile(
                "kind=pool;provider=speaches;model=Systran/faster-whisper-large-v3"
            )

    def test_slug_token_normalizes_separators(self):
        self.assertEqual("large-v3-turbo", slug_token("Large/V3 Turbo"))


if __name__ == "__main__":
    unittest.main()
