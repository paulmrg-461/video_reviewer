"""SessionsJsonGateway — low-level, dict-based persistence over sessions.json.

`list_sessions`, `get_session`, `create_session`, `delete_session`,
`update_video` and `get_video` are ported VERBATIM (same load/save/lock
semantics, same on-disk JSON shape, same id/timestamp generation) from
`pipeline.server.SessionStore`, merely renamed. This class still speaks
entirely in raw dicts — it does NOT know about `Session`/`Video` domain
objects; that translation lives in `mappers.py` and is used by
`JsonSessionRepository`/`JsonVideoRepository`.

On-disk shape (unchanged):
    {"sessions": {sid: {id, name, instructions, created_at, videos: [...]}}}

This is the ONE class allowed to touch `sessions.json` directly and hold
the `asyncio.Lock` guarding it. `JsonSessionRepository` and
`JsonVideoRepository` MUST be constructed with the SAME gateway instance
when they persist to the same file — two separate gateways (and therefore
two separate locks) over one file would reintroduce the exact
concurrent-write race the lock exists to prevent.
"""
from __future__ import annotations

import asyncio
import json
import uuid
from datetime import datetime, timezone
from pathlib import Path


class SessionsJsonGateway:
    def __init__(self, path: Path) -> None:
        self.path = path
        self._lock = asyncio.Lock()

    def _load(self) -> dict:
        if self.path.exists():
            return json.loads(self.path.read_text())
        return {"sessions": {}}

    def _save(self, data: dict) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(data, ensure_ascii=False, indent=2))

    # --- Ported verbatim from pipeline.server.SessionStore ---

    async def list_sessions(self) -> list[dict]:
        async with self._lock:
            data = self._load()
        return sorted(data["sessions"].values(), key=lambda s: s["created_at"], reverse=True)

    async def get_session(self, sid: str) -> dict | None:
        async with self._lock:
            data = self._load()
        return data["sessions"].get(sid)

    async def create_session(self, name: str, instructions: str = "") -> dict:
        sid = uuid.uuid4().hex[:12]
        session = {
            "id": sid,
            "name": name.strip(),
            "instructions": instructions.strip(),
            "created_at": datetime.now(timezone.utc).isoformat(),
            "videos": [],
        }
        async with self._lock:
            data = self._load()
            data["sessions"][sid] = session
            self._save(data)
        return session

    async def delete_session(self, sid: str) -> bool:
        async with self._lock:
            data = self._load()
            if sid not in data["sessions"]:
                return False
            del data["sessions"][sid]
            self._save(data)
        return True

    async def update_video(self, sid: str, video: dict) -> bool:
        async with self._lock:
            data = self._load()
            session = data["sessions"].get(sid)
            if not session:
                return False
            for i, v in enumerate(session["videos"]):
                if v["id"] == video["id"]:
                    session["videos"][i] = video
                    self._save(data)
                    return True
            session["videos"].append(video)
            self._save(data)
            return True

    async def get_video(self, sid: str, vid: str) -> dict | None:
        session = await self.get_session(sid)
        if not session:
            return None
        for v in session["videos"]:
            if v["id"] == vid:
                return v
        return None

    # --- New in Step 2: needed so the repositories can work in terms of
    # already-constructed domain objects (which already carry their own
    # id) instead of being forced through `create_session`'s "mint a new
    # id from a bare name/instructions" shape. Original methods above are
    # left untouched for later-step compatibility. ---

    async def save_session_dict(self, sid: str, session: dict) -> None:
        """Insert or overwrite a full session dict under `sid` as-is
        (preserving whatever id/created_at/videos it already carries).
        Used by `JsonSessionRepository.add()`."""
        async with self._lock:
            data = self._load()
            data["sessions"][sid] = session
            self._save(data)

    async def remove_video(self, sid: str, vid: str) -> bool:
        """Remove a single video dict from a session's `videos` list —
        mirrors today's `DELETE /api/sessions/{sid}/videos/{vid}` endpoint
        in `pipeline/server.py`. Added for `JsonVideoRepository.remove()`."""
        async with self._lock:
            data = self._load()
            session = data["sessions"].get(sid)
            if not session:
                return False
            videos = session["videos"]
            for i, v in enumerate(videos):
                if v["id"] == vid:
                    del videos[i]
                    self._save(data)
                    return True
            return False
