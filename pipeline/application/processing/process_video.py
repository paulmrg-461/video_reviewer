"""Use case: process one queued video end-to-end (extract audio, transcribe,
optionally analyze visually, summarize).

Direct replacement for `pipeline/server.py`'s `_process_video()`. Faithfully
reproduces that function's exact sequencing (see the Step 6 migration spec)
but drives the domain `Video` object's guarded lifecycle methods instead of
raw dict mutation, and delegates real work to the injected use cases/
`GpuResourceScheduler` instead of the old module-level helper functions
(`_run_transcribe`/`_liberar_ollama`/`_run_summarize`/`_run_visual`).

Progress emission (`_emit_progress`) is NOT ported here — it was dead code
(nothing read `progress_data`/`progress_events`; the `/api/progress` SSE
endpoint independently polls `store.list_sessions()` every second). The
`video_repo.update(video)` calls below are what actually make each stage
transition visible to that polling loop, and are kept at every step
`_process_video` persisted at.
"""
from __future__ import annotations

import asyncio
import os
import traceback
from pathlib import Path

from pipeline.application.gpu.ports import GpuResourceScheduler
from pipeline.application.summarization.summarize_video import SummarizeVideoUseCase
from pipeline.application.transcription.transcribe_video import TranscribeVideoUseCase
from pipeline.application.videos.ports import VideoRepository
from pipeline.application.visual_analysis.analyze_visual import AnalyzeVisualUseCase
from pipeline.domain.sessions.session import SessionId
from pipeline.domain.videos.analysis import AnalysisResult, Summary
from pipeline.domain.videos.transcript import Segment, Transcript
from pipeline.domain.videos.value_objects import VideoId
from pipeline.domain.videos.video import Video


def _read_transcript_from_disk(out_dir: Path) -> Transcript:
    """Reconstructs a `Transcript` whose `.plain_text()`/`.to_srt()` are
    consistent with the already-written `transcript.txt` on disk, for the
    idempotent skip-if-exists path: `TranscribeVideoUseCase.execute()`
    returns `None` (not the transcript) when both `transcript.txt`/
    `transcript.srt` already exist, but `Video.mark_transcribed()` needs a
    real `Transcript` object so that later `start_visual_analysis()`/
    `start_summarizing()` calls (which raise `ValueError` if
    `video.transcript is None`) stay legal.

    Mirrors `pipeline/summarize.py`'s shim-level `_read_transcript` helper
    (Step 5): `Transcript.plain_text()` is a free-form
    `"\\n".join(seg.text for seg in segments) + "\\n"` join, so a single
    `Segment` whose text is the file's content (minus its one trailing
    "\\n") round-trips `.plain_text()` byte-for-byte regardless of the
    original whisper segment boundaries — those per-segment boundaries
    aren't needed downstream (only the joined text is consumed by the
    summarization map-reduce step)."""
    content = (out_dir / "transcript.txt").read_text(encoding="utf-8")
    text = content[:-1] if content.endswith("\n") else content
    return Transcript(segments=(Segment(start=0.0, end=0.0, text=text),), language="")


def _read_summary_and_analysis_from_disk(out_dir: Path) -> tuple[Summary, AnalysisResult]:
    """Reconstructs `Summary`/`AnalysisResult` from `summary.md`/
    `analysis.md` on disk, for the idempotent skip-if-exists path:
    `SummarizeVideoUseCase.execute()` returns `None` when both files already
    exist, but `Video.mark_done()` needs real objects. Unlike the transcript
    case, no round-trip trick is needed — both value objects are a direct
    `content: str` wrapper, so the file's raw text is the exact value."""
    summary = Summary(content=(out_dir / "summary.md").read_text(encoding="utf-8"))
    analysis = AnalysisResult(content=(out_dir / "analysis.md").read_text(encoding="utf-8"))
    return summary, analysis


