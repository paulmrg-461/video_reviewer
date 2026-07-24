"""Port (interface) for releasing GPU-resident models.

Implementation lives in `pipeline.infrastructure.gpu.ollama_gpu_scheduler`.
No consumer wires this in yet — that's Step 6.
"""
from __future__ import annotations

import typing


class GpuResourceScheduler(typing.Protocol):
    def release(self, model_name: str) -> None: ...
