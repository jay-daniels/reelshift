"""Optional online episode-title lookup (TMDb German, TVmaze fallback)."""
from __future__ import annotations

import json
import re
from difflib import SequenceMatcher
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


def _get(url: str, params: dict, token: str = "") -> object:
    qs = urlencode(params)
    headers = {"Accept": "application/json", "User-Agent": "ReelShift/0.1 (personal media manager)"}
    if token:
        if token.startswith("eyJ"):
            headers["Authorization"] = f"Bearer {token}"
        else:
            qs += "&" + urlencode({"api_key": token})
    req = Request(url + ("?" + qs if qs else ""), headers=headers)
    with urlopen(req, timeout=7) as response:
        return json.load(response)


def _normalize(name: str) -> str:
    return re.sub(r"[^a-z0-9]", "", name.casefold())


def _best(query: str, candidates: list[tuple[str, int]]) -> int | None:
    if not candidates:
        return None
    ranked = sorted(((SequenceMatcher(None, _normalize(query), _normalize(name)).ratio(), ident)
                     for name, ident in candidates), reverse=True)
    return ranked[0][1] if ranked[0][0] >= .76 else None


class EpisodeLookup:
    def __init__(self, tmdb_token: str = "") -> None:
        self.tmdb_token = tmdb_token.strip()
        self.cache: dict[tuple[str, int, int], tuple[str, str] | None] = {}
        self.tvmaze_shows: dict[str, int | None] = {}
        self.tmdb_shows: dict[str, int | None] = {}

    def find(self, series: str, season: int, episode: int) -> tuple[str, str] | None:
        key = (series.casefold(), season, episode)
        if key in self.cache:
            return self.cache[key]
        result = None
        if self.tmdb_token:
            try:
                result = self._tmdb(series, season, episode)
            except (HTTPError, URLError, TimeoutError, ValueError, KeyError):
                pass
        if not result:
            try:
                result = self._tvmaze(series, season, episode)
            except (HTTPError, URLError, TimeoutError, ValueError, KeyError):
                pass
        self.cache[key] = result
        return result

    def _tmdb(self, series: str, season: int, episode: int) -> tuple[str, str] | None:
        base = "https://api.themoviedb.org/3"
        if series not in self.tmdb_shows:
            shows = _get(base + "/search/tv", {"query": series, "language": "de-DE"}, self.tmdb_token)
            self.tmdb_shows[series] = _best(series, [
                (entry.get("name") or entry.get("original_name") or "", entry["id"])
                for entry in shows.get("results", [])[:12]
            ])
        show_id = self.tmdb_shows[series]
        if show_id is None:
            return None
        entry = _get(f"{base}/tv/{show_id}/season/{season}/episode/{episode}",
                     {"language": "de-DE"}, self.tmdb_token)
        title = (entry.get("name") or "").strip()
        # TMDb sometimes returns generic placeholders or original-language titles.
        if title and not re.fullmatch(r"(?i)episode\s+\d+|folge\s+\d+", title):
            return title, "TMDb (de-DE, sofern verfügbar)"
        return None

    def _tvmaze(self, series: str, season: int, episode: int) -> tuple[str, str] | None:
        base = "https://api.tvmaze.com"
        if series not in self.tvmaze_shows:
            matches = _get(base + "/search/shows", {"q": series})
            self.tvmaze_shows[series] = _best(series, [
                (entry["show"].get("name", ""), entry["show"]["id"])
                for entry in matches[:10]
            ])
        show_id = self.tvmaze_shows[series]
        if show_id is None:
            return None
        entry = _get(f"{base}/shows/{show_id}/episodebynumber",
                     {"season": season, "number": episode})
        title = (entry.get("name") or "").strip()
        return (title, "TVmaze (meist Englisch)") if title else None
