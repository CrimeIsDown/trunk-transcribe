import unittest
from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient

from app.ai.scanner_summary_agent import (
    ChatMessage,
    ScannerSummaryCitation,
    ScannerSummaryResponse,
    ScannerSummaryServiceError,
)
from app.api.main import app


class TestChatbotRoutes(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)

    def test_chat_transcript_summary_success(self):
        mocked_response = ScannerSummaryResponse(
            answer_markdown="- Summary",
            citations=[
                ScannerSummaryCitation(
                    id="123",
                    start_time="2026-02-06T09:00:00+00:00",
                    talkgroup_description="Main Dispatch",
                    search_url="https://example.com/search#hit-123",
                )
            ],
            result_count=1,
            history=[
                ChatMessage(role="user", content="Summarize incidents"),
                ChatMessage(role="assistant", content="- Summary"),
            ],
        )

        with patch.dict("os.environ", {"API_KEY": ""}, clear=False):
            with patch(
                "app.api.routes.chatbot.summarize_scanner_events",
                new=AsyncMock(return_value=mocked_response),
            ):
                response = self.client.post(
                    "/chat/transcript-summary",
                    json={
                        "radio_channel": "Main Dispatch",
                        "start_datetime": "2026-02-06T08:00:00-06:00",
                        "end_datetime": "2026-02-06T10:00:00-06:00",
                        "question": "Summarize incidents",
                        "history": [],
                    },
                )

        self.assertEqual(200, response.status_code)
        body = response.json()
        self.assertEqual("- Summary", body["answer_markdown"])
        self.assertEqual(1, body["result_count"])
        self.assertEqual("123", body["citations"][0]["id"])

    def test_chat_transcript_summary_maps_service_error_to_503(self):
        with patch.dict("os.environ", {"API_KEY": ""}, clear=False):
            with patch(
                "app.api.routes.chatbot.summarize_scanner_events",
                new=AsyncMock(
                    side_effect=ScannerSummaryServiceError("service unavailable")
                ),
            ):
                response = self.client.post(
                    "/chat/transcript-summary",
                    json={
                        "radio_channel": "Main Dispatch",
                        "start_datetime": "2026-02-06T08:00:00-06:00",
                        "end_datetime": "2026-02-06T10:00:00-06:00",
                        "question": "Summarize incidents",
                        "history": [],
                    },
                )

        self.assertEqual(503, response.status_code)
        self.assertEqual("service unavailable", response.json()["detail"])

    def test_chat_transcript_summary_rejects_naive_datetimes(self):
        with patch.dict("os.environ", {"API_KEY": ""}, clear=False):
            response = self.client.post(
                "/chat/transcript-summary",
                json={
                    "radio_channel": "Main Dispatch",
                    "start_datetime": "2026-02-06T08:00:00",
                    "end_datetime": "2026-02-06T10:00:00",
                    "question": "Summarize incidents",
                    "history": [],
                },
            )

        self.assertEqual(422, response.status_code)


if __name__ == "__main__":
    unittest.main()
