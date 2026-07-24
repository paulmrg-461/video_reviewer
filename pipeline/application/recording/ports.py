"""Ports (interfaces) for the Recording feature.

Implementations live in `pipeline.infrastructure.recording`. Nothing in
`pipeline.domain` or `pipeline.application` may depend on a concrete
recording technology or a concrete `sessions.json` gateway — only on
these Protocols.
"""
from __future__ import annotations

import typing
from pathlib import Path

from pipeline.domain.recording import ActiveRecording


class ScreenRecorderPort(typing.Protocol):
    """Wraps the OS-level screen recording process (`gpu-screen-recorder`
    in practice — see
    `pipeline.infrastructure.recording.gpu_screen_recorder_adapter`).

    `start`/`stop` exchange an opaque handle (a `subprocess.Popen` in
    practice) that this port deliberately does not name, so the
    application layer never has to import `subprocess`.
    """

    def start(self, output: Path) -> object: ...

    def stop(self, handle: object, timeout: float = 15.0) -> bool: ...


class ActiveRecordingsRegistry(typing.Protocol):
    """Tracks in-flight recordings and their OS-level handles.

    Given a port here, unlike `processing_queue` (Step 6), which stayed a
    bare `asyncio.Queue` with no port/adapter pair: `get_by_session` is a
    real query need a plain queue never had (it's what the
    concurrent-recording guard in `StartRecordingUseCase` is built on),
    and — unlike the queue — "swap the backing store for something that
    survives a server restart" is a plausible future need for in-flight
    recordings specifically. Today's only implementation
    (`InMemoryActiveRecordingsRegistry`) is still just a dict, matching
    the processing queue's actual current shape; only the reasoning for
    why a seam is worth it here differs from Step 6's reasoning for why
    one wasn't.
    """

    def track(self, recording: ActiveRecording, handle: object) -> None: ...

    def get(self, recording_id: str) -> tuple[ActiveRecording, object] | None: ...

    def untrack(self, recording_id: str) -> None: ...

    def list_all(self) -> list[ActiveRecording]: ...

    def get_by_session(self, session_id: str) -> ActiveRecording | None: ...


class SessionGateway(typing.Protocol):
    """The minimal slice of `SessionsJsonGateway` the Recording use cases
    need for pure session-existence/instructions-fallback checks — the
    same raw-dict-in/dict-out style Steps 3/4 used for the *routers'*
    equivalent checks (see e.g. `pipeline.presentation.routes.
    videos_routes.add_video`), just promoted to a named Protocol here
    because, unlike those routers, these use cases receive the gateway as
    a constructor dependency rather than importing the shared instance
    directly — the first Recording-feature-specific application-layer
    seam over the gateway.
    """

    async def get_session(self, session_id: str) -> dict | None: ...
