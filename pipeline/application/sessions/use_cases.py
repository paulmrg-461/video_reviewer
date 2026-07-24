"""Sessions use cases.

Pure application logic sitting between the presentation routes and the
`SessionRepository`/`SessionFilesCleaner` ports: no FastAPI, no raw
dict/JSON handling, no filesystem calls.
"""
from __future__ import annotations

from pipeline.application.sessions.exceptions import (
    EmptySessionNameError,
    SessionNotFoundError,
)
from pipeline.application.sessions.ports import SessionFilesCleaner, SessionRepository
from pipeline.application.shared.ports import Clock, IdProvider
from pipeline.domain.sessions.session import Session, SessionId


class CreateSessionUseCase:
    def __init__(
        self,
        session_repo: SessionRepository,
        id_provider: IdProvider,
        clock: Clock,
    ) -> None:
        self._session_repo = session_repo
        self._id_provider = id_provider
        self._clock = clock

    async def execute(self, name: str, instructions: str = "") -> Session:
        if not name.strip():
            raise EmptySessionNameError()
        session = Session.new(
            id=SessionId(self._id_provider.new_id()),
            name=name.strip(),
            instructions=instructions.strip(),
            created_at=self._clock.now_iso(),
        )
        await self._session_repo.add(session)
        return session


class ListSessionsUseCase:
    def __init__(self, session_repo: SessionRepository) -> None:
        self._session_repo = session_repo

    async def execute(self) -> list[Session]:
        return await self._session_repo.list_all()


class GetSessionUseCase:
    def __init__(self, session_repo: SessionRepository) -> None:
        self._session_repo = session_repo

    async def execute(self, session_id: SessionId) -> Session:
        session = await self._session_repo.get(session_id)
        if session is None:
            raise SessionNotFoundError(session_id.value)
        return session


class DeleteSessionUseCase:
    def __init__(
        self,
        session_repo: SessionRepository,
        files_cleaner: SessionFilesCleaner,
    ) -> None:
        self._session_repo = session_repo
        self._files_cleaner = files_cleaner

    async def execute(self, session_id: SessionId) -> None:
        removed = await self._session_repo.remove(session_id)
        if not removed:
            raise SessionNotFoundError(session_id.value)
        await self._files_cleaner.delete(session_id)
