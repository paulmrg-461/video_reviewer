"""Recording use cases.

Ports today's `start_recording`/`stop_recording`/`delete_recording_file`
routes in `pipeline/server.py` (pre-Step-7) into pure application logic —
no FastAPI, no raw `subprocess`/registry-dict handling. Follows the same
shape as `pipeline.application.videos.use_cases` (Step 4): `enqueue` is an
injected `Callable[[dict], Awaitable[None]]` rather than a concrete queue
(see that module's docstring, still accurate — `processing_queue` is wired
in eagerly by `pipeline.presentation.composition_root`, this feature just
receives its `.put` method the same way `AddVideosToSessionUseCase`/
`RetryVideoUseCase` do).
"""
from __future__ import annotations

import asyncio
import typing
from pathlib import Path

from pipeline.application.recording.exceptions import (
    ConcurrentRecordingError,
    NotARecordingError,
    RecorderNotAvailableError,
    RecordingNotFoundError,
    RecordingPathTraversalError,
    RecordingSaveFailedError,
)
from pipeline.application.recording.ports import (
    ActiveRecordingsRegistry,
    ScreenRecorderPort,
    SessionGateway,
)
from pipeline.application.sessions.exceptions import SessionNotFoundError
from pipeline.application.shared.ports import Clock, IdProvider
from pipeline.application.videos.exceptions import VideoNotFoundError
from pipeline.application.videos.ports import VideoRepository
from pipeline.domain.recording import ActiveRecording
from pipeline.domain.sessions.session import SessionId
from pipeline.domain.videos.value_objects import ProcessingOptions, VideoId
from pipeline.domain.videos.video import Video
from pipeline.shared.config import DEFAULT_RECORD_INSTRUCTIONS

Enqueue = typing.Callable[[dict], typing.Awaitable[None]]


class StartRecordingUseCase:
    """Mirrors today's `start_recording` route, plus the bug fix: rejects
    a second concurrent recording for the same session (nothing in
    today's app checks this — it would happily launch a second
    `gpu-screen-recorder` process against the same session)."""

    def __init__(
        self,
        recorder: ScreenRecorderPort,
        registry: ActiveRecordingsRegistry,
        gateway: SessionGateway,
        id_provider: IdProvider,
        clock: Clock,
        sessions_root: Path,
    ) -> None:
        self._recorder = recorder
        self._registry = registry
        self._gateway = gateway
        self._id_provider = id_provider
        self._clock = clock
        self._sessions_root = sessions_root

    async def execute(self, session_id: str) -> ActiveRecording:
        session = await self._gateway.get_session(session_id)
        if not session:
            raise SessionNotFoundError(session_id)

        if self._registry.get_by_session(session_id) is not None:
            raise ConcurrentRecordingError(session_id)

        rid = self._id_provider.new_id()
        output = self._sessions_root / session_id / f"rec_{rid}.mp4"
        try:
            handle = self._recorder.start(output)
        except FileNotFoundError as exc:
            raise RecorderNotAvailableError() from exc

        recording = ActiveRecording(
            id=rid,
            session_id=session_id,
            output_path=output,
            started_at=self._clock.now_iso(),
        )
        self._registry.track(recording, handle)
        return recording


class StopRecordingUseCase:
    """Mirrors today's `stop_recording` route exactly, including its
    3-level instructions fallback chain (explicit override, then the
    session's default instructions, then `DEFAULT_RECORD_INSTRUCTIONS`).

    Deviation from the task's suggested constructor shape, noted
    explicitly: an `IdProvider` is required here. Today's route mints a
    brand-new video id (`vid = uuid.uuid4().hex[:12]`) distinct from the
    recording id (`rid`) — it does NOT reuse the recording id as the video
    id. Preserving that exact behavior needs a fresh id source.
    """

    def __init__(
        self,
        recorder: ScreenRecorderPort,
        registry: ActiveRecordingsRegistry,
        video_repo: VideoRepository,
        gateway: SessionGateway,
        id_provider: IdProvider,
        sessions_root: Path,
        enqueue: Enqueue,
    ) -> None:
        self._recorder = recorder
        self._registry = registry
        self._video_repo = video_repo
        self._gateway = gateway
        self._id_provider = id_provider
        self._sessions_root = sessions_root
        self._enqueue = enqueue

    async def execute(
        self,
        session_id: str,
        recording_id: str,
        language: str,
        analyze_visual: bool,
        instructions_override: str,
    ) -> Video:
        tracked = self._registry.get(recording_id)
        if tracked is None or tracked[0].session_id != session_id:
            raise RecordingNotFoundError(session_id, recording_id)
        recording, handle = tracked

        loop = asyncio.get_running_loop()
        ok = await loop.run_in_executor(None, self._recorder.stop, handle)
        self._registry.untrack(recording_id)

        output = recording.output_path
        if not ok or not output.exists() or output.stat().st_size == 0:
            raise RecordingSaveFailedError()

        session = await self._gateway.get_session(session_id)
        instructions = (
            instructions_override.strip()
            or (session.get("instructions", "").strip() if session else "")
            or DEFAULT_RECORD_INSTRUCTIONS
        )

        video = Video.new_from_recording(
            id=VideoId(self._id_provider.new_id()),
            session_id=session_id,
            name=output.name,
            original_path=str(output),
            options=ProcessingOptions(language=language, analyze_visual=analyze_visual),
            instructions=instructions,
        )
        # Same deliberate, documented exception to the "only `mark_done`
        # sets `output_dir`" domain convention as
        # `AddVideosToSessionUseCase` (Step 4, see its docstring): today's
        # app sets this field at creation time (before any processing) to
        # keep the persisted dict shape matching every other video.
        # Harmless for the same reasons given there.
        video.output_dir = str(self._sessions_root / session_id / video.id.value)

        await self._video_repo.add(video)
        await self._enqueue({
            "session_id": session_id,
            "video_id": video.id.value,
            "instructions": video.instructions,
            "language": language,
            "analyze_visual": analyze_visual,
        })
        return video


class DeleteRecordingFileUseCase:
    """Ports today's `delete_recording_file` route verbatim, including its
    path-traversal safety check byte-exact:
    `sessions_root.resolve() not in resolved_path.parents`.
    """

    def __init__(self, video_repo: VideoRepository, sessions_root: Path) -> None:
        self._video_repo = video_repo
        self._sessions_root = sessions_root

    async def execute(self, session_id: str, video_id: str) -> None:
        video = await self._video_repo.get(SessionId(session_id), VideoId(video_id))
        if video is None:
            raise VideoNotFoundError(session_id, video_id)
        if not video.is_recording:
            raise NotARecordingError(session_id, video_id)

        path = Path(video.original_path)
        sessions_root = self._sessions_root.resolve()
        resolved = path.resolve() if path.exists() else path
        if sessions_root not in resolved.parents:
            raise RecordingPathTraversalError(str(path))

        if path.exists():
            path.unlink()
        video.original_deleted = True
        await self._video_repo.update(video)
