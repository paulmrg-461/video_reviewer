"""`InMemoryActiveRecordingsRegistry` — plain dict-backed
`ActiveRecordingsRegistry`, replacing today's `active_recordings: dict[str,
dict]` module global in `pipeline/server.py`.
"""
from __future__ import annotations

from pipeline.domain.recording import ActiveRecording


class InMemoryActiveRecordingsRegistry:
    def __init__(self) -> None:
        self._entries: dict[str, tuple[ActiveRecording, object]] = {}

    def track(self, recording: ActiveRecording, handle: object) -> None:
        self._entries[recording.id] = (recording, handle)

    def get(self, recording_id: str) -> tuple[ActiveRecording, object] | None:
        return self._entries.get(recording_id)

    def untrack(self, recording_id: str) -> None:
        self._entries.pop(recording_id, None)

    def list_all(self) -> list[ActiveRecording]:
        return [recording for recording, _handle in self._entries.values()]

    def get_by_session(self, session_id: str) -> ActiveRecording | None:
        for recording, _handle in self._entries.values():
            if recording.session_id == session_id:
                return recording
        return None
