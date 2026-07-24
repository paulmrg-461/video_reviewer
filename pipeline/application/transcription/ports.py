"""Ports (interfaces) for the transcription feature.

Implementations live in `pipeline.infrastructure.transcription.*`.
"""
from __future__ import annotations

import typing
from pathlib import Path

from pipeline.domain.videos.transcript import Transcript


class AudioExtractionPort(typing.Protocol):
    def extract(self, video: Path, wav_out: Path) -> None: ...


class TranscriptionProvider(typing.Protocol):
    def transcribe(
        self,
        audio: Path,
        language: str,
        model_name: str,
        device: str,
        compute_type: str,
    ) -> Transcript: ...
