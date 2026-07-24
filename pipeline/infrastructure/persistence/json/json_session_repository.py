"""JsonSessionRepository — `SessionRepository` port backed by
`SessionsJsonGateway`.
"""
from __future__ import annotations

from pipeline.domain.sessions.session import Session, SessionId

from .mappers import session_dict_to_domain, session_domain_to_dict
from .sessions_json_gateway import SessionsJsonGateway


class JsonSessionRepository:
    """`SessionRepository` implementation over `SessionsJsonGateway`.

    Speaks entirely in `Session` domain objects; delegates all raw
    dict/file access to the shared gateway. Must be constructed with the
    same gateway instance as any `JsonVideoRepository` persisting to the
    same file (see `SessionsJsonGateway`'s docstring).
    """

    def __init__(self, gateway: SessionsJsonGateway) -> None:
        self._gateway = gateway

    async def add(self, session: Session) -> None:
        if session.video_ids:
            # Every current caller creates a Session before any Video
            # exists for it, so this repository has no full Video objects
            # to persist alongside a non-empty video_ids list — only
            # JsonVideoRepository can materialize those. Guard against
            # silent data loss rather than writing an empty `videos: []`
            # that would disagree with `session.video_ids`.
            raise ValueError(
                "JsonSessionRepository.add() cannot persist a Session with "
                "non-empty video_ids — add the session first, then add "
                "each Video via JsonVideoRepository.add()"
            )
        d = session_domain_to_dict(session, videos=[])
        await self._gateway.save_session_dict(session.id.value, d)

    async def get(self, session_id: SessionId) -> Session | None:
        d = await self._gateway.get_session(session_id.value)
        if d is None:
            return None
        return session_dict_to_domain(d)

    async def list_all(self) -> list[Session]:
        dicts = await self._gateway.list_sessions()
        return [session_dict_to_domain(d) for d in dicts]

    async def remove(self, session_id: SessionId) -> bool:
        return await self._gateway.delete_session(session_id.value)
