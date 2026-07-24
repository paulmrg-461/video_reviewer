"""Ollama GPU-release adapter.

Ports today's `server.py`'s `_liberar_ollama(modelo)` (a near-identical
duplicate, `liberar_ollama`, also lives in `run_all.py` — the two are the
same 6-line `subprocess.run(["ollama", "stop", model], ...)` wrapper).

No consumer wires this in yet — that's Step 6.
"""
from __future__ import annotations

import subprocess


class OllamaGpuScheduler:
    def release(self, model_name: str) -> None:
        try:
            subprocess.run(
                ["ollama", "stop", model_name],
                check=False,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        except FileNotFoundError:
            pass
