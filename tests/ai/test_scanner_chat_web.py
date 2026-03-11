import datetime as dt
import sys
import types
from unittest import TestCase
from unittest.mock import patch

from fastapi.testclient import TestClient

from app.ai.scanner_chat_web import (
    DEFAULT_MAX_ANALYSIS_HITS,
    SearchScope,
    SearchScopeRange,
    _build_error_app,
    _build_scope_filters,
    _default_system_prompt,
    _get_valid_talkgroups_from_database,
    _index_guidance,
    _normalize_model_name,
    _normalize_search_scope,
    _search_transcripts_for_scope,
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

    def test_system_prompt_requires_current_search_scope(self):
        prompt = _default_system_prompt()
        self.assertIn("get_current_search_scope", prompt)
        self.assertIn("search_transcripts", prompt)
        self.assertIn("paginates through matching results", prompt)

    def test_normalize_search_scope_discards_unsupported_fields(self):
        scope = _normalize_search_scope(
            {
                "query": "  shots fired ",
                "refinementList": {
                    "short_name": ["sys2", "sys1", "sys1"],
                    "ignored": ["value"],
                },
                "hierarchicalMenu": {
                    "talkgroup_hierarchy.lvl1": "sys1 > Police",
                    "ignored": "value",
                },
                "range": {"start_time": "1700000000:1700003600"},
                "maxHits": 150,
            }
        )

        self.assertEqual("shots fired", scope.query)
        self.assertEqual({"short_name": ["sys1", "sys2"]}, scope.refinementList)
        self.assertEqual(
            {"talkgroup_hierarchy.lvl1": "sys1 > Police"},
            scope.hierarchicalMenu,
        )
        self.assertEqual("1700000000:1700003600", scope.range.start_time)
        self.assertEqual(150, scope.maxHits)

    def test_build_scope_filters_uses_refinements_hierarchy_and_time_constraints(self):
        filters = _build_scope_filters(
            SearchScope(
                refinementList={
                    "short_name": ["chi_cpd"],
                    "talkgroup_tag": ["Chi PD Zone 10", "Citywide 1"],
                },
                hierarchicalMenu={
                    "talkgroup_hierarchy.lvl1": "chi_cpd > Chicago Police Department"
                },
                range=SearchScopeRange(start_time="1772964000:1772967600"),
            )
        )

        self.assertEqual(
            [
                ['short_name = "chi_cpd"'],
                [
                    'talkgroup_tag = "Chi PD Zone 10"',
                    'talkgroup_tag = "Citywide 1"',
                ],
                'talkgroup_hierarchy.lvl1 = "chi_cpd > Chicago Police Department"',
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

    def test_search_transcripts_for_scope_paginates_until_scope_cap(self):
        offsets: list[int] = []

        def fake_search_index_page(**kwargs):
            offsets.append(kwargs["offset"])
            remaining_hits = max(0, 130 - kwargs["offset"])
            page_hits = min(kwargs["limit"], remaining_hits)
            hits = [
                {
                    "id": f"call-{kwargs['offset'] + index}",
                    "start_time": 1772967600 - kwargs["offset"] - index,
                    "index_name": kwargs["index_name"],
                }
                for index in range(page_hits)
            ]
            return {
                "index_name": kwargs["index_name"],
                "estimated_total_hits": 130,
                "filter": kwargs["filters"],
                "hits": hits,
                "offset": kwargs["offset"],
                "limit": kwargs["limit"],
            }

        with patch(
            "app.ai.scanner_chat_web._get_index_names_for_scope",
            return_value=["calls_2026_03"],
        ), patch(
            "app.ai.scanner_chat_web._search_index_page",
            side_effect=fake_search_index_page,
        ):
            response = _search_transcripts_for_scope(
                SearchScope(
                    query="shots fired",
                    refinementList={"short_name": ["chi_cpd"]},
                    maxHits=120,
                )
            )

        self.assertEqual([0, 50, 100], offsets)
        self.assertEqual(120, response["examined_hits"])
        self.assertEqual(130, response["estimated_total_hits"])
        self.assertTrue(response["truncated"])
        self.assertEqual(120, len(response["hits"]))

    def test_search_transcripts_for_scope_honors_default_cap(self):
        offsets: list[int] = []

        def fake_search_index_page(**kwargs):
            offsets.append(kwargs["offset"])
            hits = [
                {
                    "id": f"call-{kwargs['offset'] + index}",
                    "start_time": 1772967600 - kwargs["offset"] - index,
                    "index_name": kwargs["index_name"],
                }
                for index in range(kwargs["limit"])
            ]
            return {
                "index_name": kwargs["index_name"],
                "estimated_total_hits": DEFAULT_MAX_ANALYSIS_HITS + 60,
                "filter": kwargs["filters"],
                "hits": hits,
                "offset": kwargs["offset"],
                "limit": kwargs["limit"],
            }

        with patch.dict("os.environ", {}, clear=False), patch(
            "app.ai.scanner_chat_web._get_index_names_for_scope",
            return_value=["calls_2026_03"],
        ), patch(
            "app.ai.scanner_chat_web._search_index_page",
            side_effect=fake_search_index_page,
        ):
            response = _search_transcripts_for_scope(SearchScope(query="shots fired"))

        self.assertEqual([0, 50, 100, 150], offsets)
        self.assertEqual(DEFAULT_MAX_ANALYSIS_HITS, response["examined_hits"])
        self.assertTrue(response["truncated"])

    def test_error_app_reports_unhealthy(self):
        app = _build_error_app("missing config")
        client = TestClient(app)
        health = client.get("/api/health")
        self.assertEqual(503, health.status_code)
        self.assertIn("missing config", health.json()["detail"])
