import unittest
import time
import pytz
import os
import platform
from app.notification import truncate_transcript
from app.notification import add_channels
from datetime import datetime
from app.notification import build_suffix
from app.notification import check_transcript_for_alert_keywords
from app.notification import get_matching_config
from unittest.mock import patch, Mock, ANY
from app.notification import send_notifications, Metadata
from app.notification import notify_channels, NotifyFormat
from app.notification import send_alert, NotifyFormat, Apprise, AppriseAttachment




class TestTruncateTranscript(unittest.TestCase):
    def test_truncate_max_length_transcript(self):
        transcript = 'A' * 824
        result = truncate_transcript(transcript)
        self.assertEqual(result, transcript)

class AppriseStub:
    def __init__(self):
        self.channels = []

    def add(self, channel):
        self.channels.append(channel)

class TestAddChannels(unittest.TestCase):
    def test_add_channels_with_token(self):
        apprise = AppriseStub()
        channels = ['tgram://$TELEGRAM_BOT_TOKEN']
        result = add_channels(apprise, channels)

        self.assertEqual(len(result.channels), 1)
        self.assertIn('tgram://no-token-defined', result.channels)

class TestBuildSuffix(unittest.TestCase):
    def test_build_suffix_with_all_additional_info(self):
        delayed_threshold = 120  # seconds
        now = datetime.now()
        metadata = {
            'talkgroup_tag': 'TG123',
            'stop_time': now.timestamp() - delayed_threshold - 1,
            'start_time': time.time(),
        }
        search_url = 'https://example.com/search?q=TG123'
        result = build_suffix(metadata, add_talkgroup=True, search_url=search_url)

        linux_format = "%-m/%-d/%Y %-I:%M:%S %p %Z"
        windows_format = linux_format.replace("-", "#")
        timestamp = (
            datetime.fromtimestamp(metadata["start_time"], tz=pytz.UTC)
            .astimezone(pytz.timezone(os.getenv("DISPLAY_TZ", "America/Chicago")))
            .strftime(windows_format if platform.system() == "Windows" else linux_format)
        )
        expected_suffix = (
            f"<b>{metadata['talkgroup_tag']}</b><br /><br /><i>{timestamp} (delayed)</i>"
            f"<br /><br /><a href=\"{search_url}\">View in search</a>"
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
        keywords = ['fire', 'shoot', 'crime', 'line with FIRE']
        expected_matched_keywords = ['fire', 'line with FIRE']
        expected_matched_lines = [
            'It contains keywords like fire, shoot, and crime.',
            'Another line with FIRE.'
        ]

        matched_keywords, matched_lines = check_transcript_for_alert_keywords(transcript, keywords)

        self.assertTrue(set(expected_matched_keywords).issubset(set(matched_keywords)))
        self.assertListEqual([line.strip() for line in matched_lines], expected_matched_lines)

class TestGetMatchingConfig(unittest.TestCase):
    def test_get_matching_config(self):
        metadata = Metadata(
            talkgroup='TG123',
            short_name='ShortName123'
        )
        config = {
            r'TG.*@.*': {'config1': 'value1'},
            r'TG\d+@ShortName\d+': {'config2': 'value2'},
            r'OtherRegex': {'config3': 'value3'}
        }
        expected_matching_configs = [
            {'config1': 'value1'},
            {'config2': 'value2'}
        ]
        matching_configs = get_matching_config(metadata, config)
        self.assertListEqual(matching_configs, expected_matching_configs)

class TestSendNotifications(unittest.TestCase):
    @patch('app.notification.requests.get')
    @patch('app.notification.Transcript')
    def test_send_notifications(self, mock_transcript, mock_requests_get):
        audio_file = 'audio.wav'
        mp3_file = 'audio.mp3'
        search_url = 'https://example.com/search?q=TG123'

        metadata = Metadata(
            talkgroup='TG123',
            short_name='ShortName123',
            stop_time=1234567890
        )

        mock_transcript_instance = mock_transcript.return_value
        mock_transcript_instance.html = '<p>This is the transcript.</p>'

        #Plug for the function requests.get
        mock_response = mock_requests_get.return_value
        mock_response.json.return_value = {
            "regex1": {
                "config_key1": "config_value1",
                "config_key2": "config_value2",
                "alerts": []
            },
            "regex2": {
                "config_key3": "config_value3",
                "config_key4": "config_value4",
                "alerts": []
            },

        }

        send_notifications(audio_file, metadata, mock_transcript_instance, mp3_file, search_url)

class TestNotifyChannels(unittest.TestCase):
    @patch('app.notification.build_suffix')
    @patch('app.notification.truncate_transcript')
    @patch('app.notification.convert_to_ogg')
    @patch('app.notification.add_channels')
    def test_notify_channels(
        self,
        mock_add_channels,
        mock_convert_to_ogg,
        mock_truncate_transcript,
        mock_build_suffix,
    ):
        #Mock input data
        config = {
            "channels": ["tgram://channel1", "tgram://channel2"],
            "append_talkgroup": True
        }
        audio_file = "audio.wav"
        metadata = {
            "talkgroup_tag": "TG123"
        }
        transcript = "This is the transcript."

        #Mock return values and behaviors
        mock_convert_to_ogg.return_value = "audio.ogg"
        mock_truncate_transcript.return_value = transcript
        mock_build_suffix.return_value = "TG123"

        #Mock the Apprise instance
        apprise_mock = Mock()
        mock_add_channels.return_value = apprise_mock

        #Call the function
        notify_channels(config, audio_file, metadata, transcript)

        #Perform assertions
        mock_convert_to_ogg.assert_called_once_with(audio_file, metadata)
        mock_truncate_transcript.assert_called_once_with(transcript)
        mock_build_suffix.assert_called_once_with(metadata, True)
        apprise_mock.notify.assert_called_once_with(
            body="<br />".join([transcript, "TG123"]),
            body_format=NotifyFormat.HTML,
            attach=ANY
        )

class TestSendAlert(unittest.TestCase):
    @patch('app.notification.truncate_transcript')
    @patch('app.notification.build_suffix')
    @patch('app.notification.check_transcript_for_alert_keywords')
    @patch('app.notification.add_channels')
    def test_send_alert(
        self,
        mock_add_channels,
        mock_check_transcript_for_alert_keywords,
        mock_build_suffix,
        mock_truncate_transcript,
    ):
        #Mock input data
        config = {
            "channels": ["tgram://channel1", "tgram://channel2"],
            "keywords": ["keyword1", "keyword2"]
        }
        metadata = {
            "talkgroup_tag": "TG123"
        }
        transcript = "This is the transcript."
        mp3_file = "audio.mp3"
        search_url = "https://example.com"

        #Mock return values and behaviors
        mock_truncate_transcript.return_value = transcript
        mock_build_suffix.return_value = "TG123"
        mock_check_transcript_for_alert_keywords.return_value = (["keyword1"], ["line1", "line2"])

        #Mock the Apprise instance
        apprise_mock = Mock()
        mock_add_channels.return_value = apprise_mock

        #Call the function
        send_alert(config, metadata, transcript, mp3_file, search_url)

        #Perform assertions
        mock_truncate_transcript.assert_called_once_with(transcript)
        mock_build_suffix.assert_called_once_with(metadata, add_talkgroup=True, search_url=search_url)
        mock_check_transcript_for_alert_keywords.assert_called_once_with(transcript, config["keywords"])
        apprise_mock.notify.assert_called_once()

if __name__ == '__main__':
 unittest.main()


