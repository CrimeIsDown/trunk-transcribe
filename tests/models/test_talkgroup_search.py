import datetime as dt
import unittest

from app.models.models import get_talkgroups


class _FakeResult:
    def fetchall(self):
        return []


class _FakeDb:
    def __init__(self):
        self.statement = None
        self.params = None

    def execute(self, statement, params):
        self.statement = statement
        self.params = params
        return _FakeResult()


class TestTalkgroupSearch(unittest.TestCase):
    def test_get_talkgroups_uses_full_text_search_vector(self):
        db = _FakeDb()
        start_datetime = dt.datetime(2026, 3, 8, 10, 0, tzinfo=dt.timezone.utc)
        end_datetime = dt.datetime(2026, 3, 8, 11, 0, tzinfo=dt.timezone.utc)

        get_talkgroups(
            db,
            radio_system="chi_cpd",
            start_datetime=start_datetime,
            end_datetime=end_datetime,
            search_query="cpd zone 1",
            limit=25,
        )

        statement = str(db.statement)
        self.assertIn("search_vector @@ websearch_to_tsquery('simple', :search_query)", statement)
        self.assertNotIn("ILIKE", statement)
        self.assertEqual("cpd zone 1", db.params["search_query"])
        self.assertEqual("chi_cpd", db.params["radio_system"])
        self.assertEqual(25, db.params["limit"])


if __name__ == "__main__":
    unittest.main()
