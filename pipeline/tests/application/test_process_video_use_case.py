"""Tests for `ProcessVideoUseCase` (Step 6) — the direct replacement for
`pipeline/server.py`'s `_process_video`. Fakes for `VideoRepository`, the 3
processing use cases, and `GpuResourceScheduler`; no ffmpeg/faster-whisper/
Ollama involved.
"""
from __future__ import annotations

import asyncio

from pipeline.application.processing.process_video import ProcessVideoUseCase
from pipeline.domain.sessions.session import SessionId
from pipeline.domain.videos.analysis import AnalysisResult, Summary
from pipeline.domain.videos.transcript import Segment, Transcript
from pipeline.domain.videos.value_objects import ProcessingOptions, VideoId
from pipeline.domain.videos.video import ProcessingStatus, Video
from pipeline.domain.videos.visual_note import VisualNote, VisualNotes


class FakeVideoRepository:
    def __init__(self) -> None:
        self.videos: dict[tuple[str, str], Video] = {}
        self.updated: list[Video] = []
        # `video` is mutated in place (its `.status` is reassigned, not
        # copied), so appending the same object to `self.updated` on every
        # call and reading `.status` back afterwards would only ever show
        # the FINAL status for every entry. Snapshot the (immutable) enum
        # value at call time instead, to assert the actual sequence of
        # transitions the use case persisted.
        self.updated_statuses: list[ProcessingStatus] = []

    async def add(self, video: Video) -> None:
        self.videos[(video.session_id, video.id.value)] = video

    async def get(self, session_id: SessionId, video_id: VideoId) -> Video | None:
        return self.videos.get((session_id.value, video_id.value))

    async def update(self, video: Video) -> bool:
        self.videos[(video.session_id, video.id.value)] = video
        self.updated.append(video)
        self.updated_statuses.append(video.status)
        return True

    async def remove(self, session_id: SessionId, video_id: VideoId) -> bool:
        raise NotImplementedError

    async def list_by_session(self, session_id: SessionId) -> list[Video]:
        raise NotImplementedError


class FakeTranscribeUseCase:
    def __init__(self, transcript: Transcript | None) -> None:
        self._transcript = transcript
        self.calls: list[tuple] = []

    def execute(self, video, out_dir, model_name, device, compute_type, language):
        self.calls.append((video, out_dir, model_name, device, compute_type, language))
        return self._transcript


class FakeAnalyzeVisualUseCase:
    def __init__(self, notes: VisualNotes | None, exc: Exception | None = None) -> None:
        self._notes = notes
        self._exc = exc
        self.calls: list[tuple] = []

    def execute(self, video, out_dir, vision_model, interval_seconds):
        self.calls.append((video, out_dir, vision_model, interval_seconds))
        if self._exc is not None:
            raise self._exc
        return self._notes


class FakeSummarizeUseCase:
    def __init__(self, result) -> None:
        self._result = result
        self.calls: list[tuple] = []

    def execute(self, out_dir, model, transcript, visual_notes, video_name, instructions):
        self.calls.append((out_dir, model, transcript, visual_notes, video_name, instructions))
        return self._result


class FakeGpuScheduler:
    def __init__(self) -> None:
        self.released: list[str] = []

    def release(self, model_name: str) -> None:
        self.released.append(model_name)


def _make_video(tmp_path, analyze_visual: bool = False) -> Video:
    original = tmp_path / "clip.mp4"
    original.write_bytes(b"data")
    return Video.new_from_upload(
        id=VideoId("vid-1"),
        session_id="sess-1",
        name="clip.mp4",
        original_path=str(original),
        options=ProcessingOptions(language="es", analyze_visual=analyze_visual),
        instructions="be thorough",
    )


def _sample_transcript() -> Transcript:
    return Transcript(segments=(Segment(0.0, 1.0, "hola"),), language="es")


def _task(analyze_visual: bool = False) -> dict:
    return {
        "session_id": "sess-1",
        "video_id": "vid-1",
        "instructions": "be thorough",
        "language": "es",
        "analyze_visual": analyze_visual,
    }


# --- Happy paths ---


def test_full_happy_path_without_visual_analysis(tmp_path) -> None:
    repo = FakeVideoRepository()
    asyncio.run(repo.add(_make_video(tmp_path)))

    transcript = _sample_transcript()
    summary = Summary(content="s\n")
    analysis = AnalysisResult(content="a\n")

    transcribe = FakeTranscribeUseCase(transcript)
    visual = FakeAnalyzeVisualUseCase(None)
    summarize = FakeSummarizeUseCase((summary, analysis))
    gpu = FakeGpuScheduler()

    use_case = ProcessVideoUseCase(
        repo, transcribe, visual, summarize, gpu, tmp_path / "sessions"
    )
    asyncio.run(use_case.execute(_task()))

    result = repo.videos[("sess-1", "vid-1")]
    assert result.status == ProcessingStatus.DONE
    assert result.transcript == transcript
    assert result.summary == summary
    assert result.analysis == analysis
    assert visual.calls == []  # analyze_visual=False -> never invoked

    statuses = repo.updated_statuses
    assert statuses == [
        ProcessingStatus.EXTRACTING_AUDIO,
        ProcessingStatus.TRANSCRIBING,
        ProcessingStatus.SUMMARIZING,
        ProcessingStatus.DONE,
    ]
    # llm_model released before transcribing, and again right before
    # mark_done — matches today's `_process_video` sequencing.
    assert gpu.released == ["qwen2.5:14b", "qwen2.5:14b"]

    out_dir = tmp_path / "sessions" / "sess-1" / "vid-1"
    assert (out_dir / "instructions.txt").read_text() == "be thorough"


