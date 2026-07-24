"""Composition root for the Sessions feature.

Builds exactly ONE `SessionsJsonGateway` instance for the whole
application. The gateway owns the single `asyncio.Lock` guarding
`sessions.json` — a second instance (even pointed at the same file)
would mean two independent locks and reintroduce the concurrent-write
race the lock exists to prevent. `pipeline/server.py` imports `gateway`
from this module (as `store`) rather than constructing its own, so the
not-yet-migrated video/recording routes and the new Sessions use cases
below all serialize through the same lock.

This module must NOT import anything from `pipeline.server` — see
`pipeline.shared.config` for why (circular import avoidance).
"""
from __future__ import annotations

import asyncio

from pipeline.application.gpu.ports import GpuResourceScheduler
from pipeline.application.processing.process_video import ProcessVideoUseCase
from pipeline.application.recording.use_cases import (
    DeleteRecordingFileUseCase,
    StartRecordingUseCase,
    StopRecordingUseCase,
)
from pipeline.application.sessions.use_cases import (
    CreateSessionUseCase,
    DeleteSessionUseCase,
    GetSessionUseCase,
    ListSessionsUseCase,
)
from pipeline.application.summarization.summarize_video import SummarizeVideoUseCase
from pipeline.application.transcription.transcribe_video import TranscribeVideoUseCase
from pipeline.application.videos.use_cases import (
    AddVideosToSessionUseCase,
    DeleteVideoUseCase,
    RetryVideoUseCase,
    SaveArtifactsUseCase,
)
from pipeline.application.visual_analysis.analyze_visual import AnalyzeVisualUseCase
from pipeline.infrastructure.filesystem.filesystem_session_files_cleaner import (
    FilesystemSessionFilesCleaner,
)
from pipeline.infrastructure.gpu.ollama_gpu_scheduler import OllamaGpuScheduler
from pipeline.infrastructure.ollama.ollama_client import OllamaClient
from pipeline.infrastructure.persistence.json.json_session_repository import (
    JsonSessionRepository,
)
from pipeline.infrastructure.persistence.json.json_video_repository import (
    JsonVideoRepository,
)
from pipeline.infrastructure.persistence.json.sessions_json_gateway import (
    SessionsJsonGateway,
)
from pipeline.infrastructure.recording.gpu_screen_recorder_adapter import (
    GpuScreenRecorderAdapter,
)
from pipeline.infrastructure.recording.in_memory_active_recordings_registry import (
    InMemoryActiveRecordingsRegistry,
)
from pipeline.infrastructure.shared.system_clock import SystemClock
from pipeline.infrastructure.shared.uuid_id_provider import UuidIdProvider
from pipeline.infrastructure.summarization.ollama_summarization_provider import (
    OllamaSummarizationProvider,
)
from pipeline.infrastructure.transcription.faster_whisper_provider import (
    FasterWhisperProvider,
)
from pipeline.infrastructure.transcription.ffmpeg_audio_extractor import (
    FfmpegAudioExtractor,
)
from pipeline.infrastructure.visual_analysis.ffmpeg_frame_extractor import (
    FfmpegFrameExtractor,
)
from pipeline.infrastructure.visual_analysis.ollama_vision_provider import (
    OllamaVisionAnalysisProvider,
)
from pipeline.shared.config import ROOT, SESSIONS_FILE

# --- Single shared instances (see module docstring) ---

gateway = SessionsJsonGateway(SESSIONS_FILE)

_session_repo = JsonSessionRepository(gateway)
_video_repo = JsonVideoRepository(gateway)
_id_provider = UuidIdProvider()
_clock = SystemClock()
_sessions_root = ROOT / "sessions"
_files_cleaner = FilesystemSessionFilesCleaner(_sessions_root)

create_session_use_case = CreateSessionUseCase(_session_repo, _id_provider, _clock)
list_sessions_use_case = ListSessionsUseCase(_session_repo)
get_session_use_case = GetSessionUseCase(_session_repo)
delete_session_use_case = DeleteSessionUseCase(_session_repo, _files_cleaner)

# --- Videos feature (Step 4) ---
#
# `DeleteVideoUseCase`/`SaveArtifactsUseCase` need no queue, so they're
# built eagerly like every Sessions use case above.

