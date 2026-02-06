import json
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from fastapi.testclient import TestClient

from app.api.depends import get_db
from app.api.main import app


def build_metadata(audio_type: str = "analog") -> dict:
    return {
        "freq": 1,
        "start_time": 1700000000,
        "stop_time": 1700000005,
        "call_length": 5.0,
        "talkgroup": 1,
        "talkgroup_tag": "tag",
        "talkgroup_description": "desc",
        "talkgroup_group_tag": "group-tag",
        "talkgroup_group": "group",
        "audio_type": audio_type,
        "short_name": "short",
        "emergency": 0,
        "encrypted": 0,
        "freqList": [],
        "srcList": [],
    }


class TestApiRoutes(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)

    def test_tasks_route_queues_job_with_explicit_implementation(self):
        metadata = build_metadata(audio_type="analog")
        queue_result = SimpleNamespace(id="task-123")

        with patch.dict("os.environ", {"API_KEY": ""}, clear=False):
            with patch(
                "app.api.routes.tasks.storage.upload_raw_audio",
                return_value="s3://audio.wav",
            ) as upload_mock:
                with patch(
                    "app.api.routes.tasks.worker.queue_task",
                    return_value=queue_result,
                ) as queue_mock:
                    response = self.client.post(
                        "/tasks?whisper_implementation=deepgram:nova-2",
                        files={
                            "call_audio": ("tiny.wav", b"RIFF", "audio/wav"),
                            "call_json": (
                                "call.json",
                                json.dumps(metadata),
                                "application/json",
                            ),
                        },
                    )

        self.assertEqual(201, response.status_code)
        self.assertEqual({"task_id": "task-123"}, response.json())
        upload_mock.assert_called_once()
        queue_mock.assert_called_once()
        self.assertEqual("deepgram:nova-2", queue_mock.call_args.args[3])

    def test_calls_route_queues_job_and_uses_db_call_id(self):
        metadata = build_metadata(audio_type="analog")
        db_call = SimpleNamespace(id=42)
        queue_result = SimpleNamespace(id="task-456")

        app.dependency_overrides[get_db] = lambda: object()
        try:
            with patch.dict("os.environ", {"API_KEY": ""}, clear=False):
                with patch(
                    "app.api.routes.calls.storage.upload_raw_audio",
                    return_value="s3://audio.wav",
                ) as upload_mock:
                    with patch(
                        "app.api.routes.calls.models.create_call",
                        return_value=db_call,
                    ) as create_call_mock:
                        with patch(
                            "app.api.routes.calls.worker.queue_task",
                            return_value=queue_result,
                        ) as queue_mock:
                            response = self.client.post(
                                "/calls?whisper_implementation=openai:whisper-1",
                                files={
                                    "call_audio": ("tiny.wav", b"RIFF", "audio/wav"),
                                    "call_json": (
                                        "call.json",
                                        json.dumps(metadata),
                                        "application/json",
                                    ),
                                },
                            )
        finally:
            app.dependency_overrides.pop(get_db, None)

        self.assertEqual(201, response.status_code)
        self.assertEqual({"task_id": "task-456"}, response.json())
        upload_mock.assert_called_once()
        create_call_mock.assert_called_once()
        queue_mock.assert_called_once()
        self.assertEqual("openai:whisper-1", queue_mock.call_args.args[3])
        self.assertEqual(42, queue_mock.call_args.args[4])


if __name__ == "__main__":
    unittest.main()
