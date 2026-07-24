"""UUID-based `IdProvider`.

Format matches today's id generation used by `create_session`, `add_video`
and the recording routes in `pipeline/server.py`
(`uuid.uuid4().hex[:12]`) exactly, so ids minted through this provider are
indistinguishable from ids already present in `sessions.json`.
"""
from __future__ import annotations

import uuid


class UuidIdProvider:
    def new_id(self) -> str:
        return uuid.uuid4().hex[:12]
