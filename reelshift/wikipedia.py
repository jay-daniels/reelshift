"""German TV episode titles via the public MediaWiki API (no signup, no API key).

Results are suggestions with source attribution. Wikipedia articles have
inconsistent table formats; ambiguous/unrecognised tables never produce titles.
"""
from __future__ import annotations

import html
import json
import re
from html.parser import HTMLParser
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from .catalog_de import VIKINGS_2013_GERMAN

API = "https://de.wikipedia.org/w/api.php"
USER_AGENT = "ReelShift/0.4 (https://github.com/jay-daniels/reelshift)"
SEASON = re.compile(r"\bStaffel\s+(\d{1,2})\b", re.I)


def _request(params: dict) -> dict:
    url = API + "?" + urlencode({"format": "json", "formatversion": "2", **params})
    with urlopen(Request(url, headers={
        "User-Agent": USER_AGENT,
        "Accept": "application/json",
    }), timeout=12) as response:
        return json.load(response)


def _norm(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", value.casefold())


class EpisodeTableReader(HTMLParser):
    """Read common German Wikipedia episode-list tables, scoped by 'Staffel N'.

    The wiki table convention is: overall no., season no., German title,
    original title, other columns. Reject unrelated tables by requiring the
    actual header labels and two numeric first columns.
    """
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.episodes: dict[tuple[int, int], str] = {}
        self.season: int | None = None
        self.heading: list[str] | None = None
        self.table_depth = 0
        self.row: list[tuple[str, str]] | None = None
        self.cell: list[str] | None = None
        self.cell_tag = ""
        self.header_confirmed = False
        self.header_buffer: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in ("h2", "h3"):
            self.heading = []
        elif tag == "table":
            if self.season is not None or self.table_depth:
                self.table_depth += 1
                if self.table_depth == 1:
                    self.header_confirmed = False
                    self.header_buffer = []
        elif self.table_depth == 1:
            if tag == "tr":
                self.row = []
            elif tag in ("td", "th") and self.row is not None:
                self.cell = []
                self.cell_tag = tag

    def handle_data(self, data: str) -> None:
        if self.heading is not None:
            self.heading.append(data)
        if self.cell is not None:
            self.cell.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag in ("h2", "h3") and self.heading is not None:
            match = SEASON.search(" ".join(self.heading))
            self.season = int(match.group(1)) if match else None
            self.heading = None
        elif tag in ("td", "th") and self.table_depth == 1 and self.cell is not None:
            clean = re.sub(r"\s+", " ", "".join(self.cell)).strip()
            if self.row is not None:
                self.row.append((self.cell_tag, clean))
            self.cell = None
        elif tag == "tr" and self.table_depth == 1 and self.row is not None:
            self._parse_row(self.row)
            self.row = None
        elif tag == "table" and self.table_depth:
            self.table_depth -= 1

    def _parse_row(self, cells: list[tuple[str, str]]) -> None:
        if self.season is None or len(cells) < 3:
            return
        labels = [value.casefold().replace("\u00ad", "") for _, value in cells]
        if any("deutscher titel" in label for label in labels):
            self.header_confirmed = True
            return
        # No guesswork on title-less tables; the column order must be known.
        if not self.header_confirmed:
            return
        if not (re.fullmatch(r"\d{1,3}", cells[0][1])
                and re.fullmatch(r"\d{1,3}", cells[1][1])):
            return
        ep = int(cells[1][1])
        title = html.unescape(cells[2][1]).strip(" \"'„“”")
        if ep < 1 or ep > 200 or len(title) < 2 or len(title) > 160:
            return
        if re.fullmatch(r"(?:Folge|Episode)\s+\d+", title, flags=re.I):
            return
        self.episodes[(self.season, ep)] = title


def parse_episode_tables(page_html: str) -> dict[tuple[int, int], str]:
    parser = EpisodeTableReader()
    parser.feed(page_html)
    parser.close()
    return parser.episodes


class WikipediaGermanLookup:
    def __init__(self) -> None:
        self.series_cache: dict[str, dict[tuple[int, int], str]] = {}
        self.page_cache: dict[str, str] = {}
        self.last_error = ""
        self.last_page = ""

    def _get_page(self, title: str) -> dict[tuple[int, int], str]:
        response = _request({"action": "parse", "page": title, "prop": "text"})
        if "error" in response:
            return {}
        data = response.get("parse", {})
        markup = data.get("text", "")
        if isinstance(markup, dict):
            markup = markup.get("*", "")
        if not markup:
            return {}
        return parse_episode_tables(markup)

    def _search_pages(self, series: str) -> list[str]:
        response = _request({
            "action": "query", "list": "search",
            "srsearch": f'intitle:"{series}" Episodenliste',
            "srnamespace": "0", "srlimit": "10",
        })
        result: list[str] = []
        normalized = _norm(series)
        for match in response.get("query", {}).get("search", []):
            title = str(match.get("title", ""))
            if not title.casefold().endswith("/episodenliste"):
                continue
            name = title.split("/", 1)[0]
            name = re.sub(r"\s*\(Fernsehserie\)$", "", name, flags=re.I)
            # Require exact base title to avoid Vikings: Valhalla collisions.
            if _norm(name) == normalized and title not in result:
                result.append(title)
        return result

    def find(self, series: str, season: int, episode: int) -> tuple[str, str] | None:
        key = series.casefold()
        # Reliable offline data for the exact show in the initial ReelShift use-case.
        # These are the 2013 drama titles; the 2012 documentary/Valhalla are distinct.
        if key == "vikings":
            names = VIKINGS_2013_GERMAN.get(str(season), [])
            if 1 <= episode <= len(names):
                self.last_error = ""
                self.last_page = "Vikings (Fernsehserie)/Episodenliste"
                return names[episode - 1], "Wikipedia DE (Offline-Katalog)"

        if key not in self.series_cache:
            self.last_error = ""
            variants = [
                f"{series} (Fernsehserie)/Episodenliste",
                f"{series}/Episodenliste",
            ]
            episodes: dict[tuple[int, int], str] = {}
            errors: list[str] = []
            for candidate in variants:
                try:
                    episodes = self._get_page(candidate)
                except (HTTPError, URLError, TimeoutError, ValueError, KeyError, TypeError) as exc:
                    errors.append(f"{type(exc).__name__}: {str(exc)[:80]}")
                if episodes:
                    self.last_page = candidate
                    break
            if not episodes:
                try:
                    for candidate in self._search_pages(series):
                        if candidate in variants:
                            continue
                        episodes = self._get_page(candidate)
                        if episodes:
                            self.last_page = candidate
                            break
                except (HTTPError, URLError, TimeoutError, ValueError, KeyError, TypeError) as exc:
                    errors.append(f"{type(exc).__name__}: {str(exc)[:80]}")
            self.series_cache[key] = episodes
            if not episodes:
                self.last_error = (
                    "Wikipedia DE: keine geeignete deutsche Episodenliste gefunden"
                    + (f"; API: {errors[0]}" if errors else "")
                )
        name = self.series_cache[key].get((season, episode))
        if not name:
            if self.series_cache[key]:
                self.last_error = (
                    f"Wikipedia DE: kein Titel für {series} S{season:02d}E{episode:02d}; "
                    "evtl. abweichende Episodenreihenfolge"
                )
            return None
        self.last_error = ""
        return name, "Wikipedia DE (ohne Key)"
