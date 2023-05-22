import json
from typing import Tuple, TypeAlias, Union

from app.metadata import SrcListItem

RawTranscript: TypeAlias = list[Tuple[Union[None, SrcListItem], str]]


class Transcript:
    transcript: RawTranscript

    banned_keywords = ["urn.com", "urn.schemas"]
    invalid_segments = ["Thank you.", "(unintelligible)"]
    unintelligible = "(unintelligible)"

    def __init__(self, transcript: RawTranscript | None = None):
        self.transcript = transcript if transcript else []

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
        if len(transcript) <= 1 or True in [
            keyword in transcript for keyword in Transcript.banned_keywords
        ]:
            transcript = self.unintelligible
        self.transcript.append((src, transcript))
        return self

    def empty(self):
        return not len(self.transcript)

    def validate(self):
        if self.empty():
            raise RuntimeError("Transcript empty/null")
        first_segment = self.transcript[0][1]
        if len(self.transcript) == 1 and first_segment in self.invalid_segments:
            raise RuntimeError("No speech found")
        return self

    def update_src(self, newSrc: SrcListItem):
        for i in range(len(self.transcript)):
            src = self.transcript[i][0]
            if src and src["src"] == newSrc["src"]:
                self.transcript[i] = (newSrc, self.transcript[i][1])
