"""Tests for `AnalyzeVisualUseCase` (Step 5) using fake ports — no ffmpeg,
no Ollama involved."""
from __future__ import annotations

from pathlib import Path

from pipeline.application.visual_analysis.analyze_visual import AnalyzeVisualUseCase
from pipeline.domain.videos.visual_note import VisualNote, VisualNotes


class _FakeFrameExtractor:
    def __init__(self, frames: list[Path]) -> None:
        self._frames = frames
        self.calls: list[tuple] = []

    def extract_frames(self, video, out_dir, interval_seconds):
        self.calls.append((video, out_dir, interval_seconds))
        for f in self._frames:
            f.write_bytes(b"jpg")
        return self._frames


class _FakeVisionProvider:
    def __init__(self, descriptions: dict[str, str] | None = None, raise_for: set[str] | None = None):
        self._descriptions = descriptions or {}
        self._raise_for = raise_for or set()
        self.calls: list[tuple] = []

    def describe(self, frame: Path, model: str) -> str:
        self.calls.append((frame, model))
        if frame.name in self._raise_for:
            raise RuntimeError("boom")
        return self._descriptions.get(frame.name, f"desc-{frame.name}")


def test_execute_builds_visual_notes_and_writes_markdown(tmp_path):
    frame_dir = tmp_path / "frames_src"
    frame_dir.mkdir()
    frames = [frame_dir / "frame_00001.jpg", frame_dir / "frame_00002.jpg"]

    extractor = _FakeFrameExtractor(frames)
    provider = _FakeVisionProvider({"frame_00001.jpg": "primero", "frame_00002.jpg": "segundo"})
    use_case = AnalyzeVisualUseCase(extractor, provider)

    result = use_case.execute(tmp_path / "video.mp4", tmp_path, "gemma4:e4b", 15)

    expected = VisualNotes(
        notes=(
            VisualNote(timestamp_seconds=0, description="primero"),
            VisualNote(timestamp_seconds=15, description="segundo"),
        )
    )
    assert result == expected
    assert (tmp_path / "visual_notes.md").read_text(encoding="utf-8") == expected.to_markdown()
    assert provider.calls[0][1] == "gemma4:e4b"


def test_execute_returns_none_when_zero_frames_extracted(tmp_path):
    extractor = _FakeFrameExtractor([])
    provider = _FakeVisionProvider()
    use_case = AnalyzeVisualUseCase(extractor, provider)

    result = use_case.execute(tmp_path / "video.mp4", tmp_path, "gemma4:e4b", 15)

    assert result is None
    assert not (tmp_path / "visual_notes.md").exists()


def test_execute_returns_none_when_notes_already_exist(tmp_path):
    (tmp_path / "visual_notes.md").write_text("### [00:00:00]\nya existe\n", encoding="utf-8")
    extractor = _FakeFrameExtractor([tmp_path / "frame_00001.jpg"])
    provider = _FakeVisionProvider()
    use_case = AnalyzeVisualUseCase(extractor, provider)

    result = use_case.execute(tmp_path / "video.mp4", tmp_path, "gemma4:e4b", 15)

    assert result is None
    assert extractor.calls == []  # skip happens before frame extraction


def test_execute_swallows_per_frame_description_errors_into_placeholder(tmp_path):
    frame_dir = tmp_path / "frames_src"
    frame_dir.mkdir()
    frames = [frame_dir / "frame_00001.jpg"]
    extractor = _FakeFrameExtractor(frames)
    provider = _FakeVisionProvider(raise_for={"frame_00001.jpg"})
    use_case = AnalyzeVisualUseCase(extractor, provider)

    result = use_case.execute(tmp_path / "video.mp4", tmp_path, "gemma4:e4b", 15)

    assert result is not None
    assert result.notes[0].description == "(error analizando frame: boom)"
