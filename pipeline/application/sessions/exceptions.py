"""Exceptions raised by Sessions use cases.

Pure application-layer exceptions — no HTTP/FastAPI knowledge here.
Translated to `HTTPException`s by the presentation layer (see
`pipeline.presentation.routes.sessions_routes`).
"""
from __future__ import annotations


class SessionNotFoundError(Exception):
    def __init__(self, session_id: str) -> None:
        self.session_id = session_id
        super().__init__(f"Session not found: {session_id}")


class EmptySessionNameError(Exception):
    def __init__(self) -> None:
        super().__init__("Session name must not be empty")
