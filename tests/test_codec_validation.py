"""Codec health regression tests, including missing H264 codec parameters."""
import json
import subprocess
import unittest
from pathlib import Path
from unittest.mock import patch

from reelshift.engine import (
    DecodeSample, VideoCodecInfo, decode_video_sample, probe_video_codec,
)


class CodecHealthTests(unittest.TestCase):
    def test_h264_stream_with_complete_parameters(self):
        stream = VideoCodecInfo("h264", "High", "yuv420p", 1920, 1080, 40, 43, "")
        self.assertTrue(stream.usable_h264)

    def test_h264_without_profile_or_pixel_format_is_rejected(self):
        stream = VideoCodecInfo("h264", "", "", 1920, 1080, None, None, "")
        self.assertFalse(stream.usable_h264)

    def test_missing_resolution_is_rejected(self):
        stream = VideoCodecInfo("h264", "High", "yuv420p", 0, 0, 40, None, "")
        self.assertFalse(stream.usable_h264)

    def test_noncompatible_pixel_format_is_rejected(self):
        stream = VideoCodecInfo("h264", "High 10", "yuv420p10le", 1920, 1080, 40, None, "")
        self.assertFalse(stream.usable_h264)

    def test_probe_preserves_empty_parameters_for_diagnosis(self):
        fake = subprocess.CompletedProcess(
            args=[], returncode=0,
            stdout=json.dumps({"streams": [{"codec_name": "h264", "width": 1920,
                                            "height": 1080}]}),
            stderr="missing picture in access unit")
        with patch("reelshift.engine.subprocess.run", return_value=fake):
            result = probe_video_codec(Path("output.mkv"), "ffprobe")
        self.assertEqual(result.profile, "")
        self.assertEqual(result.pixel_format, "")
        self.assertIn("missing picture", result.probe_warnings)
        self.assertFalse(result.usable_h264)

    def test_decode_progress_and_error(self):
        fake = subprocess.CompletedProcess(
            args=[], returncode=0,
            stdout="frame=1\nprogress=continue\nframe=300\nprogress=end\n", stderr="")
        with patch("reelshift.engine.subprocess.run", return_value=fake):
            result = decode_video_sample(Path("output.mkv"), "ffmpeg")
        self.assertEqual(result.frames, 300)
        self.assertTrue(result.passed)

        self.assertFalse(DecodeSample(0, "no frames", 0).passed)
        self.assertFalse(DecodeSample(300, "invalid bitstream", 1).passed)


if __name__ == "__main__":
    unittest.main()
