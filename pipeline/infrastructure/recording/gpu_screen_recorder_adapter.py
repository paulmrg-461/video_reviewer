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


class GpuScreenRecorderAdapter:
    def start(self, output: Path) -> subprocess.Popen:
        return recorder.iniciar(output)

    def stop(self, handle: object, timeout: float = 15.0) -> bool:
        return recorder.detener(handle, timeout)