delete_video_use_case = DeleteVideoUseCase(_video_repo, _sessions_root)
save_artifacts_use_case = SaveArtifactsUseCase(_video_repo, _sessions_root)

# --- Processing queue + worker (Step 6) ---
#
# Plain `asyncio.Queue` — an in-process concurrency primitive, not an
# external-system boundary like the GPU/Ollama/ffmpeg ports above, so it
# gets no `ProcessingQueuePort`/adapter pair: introducing an interface for
# a single always-`asyncio.Queue` implementation with no foreseeable
# second implementation is exactly the kind of ceremony this migration has
# avoided elsewhere (see e.g. `pipeline.infrastructure.persistence.json.
# mappers`'s and `pipeline.domain.videos.video`'s docstrings for the same
# stated principle applied to other seams).
#
# `processing_queue` now exists at module-load time, so
# `AddVideosToSessionUseCase`/`RetryVideoUseCase` (which both need to
# enqueue background work) can be built eagerly too, exactly like every
# other use case in this module — this removes the Step 4 temporary seam
# (`set_enqueue_callable`/`get_add_videos_use_case`/
# `get_retry_video_use_case`) entirely.

processing_queue: asyncio.Queue = asyncio.Queue()

add_videos_use_case = AddVideosToSessionUseCase(
    _video_repo, _id_provider, _sessions_root, processing_queue.put
)
retry_video_use_case = RetryVideoUseCase(_video_repo, processing_queue.put)

# --- Recording feature (Step 7) ---
#
# Wired eagerly at module-load time, exactly like every other use case in
# this module — same precedent as the Videos use cases just above (no
# deferred seam, `gateway`/`_video_repo`/`_id_provider`/`_clock`/
# `_sessions_root`/`processing_queue.put` all already exist here).
#
# `ScreenRecorderPort` and `ActiveRecordingsRegistry` get real
# infrastructure adapters (`GpuScreenRecorderAdapter`,
# `InMemoryActiveRecordingsRegistry`) rather than being folded into
# existing instances above — they're genuinely new concerns, not
# alternate implementations of `_video_repo`/`gateway`/etc.

_screen_recorder = GpuScreenRecorderAdapter()
active_recordings_registry = InMemoryActiveRecordingsRegistry()

start_recording_use_case = StartRecordingUseCase(
    _screen_recorder, active_recordings_registry, gateway, _id_provider, _clock, _sessions_root
)
stop_recording_use_case = StopRecordingUseCase(
    _screen_recorder,
    active_recordings_registry,
    _video_repo,
    gateway,
    _id_provider,
    _sessions_root,
    processing_queue.put,
)
delete_recording_file_use_case = DeleteRecordingFileUseCase(_video_repo, _sessions_root)

_gpu_scheduler: GpuResourceScheduler = OllamaGpuScheduler()
_ollama_client = OllamaClient()

transcribe_use_case = TranscribeVideoUseCase(FfmpegAudioExtractor(), FasterWhisperProvider())
analyze_visual_use_case = AnalyzeVisualUseCase(
    FfmpegFrameExtractor(), OllamaVisionAnalysisProvider(_ollama_client)
)
summarize_use_case = SummarizeVideoUseCase(OllamaSummarizationProvider(_ollama_client))

process_video_use_case = ProcessVideoUseCase(
    _video_repo,
    transcribe_use_case,
    analyze_visual_use_case,
    summarize_use_case,
    _gpu_scheduler,
    _sessions_root,
)


async def worker() -> None:
    """Background task started once at app startup (see `server.py`'s
    `@app.on_event("startup")` handler) — direct replacement for that
    module's `_worker()`."""
    while True:
        task = await processing_queue.get()
        await process_video_use_case.execute(task)
        processing_queue.task_done()


# --- FastAPI Depends() accessors ---


def get_create_session_use_case() -> CreateSessionUseCase:
    return create_session_use_case


def get_list_sessions_use_case() -> ListSessionsUseCase:
    return list_sessions_use_case


def get_get_session_use_case() -> GetSessionUseCase:
    return get_session_use_case


def get_delete_session_use_case() -> DeleteSessionUseCase:
    return delete_session_use_case


def get_delete_video_use_case() -> DeleteVideoUseCase:
    return delete_video_use_case


def get_save_artifacts_use_case() -> SaveArtifactsUseCase:
    return save_artifacts_use_case
