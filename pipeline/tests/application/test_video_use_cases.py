"""Tests for the Videos use cases (Step 4), against an in-memory fake
`VideoRepository`, a fake `IdProvider`, and a list-appending fake enqueue
callable — no filesystem (beyond real tmp_path dirs for path-existence
checks), no JSON, no FastAPI involved.
"""
from __future__ import annotations

import asyncio

import pytest

from pipeline.application.videos.exceptions import VideoNotFoundError
from pipeline.application.videos.use_cases import (
    AddVideosToSessionUseCase,
    DeleteVideoUseCase,
    RetryVideoUseCase,
    SaveArtifactsUseCase,
)
from pipeline.domain.sessions.session import SessionId
from pipeline.domain.videos.exceptions import InvalidVideoStateTransitionError
from pipeline.domain.videos.value_objects import ProcessingOptions, VideoId
from pipeline.domain.videos.video import ProcessingStatus, Video


class FakeVideoRepository:
    def __init__(self) -> None:
        self.videos: dict[tuple[str, str], Video] = {}
        self.added: list[Video] = []
        self.updated: list[Video] = []
        self.removed_ids: list[tuple[str, str]] = []

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
        key = (session_id.value, video_id.value)
        if key not in self.videos:
            return False
        del self.videos[key]
        self.removed_ids.append(key)
        return True

    async def list_by_session(self, session_id: SessionId) -> list[Video]:
        return [v for (sid, _), v in self.videos.items() if sid == session_id.value]


class FakeIdProvider:
    def __init__(self, ids: list[str]) -> None:
        self._ids = list(ids)

    def new_id(self) -> str:
        return self._ids.pop(0)


class FakeEnqueue:
    def __init__(self) -> None:
        self.tasks: list[dict] = []

    async def __call__(self, task: dict) -> None:
        self.tasks.append(task)


def _make_video(
    session_id: str = "sess-1",
    video_id: str = "vid-1",
    status: ProcessingStatus = ProcessingStatus.QUEUED,
) -> Video:
    video = Video.new_from_upload(
        id=VideoId(video_id),
        session_id=session_id,
        name="clip.mp4",
        original_path="/tmp/clip.mp4",
        options=ProcessingOptions(),
        instructions="be thorough",
    )
    video.status = status
    return video


# --- AddVideosToSessionUseCase ---


def test_add_videos_skips_nonexistent_paths_and_adds_only_valid_ones(tmp_path) -> None:
    existing = tmp_path / "real.mp4"
    existing.write_bytes(b"data")
    missing = tmp_path / "missing.mp4"

    repo = FakeVideoRepository()
    enqueue = FakeEnqueue()
    use_case = AddVideosToSessionUseCase(
        repo, FakeIdProvider(["vid-a"]), tmp_path / "sessions_root", enqueue
    )

    added = asyncio.run(
        use_case.execute(
            session_id="sess-1",
            paths=[str(existing), str(missing), "  ", ""],
            instructions="",
            language="es",
            analyze_visual=True,
            session_instructions_fallback="fallback instructions",
        )
    )

    assert len(added) == 1
    video = added[0]
    assert video.id == VideoId("vid-a")
    assert video.name == "real.mp4"
    assert video.original_path == str(existing)
    assert video.instructions == "fallback instructions"
    assert video.options.language == "es"
    assert video.options.analyze_visual is True
    assert video.output_dir == str(tmp_path / "sessions_root" / "sess-1" / "vid-a")
    assert repo.added == [video]
    assert enqueue.tasks == [
        {
            "session_id": "sess-1",
            "video_id": "vid-a",
            "instructions": "fallback instructions",
            "language": "es",
            "analyze_visual": True,
        }
    ]


def test_add_videos_uses_explicit_instructions_over_session_fallback(tmp_path) -> None:
    existing = tmp_path / "real.mp4"
    existing.write_bytes(b"data")

    repo = FakeVideoRepository()
    enqueue = FakeEnqueue()
    use_case = AddVideosToSessionUseCase(
        repo, FakeIdProvider(["vid-a"]), tmp_path, enqueue
    )

    added = asyncio.run(
        use_case.execute(
            session_id="sess-1",
            paths=[str(existing)],
            instructions="  explicit instructions  ",
            language="en",
            analyze_visual=False,
            session_instructions_fallback="fallback",
        )
    )

    assert added[0].instructions == "explicit instructions"


def test_add_videos_with_all_invalid_paths_adds_nothing_and_enqueues_nothing(tmp_path) -> None:
    repo = FakeVideoRepository()
    enqueue = FakeEnqueue()
    use_case = AddVideosToSessionUseCase(repo, FakeIdProvider([]), tmp_path, enqueue)

    added = asyncio.run(
        use_case.execute(
            session_id="sess-1",
            paths=[str(tmp_path / "nope.mp4"), "   "],
            instructions="",
            language="es",
            analyze_visual=False,
            session_instructions_fallback="",
        )
    )

    assert added == []
    assert repo.added == []
    assert enqueue.tasks == []


