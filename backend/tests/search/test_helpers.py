import unittest

from app.search.helpers import flatten_dict, encode_params


class TestFlattenDict(unittest.TestCase):
    def test_flat_dict_is_unchanged(self):
        d = {"a": 1, "b": "hello"}
        result = flatten_dict(d)
        self.assertEqual({"a": 1, "b": "hello"}, result)

    def test_nested_dict_is_flattened(self):
        d = {"outer": {"inner": "value"}}
        result = flatten_dict(d)
        self.assertIn("outer[inner]", result)
        self.assertEqual("value", result["outer[inner]"])

    def test_nested_list_is_flattened_with_indices(self):
        d = {"outer": {"items": ["a", "b"]}}
        result = flatten_dict(d)
        self.assertIn("outer[items][0]", result)
        self.assertIn("outer[items][1]", result)
        self.assertEqual("a", result["outer[items][0]"])
        self.assertEqual("b", result["outer[items][1]"])

    def test_deeply_nested_dict(self):
        d = {"a": {"b": {"c": "deep"}}}
        result = flatten_dict(d)
        self.assertIn("a[b][c]", result)
        self.assertEqual("deep", result["a[b][c]"])

    def test_empty_dict(self):
        result = flatten_dict({})
        self.assertEqual({}, result)

    def test_meilisearch_style_params(self):
        """Regression test matching the shape used by build_search_url."""
        params = {
            "calls": {
                "sortBy": "calls:start_time:desc",
                "refinementList": {"talkgroup_tag": ["Tag1"]},
            }
        }
        result = flatten_dict(params)
        self.assertIn("calls[sortBy]", result)
        self.assertEqual("calls:start_time:desc", result["calls[sortBy]"])
        self.assertIn("calls[refinementList][talkgroup_tag][0]", result)
        self.assertEqual("Tag1", result["calls[refinementList][talkgroup_tag][0]"])


class TestEncodeParams(unittest.TestCase):
    def test_encodes_simple_dict(self):
        params = {"q": "fire", "page": 1}
        result = encode_params(params)
        self.assertIn("q=fire", result)
        self.assertIn("page=1", result)

    def test_encodes_nested_dict(self):
        params = {"filter": {"talkgroup": 100}}
        result = encode_params(params)
        self.assertIn("filter%5Btalkgroup%5D=100", result)

    def test_produces_non_empty_string_for_search_url_params(self):
        params = {
            "calls": {
                "sortBy": "calls:start_time:desc",
                "hitsPerPage": 60,
                "refinementList": {"talkgroup_tag": ["CFD Fire N"]},
                "range": {"start_time": "1609459200:1609459800"},
            }
        }
        result = encode_params(params)
        self.assertIsInstance(result, str)
        self.assertGreater(len(result), 0)


if __name__ == "__main__":
    unittest.main()
