"""JsonVideoRepository — `VideoRepository` port backed by
`SessionsJsonGateway`.
"""
from __future__ import annotations

from pipeline.domain.sessions.session import SessionId
from pipeline.domain.videos.value_objects import VideoId
from pipeline.domain.videos.video import Video

from .mappers import video_dict_to_domain, video_domain_to_dict
from .sessions_json_gateway import SessionsJsonGateway


class JsonVideoRepository:
    """`VideoRepository` implementation over `SessionsJsonGateway`.

    Must be constructed with the same gateway instance as any
    `JsonSessionRepository` persisting to the same file (see
    `SessionsJsonGateway`'s docstring) — both repositories share the one
    lock guarding `sessions.json`.
    """

    def __init__(self, gateway: SessionsJsonGateway) -> None:
        self._gateway = gateway

    async def add(self, video: Video) -> None:
        # The gateway's `update_video` already has upsert semantics, which
        # is a superset of "add" — there is no separate insert-only path in
        # today's storage format, so both `add` and `update` delegate to it.
        d = video_domain_to_dict(video)
        await self._gateway.update_video(video.session_id, d)

    async def get(self, session_id: SessionId, video_id: VideoId) -> Video | None:
        d = await self._gateway.get_video(session_id.value, video_id.value)
        if d is None:
            return None
        return video_dict_to_domain(d, session_id.value)

    async def update(self, video: Video) -> bool:
        d = video_domain_to_dict(video)
        return await self._gateway.update_video(video.session_id, d)

    async def remove(self, session_id: SessionId, video_id: VideoId) -> bool:
        return await self._gateway.remove_video(session_id.value, video_id.value)

    async def list_by_session(self, session_id: SessionId) -> list[Video]:
        session_dict = await self._gateway.get_session(session_id.value)
        if session_dict is None:
            return []
        return [
            video_dict_to_domain(v, session_id.value)
            for v in session_dict.get("videos", [])
        ]
