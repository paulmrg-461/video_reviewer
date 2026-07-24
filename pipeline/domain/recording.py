"""`ActiveRecording` — the domain-level record of an in-flight screen
recording.

No state machine (unlike `Video`'s `ProcessingStatus`): a recording is
"active" precisely for as long as it exists in an
`ActiveRecordingsRegistry` (see `pipeline.application.recording.ports`) —
once stopped, the entry is removed entirely, mirroring today's
`del active_recordings[rid]` in `pipeline/server.py`. There is no
"stopped" status to model.

The actual OS-level subprocess handle (a `subprocess.Popen` in practice —
see `pipeline.infrastructure.recording.gpu_screen_recorder_adapter`) is
deliberately NOT a field here: it is an infrastructure concern, not a
domain concept, and this dataclass must stay constructible/comparable in
tests without ever touching `subprocess`. The registry holds the handle
alongside the `ActiveRecording` instance instead (see
`ActiveRecordingsRegistry.track`/`.get`).
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class ActiveRecording:
    id: str
    session_id: str
    output_path: Path
    started_at: str
