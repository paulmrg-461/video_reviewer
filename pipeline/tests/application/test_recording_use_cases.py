"""Tests for the Recording use cases (Step 7), against fake
`ScreenRecorderPort`/`ActiveRecordingsRegistry`/`VideoRepository`/
`SessionGateway`/`IdProvider`/`Clock` — no real `gpu-screen-recorder`, no
JSON, no FastAPI involved.
"""
from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from pipeline.application.recording.exceptions import (
    ConcurrentRecordingError,
    NotARecordingError,
    RecorderNotAvailableError,
    RecordingNotFoundError,
    RecordingPathTraversalError,
    RecordingSaveFailedError,
)
from pipeline.application.recording.use_cases import (
    DeleteRecordingFileUseCase,
    StartRecordingUseCase,
    StopRecordingUseCase,
)
from pipeline.application.sessions.exceptions import SessionNotFoundError
from pipeline.application.videos.exceptions import VideoNotFoundError
from pipeline.domain.recording import ActiveRecording
from pipeline.domain.sessions.session import SessionId
from pipeline.domain.videos.value_objects import ProcessingOptions, VideoId
from pipeline.domain.videos.video import Video
from pipeline.shared.config import DEFAULT_RECORD_INSTRUCTIONS


class FakeScreenRecorder:
    def __init__(self, available: bool = True) -> None:
        self.available = available
        self.started: list[Path] = []
        self.stopped: list[object] = []
        self.stop_result = True
        self._next_handle = 0

    def start(self, output: Path) -> object:
        if not self.available:
            raise FileNotFoundError("gpu-screen-recorder not found")
        self.started.append(output)
        self._next_handle += 1
        return f"handle-{self._next_handle}"

    def stop(self, handle: object, timeout: float = 15.0) -> bool:
        self.stopped.append(handle)
        return self.stop_result


class FakeRegistry:
    def __init__(self) -> None:
        self._entries: dict[str, tuple[ActiveRecording, object]] = {}

    def track(self, recording: ActiveRecording, handle: object) -> None:
        self._entries[recording.id] = (recording, handle)

    def get(self, recording_id: str) -> tuple[ActiveRecording, object] | None:
        return self._entries.get(recording_id)

    def untrack(self, recording_id: str) -> None:
        self._entries.pop(recording_id, None)

    def list_all(self) -> list[ActiveRecording]:
        return [r for r, _h in self._entries.values()]

    def get_by_session(self, session_id: str) -> ActiveRecording | None:
        for r, _h in self._entries.values():
            if r.session_id == session_id:
                return r
        return None


class FakeGateway:
    def __init__(self, sessions: dict[str, dict] | None = None) -> None:
        self.sessions = sessions or {}

    async def get_session(self, session_id: str) -> dict | None:
        return self.sessions.get(session_id)


class FakeVideoRepository:
    def __init__(self) -> None:
        self.videos: dict[tuple[str, str], Video] = {}
        self.added: list[Video] = []
        self.updated: list[Video] = []

    async def add(self, video: Video) -> None:
        self.videos[(video.session_id, video.id.value)] = video
        self.added.append(video)

    async def get(self, session_id: SessionId, video_id: VideoId) -> Video | None:
        return self.videos.get((session_id.value, video_id.value))

    async def update(self, video: Video) -> bool:
        self.videos[(video.session_id, video.id.value)] = video
        self.updated.append(video)
        return True

    async def remove(self, session_id: SessionId, video_id: VideoId) -> bool:
        return bool(self.videos.pop((session_id.value, video_id.value), None))

    async def list_by_session(self, session_id: SessionId) -> list[Video]:
        return [v for (sid, _), v in self.videos.items() if sid == session_id.value]


class FakeIdProvider:
    def __init__(self, ids: list[str]) -> None:
        self._ids = list(ids)

    def new_id(self) -> str:
        return self._ids.pop(0)


class FakeClock:
    def __init__(self, value: str = "2026-07-23T00:00:00+00:00") -> None:
        self.value = value

    def now_iso(self) -> str:
        return self.value


class FakeEnqueue:
    def __init__(self) -> None:
        self.tasks: list[dict] = []

    async def __call__(self, task: dict) -> None:
        self.tasks.append(task)


