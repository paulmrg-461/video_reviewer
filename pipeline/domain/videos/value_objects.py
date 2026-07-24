"""Value objects for the videos domain."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class VideoId:
    """Identifier of a Video. Must be a non-empty, non-blank string."""

    value: str

    def __post_init__(self) -> None:
        if not self.value or not self.value.strip():
            raise ValueError("VideoId value must not be empty or blank")


@dataclass(frozen=True)
class ProcessingOptions:
    """Processing configuration for a video.

    Defaults copied verbatim from the current hardcoded values in
    pipeline/server.py's `_process_video`.
    """

    whisper_model: str = "large-v3"
    device: str = "cuda"
    compute_type: str = "int8_float16"
    llm_model: str = "qwen2.5:14b"
    vision_model: str = "gemma4:e4b"
    frame_interval_seconds: int = 15
    analyze_visual: bool = False
    language: str = "es"
