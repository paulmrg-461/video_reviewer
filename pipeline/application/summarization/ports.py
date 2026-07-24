"""Ports (interfaces) for the summarization feature.

Implementations live in `pipeline.infrastructure.summarization.*`.
"""
from __future__ import annotations

import typing

from pipeline.domain.videos.analysis import AnalysisResult, Summary
from pipeline.domain.videos.transcript import Transcript
from pipeline.domain.videos.visual_note import VisualNotes


class SummarizationProvider(typing.Protocol):
    def summarize(
        self,
        model: str,
        transcript: Transcript,
        visual_notes: VisualNotes | None,
        video_name: str,
        instructions: str | None,
    ) -> tuple[Summary, AnalysisResult]:
        """`model` is the deviation from the Step 5 spec's literal port
        signature: the spec's `summarize(transcript, visual_notes,
        video_name, instructions)` and `OllamaSummarizationProvider(...)`
        constructor both omit any way to carry the Ollama model name, but
        the original `resumir(out_dir, model, nombre, instructions)` takes
        it per-call (it varies per video via `ProcessingOptions.llm_model`).
        Adding it as a parameter here is the minimal fix that preserves that
        real per-call variability without silently hardcoding a model."""
        ...
