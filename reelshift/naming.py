"""Deterministic, offline release-name parsing and Windows-safe filenames."""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

EPISODE = re.compile(r"(?i)(?<!\w)S(?P<season>\d{1,2})[ ._-]*E(?P<episode>\d{1,3})(?!\d)|(?<!\w)(?P<s2>\d{1,2})x(?P<e2>\d{1,3})(?!\d)")
# A release tag is a boundary, not a word to remove anywhere in a real title.
TAGS = re.compile(
    r"(?i)(?<!\w)(?:2160p|1080p|720p|480p|4k|uhd|bluray|blu-ray|bdrip|brrip|"
    r"web[- .]?dl|webrip|hdtv|remux|dvdrip|x265|h265|hevc|x264|h264|avc|"
    r"german|english|multi|dl|dts(?:-hd)?|ac-?3|e-?ac-?3|ddp?5[ .]?1|"
    r"aac|truehd|atmos|hdr10?\+?|hdr|dv|dolby[ .]?vision|proper|repack|"
    r"internal|extended|uncut|limited|10bit|8bit|nf|amzn)(?!\w)"
)
INVALID = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
RESERVED = re.compile(r"(?i)^(?:CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])(?:\..*)?$")


@dataclass(frozen=True)
class EpisodeName:
    series: str
    season: int | None = None
    episode: int | None = None
    title: str = ""


def clean_piece(value: str) -> str:
    value = value.replace("_", " ").replace(".", " ")
    value = re.sub(r"\s*[-–]+\s*", " - ", value)
    return re.sub(r"\s+", " ", value).strip(" .-–_ ")


def safe_filename(value: str) -> str:
    value = INVALID.sub("", value)
    value = re.sub(r"\s+", " ", value).strip(" .")
    if RESERVED.fullmatch(value):
        value = "_" + value
    return value[:180].rstrip(" .") or "Untitled"


def parse_name(path: str | Path) -> EpisodeName:
    stem = Path(path).stem
    stem = re.sub(r"\[[^\]]*\]", " ", stem)
    match = EPISODE.search(stem)
    if not match:
        cut = TAGS.search(stem)
        return EpisodeName(clean_piece(stem[:cut.start()] if cut else stem))
    series = clean_piece(stem[:match.start()])
    remaining = stem[match.end():]
    cut = TAGS.search(remaining)
    title = clean_piece(remaining[:cut.start()] if cut else remaining)
    # Remove isolated trailing release-group bracket notation if present.
    title = re.sub(r"\s+-\s+[^ ]+$", "", title) if title.count(" - ") > 1 else title
    season = int(match.group("season") or match.group("s2"))
    episode = int(match.group("episode") or match.group("e2"))
    return EpisodeName(series or "Unknown series", season, episode, title)


def output_name(parsed: EpisodeName, title: str | None = None) -> str:
    ep_title = parsed.title if title is None else title
    if parsed.season is None or parsed.episode is None:
        return safe_filename(parsed.series) + ".mkv"
    prefix = f"{parsed.series} - S{parsed.season:02d}E{parsed.episode:02d}"
    if ep_title:
        prefix += " - " + ep_title
    return safe_filename(prefix) + ".mkv"