class ProcessVideoUseCase:
    def __init__(
        self,
        video_repo: VideoRepository,
        transcribe_use_case: TranscribeVideoUseCase,
        analyze_visual_use_case: AnalyzeVisualUseCase,
        summarize_use_case: SummarizeVideoUseCase,
        gpu_scheduler: GpuResourceScheduler,
        sessions_root: Path,
    ) -> None:
        self._video_repo = video_repo
        self._transcribe_use_case = transcribe_use_case
        self._analyze_visual_use_case = analyze_visual_use_case
        self._summarize_use_case = summarize_use_case
        self._gpu_scheduler = gpu_scheduler
        self._sessions_root = sessions_root

    async def execute(self, task: dict) -> None:
        session_id = task["session_id"]
        video_id = task["video_id"]
        loop = asyncio.get_running_loop()

        video: Video | None = None
        try:
            video = await self._video_repo.get(SessionId(session_id), VideoId(video_id))
            if video is None:
                # Video vanished (e.g. session/video deleted) between
                # enqueue and dequeue — matches today's silent no-op.
                return

            video_path = Path(video.original_path)
            if not video_path.exists():
                video.mark_error(f"Archivo no encontrado: {video_path}")
                await self._video_repo.update(video)
                return

            video.start_extracting_audio()
            await self._video_repo.update(video)

            out_dir = self._sessions_root / session_id / video_id
            out_dir.mkdir(parents=True, exist_ok=True)

            instructions = video.instructions or task.get("instructions") or ""
            (out_dir / "instructions.txt").write_text(instructions)

            whisper_model = task.get("whisper_model", "large-v3")
            device = task.get("device", "cuda")
            compute_type = task.get("compute_type", "int8_float16")
            llm_model = task.get("llm_model", "qwen2.5:14b")
            vision_model = task.get("vision_model", "gemma4:e4b")
            frame_interval = task.get("frame_interval") or int(
                os.environ.get("VISUAL_FRAME_INTERVAL_SEG", "15")
            )
            language = video.options.language
            analyze_visual = bool(video.options.analyze_visual or task.get("analyze_visual"))

            video.start_transcribing()
            await self._video_repo.update(video)

            await loop.run_in_executor(None, self._gpu_scheduler.release, llm_model)
            transcript = await loop.run_in_executor(
                None,
                self._transcribe_use_case.execute,
                video_path,
                out_dir,
                whisper_model,
                device,
                compute_type,
                language,
            )
            if transcript is None:
                # Idempotent skip-if-exists path — see helper docstring.
                transcript = _read_transcript_from_disk(out_dir)
            video.mark_transcribed(transcript)

            visual_notes = None
            if analyze_visual:
                video.start_visual_analysis()
                await self._video_repo.update(video)

                # Same model release call as right before transcribing above
                # — looks redundant (same llm_model, already released) but
                # this reproduces today's actual `_process_video` sequencing
                # verbatim; not removed for fidelity.
                await loop.run_in_executor(None, self._gpu_scheduler.release, llm_model)

                visual_notes = await loop.run_in_executor(
                    None,
                    self._analyze_visual_use_case.execute,
                    video_path,
                    out_dir,
                    vision_model,
                    frame_interval,
                )
                # None is explicitly legal here (matches Video's invariant).
                video.mark_visual_analyzed(visual_notes)
                await loop.run_in_executor(None, self._gpu_scheduler.release, vision_model)

            video.start_summarizing()
            await self._video_repo.update(video)

            result = await loop.run_in_executor(
                None,
                self._summarize_use_case.execute,
                out_dir,
                llm_model,
                transcript,
                visual_notes,
                video.name,
                instructions or None,
            )
            if result is None:
                # Idempotent skip-if-exists path — see helper docstring.
                summary, analysis = _read_summary_and_analysis_from_disk(out_dir)
            else:
                summary, analysis = result

            await loop.run_in_executor(None, self._gpu_scheduler.release, llm_model)

            video.mark_done(summary, analysis, str(out_dir))
            await self._video_repo.update(video)

        except Exception as exc:
            traceback.print_exc()
            if video is not None:
                video.mark_error(str(exc))
                await self._video_repo.update(video)
