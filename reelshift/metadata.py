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
    with urlopen(req, timeout=12) as response:
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
        # TVmaze returns a whole show's episode list in one API request,
        # avoiding repeated HTTP calls and rate limiting for season batches.
        self.tvmaze_episode_lists: dict[int, dict[tuple[int, int], str]] = {}
        # Exposed to the GUI. Never include API keys or raw request URLs.
        self.last_diagnostic = ""
        self.diagnostics: dict[tuple[str, int, int], str] = {}
        self.tmdb_error: str | None = None
        self.tvmaze_error: str | None = None

    @staticmethod
    def _error_message(provider: str, exc: Exception) -> str:
        if isinstance(exc, HTTPError):
            if exc.code == 401:
                return f"{provider}: HTTP 401 – API-Schlüssel ungültig"
            if exc.code == 403:
                return f"{provider}: HTTP 403 – Zugriff verweigert"
            if exc.code == 429:
                return f"{provider}: HTTP 429 – Anfragelimit erreicht"
            return f"{provider}: HTTP {exc.code}"
        if isinstance(exc, (URLError, TimeoutError)):
            return f"{provider}: Netzwerk-/DNS-/TLS-Fehler oder Zeitüberschreitung"
        return f"{provider}: ungültige API-Antwort ({type(exc).__name__})"

    def find(self, series: str, season: int, episode: int) -> tuple[str, str] | None:
        key = (series.casefold(), season, episode)
        if key in self.cache:
            self.last_diagnostic = self.diagnostics.get(key, "")
            return self.cache[key]
        errors: list[str] = []
        result = None
        if self.tmdb_token:
            if self.tmdb_error:
                errors.append(self.tmdb_error)
            else:
                try:
                    result = self._tmdb(series, season, episode)
                except (HTTPError, URLError, TimeoutError, ValueError, KeyError, TypeError) as exc:
                    self.tmdb_error = self._error_message("TMDb", exc)
                    errors.append(self.tmdb_error)
        if not result:
            if self.tvmaze_error:
                errors.append(self.tvmaze_error)
            else:
                try:
                    result = self._tvmaze(series, season, episode)
                except (HTTPError, URLError, TimeoutError, ValueError, KeyError, TypeError) as exc:
                    self.tvmaze_error = self._error_message("TVmaze", exc)
                    errors.append(self.tvmaze_error)
        if result:
            self.last_diagnostic = ""
        elif errors:
            self.last_diagnostic = " | ".join(errors)
        else:
            self.last_diagnostic = f"Kein passender Episodentitel gefunden ({series} S{season:02d}E{episode:02d})"
        self.diagnostics[key] = self.last_diagnostic
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
        if show_id not in self.tvmaze_episode_lists:
            episodes = _get(f"{base}/shows/{show_id}/episodes", {})
            self.tvmaze_episode_lists[show_id] = {
                (entry["season"], entry["number"]): entry["name"].strip()
                for entry in episodes
                if isinstance(entry.get("season"), int)
                and isinstance(entry.get("number"), int)
                and isinstance(entry.get("name"), str)
                and entry["name"].strip()
            }
        title = self.tvmaze_episode_lists[show_id].get((season, episode))
        return (title, "TVmaze (meist Englisch)") if title else None
