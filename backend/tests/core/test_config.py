import unittest

from app.core.config import (
    parse_csv_list,
    validate_transcription_backend,
    resolve_api_backend_for_implementation,
    resolve_transcription_backend,
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


class TestValidateTranscriptionBackend(unittest.TestCase):
    def test_accepts_whisper(self):
        self.assertEqual("whisper", validate_transcription_backend("whisper"))

    def test_accepts_api(self):
        self.assertEqual("api", validate_transcription_backend("api"))

    def test_accepts_qwen(self):
        self.assertEqual("qwen", validate_transcription_backend("qwen"))

    def test_accepts_voxtral(self):
        self.assertEqual("voxtral", validate_transcription_backend("voxtral"))

    def test_raises_on_unknown_backend(self):
        with self.assertRaises(ValueError) as ctx:
            validate_transcription_backend("unknown")
        self.assertIn("Unsupported transcription backend", str(ctx.exception))


class TestResolveApiBackendForImplementation(unittest.TestCase):
    def test_whisper_with_openai_implementation_returns_api(self):
        self.assertEqual(
            "api",
            resolve_api_backend_for_implementation("whisper", "openai"),
        )

    def test_whisper_with_deepinfra_implementation_returns_api(self):
        self.assertEqual(
            "api",
            resolve_api_backend_for_implementation("whisper", "deepinfra"),
        )

    def test_whisper_with_vendor_prefix_returns_api(self):
        self.assertEqual(
            "api",
            resolve_api_backend_for_implementation("whisper", "openai:whisper-1"),
        )

    def test_whisper_with_asr_api_implementation_stays_whisper(self):
        self.assertEqual(
            "whisper",
            resolve_api_backend_for_implementation("whisper", "whisper-asr-api"),
        )

    def test_non_whisper_backend_is_unchanged(self):
        self.assertEqual(
            "qwen",
            resolve_api_backend_for_implementation("qwen", "openai"),
        )

    def test_no_implementation_stays_as_is(self):
        self.assertEqual(
            "whisper",
            resolve_api_backend_for_implementation("whisper", None),
        )


class TestResolveTranscriptionBackend(unittest.TestCase):
    def test_explicit_backend_takes_precedence(self):
        self.assertEqual(
            "qwen",
            resolve_transcription_backend("qwen", default_backend="whisper"),
        )

    def test_falls_back_to_default(self):
        self.assertEqual(
            "whisper",
            resolve_transcription_backend(None, default_backend="whisper"),
        )

    def test_vendor_implementation_promotes_to_api(self):
        self.assertEqual(
            "api",
            resolve_transcription_backend(
                "whisper",
                default_backend="whisper",
                whisper_implementation="openai:whisper-1",
            ),
        )

    def test_raises_on_unknown_explicit_backend(self):
        with self.assertRaises(ValueError):
            resolve_transcription_backend("bad-backend", default_backend="whisper")

    def test_raises_on_unknown_default_backend(self):
        with self.assertRaises(ValueError):
            resolve_transcription_backend(None, default_backend="bad-backend")


if __name__ == "__main__":
    unittest.main()
