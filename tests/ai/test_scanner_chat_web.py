import datetime as dt
from unittest import TestCase
from unittest.mock import patch

from fastapi.testclient import TestClient

from app.ai.scanner_chat_web import (
    _aggregate_talkgroup_facets,
    _build_filter,
    _build_error_app,
    _default_system_prompt,
    _index_guidance,
    _normalize_model_name,
)


class TestScannerChatWebHelpers(TestCase):
    def test_normalize_model_name_adds_openai_prefix(self):
        self.assertEqual("openai:gpt-4o-mini", _normalize_model_name("gpt-4o-mini"))

    def test_normalize_model_name_keeps_provider(self):
        self.assertEqual(
            "google-gla:gemini-2.5-flash",
            _normalize_model_name("google-gla:gemini-2.5-flash"),
        )

    def test_index_guidance_for_monthly_indexes(self):
        with patch.dict(
            "os.environ",
            {"MEILI_INDEX": "calls", "MEILI_INDEX_SPLIT_BY_MONTH": "true"},
            clear=False,
        ):
            guidance = _index_guidance()
        self.assertIn("calls_YYYY_MM", guidance)

    def test_system_prompt_requires_talkgroup_clarification(self):
        prompt = _default_system_prompt()
        self.assertIn("get_valid_talkgroups", prompt)
        self.assertIn(
            "Never run a transcript search without a talkgroup filter",
            prompt,
        )

    def test_build_filter_uses_talkgroup_or_group_and_time_constraints(self):
        start_datetime = dt.datetime(2026, 3, 8, 10, 0, tzinfo=dt.timezone.utc)
        end_datetime = dt.datetime(2026, 3, 8, 11, 0, tzinfo=dt.timezone.utc)

        filters = _build_filter(
            talkgroup_descriptions=["Main Dispatch", "Citywide 1"],
            radio_system="chi_cpd",
            start_datetime=start_datetime,
            end_datetime=end_datetime,
        )

        self.assertEqual(
            [
                [
                    'talkgroup_description = "Main Dispatch"',
                    'talkgroup_description = "Citywide 1"',
                ],
                'short_name = "chi_cpd"',
                "start_time >= 1772964000",
                "start_time <= 1772967600",
            ],
            filters,
        )

    def test_aggregate_talkgroup_facets_sums_counts_and_applies_query(self):
        choices = _aggregate_talkgroup_facets(
            [
                {"Main Dispatch": 4, "Citywide": 2},
                {"Main Dispatch": 3, "Tac 1": 8},
            ],
            facet_query="dis",
            limit=5,
        )

        self.assertEqual(
            [{"talkgroup_description": "Main Dispatch", "count": 7}],
            choices,
        )

    def test_error_app_reports_unhealthy(self):
        app = _build_error_app("missing config")
        client = TestClient(app)
        health = client.get("/api/health")
        self.assertEqual(503, health.status_code)
        self.assertIn("missing config", health.json()["detail"])
