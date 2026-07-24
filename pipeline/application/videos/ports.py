"""Ports (interfaces) for Video persistence.

Implementations live in `pipeline.infrastructure.persistence.*`. Nothing in
`pipeline.domain` or `pipeline.application` may depend on a concrete
persistence technology — only on this Protocol.
"""
from __future__ import annotations

import typing

from pipeline.domain.sessions.session import SessionId
from pipeline.domain.videos.value_objects import VideoId
from pipeline.domain.videos.video import Video


class VideoRepository(typing.Protocol):
    """Persistence port for `Video` aggregates.

    `Video` is its own aggregate root (not nested inside `Session`), so it
    is addressed by `(session_id, video_id)` rather than reached through a
    loaded `Session` object.
    """

    async def add(self, video: Video) -> None: ...

    async def get(self, session_id: SessionId, video_id: VideoId) -> Video | None: ...

    async def update(self, video: Video) -> bool:
        """Upsert semantics: updates the video if it already exists in its
        session, inserts it otherwise — mirrors today's
        `SessionStore.update_video`."""
        ...

    async def remove(self, session_id: SessionId, video_id: VideoId) -> bool: ...

    async def list_by_session(self, session_id: SessionId) -> list[Video]: ...
