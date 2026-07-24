"""Tests for `FfmpegFrameExtractor` (Step 5)."""
from __future__ import annotations

from pipeline.infrastructure.visual_analysis import ffmpeg_frame_extractor as mod
from pipeline.infrastructure.visual_analysis.ffmpeg_frame_extractor import (
    FfmpegFrameExtractor,
)


def test_extract_frames_builds_correct_fps_filter_and_returns_sorted_paths(
    monkeypatch, tmp_path
):
    captured = {}

    def fake_run(cmd, capture_output, text):
        captured["cmd"] = cmd
        (tmp_path / "frame_00002.jpg").write_bytes(b"x")
        (tmp_path / "frame_00001.jpg").write_bytes(b"x")
        return None

    monkeypatch.setattr(mod.subprocess, "run", fake_run)

    result = FfmpegFrameExtractor().extract_frames(tmp_path / "video.mp4", tmp_path, 15)

    assert "-vf" in captured["cmd"]
    assert captured["cmd"][captured["cmd"].index("-vf") + 1] == "fps=1/15"
    assert result == [tmp_path / "frame_00001.jpg", tmp_path / "frame_00002.jpg"]


def test_extract_frames_returns_empty_list_when_no_frames_produced(monkeypatch, tmp_path):
    monkeypatch.setattr(mod.subprocess, "run", lambda *a, **k: None)

    result = FfmpegFrameExtractor().extract_frames(tmp_path / "video.mp4", tmp_path, 15)

    assert result == []
