"""Read-only video startup diagnosis. Run: python -m reelshift.diagnose original.mkv converted.mkv"""
from __future__ import annotations

import argparse
from pathlib import Path

from .engine import (
    av_sync_report, executable, inspect_video, probe_av_sync,
    probe_decode_start, validate_decode_start,
)


def explain(path: Path, ffprobe: str) -> tuple[str, object, object]:
    movie = inspect_video(path, ffprobe)
    meta = probe_av_sync(path, ffprobe)
    decode = probe_decode_start(path, ffprobe)
    description = (
        f"Datei: {path}\n"
        f"Codec: {movie.codec}; {movie.profile}; {movie.pix_fmt}; "
        f"Dauer: {movie.duration:.2f}s\n"
        f"Stream-Video-Start: {meta.video_start}\n"
        f"Stream-Audio-Starts: {meta.audio_starts}\n"
        f"Erstes decodierbares Videobild: {decode.video_frame}\n"
        f"Erstes Videobild Keyframe: {decode.video_keyframe}\n"
        f"Erstes Audiopaket: {decode.audio_packet}\n"
        f"Tatsächlicher Anfangs-Abstand Bild minus Ton: {decode.video_audio_gap} s\n"
    )
    return description, meta, decode


def main() -> int:
    parser = argparse.ArgumentParser(
        description="ReelShift: Original gegen konvertierte MKV vergleichen – nur lesen")
    parser.add_argument("original", type=Path)
    parser.add_argument("converted", type=Path)
    parser.add_argument("--ffprobe", help="Pfad zu ffprobe.exe, falls nicht im PATH")
    parser.add_argument("--save", type=Path, help="Bericht als UTF-8-Text speichern")
    args = parser.parse_args()
    try:
        probe = str(args.ffprobe) if args.ffprobe else executable("ffprobe")
        for candidate in (args.original, args.converted):
            if not candidate.is_file():
                parser.error(f"Datei existiert nicht: {candidate}")
        source_text, source_meta, source_decode = explain(args.original, probe)
        result_text, result_meta, result_decode = explain(args.converted, probe)
        meta_ok, meta_msg = av_sync_report(source_meta, result_meta)
        decode_ok, decode_msg = validate_decode_start(source_decode, result_decode)
        report = ("REELSHIFT – NUR-LESEN SYNC-DIAGNOSE\n\n"
                  "ORIGINAL\n" + source_text + "\nAUSGABE\n" + result_text
                  + "\nMETADATEN-CHECK: " + ("OK" if meta_ok else "WARNUNG") + "\n" + meta_msg
                  + "\nECHTER VIDEO-START: " + ("OK" if decode_ok else "WARNUNG") + "\n" + decode_msg + "\n")
        print(report)
        if args.save:
            args.save.write_text(report, encoding="utf-8")
            print(f"Gespeichert: {args.save}")
        return 0 if meta_ok and decode_ok else 2
    except Exception as exc:
        print(f"Diagnose fehlgeschlagen: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
