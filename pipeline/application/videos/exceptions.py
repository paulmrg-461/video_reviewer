"""Exceptions raised by Videos use cases.

Pure application-layer exceptions — no HTTP/FastAPI knowledge here.
Translated to `HTTPException`s by the presentation layer (see
`pipeline.presentation.routes.videos_routes`).

`SessionNotFoundError` is NOT redefined here — it already exists in
`pipeline.application.sessions.exceptions` (built in Step 3) and is
reused as-is for the "session does not exist" checks the Videos use
cases also need, rather than forking a second copy of the same concept.
"""
from __future__ import annotations


class VideoNotFoundError(Exception):
    def __init__(self, session_id: str, video_id: str) -> None:
        self.session_id = session_id
        self.video_id = video_id
        super().__init__(f"Video not found: session={session_id} video={video_id}")
