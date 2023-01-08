from threading import Lock
import os
import whisper

model = None
model_lock = Lock()


def load_model() -> whisper.Whisper:
    global model
    if not model:
        model_name = os.getenv("WHISPER_MODEL")
        if not isinstance(model_name, str):
            raise RuntimeError("WHISPER_MODEL env must be set")
        model = whisper.load_model(model_name)
    return model


def transcribe(audio_file: str, initial_prompt: str = "") -> dict:
    with model_lock:
        if os.getenv("FAKE_WHISPER", "").lower() == "true":
            return {
                "text": " some fake text",
                "segments": [
                    {
                        "id": 0,
                        "seek": 0,
                        "start": 0.0,
                        "end": 30.0,
                        "text": " some fake text",
                        "tokens": [
                            50363,
                            6934,
                            6294,
                            379,
                            262,
                            1644,
                            6934,
                            6294,
                            379,
                            262,
                            1644,
                        ],
                        "temperature": 0.2,
                        "avg_logprob": -0.46622033913930255,
                        "compression_ratio": 1.3783783783783783,
                        "no_speech_prob": 0.06185518577694893,
                    }
                ],
                "language": "en",
            }
        return load_model().transcribe(
            audio_file, language="en", initial_prompt=initial_prompt
        )
