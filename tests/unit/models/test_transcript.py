import unittest
import json
from app.whisper.exceptions import WhisperException
from app.models.transcript import Transcript, RawTranscript, SrcListItem


class TestTranscript(unittest.TestCase):
    def test_init_with_transcript(self):
        src_item_1 = SrcListItem({"tag": "Speaker 1", "other_key": "value"})
        src_item_2 = SrcListItem({"tag": "Speaker 2", "other_key": "value"})
        raw_transcript: RawTranscript = [
            (src_item_1, ""),
            (src_item_2, ""),
        ]
        transcript = Transcript(transcript=raw_transcript)

        self.assertEqual(transcript.transcript, raw_transcript)

    def test_json(self):
        raw_transcript: RawTranscript = [
            (None, ""),
            (None, ""),
        ]
        transcript = Transcript(transcript=raw_transcript)

        result = transcript.json

        expected_json = json.dumps(raw_transcript)
        self.assertEqual(result, expected_json)

    def test_html(self):
        raw_transcript = [
            (None, "Hello"),
            ({"src": "Speaker 1", "tag": "John"}, "How are you?"),
            ({"src": "Speaker 2", "tag": "Andy"}, "Im good."),
            (None, "(unintelligible)"),
        ]
        transcript = Transcript(transcript=raw_transcript)

        result = transcript.html

        expected_html = 'Hello<br><i data-src="Speaker 1">John:</i> How are you?<br><i data-src="Speaker 2">Andy:</i> Im good.<br>(unintelligible)'

        self.assertEqual(result, expected_html)

    def test_markdown(self):
        raw_transcript = [
            ({"src": "Speaker 1", "tag": "Alex"}, "How are you"),
            (None, "What happened?"),
            ({"src": "Speaker 2", "tag": ""}, "Shooting in the next house!"),
            (None, "(unintelligible)"),
        ]
        transcript = Transcript(transcript=raw_transcript)

        result = transcript.markdown

        expected_markdown = "_Alex:_ How are you\nWhat happened?\n_Speaker 2:_ Shooting in the next house!\n(unintelligible)"
        self.assertEqual(result, expected_markdown)

    def test_txt(self):
        raw_transcript = [
            ({"src": "Speaker 1", "tag": "Helena"}, "Hi"),
            (None, "Are you far away now?"),
            ({"src": "Speaker 2", "tag": "Kate"}, "Yes, we went out of town."),
            (None, "(unintelligible)"),
        ]
        transcript = Transcript(transcript=raw_transcript)

        result = transcript.txt

        expected_txt = "Helena: Hi\nAre you far away now?\nKate: Yes, we went out of town.\n(unintelligible)"
        self.assertEqual(result, expected_txt)

    def test_append(self):
        transcript = Transcript()

        transcript.append("Hello", {"src": "Speaker 1"})
        self.assertEqual(len(transcript.transcript), 1)
        self.assertEqual(transcript.transcript[0], ({"src": "Speaker 1"}, "Hello"))

    def test_empty(self):
        # Test with an empty transcript
        transcript = Transcript()
        self.assertTrue(transcript.empty())

        # Test with a non empty transcript
        transcript.append("Welcome")
        self.assertFalse(transcript.empty())

    def test_validate(self):
        # Test with an empty transcript
        transcript = Transcript()
        with self.assertRaises(WhisperException):
            transcript.validate()

    def test_update_src(self):
        # Test with an empty transcript
        transcript = Transcript()
        new_src = SrcListItem(
            src=1,
            time=123,
            pos=0.5,
            emergency=0,
            signal_system="System",
            tag="Tag",
            transcript_prompt="Prompt",
        )
        transcript.update_src(new_src)
        self.assertEqual(transcript.transcript, [])

        # Test with a transcript without a matching item
        transcript = Transcript()
        transcript.append(
            "Hello",
            SrcListItem(
                src=1,
                time=123,
                pos=0.5,
                emergency=0,
                signal_system="System",
                tag="Tag",
                transcript_prompt="Prompt",
            ),
        )
        transcript.append(
            "How are you?",
            SrcListItem(
                src=2,
                time=456,
                pos=0.8,
                emergency=1,
                signal_system="System",
                tag="Tag",
                transcript_prompt="Prompt",
            ),
        )
        new_src = SrcListItem(
            src=3,
            time=789,
            pos=0.2,
            emergency=0,
            signal_system="System",
            tag="Tag",
            transcript_prompt="Prompt",
        )
        transcript.update_src(new_src)
        self.assertEqual(
            transcript.transcript,
            [
                (
                    SrcListItem(
                        src=1,
                        time=123,
                        pos=0.5,
                        emergency=0,
                        signal_system="System",
                        tag="Tag",
                        transcript_prompt="Prompt",
                    ),
                    "Hello",
                ),
                (
                    SrcListItem(
                        src=2,
                        time=456,
                        pos=0.8,
                        emergency=1,
                        signal_system="System",
                        tag="Tag",
                        transcript_prompt="Prompt",
                    ),
                    "How are you?",
                ),
            ],
        )


if __name__ == "__main__":
    unittest.main()