# --- StartRecordingUseCase ---


def test_start_recording_succeeds_and_tracks(tmp_path) -> None:
    recorder = FakeScreenRecorder()
    registry = FakeRegistry()
    gateway = FakeGateway({"sess-1": {"id": "sess-1", "instructions": ""}})
    use_case = StartRecordingUseCase(
        recorder, registry, gateway, FakeIdProvider(["rec-a"]), FakeClock(), tmp_path
    )

    recording = asyncio.run(use_case.execute("sess-1"))

    assert recording.id == "rec-a"
    assert recording.session_id == "sess-1"
    assert recording.output_path == tmp_path / "sess-1" / "rec_rec-a.mp4"
    assert recording.started_at == "2026-07-23T00:00:00+00:00"
    assert recorder.started == [recording.output_path]
    tracked = registry.get("rec-a")
    assert tracked is not None
    assert tracked[0] == recording
    assert tracked[1] == "handle-1"


def test_start_recording_on_nonexistent_session_raises(tmp_path) -> None:
    recorder = FakeScreenRecorder()
    registry = FakeRegistry()
    gateway = FakeGateway({})
    use_case = StartRecordingUseCase(
        recorder, registry, gateway, FakeIdProvider(["rec-a"]), FakeClock(), tmp_path
    )

    with pytest.raises(SessionNotFoundError):
        asyncio.run(use_case.execute("missing-sess"))
    assert recorder.started == []


def test_start_recording_when_session_already_has_active_recording_raises(tmp_path) -> None:
    """Regression test for the concurrent-recording bug fix: nothing in
    today's app prevents starting a second recording for a session that
    already has one active."""
    recorder = FakeScreenRecorder()
    registry = FakeRegistry()
    gateway = FakeGateway({"sess-1": {"id": "sess-1", "instructions": ""}})
    use_case = StartRecordingUseCase(
        recorder, registry, gateway, FakeIdProvider(["rec-a", "rec-b"]), FakeClock(), tmp_path
    )

    asyncio.run(use_case.execute("sess-1"))

    with pytest.raises(ConcurrentRecordingError):
        asyncio.run(use_case.execute("sess-1"))

    # Only the first recording was ever started against the real recorder.
    assert recorder.started == [tmp_path / "sess-1" / "rec_rec-a.mp4"]


def test_start_recording_with_recorder_unavailable_raises(tmp_path) -> None:
    recorder = FakeScreenRecorder(available=False)
    registry = FakeRegistry()
    gateway = FakeGateway({"sess-1": {"id": "sess-1", "instructions": ""}})
    use_case = StartRecordingUseCase(
        recorder, registry, gateway, FakeIdProvider(["rec-a"]), FakeClock(), tmp_path
    )

    with pytest.raises(RecorderNotAvailableError):
        asyncio.run(use_case.execute("sess-1"))
    assert registry.list_all() == []


# --- StopRecordingUseCase ---


def _start_tracked_recording(
    registry: FakeRegistry, tmp_path: Path, session_id: str = "sess-1", rid: str = "rec-a"
) -> Path:
    output = tmp_path / session_id / f"rec_{rid}.mp4"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(b"video-bytes")
    registry.track(
        ActiveRecording(id=rid, session_id=session_id, output_path=output, started_at="t"),
        f"handle-{rid}",
    )
    return output


def test_stop_recording_succeeds_untracks_persists_and_enqueues(tmp_path) -> None:
    recorder = FakeScreenRecorder()
    registry = FakeRegistry()
    output = _start_tracked_recording(registry, tmp_path)
    gateway = FakeGateway({"sess-1": {"id": "sess-1", "instructions": ""}})
    video_repo = FakeVideoRepository()
    enqueue = FakeEnqueue()
    use_case = StopRecordingUseCase(
        recorder, registry, video_repo, gateway, FakeIdProvider(["vid-x"]), tmp_path, enqueue
    )

    video = asyncio.run(
        use_case.execute(
            session_id="sess-1",
            recording_id="rec-a",
            language="es",
            analyze_visual=True,
            instructions_override="",
        )
    )

    assert video.id == VideoId("vid-x")
    assert video.is_recording is True
    assert video.original_path == str(output)
    assert video.output_dir == str(tmp_path / "sess-1" / "vid-x")
    assert registry.get("rec-a") is None
    assert video_repo.added == [video]
    assert recorder.stopped == ["handle-rec-a"]
    assert enqueue.tasks == [
        {
            "session_id": "sess-1",
            "video_id": "vid-x",
            "instructions": video.instructions,
            "language": "es",
            "analyze_visual": True,
        }
    ]


