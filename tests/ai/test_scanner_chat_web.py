from unittest import TestCase
from unittest.mock import patch

from fastapi.testclient import TestClient

from app.ai.scanner_chat_web import (
    _build_error_app,
    _index_guidance,
    _normalize_model_name,
)


class TestScannerChatWebHelpers(TestCase):
    def test_normalize_model_name_adds_openai_prefix(self):
        self.assertEqual("openai:gpt-4o-mini", _normalize_model_name("gpt-4o-mini"))

    def test_normalize_model_name_keeps_provider(self):
        self.assertEqual("google-gla:gemini-2.5-flash", _normalize_model_name("google-gla:gemini-2.5-flash"))

    def test_index_guidance_for_monthly_indexes(self):
        with patch.dict(
            "os.environ",
            {"MEILI_INDEX": "calls", "MEILI_INDEX_SPLIT_BY_MONTH": "true"},
            clear=False,
        ):
            guidance = _index_guidance()
        self.assertIn("calls_YYYY_MM", guidance)

    def test_error_app_reports_unhealthy(self):
        app = _build_error_app("missing config")
        client = TestClient(app)
        health = client.get("/api/health")
        self.assertEqual(503, health.status_code)
        self.assertIn("missing config", health.json()["detail"])
