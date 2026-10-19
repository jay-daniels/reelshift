"""Offline lookup regression tests: TVmaze works without a token, errors are visible."""
import unittest
from unittest.mock import patch
from urllib.error import URLError

from reelshift.metadata import EpisodeLookup
from reelshift.naming import output_name, parse_name


class MetadataLookupTests(unittest.TestCase):
    def test_vikings_release_triggers_lookup(self):
        parsed = parse_name("Vikings.S02E01.German.AC3.DL.1080p.BluRay.x265-FuN.mkv")
        self.assertEqual((parsed.series, parsed.season, parsed.episode, parsed.title),
                         ("Vikings", 2, 1, ""))

    def test_tvmaze_without_token_fetches_full_season_in_two_requests(self):
        def api(url, params, token=""):
            self.assertEqual(token, "")
            if url.endswith("/search/shows"):
                self.assertEqual(params, {"q": "Vikings"})
                return [{"show": {"name": "Vikings", "id": 29}}]
            if url.endswith("/shows/29/episodes"):
                return [
                    {"season": 2, "number": 1, "name": "Brother's War"},
                    {"season": 2, "number": 2, "name": "Invasion"},
                ]
            raise AssertionError(url)

        resolver = EpisodeLookup()
        with patch("reelshift.metadata._get", side_effect=api) as get:
            self.assertEqual(resolver.find("Vikings", 2, 1),
                             ("Brother's War", "TVmaze (meist Englisch)"))
            self.assertEqual(resolver.find("Vikings", 2, 2),
                             ("Invasion", "TVmaze (meist Englisch)"))
            self.assertEqual(get.call_count, 2)
        self.assertEqual(resolver.last_diagnostic, "")

    def test_api_network_error_is_reported_and_not_repeated_for_same_scan(self):
        resolver = EpisodeLookup()
        with patch("reelshift.metadata._get", side_effect=URLError("network offline")) as get:
            self.assertIsNone(resolver.find("Vikings", 2, 1))
            self.assertIn("TVmaze:", resolver.last_diagnostic)
            self.assertIn("Netzwerk", resolver.last_diagnostic)
            self.assertIsNone(resolver.find("Vikings", 2, 2))
            self.assertEqual(get.call_count, 1)

    def test_missing_episode_has_clear_diagnostic(self):
        resolver = EpisodeLookup()
        with patch("reelshift.metadata._get", side_effect=[
            [{"show": {"name": "Vikings", "id": 29}}],
            [{"season": 2, "number": 1, "name": "Brother's War"}],
        ]):
            self.assertIsNone(resolver.find("Vikings", 2, 99))
        self.assertIn("S02E99", resolver.last_diagnostic)

    def test_tmdb_failure_falls_back_to_tvmaze(self):
        resolver = EpisodeLookup("invalid_test_key")
        def api(url, params, token=""):
            if "themoviedb.org" in url:
                raise URLError("temporary error")
            if url.endswith("/search/shows"):
                return [{"show": {"name": "Vikings", "id": 29}}]
            if url.endswith("/shows/29/episodes"):
                return [{"season": 2, "number": 1, "name": "Brother's War"}]
            raise AssertionError(url)
        with patch("reelshift.metadata._get", side_effect=api):
            self.assertEqual(resolver.find("Vikings", 2, 1)[0], "Brother's War")
        self.assertEqual(resolver.last_diagnostic, "")

    def test_fetched_title_is_valid_output_name(self):
        parsed = parse_name("Vikings.S02E01.German.AC3.DL.1080p.BluRay.x265-FuN.mkv")
        self.assertEqual(output_name(parsed, "Brother's War"),
                         "Vikings - S02E01 - Brother's War.mkv")


if __name__ == "__main__":
    unittest.main()
