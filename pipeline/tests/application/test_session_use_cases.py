"""Tests for the Sessions use cases (Step 3), against in-memory fakes of
every port (`SessionRepository`, `SessionFilesCleaner`, `IdProvider`,
`Clock`) — no filesystem, no JSON, no FastAPI involved.
"""
from __future__ import annotations

import asyncio

import pytest

from pipeline.application.sessions.exceptions import (
    EmptySessionNameError,
    SessionNotFoundError,
)
from pipeline.application.sessions.use_cases import (
    CreateSessionUseCase,
    DeleteSessionUseCase,
    GetSessionUseCase,
    ListSessionsUseCase,
)
from pipeline.domain.sessions.session import Session, SessionId


class FakeSessionRepository:
    def __init__(self) -> None:
        self.sessions: dict[str, Session] = {}
        self.added: list[Session] = []
        self.removed_ids: list[str] = []

    async def add(self, session: Session) -> None:
        self.sessions[session.id.value] = session
        self.added.append(session)

    async def get(self, session_id: SessionId) -> Session | None:
        return self.sessions.get(session_id.value)

    async def list_all(self) -> list[Session]:
        return sorted(
            self.sessions.values(), key=lambda s: s.created_at, reverse=True
        )

    async def remove(self, session_id: SessionId) -> bool:
        if session_id.value not in self.sessions:
            return False
        del self.sessions[session_id.value]
        self.removed_ids.append(session_id.value)
        return True


class FakeSessionFilesCleaner:
    def __init__(self) -> None:
        self.deleted_ids: list[str] = []

    async def delete(self, session_id: SessionId) -> None:
        self.deleted_ids.append(session_id.value)


class FakeIdProvider:
    def __init__(self, next_id: str = "generated-id") -> None:
        self._next_id = next_id

    def new_id(self) -> str:
        return self._next_id


class FakeClock:
    def __init__(self, fixed: str = "2026-01-01T00:00:00+00:00") -> None:
        self._fixed = fixed

    def now_iso(self) -> str:
        return self._fixed


# --- CreateSessionUseCase ---


def test_create_session_with_valid_name_succeeds_and_adds_to_repo() -> None:
    repo = FakeSessionRepository()
    use_case = CreateSessionUseCase(repo, FakeIdProvider("sess-123"), FakeClock())

    session = asyncio.run(use_case.execute("  My Session  ", "  be thorough  "))

    assert session.id == SessionId("sess-123")
    assert session.name == "My Session"
    assert session.instructions == "be thorough"
    assert session.created_at == "2026-01-01T00:00:00+00:00"
    assert session.video_ids == []
    assert repo.added == [session]


def test_create_session_with_blank_name_raises_empty_session_name_error() -> None:
    repo = FakeSessionRepository()
    use_case = CreateSessionUseCase(repo, FakeIdProvider(), FakeClock())

    with pytest.raises(EmptySessionNameError):
        asyncio.run(use_case.execute("   "))

    assert repo.added == []


def test_create_session_with_empty_name_raises_empty_session_name_error() -> None:
    repo = FakeSessionRepository()
    use_case = CreateSessionUseCase(repo, FakeIdProvider(), FakeClock())

    with pytest.raises(EmptySessionNameError):
        asyncio.run(use_case.execute(""))


# --- ListSessionsUseCase ---


def test_list_sessions_returns_all_sessions_from_repo() -> None:
    repo = FakeSessionRepository()
    asyncio.run(
        repo.add(Session.new(SessionId("a"), "A", "", "2025-01-01T00:00:00+00:00"))
    )
    asyncio.run(
        repo.add(Session.new(SessionId("b"), "B", "", "2026-01-01T00:00:00+00:00"))
    )
    use_case = ListSessionsUseCase(repo)

    sessions = asyncio.run(use_case.execute())

    assert [s.id.value for s in sessions] == ["b", "a"]


# --- GetSessionUseCase ---


def test_get_existing_session_returns_it() -> None:
    repo = FakeSessionRepository()
    session = Session.new(SessionId("sess-1"), "S", "", "2026-01-01T00:00:00+00:00")
    asyncio.run(repo.add(session))
    use_case = GetSessionUseCase(repo)

    result = asyncio.run(use_case.execute(SessionId("sess-1")))

    assert result is session


def test_get_nonexistent_session_raises_session_not_found_error() -> None:
    repo = FakeSessionRepository()
    use_case = GetSessionUseCase(repo)

    with pytest.raises(SessionNotFoundError):
        asyncio.run(use_case.execute(SessionId("missing")))


# --- DeleteSessionUseCase ---


def test_delete_nonexistent_session_raises_session_not_found_error() -> None:
    repo = FakeSessionRepository()
    cleaner = FakeSessionFilesCleaner()
    use_case = DeleteSessionUseCase(repo, cleaner)

    with pytest.raises(SessionNotFoundError):
        asyncio.run(use_case.execute(SessionId("missing")))

    assert cleaner.deleted_ids == []


def test_delete_existing_session_calls_repo_remove_and_files_cleaner_delete() -> None:
    repo = FakeSessionRepository()
    session = Session.new(SessionId("sess-1"), "S", "", "2026-01-01T00:00:00+00:00")
    asyncio.run(repo.add(session))
    cleaner = FakeSessionFilesCleaner()
    use_case = DeleteSessionUseCase(repo, cleaner)

    asyncio.run(use_case.execute(SessionId("sess-1")))

    assert repo.removed_ids == ["sess-1"]
    assert cleaner.deleted_ids == ["sess-1"]
