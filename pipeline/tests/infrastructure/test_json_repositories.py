"""Tests for the JSON-file-backed Session/Video repositories (Step 2).

No pytest-asyncio dependency is added for this — each test drives its own
`async def scenario()` via `asyncio.run(...)` from an ordinary sync test
function, which is enough for the coroutine-based repositories/gateway
under test.

`tmp_path` is used everywhere: the real `sessions.json` at the repo root
must NEVER be touched by these tests.
"""
from __future__ import annotations

import asyncio
import json
from pathlib import Path

from pipeline.domain.sessions.session import Session, SessionId
from pipeline.domain.videos.value_objects import ProcessingOptions, VideoId
from pipeline.domain.videos.video import ProcessingStatus, Video
from pipeline.infrastructure.persistence.json.json_session_repository import (
    JsonSessionRepository,
)
from pipeline.infrastructure.persistence.json.json_video_repository import (
    JsonVideoRepository,
)
from pipeline.infrastructure.persistence.json.mappers import video_dict_to_domain
from pipeline.infrastructure.persistence.json.sessions_json_gateway import (
    SessionsJsonGateway,
)


def _make_repos(
    tmp_path: Path,
) -> tuple[SessionsJsonGateway, JsonSessionRepository, JsonVideoRepository]:
    # ONE gateway instance shared by both repositories, as required —
    # two separate gateways over the same file would defeat the lock.
    gateway = SessionsJsonGateway(tmp_path / "sessions.json")
    return gateway, JsonSessionRepository(gateway), JsonVideoRepository(gateway)


# --- Round trip ---


def test_round_trip_session_and_video(tmp_path: Path) -> None:
    gateway, session_repo, video_repo = _make_repos(tmp_path)

    async def scenario():
        session = Session.new(
            id=SessionId("sess-1"),
            name="  My Session  ",
            instructions="be thorough",
            created_at="2026-01-01T00:00:00+00:00",
        )
        await session_repo.add(session)

        video = Video.new_from_upload(
            id=VideoId("vid-1"),
            session_id="sess-1",
            name="clip.mp4",
            original_path="/videos/clip.mp4",
            options=ProcessingOptions(language="es", analyze_visual=True),
            instructions="video specific instructions",
        )
        await video_repo.add(video)

        loaded_session = await session_repo.get(SessionId("sess-1"))
        loaded_video = await video_repo.get(SessionId("sess-1"), VideoId("vid-1"))
        return loaded_session, loaded_video

    loaded_session, loaded_video = asyncio.run(scenario())

    assert loaded_session is not None
    assert loaded_session.id == SessionId("sess-1")
    assert loaded_session.name == "  My Session  "
    assert loaded_session.instructions == "be thorough"
    assert loaded_session.created_at == "2026-01-01T00:00:00+00:00"
    assert loaded_session.video_ids == [VideoId("vid-1")]

    assert loaded_video is not None
    assert loaded_video.id == VideoId("vid-1")
    assert loaded_video.session_id == "sess-1"
    assert loaded_video.name == "clip.mp4"
    assert loaded_video.original_path == "/videos/clip.mp4"
    assert loaded_video.status == ProcessingStatus.QUEUED
    assert loaded_video.options.language == "es"
    assert loaded_video.options.analyze_visual is True
    assert loaded_video.instructions == "video specific instructions"
    assert loaded_video.is_recording is False
    assert loaded_video.original_deleted is False


def test_list_all_sessions_sorted_by_created_at_desc(tmp_path: Path) -> None:
    _, session_repo, _ = _make_repos(tmp_path)

    async def scenario():
        await session_repo.add(
            Session.new(SessionId("older"), "Older", "", "2025-01-01T00:00:00+00:00")
        )
        await session_repo.add(
            Session.new(SessionId("newer"), "Newer", "", "2026-01-01T00:00:00+00:00")
        )
        return await session_repo.list_all()

    sessions = asyncio.run(scenario())

    assert [s.id.value for s in sessions] == ["newer", "older"]


