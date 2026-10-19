"""No-key German Wikipedia metadata and safe, validated episode-table parsing."""
import unittest
from unittest.mock import patch

from reelshift.catalog_de import VIKINGS_2013_GERMAN
from reelshift.wikipedia import WikipediaGermanLookup, parse_episode_tables
from reelshift.metadata import EpisodeLookup


WIKIPEDIA_HTML = """
<h2><span>Staffel 1</span></h2>
<table class="wikitable">
<tr><th>Nr. (ges.)</th><th>Nr. (St.)</th><th>Deutscher Titel</th><th>Originaltitel</th></tr>
<tr><td>1</td><td>1</td><td>Der Anfang</td><td>Start</td></tr>
</table>
<h2><span>Staffel 2</span></h2>
<table class="wikitable">
<tr><th>Nr. (ges.)</th><th>Nr. (St.)</th><th>Deutscher Titel</th><th>Originaltitel</th></tr>
<tr><th>10</th><th>1</th><td>Bruderkrieg</td><td>Brother’s War</td></tr>
<tr><th>11</th><th>2</th><td>Invasion</td><td>Invasion</td></tr>
</table>
<h2>Einzelnachweise</h2>
<table><tr><td>12</td><td>3</td><td>Fake</td></tr></table>
"""


class GermanWikiTests(unittest.TestCase):
    def test_extract_episode_columns_per_season(self):
        episodes = parse_episode_tables(WIKIPEDIA_HTML)
        self.assertEqual(episodes, {
            (1, 1): "Der Anfang", (2, 1): "Bruderkrieg", (2, 2): "Invasion"
        })
        self.assertNotIn((2, 3), episodes)

    def test_reject_unlabelled_table(self):
        self.assertFalse(parse_episode_tables(
            '<h2>Staffel 2</h2><table><tr><td>10</td><td>1</td><td>DO NOT TRUST</td></tr></table>'
        ))

    def test_vikings_2013_all_89_titles_available_without_network(self):
        self.assertEqual({int(k): len(v) for k, v in VIKINGS_2013_GERMAN.items()},
                         {1: 9, 2: 10, 3: 10, 4: 20, 5: 20, 6: 20})
        with patch("reelshift.wikipedia._request") as api:
            resolver = WikipediaGermanLookup()
            self.assertEqual(resolver.find("Vikings", 2, 1),
                             ("Bruderkrieg", "Wikipedia DE (Offline-Katalog)"))
            self.assertEqual(resolver.find("Vikings", 2, 7)[0], "Blutadler")
            self.assertEqual(resolver.find("Vikings", 6, 20)[0], "Die Neue Welt")
            api.assert_not_called()

    def test_generic_series_mediawiki_parse_without_key(self):
        lookup = WikipediaGermanLookup()
        def remote(params):
            self.assertEqual(params["action"], "parse")
            self.assertIn("Testserie", params["page"])
            return {"parse": {"text": WIKIPEDIA_HTML}}
        with patch("reelshift.wikipedia._request", side_effect=remote) as http:
            self.assertEqual(lookup.find("Testserie", 2, 1),
                             ("Bruderkrieg", "Wikipedia DE (ohne Key)"))
            self.assertEqual(lookup.find("Testserie", 2, 2)[0], "Invasion")
            self.assertEqual(http.call_count, 1)

    def test_missing_wikipedia_episode_does_not_guess(self):
        lookup = WikipediaGermanLookup()
        with patch("reelshift.wikipedia._request", return_value={
            "parse": {"text": WIKIPEDIA_HTML}
        }):
            self.assertIsNone(lookup.find("Testserie", 2, 99))
        self.assertIn("S02E99", lookup.last_error)

    def test_episode_lookup_falls_back_to_tmdb_only_when_configured(self):
        resolver = EpisodeLookup(language="de")
        resolver.wikipedia.find = lambda *args: None
        with patch("reelshift.metadata._get") as network:
            self.assertIsNone(resolver.find("Testserie", 2, 1))
            network.assert_not_called()


if __name__ == "__main__":
    unittest.main()
