from deepgram import DeepgramClient
from deepgram import FileSource, PrerecordedOptions, PrerecordedResponse

from .base import BaseWhisper, TranscribeOptions, WhisperResult


class DeepgramApi(BaseWhisper):
    def __init__(self, api_key: str, model: str = "nova-2"):
        self.client = DeepgramClient(api_key=api_key)
        self.model = model

    def transcribe(
        self,
        audio: str,
        options: TranscribeOptions,
        language: str = "en",
    ) -> WhisperResult:
        with open(audio, "rb") as audio_file:
            payload: FileSource = {"buffer": audio_file.read()}

        deepgram_options = PrerecordedOptions(
            model=self.model,
            utterances=True,
            smart_format=True,
            language=language,
            keywords=options["initial_prompt"],
        )
        response: PrerecordedResponse = self.client.listen.prerecorded.v(
            "1"
        ).transcribe_file(payload, deepgram_options, timeout=120)  # type: ignore

        if (
            response.results
            and response.results.utterances
            and response.results.channels
        ):
            return {
                "segments": [
                    {"start": u.start, "end": u.end, "text": u.transcript}
                    for u in response.results.utterances
                ],
                "text": response.results.channels[0].alternatives[0].transcript,
                "language": language,
            }
        return {"segments": [], "text": "", "language": language}
