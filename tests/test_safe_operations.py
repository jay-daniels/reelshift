"""Regression tests for A/V start offsets and safe rename-only planning."""
from __future__ import annotations

import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from reelshift.engine import (AVSyncInfo, VideoItem, av_sync_report, ffmpeg_command,
                              inspect_video, probe_av_sync, rename_conflicts, scan_paths)
from reelshift.naming import EpisodeName


def item(source: Path, name: str) -> VideoItem:
    return VideoItem(source, name, "hevc", 10, EpisodeName("Vikings"))


class RenameSafetyTests(unittest.TestCase):
    def test_in_place_rename_does_not_change_media(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            source = root / "Vikings.S01E01.x265.mkv"
            source.write_bytes(b"Original MKV bytes must not be touched")
            desired = "Vikings - S01E01.mkv"
            self.assertEqual(rename_conflicts([item(source, desired)]), [])
            self.assertEqual(scan_paths(root, "Vikings*", False), [source])
            source.rename(source.with_name(desired))
            self.assertEqual((root / desired).read_bytes(), b"Original MKV bytes must not be touched")

    def test_conflict_never_overwrites(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            source, target = root / "bad.mkv", root / "Episode.mkv"
            source.write_bytes(b"first")
            target.write_bytes(b"second")
            self.assertTrue(rename_conflicts([item(source, target.name)]))
            self.assertEqual(source.read_bytes(), b"first")
            self.assertEqual(target.read_bytes(), b"second")

    def test_duplicate_target_case_insensitive(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            a, b = root / "E01.a.mkv", root / "E02.b.mkv"
            a.touch(); b.touch()
            self.assertTrue(rename_conflicts([item(a, "Episode.mkv"), item(b, "episode.mkv")]))

    def test_same_name_separate_folders(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            a, b = root / "S1" / "old.mkv", root / "S2" / "old.mkv"
            a.parent.mkdir(); b.parent.mkdir()
            a.touch(); b.touch()
            self.assertEqual(rename_conflicts([item(a, "Episode.mkv"), item(b, "Episode.mkv")]), [])

    def test_preexisting_case_insensitive_conflict(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            source = root / "Old.mkv"
            source.touch()
            (root / "episode.mkv").touch()
            self.assertTrue(rename_conflicts([item(source, "Episode.mkv")]))


class SyncTests(unittest.TestCase):
    def test_offsets_preserved(self):
        self.assertTrue(av_sync_report(AVSyncInfo(0, (0.25,)), AVSyncInfo(1, (1.25,)))[0])

    def test_new_offset_rejected(self):
        ok, description = av_sync_report(AVSyncInfo(0, (0.0,)), AVSyncInfo(0, (0.4,)))
        self.assertFalse(ok)
        self.assertIn("400 ms", description)

    def test_audio_stream_count_must_match(self):
        before = AVSyncInfo(0.0, (0.0, 0.12))
        self.assertTrue(av_sync_report(before, AVSyncInfo(0.0, (0.0, 0.12)))[0])
        self.assertFalse(av_sync_report(before, AVSyncInfo(0, (0,)))[0])

    def test_codec_commands_do_not_fake_audio_offset(self):
        cmd = ffmpeg_command("ffmpeg", item(Path("source.mkv"), "target.mkv"),
                             Path("out.mkv"), False, 22, False)
        self.assertIn("-fps_mode:v:0", cmd)
        self.assertIn("passthrough", cmd)
        self.assertIn("-bf:v:0", cmd)
        self.assertIn("-avoid_negative_ts", cmd)
        self.assertNotIn("-itsoffset", cmd)

    @unittest.skipUnless(shutil.which("ffmpeg") and shutil.which("ffprobe"), "FFmpeg not installed")
    def test_real_hevc_ac3_to_h264_preserves_audio_start(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            source, target = root / "Sample.S01E01.mkv", root / "encoded.mkv"
            cmd = ["ffmpeg", "-nostdin", "-hide_banner", "-loglevel", "error", "-y",
                   "-f", "lavfi", "-i", "testsrc2=size=256x144:rate=25:duration=2",
                   "-itsoffset", "0.25", "-f", "lavfi",
                   "-i", "sine=duration=1.5:sample_rate=48000",
                   "-map", "0:v", "-map", "1:a", "-c:v", "libx265",
                   "-preset", "ultrafast", "-x265-params", "log-level=error:pools=1",
                   "-threads", "2", "-c:a", "ac3", "-b:a", "192k", str(source)]
            make = subprocess.run(cmd, capture_output=True, text=True, timeout=40)
            if make.returncode:
                self.skipTest("Required FFmpeg test encoders missing: " + make.stderr[-180:])
            video = inspect_video(source, "ffprobe")
            encode = subprocess.run(ffmpeg_command("ffmpeg", video, target, False, 22, False),
                                    capture_output=True, text=True, timeout=40)
            self.assertEqual(encode.returncode, 0, encode.stderr)
            before = probe_av_sync(source, "ffprobe")
            after = probe_av_sync(target, "ffprobe")
            self.assertTrue(av_sync_report(before, after)[0], f"{before} vs {after}")


if __name__ == "__main__":
    unittest.main()