def test_stop_recording_not_found_raises(tmp_path) -> None:
    recorder = FakeScreenRecorder()
    registry = FakeRegistry()
    gateway = FakeGateway({})
    video_repo = FakeVideoRepository()
    enqueue = FakeEnqueue()
    use_case = StopRecordingUseCase(
        recorder, registry, video_repo, gateway, FakeIdProvider([]), tmp_path, enqueue
    )

    with pytest.raises(RecordingNotFoundError):
        asyncio.run(
            use_case.execute(
                session_id="sess-1",
                recording_id="missing",
                language="es",
                analyze_visual=True,
                instructions_override="",
            )
        )
    assert enqueue.tasks == []


def test_stop_recording_session_mismatch_raises_not_found(tmp_path) -> None:
    recorder = FakeScreenRecorder()
    registry = FakeRegistry()
    _start_tracked_recording(registry, tmp_path, session_id="sess-1", rid="rec-a")
    gateway = FakeGateway({})
    video_repo = FakeVideoRepository()
    enqueue = FakeEnqueue()
    use_case = StopRecordingUseCase(
        recorder, registry, video_repo, gateway, FakeIdProvider([]), tmp_path, enqueue
    )

    with pytest.raises(RecordingNotFoundError):
        asyncio.run(
            use_case.execute(
                session_id="sess-other",
                recording_id="rec-a",
                language="es",
                analyze_visual=True,
                instructions_override="",
            )
        )


def test_stop_recording_with_zero_byte_output_raises_save_failed(tmp_path) -> None:
    recorder = FakeScreenRecorder()
    registry = FakeRegistry()
    output = tmp_path / "sess-1" / "rec_rec-a.mp4"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(b"")  # zero-byte output
    registry.track(
        ActiveRecording(id="rec-a", session_id="sess-1", output_path=output, started_at="t"),
        "handle-rec-a",
    )
    gateway = FakeGateway({"sess-1": {"id": "sess-1", "instructions": ""}})
    video_repo = FakeVideoRepository()
    enqueue = FakeEnqueue()
    use_case = StopRecordingUseCase(
        recorder, registry, video_repo, gateway, FakeIdProvider(["vid-x"]), tmp_path, enqueue
    )

    with pytest.raises(RecordingSaveFailedError):
        asyncio.run(
            use_case.execute(
                session_id="sess-1",
                recording_id="rec-a",
                language="es",
                analyze_visual=True,
                instructions_override="",
            )
        )
    assert registry.get("rec-a") is None  # still untracked even on failure
    assert video_repo.added == []
    assert enqueue.tasks == []


def test_stop_recording_with_missing_output_raises_save_failed(tmp_path) -> None:
    recorder = FakeScreenRecorder()
    recorder.stop_result = False
    registry = FakeRegistry()
    output = tmp_path / "sess-1" / "rec_rec-a.mp4"
    registry.track(
        ActiveRecording(id="rec-a", session_id="sess-1", output_path=output, started_at="t"),
        "handle-rec-a",
    )
    gateway = FakeGateway({"sess-1": {"id": "sess-1", "instructions": ""}})
    video_repo = FakeVideoRepository()
    enqueue = FakeEnqueue()
    use_case = StopRecordingUseCase(
        recorder, registry, video_repo, gateway, FakeIdProvider(["vid-x"]), tmp_path, enqueue
    )

    with pytest.raises(RecordingSaveFailedError):
        asyncio.run(
            use_case.execute(
                session_id="sess-1",
                recording_id="rec-a",
                language="es",
                analyze_visual=True,
                instructions_override="",
            )
        )


