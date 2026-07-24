"""Filesystem-backed `SessionFilesCleaner`.

Ports today's inline cascade-delete logic from the
`DELETE /api/sessions/{sid}` route in `pipeline/server.py`
(`shutil.rmtree(ROOT / "sessions" / sid)` if it exists).
"""
from __future__ import annotations

import shutil
from pathlib import Path

from pipeline.domain.sessions.session import SessionId


class FilesystemSessionFilesCleaner:
    def __init__(self, sessions_root: Path) -> None:
        self._sessions_root = sessions_root

    async def delete(self, session_id: SessionId) -> None:
        session_dir = self._sessions_root / session_id.value
        if session_dir.exists():
            shutil.rmtree(session_dir)
