"""Session entity and its identifier value object.

Mirrors the style of `pipeline.domain.videos.value_objects.VideoId` and
`pipeline.domain.videos.video.Video` from Step 1.
"""
from __future__ import annotations

from dataclasses import dataclass

from pipeline.domain.videos.value_objects import VideoId


@dataclass(frozen=True)
class SessionId:
    """Identifier of a Session. Must be a non-empty, non-blank string."""

    value: str

    def __post_init__(self) -> None:
        if not self.value or not self.value.strip():
            raise ValueError("SessionId value must not be empty or blank")


class Session:
    """Mutable entity representing a named group of videos with shared
    default instructions.

    Holds only `video_ids` references, NOT full `Video` objects — `Video` is
    its own aggregate root (confirmed design for this migration), persisted
    in the same physical file but not nested inside this domain object.
    """

    def __init__(
        self,
        id: SessionId,
        name: str,
        instructions: str,
        created_at: str,
        video_ids: list[VideoId],
    ) -> None:
        self.id = id
        self.name = name
        self.instructions = instructions
        self.created_at = created_at
        self.video_ids = video_ids

    @classmethod
    def new(
        cls, id: SessionId, name: str, instructions: str, created_at: str
    ) -> "Session":
        return cls(
            id=id,
            name=name,
            instructions=instructions,
            created_at=created_at,
            video_ids=[],
        )

    def add_video_id(self, video_id: VideoId) -> None:
        if video_id not in self.video_ids:
            self.video_ids.append(video_id)

    def remove_video_id(self, video_id: VideoId) -> None:
        self.video_ids = [v for v in self.video_ids if v != video_id]
