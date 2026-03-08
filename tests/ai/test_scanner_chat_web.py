import datetime as dt
import sys
import types
from unittest import TestCase
from unittest.mock import patch

from fastapi.testclient import TestClient

from app.ai.scanner_chat_web import (
    _build_filter,
    _build_error_app,
    _default_system_prompt,
    _get_valid_talkgroups_from_database,
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

    def test_get_valid_talkgroups_from_database_uses_filtered_query(self):
        class FakeSession:
            def __init__(self, _engine: object):
                self.engine = _engine

            def __enter__(self):
                return "db-session"

            def __exit__(self, exc_type, exc, tb):
                return False

        fake_models_module = types.ModuleType("app.models.models")
        captured_kwargs: dict[str, object] = {}

        def fake_get_talkgroups(db: object, **kwargs: object) -> list[dict[str, str]]:
            captured_kwargs["db"] = db
            captured_kwargs.update(kwargs)
            return [
                {
                    "short_name": "chi_cpd",
                    "talkgroup_group": "Chicago Police Department",
                    "talkgroup_tag": "Zone 1",
                    "talkgroup_description": "Main Dispatch",
                    "talkgroup": "1",
                }
            ]

        fake_models_module.get_talkgroups = fake_get_talkgroups
        fake_models_package = types.ModuleType("app.models")
        fake_models_package.models = fake_models_module

        start_datetime = dt.datetime(2026, 3, 8, 10, 0, tzinfo=dt.timezone.utc)
        end_datetime = dt.datetime(2026, 3, 8, 11, 0, tzinfo=dt.timezone.utc)

        with patch.dict(
            sys.modules,
            {
                "sqlmodel": types.ModuleType("sqlmodel"),
                "app.models": fake_models_package,
                "app.models.database": types.ModuleType("app.models.database"),
            },
        ):
            sys.modules["sqlmodel"].Session = FakeSession
            sys.modules["app.models.database"].engine = "fake-engine"
            choices = _get_valid_talkgroups_from_database(
                radio_system="chi_cpd",
                start_datetime=start_datetime,
                end_datetime=end_datetime,
                search_query="dispatch",
                limit=10,
            )

        self.assertEqual("db-session", captured_kwargs["db"])
        self.assertEqual("chi_cpd", captured_kwargs["radio_system"])
        self.assertEqual(start_datetime, captured_kwargs["start_datetime"])
        self.assertEqual(end_datetime, captured_kwargs["end_datetime"])
        self.assertEqual("dispatch", captured_kwargs["search_query"])
        self.assertEqual(10, captured_kwargs["limit"])
        self.assertEqual("Main Dispatch", choices[0]["talkgroup_description"])

    def test_error_app_reports_unhealthy(self):
        app = _build_error_app("missing config")
        client = TestClient(app)
        health = client.get("/api/health")
        self.assertEqual(503, health.status_code)
        self.assertIn("missing config", health.json()["detail"])
