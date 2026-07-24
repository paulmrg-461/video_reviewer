"""Tests for `FfmpegAudioExtractor` (Step 5) — verifies the 3-strategy
fallback logic and the RuntimeError-on-total-failure contract, using a fake
`subprocess.run` that never actually shells out to ffmpeg."""
from __future__ import annotations

from pathlib import Path

import pytest

from pipeline.infrastructure.transcription import ffmpeg_audio_extractor as mod
from pipeline.infrastructure.transcription.ffmpeg_audio_extractor import (
    FfmpegAudioExtractor,
)


def test_extract_succeeds_on_first_strategy(monkeypatch, tmp_path):
    wav = tmp_path / "audio.wav"
    calls = []

    def fake_run(cmd, capture_output, text):
        calls.append(cmd)
        wav.write_bytes(b"0" * 20_000)  # usable-sized output
        return None

    monkeypatch.setattr(mod.subprocess, "run", fake_run)

    FfmpegAudioExtractor().extract(tmp_path / "video.mp4", wav)

    assert len(calls) == 1  # only the primary strategy ran
    assert calls[0][0] == "ffmpeg"
    assert "pcm_s16le" in calls[0]


def test_extract_falls_back_to_aac_reencode_when_primary_fails(monkeypatch, tmp_path):
    wav = tmp_path / "audio.wav"
    call_count = {"n": 0}

    def fake_run(cmd, capture_output, text):
        call_count["n"] += 1
        if call_count["n"] == 1:
            pass  # primary strategy: produces nothing usable
        elif "-c:a" in cmd and "aac" in cmd:
            # write to whatever tmp .m4a path was requested (last arg)
            Path(cmd[-1]).write_bytes(b"0" * 5000)
        else:
            # second ffmpeg pass, re-encoding the m4a into the final wav
            wav.write_bytes(b"0" * 20_000)
        return None

    monkeypatch.setattr(mod.subprocess, "run", fake_run)

    FfmpegAudioExtractor().extract(tmp_path / "video.mp4", wav)

    assert call_count["n"] == 3
    assert wav.exists() and wav.stat().st_size >= 16_000


def test_extract_raises_runtime_error_on_total_failure(monkeypatch, tmp_path):
    wav = tmp_path / "audio.wav"

    def fake_run(cmd, capture_output, text):
        return None  # never produces any usable output

    monkeypatch.setattr(mod.subprocess, "run", fake_run)

    with pytest.raises(RuntimeError):
        FfmpegAudioExtractor().extract(tmp_path / "video.mp4", wav)