# --- RetryVideoUseCase ---


def test_retry_video_from_error_succeeds_and_reenqueues() -> None:
    repo = FakeVideoRepository()
    video = _make_video(status=ProcessingStatus.ERROR)
    video.error = "boom"
    asyncio.run(repo.add(video))
    enqueue = FakeEnqueue()
    use_case = RetryVideoUseCase(repo, enqueue)

    result = asyncio.run(use_case.execute("sess-1", "vid-1"))

    assert result.status == ProcessingStatus.QUEUED
    assert result.error is None
    assert repo.updated == [result]
    assert enqueue.tasks == [
        {
            "session_id": "sess-1",
            "video_id": "vid-1",
            "instructions": "be thorough",
            "language": "es",
            "analyze_visual": False,
        }
    ]


@pytest.mark.parametrize(
    "status",
    [ProcessingStatus.QUEUED, ProcessingStatus.TRANSCRIBING, ProcessingStatus.DONE],
)
def test_retry_video_from_non_error_status_raises_invalid_transition(status) -> None:
    repo = FakeVideoRepository()
    video = _make_video(status=status)
    asyncio.run(repo.add(video))
    enqueue = FakeEnqueue()
    use_case = RetryVideoUseCase(repo, enqueue)

    with pytest.raises(InvalidVideoStateTransitionError):
        asyncio.run(use_case.execute("sess-1", "vid-1"))

    # This is the regression test for the retry-race bug fix: no
    # double-enqueue, no silent status mutation.
    assert enqueue.tasks == []
    assert repo.updated == []


def test_retry_nonexistent_video_raises_video_not_found_error() -> None:
    repo = FakeVideoRepository()
    enqueue = FakeEnqueue()
    use_case = RetryVideoUseCase(repo, enqueue)

    with pytest.raises(VideoNotFoundError):
        asyncio.run(use_case.execute("sess-1", "missing"))

    assert enqueue.tasks == []


# --- DeleteVideoUseCase ---


def test_delete_video_calls_repo_remove_and_removes_output_dir(tmp_path) -> None:
    sessions_root = tmp_path / "sessions"
    video_dir = sessions_root / "sess-1" / "vid-1"
    video_dir.mkdir(parents=True)
    (video_dir / "summary.md").write_text("x")

    repo = FakeVideoRepository()
    asyncio.run(repo.add(_make_video()))
    use_case = DeleteVideoUseCase(repo, sessions_root)

    asyncio.run(use_case.execute("sess-1", "vid-1"))

    assert repo.removed_ids == [("sess-1", "vid-1")]
    assert not video_dir.exists()


def test_delete_nonexistent_video_does_not_raise(tmp_path) -> None:
    sessions_root = tmp_path / "sessions"
    repo = FakeVideoRepository()
    use_case = DeleteVideoUseCase(repo, sessions_root)

    # Preserves today's permissive route behavior: no exception, no-op.
    asyncio.run(use_case.execute("sess-1", "missing"))

    assert repo.removed_ids == []


# --- SaveArtifactsUseCase ---


def test_save_artifacts_copies_only_existing_files_with_slug_prefix(tmp_path) -> None:
    sessions_root = tmp_path / "sessions"
    out_dir = sessions_root / "sess-1" / "vid-1"
    out_dir.mkdir(parents=True)
    (out_dir / "summary.md").write_text("summary content")
    # analysis.md intentionally NOT created, to prove it's skipped.

    repo = FakeVideoRepository()
    video = _make_video()
    video.name = "My Clip!.mp4"
    asyncio.run(repo.add(video))
    use_case = SaveArtifactsUseCase(repo, sessions_root)
    target_dir = tmp_path / "target"

    saved = asyncio.run(
        use_case.execute(
            "sess-1", "vid-1", str(target_dir), ["summary.md", "analysis.md"]
        )
    )

    expected_dst = target_dir / "My_Clip_summary.md"
    assert saved == [str(expected_dst)]
    assert expected_dst.read_text() == "summary content"
    assert not (target_dir / "My_Clip_analysis.md").exists()


def test_save_artifacts_uses_video_id_as_prefix_when_video_not_found(tmp_path) -> None:
    sessions_root = tmp_path / "sessions"
    out_dir = sessions_root / "sess-1" / "vid-missing"
    out_dir.mkdir(parents=True)
    (out_dir / "transcript.txt").write_text("t")

    repo = FakeVideoRepository()
    use_case = SaveArtifactsUseCase(repo, sessions_root)
    target_dir = tmp_path / "target"

    saved = asyncio.run(
        use_case.execute("sess-1", "vid-missing", str(target_dir), ["transcript.txt"])
    )

    assert saved == [str(target_dir / "vid-missing_transcript.txt")]
