import os
import unittest
from unittest.mock import patch

from app.radio.analog import build_transcribe_options as build_analog_options
from app.radio.digital import (
    build_transcribe_options as build_digital_options,
    get_closest_src,
)


def build_metadata(audio_type: str = "digital") -> dict:
    return {
        "freq": 1,
        "start_time": 1,
        "stop_time": 2,
        "call_length": 5.0,
        "talkgroup": 1,
        "talkgroup_tag": "tag",
        "talkgroup_description": "desc",
        "talkgroup_group_tag": "group-tag",
        "talkgroup_group": "group",
        "audio_type": audio_type,
        "short_name": "short",
        "emergency": 0,
        "encrypted": 0,
        "freqList": [],
        "srcList": [
            {
                "src": 100,
                "time": 10,
                "pos": 0.1,
                "emergency": 0,
                "signal_system": "sys",
                "tag": "A",
                "transcript_prompt": "alpha",
            },
            {
                "src": 200,
                "time": 20,
                "pos": 0.7,
                "emergency": 0,
                "signal_system": "sys",
                "tag": "B",
                "transcript_prompt": "beta",
            },
            {
                "src": 300,
                "time": 30,
                "pos": 0.9,
                "emergency": 0,
                "signal_system": "sys",
                "tag": "C",
                "transcript_prompt": "alpha",
            },
        ],
    }


class TestTranscribeOptions(unittest.TestCase):
    def test_build_digital_transcribe_options(self):
        metadata = build_metadata(audio_type="digital")

        with patch.dict(os.environ, {"VAD_FILTER_DIGITAL": "true"}, clear=False):
            with patch(
                "app.radio.digital.get_whisper_config", return_value={"beam_size": 3}
            ):
                with patch(
                    "app.radio.digital.get_transcript_cleanup_config",
                    return_value=[{"pattern": "foo"}],
                ):
                    options = build_digital_options(metadata)

        self.assertTrue(options["cleanup"])
        self.assertTrue(options["vad_filter"])
        self.assertEqual({"beam_size": 3}, options["decode_options"])
        self.assertEqual([{"pattern": "foo"}], options["cleanup_config"])
        self.assertEqual(["alpha", "beta"], options["initial_prompt"].split())

    def test_build_analog_transcribe_options(self):
        metadata = build_metadata(audio_type="analog")

        with patch.dict(os.environ, {"VAD_FILTER_ANALOG": "false"}, clear=False):
            with patch(
                "app.radio.analog.get_whisper_config", return_value={"beam_size": 2}
            ):
                with patch(
                    "app.radio.analog.get_transcript_cleanup_config",
                    return_value=[{"pattern": "bar"}],
                ):
                    options = build_analog_options(
                        metadata, initial_prompt="expected prompt"
                    )

        self.assertTrue(options["cleanup"])
        self.assertFalse(options["vad_filter"])
        self.assertEqual("expected prompt", options["initial_prompt"])
        self.assertEqual({"beam_size": 2}, options["decode_options"])
        self.assertEqual([{"pattern": "bar"}], options["cleanup_config"])

    def test_get_closest_src(self):
        metadata = build_metadata(audio_type="digital")
        src_list = metadata["srcList"]
        segment = {"start": 0.65, "end": 0.8, "text": "hello"}

        closest = get_closest_src(src_list, segment)

        self.assertEqual(200, closest["src"])


if __name__ == "__main__":
    unittest.main()
