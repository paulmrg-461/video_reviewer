"""System `Clock`.

Format matches today's `created_at` timestamp generation in
`pipeline/server.py` exactly (`datetime.now(timezone.utc).isoformat()`).
"""
from __future__ import annotations

from datetime import datetime, timezone


class SystemClock:
    def now_iso(self) -> str:
        return datetime.now(timezone.utc).isoformat()
