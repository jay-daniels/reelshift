"""Regression: stream.start_time can look healthy despite a 60-second video gap."""
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from reelshift.engine import (
    DecodeStartInfo, av_sync_report, probe_av_sync,
    probe_decode_start, validate_decode_start,
)


class DecodeStartupTests(unittest.TestCase):
    def test_unchanged_first_decoded_frame(self):
        before = DecodeStartInfo(0.04, True, 0.0)
        after = DecodeStartInfo(0.06, True, 0.02)
        self.assertTrue(validate_decode_start(before, after)[0])

    def test_60_second_delay_rejected(self):
        before = DecodeStartInfo(0, True, 0)
        after = DecodeStartInfo(60, True, 0)
        self.assertFalse(validate_decode_start(before, after)[0])

    def test_missing_first_frame_rejected(self):
        before = DecodeStartInfo(0, True, 0)
        self.assertFalse(validate_decode_start(before, DecodeStartInfo(None, False, 0))[0])

    def test_non_keyframe_rejected(self):
        self.assertFalse(validate_decode_start(DecodeStartInfo(0, True, 0),
                                               DecodeStartInfo(0, False, 0))[0])

    def test_video_only_media_is_valid(self):
        self.assertTrue(validate_decode_start(DecodeStartInfo(0, True, None),
                                              DecodeStartInfo(0, True, None))[0])

    @unittest.skipUnless(shutil.which("ffmpeg") and shutil.which("ffprobe"), "ffmpeg not installed")
    def test_real_delayed_video_has_same_stream_start_time_but_bad_first_frame(self):
        with tempfile.TemporaryDirectory() as d:
            delayed = Path(d) / "delayed.mkv"
            good = Path(d) / "normal.mkv"
            common = ["ffmpeg", "-nostdin", "-hide_banner", "-loglevel", "error", "-y"]
            src = ["-f", "lavfi", "-i", "sine=frequency=500:sample_rate=48000:duration=64",
                   "-f", "lavfi", "-i", "testsrc2=size=160x90:rate=25:duration=3",
                   "-map", "1:v:0", "-map", "0:a:0", "-c:v", "libx264",
                   "-preset", "ultrafast", "-pix_fmt", "yuv420p", "-threads", "2",
                   "-c:a", "aac", "-shortest"]
            for output, delayed_video in [(good, False), (delayed, True)]:
                args = common + (src[:4] + ["-itsoffset", "60"] + src[4:]
                                 if delayed_video else src) + [str(output)]
                result = subprocess.run(args, capture_output=True, text=True, timeout=45)
                self.assertEqual(result.returncode, 0, result.stderr)
            before = probe_av_sync(good, "ffprobe")
            after = probe_av_sync(delayed, "ffprobe")
            # The old metadata check passes, even with a 60-second video gap.
            self.assertTrue(av_sync_report(before, after)[0], f"{before} -> {after}")
            good_start = probe_decode_start(good, "ffprobe")
            late_start = probe_decode_start(delayed, "ffprobe")
            self.assertLess(abs(good_start.video_audio_gap), 1)
            self.assertGreater(late_start.video_audio_gap, 59)
            self.assertFalse(validate_decode_start(good_start, late_start)[0])


if __name__ == "__main__":
    unittest.main()