def test_full_happy_path_with_visual_analysis(tmp_path) -> None:
    repo = FakeVideoRepository()
    asyncio.run(repo.add(_make_video(tmp_path, analyze_visual=True)))

    transcript = _sample_transcript()
    notes = VisualNotes(notes=(VisualNote(0, "algo en pantalla"),))
    summary = Summary(content="s\n")
    analysis = AnalysisResult(content="a\n")

    transcribe = FakeTranscribeUseCase(transcript)
    visual = FakeAnalyzeVisualUseCase(notes)
    summarize = FakeSummarizeUseCase((summary, analysis))
    gpu = FakeGpuScheduler()

    use_case = ProcessVideoUseCase(
        repo, transcribe, visual, summarize, gpu, tmp_path / "sessions"
    )
    asyncio.run(use_case.execute(_task(analyze_visual=True)))

    result = repo.videos[("sess-1", "vid-1")]
    assert result.status == ProcessingStatus.DONE
    assert result.visual_notes == notes
    assert len(visual.calls) == 1

    statuses = repo.updated_statuses
    assert statuses == [
        ProcessingStatus.EXTRACTING_AUDIO,
        ProcessingStatus.TRANSCRIBING,
        ProcessingStatus.ANALYZING_VISUAL,
        ProcessingStatus.SUMMARIZING,
        ProcessingStatus.DONE,
    ]
    # llm_model released before transcribing, again (redundant, but
    # preserved for fidelity) right before visual analysis, vision_model
    # released after visual analysis, llm_model released once more right
    # before mark_done.
    assert gpu.released == ["qwen2.5:14b", "qwen2.5:14b", "gemma4:e4b", "qwen2.5:14b"]


# --- Missing source file ---


def test_missing_source_file_marks_error_and_attempts_nothing_further(tmp_path) -> None:
    repo = FakeVideoRepository()
    video = Video.new_from_upload(
        id=VideoId("vid-1"),
        session_id="sess-1",
        name="clip.mp4",
        original_path=str(tmp_path / "does_not_exist.mp4"),
        options=ProcessingOptions(),
        instructions="x",
    )
    asyncio.run(repo.add(video))

    transcribe = FakeTranscribeUseCase(_sample_transcript())
    visual = FakeAnalyzeVisualUseCase(None)
    summarize = FakeSummarizeUseCase((Summary("s"), AnalysisResult("a")))
    gpu = FakeGpuScheduler()

    use_case = ProcessVideoUseCase(
        repo, transcribe, visual, summarize, gpu, tmp_path / "sessions"
    )
    asyncio.run(use_case.execute(_task()))

    result = repo.videos[("sess-1", "vid-1")]
    assert result.status == ProcessingStatus.ERROR
    assert "no encontrado" in result.error
    assert transcribe.calls == []
    assert gpu.released == []
    assert len(repo.updated) == 1  # only the mark_error persist


# --- Exception mid-pipeline ---


def test_exception_mid_pipeline_marks_video_error(tmp_path) -> None:
    repo = FakeVideoRepository()
    asyncio.run(repo.add(_make_video(tmp_path, analyze_visual=True)))

    transcribe = FakeTranscribeUseCase(_sample_transcript())
    visual = FakeAnalyzeVisualUseCase(None, exc=RuntimeError("boom"))
    summarize = FakeSummarizeUseCase((Summary("s"), AnalysisResult("a")))
    gpu = FakeGpuScheduler()

    use_case = ProcessVideoUseCase(
        repo, transcribe, visual, summarize, gpu, tmp_path / "sessions"
    )
    asyncio.run(use_case.execute(_task(analyze_visual=True)))

    result = repo.videos[("sess-1", "vid-1")]
    assert result.status == ProcessingStatus.ERROR
    assert result.error == "boom"
    assert result.transcript is not None  # transcribed before the failure
    assert repo.updated[-1].status == ProcessingStatus.ERROR
    assert summarize.calls == []  # never reached


# --- Skip-if-exists (transcribe/summarize return None) -> read from disk ---


def test_skip_if_exists_reads_transcript_and_summary_from_disk(tmp_path) -> None:
    """When the injected use cases return `None` (idempotent skip because
    output files already exist), `ProcessVideoUseCase` must read
    `transcript.txt`/`summary.md`/`analysis.md` back from disk rather than
    passing `None` into `mark_transcribed`/`mark_done` (both of which
    require real objects for later domain-invariant checks)."""
    repo = FakeVideoRepository()
    asyncio.run(repo.add(_make_video(tmp_path)))

    out_dir = tmp_path / "sessions" / "sess-1" / "vid-1"
    out_dir.mkdir(parents=True)
    (out_dir / "transcript.txt").write_text("contenido ya transcrito\n", encoding="utf-8")
    (out_dir / "summary.md").write_text("# Resumen ya existente\n", encoding="utf-8")
    (out_dir / "analysis.md").write_text("# Analisis ya existente\n", encoding="utf-8")

    transcribe = FakeTranscribeUseCase(None)  # simulates skip-if-exists
    visual = FakeAnalyzeVisualUseCase(None)
    summarize = FakeSummarizeUseCase(None)  # simulates skip-if-exists
    gpu = FakeGpuScheduler()

    use_case = ProcessVideoUseCase(
        repo, transcribe, visual, summarize, gpu, tmp_path / "sessions"
    )
    asyncio.run(use_case.execute(_task()))

    result = repo.videos[("sess-1", "vid-1")]
    assert result.status == ProcessingStatus.DONE
    assert result.transcript is not None
    assert result.transcript.plain_text() == "contenido ya transcrito\n"
    assert result.summary.content == "# Resumen ya existente\n"
    assert result.analysis.content == "# Analisis ya existente\n"
