"""Ports (interfaces) for Session persistence.

Implementations live in `pipeline.infrastructure.persistence.*`. Nothing in
`pipeline.domain` or `pipeline.application` may depend on a concrete
persistence technology — only on this Protocol.
"""
from __future__ import annotations

import typing

from pipeline.domain.sessions.session import Session, SessionId


class SessionRepository(typing.Protocol):
    """Persistence port for `Session` aggregates."""

    async def add(self, session: Session) -> None: ...

    async def get(self, session_id: SessionId) -> Session | None: ...

    async def list_all(self) -> list[Session]:
        """Returns all sessions sorted by `created_at` descending (newest
        first), matching today's `SessionStore.list_sessions` behavior."""
        ...

    async def remove(self, session_id: SessionId) -> bool: ...


class SessionFilesCleaner(typing.Protocol):
    """Deletes on-disk artifacts (the session's directory tree) for a
    session. Used by `DeleteSessionUseCase` to perform the cascade file
    cleanup that today's `DELETE /api/sessions/{sid}` route does inline
    with `shutil.rmtree`."""

    async def delete(self, session_id: SessionId) -> None: ...
