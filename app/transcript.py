import json
import re
from typing import Tuple, TypeAlias, Union

from app.metadata import SrcListItem

RawTranscript: TypeAlias = list[Tuple[Union[None, SrcListItem], str]]


class Transcript:
    transcript: RawTranscript

    banned_keywords = ["urn.com", "urn.schemas"]
    unintelligible = "(unintelligible)"

    def __init__(self, transcript: RawTranscript | str | None = None):
        self.transcript = []

        if isinstance(transcript, list):
            self.transcript = transcript
        elif isinstance(transcript, str):
            self.load_html_transcript(transcript)

    @property
    def json(self):
        return json.dumps(self.transcript)

    @property
    def html(self):
        return "<br>".join(
            [
                f'<i data-src="{src["src"]}">{src["tag"] if len(src["tag"]) else src["src"]}:</i> {transcript}'
                if src
                else transcript
                for src, transcript in self.transcript
            ]
        )

    @property
    def markdown(self):
        """
        Convert to Markdown following https://core.telegram.org/bots/api#markdown-style
        """
        return "\n".join(
            [
                f'_{src["tag"] if len(src["tag"]) else src["src"]}:_ {transcript}'
                if src
                else transcript
                for src, transcript in self.transcript
            ]
        )

    @property
    def txt(self):
        return "\n".join(
            [
                f'{src["tag"] if len(src["tag"]) else src["src"]}: {transcript}'
                if src
                else transcript
                for src, transcript in self.transcript
            ]
        )

    def append(self, transcript: str, src: SrcListItem | None = None):
        if len(transcript) <= 1 or True in [keyword in transcript for keyword in Transcript.banned_keywords]:
            transcript = Transcript.unintelligible
        self.transcript.append((src, transcript))
        return self

    def empty(self):
        return not len(self.transcript)

    def validate(self):
        if self.empty():
            raise RuntimeError("Transcript empty/null")
        first_segment = self.transcript[0][1]
        if len(self.transcript) == 1 and first_segment in [
            "Thank you.",
            Transcript.unintelligible,
        ]:
            raise RuntimeError("No speech found")
        return self

    def update_src(self, newSrc: SrcListItem):
        for i in range(len(self.transcript)):
            src = self.transcript[i][0]
            if src and src["src"] == newSrc["src"]:
                self.transcript[i] = (newSrc, self.transcript[i][1])

    def load_html_transcript(self, html_transcript: str):
        html_transcript = html_transcript.replace("<br>", "\n")
        html_transcript_lines = html_transcript.splitlines()
        for line in html_transcript_lines:
            line = line.strip()
            if line.startswith("<i data-src="):
                html_match = re.compile(
                    r"<i data-src=\"(-?[0-9]+)\">(.*?):</i> (.*)"
                ).fullmatch(line)
                if not html_match:
                    raise RuntimeError("Cannot parse HTML: " + line)
                src = int(html_match.group(1))
                tag = (
                    html_match.group(2)
                    if html_match.group(2) != html_match.group(1)
                    else ""
                )
                segment = html_match.group(3)
                self.transcript.append(
                    (
                        {
                            "src": src,
                            "time": -1,
                            "pos": -1,
                            "emergency": 0,
                            "signal_system": "",
                            "tag": tag,
                            "transcript_prompt": "",
                        },
                        segment,
                    )
                )
            elif line.startswith("<i>"):
                html_match = re.compile(r"<i>(-?[0-9]+):</i> (.*)").fullmatch(line)
                if not html_match:
                    raise RuntimeError("Cannot parse HTML: " + line)
                src = int(html_match.group(1))
                tag = ""
                segment = html_match.group(2)
                self.transcript.append(
                    (
                        {
                            "src": src,
                            "time": -1,
                            "pos": -1,
                            "emergency": 0,
                            "signal_system": "",
                            "tag": tag,
                            "transcript_prompt": "",
                        },
                        segment,
                    )
                )
            else:
                self.transcript.append((None, line))
