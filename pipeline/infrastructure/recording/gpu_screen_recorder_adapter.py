"""`GpuScreenRecorderAdapter` — thin `ScreenRecorderPort` wrapper around
`pipeline/recorder.py` (untouched by this migration, already minimal).

`recorder.py` imports only `signal`, `subprocess` and `pathlib` — no heavy
GPU/ML deps like the transcription/vision adapters have — so, unlike
`server.py`'s old `_record_start`/`_record_stop` (which imported it lazily
inside each function, presumably out of caution near the GPU-heavy
imports elsewhere in that file), a plain module-top import here is fine
and simpler.
"""
from __future__ import annotations

import subprocess
from pathlib import Path

from pipeline import recorder
from pipeline.application.recording.exceptions import RecorderStartFailedError


class GpuScreenRecorderAdapter:
    def start(self, output: Path) -> subprocess.Popen:
        try:
            return recorder.iniciar(output)
        except recorder.RecorderError as exc:
            raise RecorderStartFailedError(str(exc)) from exc

    def stop(self, handle: object, timeout: float = 45.0) -> bool:
        return recorder.detener(handle, timeout)

    def is_alive(self, handle: object) -> bool:
        return recorder.esta_vivo(handle)
