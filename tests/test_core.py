import tempfile
import unittest
from pathlib import Path

from reelshift.engine import VideoItem, ffmpeg_command, ffmpeg_seconds, needs_video_encode, scan_paths
from reelshift.naming import EpisodeName, output_name, parse_name, safe_filename


class NameTests(unittest.TestCase):
    def test_vikings(self):
        name = "Vikings.-.S01E01.-.Initiationsriten.German.AC3.DL.1080p.BluRay.x265-FuN.mkv"
        self.assertEqual(output_name(parse_name(name)), "Vikings - S01E01 - Initiationsriten.mkv")

    def test_missing_episode_title(self):
        self.assertEqual(output_name(parse_name("Vikings.S02E04.1080p.BluRay.x265.mkv")),
                         "Vikings - S02E04.mkv")

    def test_alternative_episode(self):
        self.assertEqual(output_name(parse_name("The.Show.2x03.Hello.World.WEB-DL.mkv")),
                         "The Show - S02E03 - Hello World.mkv")

    def test_windows_invalid_characters(self):
        self.assertEqual(safe_filename('A: \\"B?*'), 'A B')
        self.assertEqual(safe_filename("CON"), "_CON")


class FFmpegTests(unittest.TestCase):
    def test_progress_microseconds(self):
        self.assertEqual(ffmpeg_seconds({"out_time_ms": "12345000"}), 12.345)
        self.assertEqual(ffmpeg_seconds({"out_time": "01:01:01.50"}), 3661.5)

    def test_copy_or_reencode(self):
        item = VideoItem(Path("input.mkv"), "out.mkv", "h264", 10, EpisodeName("show"), "yuv420p", "High")
        self.assertFalse(needs_video_encode(item))
        cmd = ffmpeg_command("ffmpeg", item, Path("output.mkv"), True, 22, False)
        self.assertNotIn("h264_nvenc", cmd)
        item.codec = "hevc"
        self.assertTrue(needs_video_encode(item))
        cmd = ffmpeg_command("ffmpeg", item, Path("output.mkv"), True, 22, True)
        self.assertIn("h264_nvenc", cmd)
        self.assertIn("aac", cmd)

    def test_scan_wildcards_and_output_exclusion(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            out = root / "output"
            out.mkdir()
            (root / "Vikings.S01E01.mkv").touch()
            (root / "Other.mkv").touch()
            (out / "Vikings.S01E02.mkv").touch()
            self.assertEqual(len(scan_paths(root, "Vikings*", True, out)), 1)


if __name__ == "__main__":
    unittest.main()
