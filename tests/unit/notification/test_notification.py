import json
import os
import platform
from apprise import NotifyFormat
import pytz
import time
import unittest

from datetime import datetime
from unittest.mock import patch, Mock, ANY

from app.models.metadata import Metadata
from app.notifications.config import AlertConfig
from app.notifications import notification


class TestTruncateTranscript(unittest.TestCase):
    def test_truncate_max_length_transcript(self):
        transcript = "A" * 824
        result = notification.truncate_transcript(transcript)
        self.assertEqual(result, transcript)


class AppriseStub:
    def __init__(self):
        self.channels = []

    def add(self, channel):
        self.channels.append(channel)


class TestAddChannels(unittest.TestCase):
    def test_add_channels_with_token(self):
        apprise = AppriseStub()
        channels = ["tgram://$TELEGRAM_BOT_TOKEN"]
        os.environ["TELEGRAM_BOT_TOKEN"] = "no-token-defined"
        result = notification.add_channels(apprise, channels)

        self.assertEqual(len(result.channels), 1)
        self.assertIn("tgram://no-token-defined", result.channels)


class TestBuildSuffix(unittest.TestCase):
    def test_build_suffix_with_all_additional_info(self):
        delayed_threshold = 120  # seconds
        now = datetime.now()
        metadata = {
            "talkgroup_tag": "TG123",
            "stop_time": now.timestamp() - delayed_threshold - 1,
            "start_time": time.time(),
        }
        search_url = "https://example.com/search?q=TG123"
        result = notification.build_suffix(metadata, add_talkgroup=True, search_url=search_url)

        linux_format = "%-m/%-d/%Y %-I:%M:%S %p %Z"
        windows_format = linux_format.replace("-", "#")
        timestamp = (
            datetime.fromtimestamp(metadata["start_time"], tz=pytz.UTC)
            .astimezone(pytz.timezone(os.getenv("DISPLAY_TZ", "America/Chicago")))
            .strftime(
                windows_format if platform.system() == "Windows" else linux_format
            )
        )
        expected_suffix = (
            f"<b>{metadata['talkgroup_tag']}</b><br /><br /><i>{timestamp} (delayed)</i>"
            f'<br /><br /><a href="{search_url}">View in search</a>'
        )
        self.assertEqual(result, expected_suffix)


class TestCheckTranscriptForAlertKeywords(unittest.TestCase):
    def test_check_transcript_for_alert_keywords(self):
        transcript = """
            This is a test transcript.
            It contains keywords like fire, shoot, and crime.
            The keywords should be matched regardless of case.
            Another line with FIRE.
            A line without any matching keyword.
        """
        keywords = ["fire", "shoot", "crime", "line with FIRE"]
        expected_matched_keywords = ["fire", "line with FIRE"]
        expected_matched_lines = [
            "It contains keywords like fire, shoot, and crime.",
            "Another line with FIRE.",
        ]

        matched_keywords, matched_lines = notification.check_transcript_for_alert_keywords(
            transcript, keywords
        )

        self.assertTrue(set(expected_matched_keywords).issubset(set(matched_keywords)))
        self.assertListEqual(
            [line.strip() for line in matched_lines], expected_matched_lines
        )


class TestGetMatchingConfig(unittest.TestCase):
    def test_get_matching_config(self):
        metadata = Metadata(talkgroup="TG123", short_name="ShortName123")
        config = {
            r"TG.*@.*": {"config1": "value1"},
            r"TG\d+@ShortName\d+": {"config2": "value2"},
            r"OtherRegex": {"config3": "value3"},
        }
        expected_matching_configs = [{"config1": "value1"}, {"config2": "value2"}]
        matching_configs = notification.get_matching_config(metadata, config)
        self.assertListEqual(matching_configs, expected_matching_configs)


class TestSendNotifications(unittest.TestCase):
    @patch("app.notifications.notification.get_notifications_config")
    @patch("app.models.transcript.Transcript")
    def test_send_notifications(self, mock_transcript, mock_get_notifications_config):
        audio_file = "audio.wav"
        search_url = "https://example.com/search?q=TG123"

        with open("tests/data/11-1673118186_460378000-call_0.json", "rb") as call_json:
            metadata = json.load(call_json)

        mock_transcript_instance = mock_transcript.return_value
        mock_transcript_instance.html = "<p>This is the transcript.</p>"

        mock_get_notifications_config.return_value = {
            "regex1": {
                "config_key1": "config_value1",
                "config_key2": "config_value2",
                "alerts": [],
            },
            "regex2": {
                "config_key3": "config_value3",
                "config_key4": "config_value4",
                "alerts": [],
            },
        }

        notification.send_notifications(
            audio_file, metadata, mock_transcript_instance, None, search_url
        )


class TestNotify(unittest.TestCase):
    @patch("app.notifications.notification.build_suffix")
    @patch("app.notifications.notification.truncate_transcript")
    @patch("app.notifications.notification.add_channels")
    def test_notify_channels(
        self,
        mock_add_channels,
        mock_truncate_transcript,
        mock_build_suffix,
    ):
        # Mock input data
        config = {
            "channels": ["tgram://channel1", "tgram://channel2"],
            "append_talkgroup": True,
        }
        audio_file = "audio.wav"
        metadata = {"talkgroup_tag": "TG123"}
        transcript = "This is the transcript."

        # Mock return values and behaviors
        mock_truncate_transcript.return_value = transcript
        mock_build_suffix.return_value = "TG123"

        # Mock the Apprise instance
        apprise_mock = Mock()
        mock_add_channels.return_value = apprise_mock

        # Call the function
        notification.notify(config, metadata, transcript, audio_file)

        # Perform assertions
        mock_truncate_transcript.assert_called_once_with(transcript)
        mock_build_suffix.assert_called_once_with(metadata, True, "")
        apprise_mock.notify.assert_called_once_with(
            body="<br />".join([transcript, "TG123"]),
            body_format=NotifyFormat.HTML,
            title="",
            attach=ANY,
        )

    @patch("app.notifications.notification.build_suffix")
    @patch("app.notifications.notification.truncate_transcript")
    @patch("app.notifications.notification.add_channels")
    def test_send_alert(
        self, mock_add_channels, mock_truncate_transcript, mock_build_suffix
    ):
        # Mock input data
        config = AlertConfig(
            {
                "channels": ["tgram://channel1", "tgram://channel2"],
                "keywords": ["keyword1", "keyword2"],
            }
        )
        metadata = {"talkgroup_tag": "TG123"}
        transcript = "This is the transcript."
        mp3_file = "audio.mp3"
        search_url = "https://example.com"

        # Mock return values and behaviors
        mock_truncate_transcript.return_value = transcript
        mock_build_suffix.return_value = "TG123"

        # Mock the Apprise instance
        apprise_mock = Mock()
        mock_add_channels.return_value = apprise_mock

        # Call the function
        notification.notify(config, metadata, transcript, mp3_file, "", search_url)

        # Perform assertions
        mock_truncate_transcript.assert_called_once_with(transcript)
        mock_build_suffix.assert_called_once_with(metadata, True, search_url)
        apprise_mock.notify.assert_called_once()


if __name__ == "__main__":
    unittest.main()
