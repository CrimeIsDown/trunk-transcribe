import json
from typing import Tuple, TypeAlias, Union

from .metadata import SrcListItem

RawTranscript: TypeAlias = list[Tuple[Union[None, SrcListItem], str]]


# TODO: write tests
class Transcript:
    transcript: RawTranscript

    hallucinations = [
        "urn.com",
        "urn.schemas",
        # Various YouTube hallucations
        "thank you for watching",
        "thanks for watching",
        "please subscribe",
        "subscribe to my channel",
        "comments below",
        "this video is a derivative work of the touhou project.",
        "i hope you enjoyed this video.",
        "if you did, please leave a like and a comment below.",
        "please leave a like and a comment.",
        "the bell icon",
        "if you enjoyed it",
    ]
    hallucination = "(unintelligible)"

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
        lowercase_transcript = transcript.lower()
        if len(lowercase_transcript) <= 1 or True in [
            h in lowercase_transcript for h in Transcript.hallucinations
        ]:
            transcript = self.hallucination
        self.transcript.append((src, transcript))
        return self

    def empty(self):
        return not len(self.transcript)

    def validate(self):
        if self.empty():
            raise RuntimeError("Transcript empty/null")
        hallucination_count = 0
        for i in range(len(self.transcript)):
            segment = self.transcript[i][1]
            if segment is self.hallucination:
                hallucination_count = hallucination_count + 1

        if len(self.transcript) == hallucination_count:
            raise RuntimeError("Transcript invalid, 100%% hallucination")
        return self

    def update_src(self, newSrc: SrcListItem):
        for i in range(len(self.transcript)):
            src = self.transcript[i][0]
            if src and src["src"] == newSrc["src"]:
                self.transcript[i] = (newSrc, self.transcript[i][1])
