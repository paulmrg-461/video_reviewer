"""Exceptions raised by Recording use cases.

Pure application-layer exceptions — no HTTP/FastAPI knowledge here.
Translated to `HTTPException`s by the presentation layer (see
`pipeline.presentation.routes.recording_routes`).

`SessionNotFoundError` and `VideoNotFoundError` are NOT redefined here —
they already exist in `pipeline.application.sessions.exceptions` (Step 3)
and `pipeline.application.videos.exceptions` (Step 4) respectively, and
are reused as-is rather than forking copies of the same concepts.
"""
from __future__ import annotations


class RecorderNotAvailableError(Exception):
    """Today: `_record_start` lets `FileNotFoundError` (from
    `subprocess.Popen` when `gpu-screen-recorder` isn't installed) escape
    into `start_recording`, which turns it into `HTTPException(500, ...)`.
    """

    def __init__(self) -> None:
        super().__init__("gpu-screen-recorder no está instalado")


class RecordingNotFoundError(Exception):
    def __init__(self, session_id: str, recording_id: str) -> None:
        self.session_id = session_id
        self.recording_id = recording_id
        super().__init__(
            f"Recording not found: session={session_id} recording={recording_id}"
        )


class RecordingSaveFailedError(Exception):
    def __init__(self) -> None:
        super().__init__("La grabación no se guardó correctamente")


class ConcurrentRecordingError(Exception):
    """NEW in Step 7 — fixes the latent bug where nothing prevented
    starting two concurrent recordings for the same session (no check
    existed anywhere in `start_recording`)."""

    def __init__(self, session_id: str) -> None:
        self.session_id = session_id
        super().__init__(f"Session {session_id} already has an active recording")


class NotARecordingError(Exception):
    """Today: `delete_recording_file` raises
    `HTTPException(400, "Este video no es una grabación gestionada por la
    app")` when `video.get("is_recording")` is falsy."""

    def __init__(self, session_id: str, video_id: str) -> None:
        self.session_id = session_id
        self.video_id = video_id
        super().__init__(
            f"Video is not an app-managed recording: session={session_id} "
            f"video={video_id}"
        )


class RecordingPathTraversalError(Exception):
    """Today: `delete_recording_file` raises
    `HTTPException(400, "Ruta fuera del directorio de grabaciones")` when
    the recording's `original_path`, resolved, does not sit under
    `sessions_root`."""

    def __init__(self, path: str) -> None:
        self.path = path
        super().__init__(f"Path outside recordings directory: {path}")