def test_video_repository_update_and_remove(tmp_path: Path) -> None:
    _, session_repo, video_repo = _make_repos(tmp_path)

    async def scenario():
        await session_repo.add(
            Session.new(SessionId("sess-1"), "S", "", "2026-01-01T00:00:00+00:00")
        )
        video = Video.new_from_upload(
            id=VideoId("vid-1"),
            session_id="sess-1",
            name="clip.mp4",
            original_path="/videos/clip.mp4",
            options=ProcessingOptions(),
            instructions="",
        )
        await video_repo.add(video)

        video.start_extracting_audio()
        updated_ok = await video_repo.update(video)
        after_update = await video_repo.get(SessionId("sess-1"), VideoId("vid-1"))

        removed_ok = await video_repo.remove(SessionId("sess-1"), VideoId("vid-1"))
        after_remove = await video_repo.get(SessionId("sess-1"), VideoId("vid-1"))
        return updated_ok, after_update, removed_ok, after_remove

    updated_ok, after_update, removed_ok, after_remove = asyncio.run(scenario())

    assert updated_ok is True
    assert after_update is not None
    assert after_update.status == ProcessingStatus.EXTRACTING_AUDIO
    assert removed_ok is True
    assert after_remove is None


# --- Legacy dict tolerance ---


def test_video_dict_to_domain_tolerates_legacy_dict_missing_newer_keys() -> None:
    # Mimics a real pre-existing entry: is_recording/original_deleted were
    # added by a later feature and are absent here.
    legacy_dict = {
        "id": "vid-legacy",
        "name": "old_clip.mp4",
        "original_path": "/videos/old_clip.mp4",
        "status": "done",
        "instructions": "some real instructions text",
        "language": "es",
        "analyze_visual": False,
        "output_dir": "/sessions/sess-1/vid-legacy",
        "error": None,
    }

    video = video_dict_to_domain(legacy_dict, session_id="sess-1")

    assert video.id == VideoId("vid-legacy")
    assert video.status == ProcessingStatus.DONE
    assert video.is_recording is False
    assert video.original_deleted is False
    assert video.output_dir == "/sessions/sess-1/vid-legacy"
    assert video.error is None


def test_video_dict_to_domain_tolerates_minimal_dict() -> None:
    # Only the fields the spec guarantees are ALWAYS present.
    minimal_dict = {
        "id": "vid-minimal",
        "name": "clip.mp4",
        "original_path": "/videos/clip.mp4",
        "status": "queued",
        "instructions": "",
    }

    video = video_dict_to_domain(minimal_dict, session_id="sess-1")

    assert video.options.language == "es"
    assert video.options.analyze_visual is False
    assert video.is_recording is False
    assert video.original_deleted is False
    assert video.output_dir is None
    assert video.error is None


# --- Concurrency ---


def test_concurrent_writes_through_shared_gateway_do_not_corrupt_file(
    tmp_path: Path,
) -> None:
    gateway, session_repo, video_repo = _make_repos(tmp_path)
    sessions_file = tmp_path / "sessions.json"

    async def scenario():
        await session_repo.add(
            Session.new(SessionId("sess-conc"), "Concurrent", "", "2026-01-01T00:00:00+00:00")
        )

        videos = [
            Video.new_from_upload(
                id=VideoId(f"vid-{i}"),
                session_id="sess-conc",
                name=f"clip{i}.mp4",
                original_path=f"/videos/clip{i}.mp4",
                options=ProcessingOptions(),
                instructions="",
            )
            for i in range(20)
        ]

        # Fire concurrent writes through BOTH repositories (sharing one
        # gateway/lock): a first wave of adds, then a second wave mixing
        # updates of the first half with adds of the second half.
        await asyncio.gather(*(video_repo.add(v) for v in videos[:10]))
        await asyncio.gather(
            *(video_repo.update(v) for v in videos[:10]),
            *(video_repo.add(v) for v in videos[10:]),
        )

    asyncio.run(scenario())

    raw = sessions_file.read_text()
    data = json.loads(raw)  # raises if the file was left corrupted
    stored_videos = data["sessions"]["sess-conc"]["videos"]
    stored_ids = {v["id"] for v in stored_videos}

    assert stored_ids == {f"vid-{i}" for i in range(20)}
    assert len(stored_videos) == 20  # no lost or duplicated writes
