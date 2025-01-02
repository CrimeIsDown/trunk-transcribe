import os
import unittest
from subprocess import CompletedProcess
from unittest.mock import patch

from app.utils.conversion import _convert_file
from app.models.metadata import Metadata


class TestConversion(unittest.TestCase):
    def setUp(self):
        self.audio_file = "test_audio.wav"
        self.format = "mp3"
        self.ffmpeg_args = ["-codec:a", "libmp3lame"]
        self.metadata = Metadata(
            {
                "freq": 477787500,
                "start_time": 1673118015,
                "stop_time": 1673118023,
                "emergency": 0,
                "encrypted": 0,
                "call_length": 5,
                "talkgroup": 1,
                "talkgroup_tag": "CFD Fire N",
                "talkgroup_description": "Fire: Main (North)",
                "talkgroup_group_tag": "Fire Dispatch",
                "talkgroup_group": "Chicago Fire Department",
                "audio_type": "digital",
                "short_name": "chi_cfd",
                "freqList": [
                    {
                        "freq": 477787500,
                        "time": 1673118015,
                        "pos": 0.00,
                        "len": 4.68,
                        "error_count": "20",
                        "spike_count": "6",
                    },
                    {
                        "freq": 477787500,
                        "time": 1673118022,
                        "pos": 4.68,
                        "len": 0.72,
                        "error_count": "8",
                        "spike_count": "6",
                    },
                ],
                "srcList": [
                    {
                        "src": 1410967,
                        "time": 1673118015,
                        "pos": 0.00,
                        "emergency": 0,
                        "signal_system": "",
                        "tag": "E96",
                        "transcript_prompt": "Engine 96 on scene",
                    },
                    {
                        "src": 911005,
                        "time": 1673118022,
                        "pos": 4.68,
                        "emergency": 0,
                        "signal_system": "",
                        "tag": "Fire Main",
                        "transcript_prompt": "Main message received stand by",
                    },
                ],
            }
        )

    @patch("subprocess.run")
    def test_convert_file(self, mock_subprocess_run):
        subprocess_args = (
            [
                "ffmpeg",
                "-y",
                "-hide_banner",
                "-loglevel",
                "error",
                "-i",
                self.audio_file,
            ]
            + self.ffmpeg_args
            + [
                "-metadata",
                "composer=trunk-recorder",
                "-metadata",
                "creation_time=2023-01-07 19:00:15",
                "-metadata",
                "date=2023-01-07",
                "-metadata",
                "year=2023",
                "-metadata",
                "title=CFD Fire N",
                "-metadata",
                "artist=E96, Fire Main",
                "-metadata",
                "album=Chicago Fire Department",
            ]
        )

        mock_subprocess_run.return_value = CompletedProcess(subprocess_args, 0)

        result = _convert_file(
            self.audio_file, self.format, self.ffmpeg_args, self.metadata
        )
        # Update expected args with our temp file name
        subprocess_args.append(result)

        mock_subprocess_run.assert_called_once_with(subprocess_args)

        self.assertTrue(os.path.exists(result))

        os.remove(result)


if __name__ == "__main__":
    unittest.main()
