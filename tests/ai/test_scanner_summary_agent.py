import datetime as dt
from unittest import IsolatedAsyncioTestCase, TestCase
from unittest.mock import AsyncMock, patch

from pydantic import ValidationError

from app.ai.scanner_summary_agent import (
    AgentCitation,
    AgentSummaryOutput,
    ChatMessage,
    ScannerSummaryRequest,
    build_citation_search_url,
    get_index_names_for_range,
    summarize_scanner_events,
)


class TestScannerSummaryRequestValidation(TestCase):
    def test_rejects_naive_datetimes(self):
        with self.assertRaises(ValidationError):
            ScannerSummaryRequest(
                radio_channel="Main Dispatch",
                start_datetime=dt.datetime(2026, 2, 6, 9, 0, 0),
                end_datetime=dt.datetime(2026, 2, 6, 10, 0, 0),
                question="What happened?",
            )

    def test_rejects_invalid_range(self):
        with self.assertRaises(ValidationError):
            ScannerSummaryRequest(
                radio_channel="Main Dispatch",
                start_datetime=dt.datetime(
                    2026, 2, 6, 10, 0, 0, tzinfo=dt.timezone.utc
                ),
                end_datetime=dt.datetime(2026, 2, 6, 9, 0, 0, tzinfo=dt.timezone.utc),
                question="What happened?",
            )

    def test_rejects_range_beyond_max_window(self):
        with patch.dict(
            "os.environ",
            {"CHAT_SUMMARY_MAX_WINDOW_HOURS": "1"},
            clear=False,
        ):
            with self.assertRaises(ValidationError):
                ScannerSummaryRequest(
                    radio_channel="Main Dispatch",
                    start_datetime=dt.datetime(
                        2026, 2, 6, 8, 0, 0, tzinfo=dt.timezone.utc
                    ),
                    end_datetime=dt.datetime(
                        2026, 2, 6, 10, 0, 0, tzinfo=dt.timezone.utc
                    ),
                    question="What happened?",
                )


class TestScannerSummaryHelpers(TestCase):
    def test_get_index_names_for_range_month_split(self):
        with patch.dict(
            "os.environ",
            {"MEILI_INDEX": "calls", "MEILI_INDEX_SPLIT_BY_MONTH": "true"},
            clear=False,
        ):
            index_names = get_index_names_for_range(
                dt.datetime(2026, 1, 31, 23, 0, tzinfo=dt.timezone.utc),
                dt.datetime(2026, 3, 1, 1, 0, tzinfo=dt.timezone.utc),
            )
        self.assertEqual(["calls_2026_01", "calls_2026_02", "calls_2026_03"], index_names)

    def test_build_citation_search_url(self):
        with patch.dict("os.environ", {"SEARCH_UI_URL": "https://example.com/search"}):
            url = build_citation_search_url(
                index_name="calls",
                call_id="123",
                talkgroup_description="Main Dispatch",
                start_time_epoch=1700000000,
            )
        self.assertIsNotNone(url)
        assert url is not None
        self.assertIn("https://example.com/search?", url)
        self.assertIn("hit-123", url)
        self.assertIn("Main+Dispatch", url)


class TestScannerSummaryService(IsolatedAsyncioTestCase):
    async def test_summarize_scanner_events_builds_response(self):
        request = ScannerSummaryRequest(
            radio_channel="Main Dispatch",
            start_datetime=dt.datetime(2026, 2, 6, 8, 0, 0, tzinfo=dt.timezone.utc),
            end_datetime=dt.datetime(2026, 2, 6, 10, 0, 0, tzinfo=dt.timezone.utc),
            question="Summarize notable incidents",
            history=[ChatMessage(role="user", content="Previous question")],
            radio_system="chi_cpd",
        )
        mocked_output = AgentSummaryOutput(
            answer_markdown="- Incident summary",
            citations=[
                AgentCitation(
                    id="abc123",
                    start_time=1700000000,
                    talkgroup_description="Main Dispatch",
                    index_name="calls",
                )
            ],
            result_count=3,
        )

        with patch.dict(
            "os.environ",
            {
                "CHAT_SUMMARY_MODEL": "openai:gpt-4o-mini",
                "SEARCH_UI_URL": "https://example.com/search",
            },
            clear=False,
        ):
            with patch(
                "app.ai.scanner_summary_agent._run_agent",
                new=AsyncMock(return_value=mocked_output),
            ):
                response = await summarize_scanner_events(request)

        self.assertEqual("- Incident summary", response.answer_markdown)
        self.assertEqual(3, response.result_count)
        self.assertEqual(1, len(response.citations))
        self.assertIsNotNone(response.citations[0].search_url)
        self.assertEqual(3, len(response.history))
        self.assertEqual("assistant", response.history[-1].role)
