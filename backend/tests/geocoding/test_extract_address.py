import unittest

from app.geocoding.geocoding import extract_address, contains_address


class TestExtractAddress(unittest.TestCase):
    def test_extracts_street_number_and_name(self):
        # The regex captures the street name token including "Central", and
        # "Avenue" is a separate word that the regex captures as the street name.
        result = extract_address("responding to 333 North Central Avenue")
        self.assertEqual("333 North Central Avenue", result)

    def test_extracts_intersection(self):
        result = extract_address("incident at Clinton and Jackson")
        self.assertEqual("Clinton and Jackson", result)

    def test_returns_none_when_no_address_found(self):
        result = extract_address("no address here just radio chatter")
        self.assertIsNone(result)

    def test_strips_punctuation_from_address(self):
        result = extract_address("located at 3,000 West Madison Street")
        self.assertIsNotNone(result)
        self.assertNotIn(",", result)

    def test_extracts_address_with_cardinal_direction(self):
        result = extract_address("unit on scene 45 South Wabash")
        self.assertEqual("45 South Wabash", result)

    def test_returns_none_for_empty_string(self):
        result = extract_address("")
        self.assertIsNone(result)

    def test_case_insensitive_via_flag(self):
        result_ci = extract_address("333 north central", ignore_case=True)
        result_cs = extract_address("333 north central", ignore_case=False)
        # With ignore_case=True it should find it; case-sensitive may differ
        self.assertIsNotNone(result_ci)
        # Both should produce the same result when pattern matches
        if result_cs:
            self.assertEqual(result_ci, result_cs)

    def test_extracts_address_with_block_of(self):
        result = extract_address("unit at 1800 block of North Western")
        self.assertIsNotNone(result)


class TestContainsAddress(unittest.TestCase):
    def test_returns_true_for_street_address(self):
        self.assertTrue(contains_address("333 North Central Avenue"))

    def test_returns_true_for_street_suffix_only(self):
        self.assertTrue(contains_address("come to Western and Lake Street"))

    def test_returns_true_for_cardinal_direction(self):
        self.assertTrue(contains_address("heading north on the expressway"))

    def test_returns_true_for_block_of(self):
        self.assertTrue(contains_address("in the 1800 block of Main"))

    def test_returns_true_for_intersection_keyword(self):
        self.assertTrue(contains_address("at the intersection of Clark and Division"))

    def test_returns_false_for_plain_radio_chatter(self):
        self.assertFalse(contains_address("copy that, all units stand by"))

    def test_returns_true_for_avenue(self):
        self.assertTrue(contains_address("proceed to Michigan Avenue"))

    def test_returns_true_for_boulevard(self):
        self.assertTrue(contains_address("squad heading to Wacker Boulevard"))


if __name__ == "__main__":
    unittest.main()
