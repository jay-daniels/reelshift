"""Metadata regressions: duplicate Vikings shows and explicit language selection."""
import unittest
from unittest.mock import patch
from urllib.error import URLError

from reelshift.metadata import EpisodeLookup, _best
from reelshift.naming import output_name, parse_name


class MetadataLookupTests(unittest.TestCase):
    def test_vikings_release_triggers_lookup(self):
        parsed = parse_name("Vikings.S02E01.German.AC3.DL.1080p.BluRay.x265-FuN.mkv")
        self.assertEqual((parsed.series, parsed.season, parsed.episode, parsed.title),
                         ("Vikings", 2, 1, ""))

    def test_duplicate_names_prefer_provider_order_not_higher_numeric_id(self):
        # TVmaze's first result is drama Vikings (2013), ID 29;
        # next exact title is BBC documentary Vikings (2012), ID 1335.
        self.assertEqual(_best("Vikings", [("Vikings", 29), ("Vikings", 1335)]), 29)

    def test_vikings_duplicate_search_result_gets_correct_episode(self):
        def api(url, params, token=""):
            if url.endswith("/search/shows"):
                return [
                    {"score": 0.89, "show": {"name": "Vikings", "id": 29,
                                              "premiered": "2013-03-03"}},
                    {"score": 0.87, "show": {"name": "Vikings", "id": 1335,
                                              "premiered": "2012-09-11"}},
                ]
            if url.endswith("/shows/29/episodes"):
                return [{"season": 2, "number": 1, "name": "Brother's War"},
                        {"season": 2, "number": 2, "name": "Invasion"}]
            raise AssertionError(f"Incorrect series chosen: {url}")
        with patch("reelshift.metadata._get", side_effect=api) as get:
            resolver = EpisodeLookup(language="en")
            self.assertEqual(resolver.find("Vikings", 2, 1)[0], "Brother's War")
            self.assertEqual(resolver.find("Vikings", 2, 2)[0], "Invasion")
            self.assertIn("TVmaze #29", resolver.chosen_series["Vikings"])
            self.assertEqual(get.call_count, 2)

    def test_tvmaze_without_token_works_for_english(self):
        def api(url, params, token=""):
            self.assertEqual(token, "")
            if url.endswith("/search/shows"):
                self.assertEqual(params, {"q": "Vikings"})
                return [{"show": {"name": "Vikings", "id": 29}}]
            if url.endswith("/shows/29/episodes"):
                return [{"season": 2, "number": 1, "name": "Brother's War"},
                        {"season": 2, "number": 2, "name": "Invasion"}]
            raise AssertionError(url)
        with patch("reelshift.metadata._get", side_effect=api) as get:
            resolver = EpisodeLookup(language="en")
            self.assertEqual(resolver.find("Vikings", 2, 1),
                             ("Brother's War", "TVmaze (meist Englisch)"))
            self.assertEqual(resolver.find("Vikings", 2, 2)[0], "Invasion")
            self.assertEqual(get.call_count, 2)

    def test_german_without_token_shows_clear_error_and_does_not_replace_with_english(self):
        with patch("reelshift.metadata._get") as network:
            resolver = EpisodeLookup(language="de")
            self.assertIsNone(resolver.find("Vikings", 2, 1))
            self.assertIn("TMDb-API-Key fehlt", resolver.last_diagnostic)
            self.assertIsNone(resolver.find("Vikings", 2, 2))
            network.assert_not_called()

    def test_german_tmdb_returns_translated_episodes_in_single_season_request(self):
        def api(url, params, token=""):
            self.assertEqual(token, "test-token")
            self.assertEqual(params.get("language"), "de-DE")
            if url.endswith("/search/tv"):
                return {"results": [{"name": "Vikings", "id": 44217}]}
            if url.endswith("/tv/44217/season/2"):
                return {"episodes": [
                    {"episode_number": 1, "name": "Bruderkrieg"},
                    {"episode_number": 2, "name": "Invasion"},
                ]}
            raise AssertionError(url)
        with patch("reelshift.metadata._get", side_effect=api) as get:
            resolver = EpisodeLookup("test-token", language="de")
            self.assertEqual(resolver.find("Vikings", 2, 1),
                             ("Bruderkrieg", "TMDb (de-DE, sofern übersetzt)"))
            self.assertEqual(resolver.find("Vikings", 2, 2)[0], "Invasion")
            self.assertEqual(get.call_count, 2)

    def test_german_tmdb_failure_does_not_silently_fallback_to_english(self):
        resolver = EpisodeLookup("test-token", language="de")
        with patch("reelshift.metadata._get", side_effect=URLError("offline")) as get:
            self.assertIsNone(resolver.find("Vikings", 2, 1))
            self.assertIn("TMDb: Netzwerk", resolver.last_diagnostic)
            self.assertIsNone(resolver.find("Vikings", 2, 2))
            self.assertEqual(get.call_count, 1)

    def test_english_ignores_tmdb_key(self):
        resolver = EpisodeLookup("even-if-configured", language="en")
        with patch("reelshift.metadata._get", side_effect=[
            [{"show": {"name": "Vikings", "id": 29}}],
            [{"season": 2, "number": 1, "name": "Brother's War"}],
        ]):
            self.assertEqual(resolver.find("Vikings", 2, 1)[0], "Brother's War")

    def test_api_network_error_is_reported_once_per_scan(self):
        resolver = EpisodeLookup(language="en")
        with patch("reelshift.metadata._get", side_effect=URLError("offline")) as get:
            self.assertIsNone(resolver.find("Vikings", 2, 1))
            self.assertIn("TVmaze:", resolver.last_diagnostic)
            self.assertIsNone(resolver.find("Vikings", 2, 2))
            self.assertEqual(get.call_count, 1)

    def test_missing_episode_has_clear_diagnostic(self):
        resolver = EpisodeLookup(language="en")
        with patch("reelshift.metadata._get", side_effect=[
            [{"show": {"name": "Vikings", "id": 29}}],
            [{"season": 2, "number": 1, "name": "Brother's War"}],
        ]):
            self.assertIsNone(resolver.find("Vikings", 2, 99))
        self.assertIn("S02E99", resolver.last_diagnostic)

    def test_fetched_title_forms_valid_output_name(self):
        parsed = parse_name("Vikings.S02E01.German.AC3.DL.1080p.BluRay.x265-FuN.mkv")
        self.assertEqual(output_name(parsed, "Bruderkrieg"), "Vikings - S02E01 - Bruderkrieg.mkv")


if __name__ == "__main__":
    unittest.main()
