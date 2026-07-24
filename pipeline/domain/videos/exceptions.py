"""Domain exceptions for the videos domain."""
from __future__ import annotations


class InvalidVideoStateTransitionError(Exception):
    """Raised when a Video's status is asked to transition illegally."""

    def __init__(self, video_id, from_status, to_status) -> None:
        self.video_id = video_id
        self.from_status = from_status
        self.to_status = to_status
        message = f"Video {video_id}: cannot transition from {from_status} to {to_status}"
        super().__init__(message)
