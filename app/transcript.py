import json
from typing import Tuple, TypeAlias, Union

from .exceptions import WhisperException
from .metadata import SrcListItem

RawTranscript: TypeAlias = list[Tuple[Union[None, SrcListItem], str]]


# TODO: write tests
class Transcript:
    MIN_LENGTH = 4

    transcript: RawTranscript

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

    @property
    def txt_nosrc(self):
        return "\n".join([transcript for _, transcript in self.transcript])

    def append(self, transcript: str, src: SrcListItem | None = None):
        if len(transcript):
            self.transcript.append((src, transcript))
        return self

    def empty(self):
        return not len(self.transcript)

    def validate(self):
        if self.empty():
            raise WhisperException("Transcript empty/null")
        if (
            len(" ".join([transcript for _, transcript in self.transcript]))
            < Transcript.MIN_LENGTH
        ):
            raise WhisperException("Transcript too short")
        return self

    def update_src(self, newSrc: SrcListItem):
        for i in range(len(self.transcript)):
            src = self.transcript[i][0]
            if src and src["src"] == newSrc["src"]:
                self.transcript[i] = (newSrc, self.transcript[i][1])