@pytest.mark.parametrize(
    "instructions_override,session_instructions,expected",
    [
        ("explicit override", "session default", "explicit override"),
        ("  ", "session default", "session default"),
        ("", "  ", DEFAULT_RECORD_INSTRUCTIONS),
    ],
)
def test_stop_recording_resolves_instructions_fallback_chain(
    tmp_path, instructions_override, session_instructions, expected
) -> None:
    recorder = FakeScreenRecorder()
    registry = FakeRegistry()
    _start_tracked_recording(registry, tmp_path)
    gateway = FakeGateway({"sess-1": {"id": "sess-1", "instructions": session_instructions}})
    video_repo = FakeVideoRepository()
    enqueue = FakeEnqueue()
    use_case = StopRecordingUseCase(
        recorder, registry, video_repo, gateway, FakeIdProvider(["vid-x"]), tmp_path, enqueue
    )

    video = asyncio.run(
        use_case.execute(
            session_id="sess-1",
            recording_id="rec-a",
            language="es",
            analyze_visual=True,
            instructions_override=instructions_override,
        )
    )

    assert video.instructions == expected


# --- DeleteRecordingFileUseCase ---


def _make_recording_video(
    session_id: str = "sess-1", video_id: str = "vid-1", original_path: str = ""
) -> Video:
    video = Video.new_from_recording(
        id=VideoId(video_id),
        session_id=session_id,
        name="rec_x.mp4",
        original_path=original_path,
        options=ProcessingOptions(),
        instructions="do it",
    )
    return video


def test_delete_recording_file_rejects_path_outside_sessions_root(tmp_path) -> None:
    sessions_root = tmp_path / "sessions"
    sessions_root.mkdir()
    outside_dir = tmp_path / "outside"
    outside_dir.mkdir()
    outside_file = outside_dir / "escaped.mp4"
    outside_file.write_bytes(b"data")

    video_repo = FakeVideoRepository()
    video = _make_recording_video(original_path=str(outside_file))
    asyncio.run(video_repo.add(video))
    use_case = DeleteRecordingFileUseCase(video_repo, sessions_root)

    with pytest.raises(RecordingPathTraversalError):
        asyncio.run(use_case.execute("sess-1", "vid-1"))

    # The file must survive the rejected deletion attempt.
    assert outside_file.exists()
    assert video_repo.videos[("sess-1", "vid-1")].original_deleted is False


def test_delete_recording_file_rejects_non_recording_video(tmp_path) -> None:
    sessions_root = tmp_path / "sessions"
    video_repo = FakeVideoRepository()
    video = Video.new_from_upload(
        id=VideoId("vid-1"),
        session_id="sess-1",
        name="upload.mp4",
        original_path=str(tmp_path / "upload.mp4"),
        options=ProcessingOptions(),
        instructions="do it",
    )
    asyncio.run(video_repo.add(video))
    use_case = DeleteRecordingFileUseCase(video_repo, sessions_root)

    with pytest.raises(NotARecordingError):
        asyncio.run(use_case.execute("sess-1", "vid-1"))


def test_delete_recording_file_missing_video_raises_video_not_found(tmp_path) -> None:
    sessions_root = tmp_path / "sessions"
    video_repo = FakeVideoRepository()
    use_case = DeleteRecordingFileUseCase(video_repo, sessions_root)

    with pytest.raises(VideoNotFoundError):
        asyncio.run(use_case.execute("sess-1", "missing"))


def test_delete_recording_file_succeeds_for_valid_recording(tmp_path) -> None:
    sessions_root = tmp_path / "sessions"
    rec_file = sessions_root / "sess-1" / "rec_x.mp4"
    rec_file.parent.mkdir(parents=True)
    rec_file.write_bytes(b"data")

    video_repo = FakeVideoRepository()
    video = _make_recording_video(original_path=str(rec_file))
    asyncio.run(video_repo.add(video))
    use_case = DeleteRecordingFileUseCase(video_repo, sessions_root)

    asyncio.run(use_case.execute("sess-1", "vid-1"))

    assert not rec_file.exists()
    assert video_repo.videos[("sess-1", "vid-1")].original_deleted is True
    assert video_repo.updated == [video]
