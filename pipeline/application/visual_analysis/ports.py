"""Ports (interfaces) for the visual-analysis feature.

Implementations live in `pipeline.infrastructure.visual_analysis.*`.
"""
from __future__ import annotations

import typing
from pathlib import Path


class FrameExtractionPort(typing.Protocol):
    def extract_frames(self, video: Path, out_dir: Path, interval_seconds: int) -> list[Path]: ...


class VisionAnalysisProvider(typing.Protocol):
    def describe(self, frame: Path, model: str) -> str: ...
