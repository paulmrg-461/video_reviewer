"""Use case: summarize a transcript (and optional visual notes) into
`summary.md` + `analysis.md`.

Ports the orchestration that used to live inline in `pipeline/summarize.py`'s
`resumir()`: skip-if-both-outputs-exist, delegate the map-reduce work to a
`SummarizationProvider`, write `.content` to disk.

Note: `execute()` takes an explicit `model: str` param not present in the
Step 5 spec's literal use-case signature — see `pipeline.application.
summarization.ports.SummarizationProvider` docstring for why (the original
`resumir(out_dir, model, nombre, instructions)` needs a per-call model
name and nothing else in the spec carries it).
"""
from __future__ import annotations

from pathlib import Path

from pipeline.application.summarization.ports import SummarizationProvider
from pipeline.domain.videos.analysis import AnalysisResult, Summary
from pipeline.domain.videos.transcript import Transcript
from pipeline.domain.videos.visual_note import VisualNotes


class SummarizeVideoUseCase:
    def __init__(self, provider: SummarizationProvider) -> None:
        self._provider = provider

    def execute(
        self,
        out_dir: Path,
        model: str,
        transcript: Transcript,
        visual_notes: VisualNotes | None,
        video_name: str,
        instructions: str | None,
    ) -> tuple[Summary, AnalysisResult] | None:
        summary_path = out_dir / "summary.md"
        analysis_path = out_dir / "analysis.md"
        if summary_path.exists() and analysis_path.exists():
            print(f"  [skip] resumen ya existe en {out_dir}")
            return None

        summary, analysis = self._provider.summarize(
            model, transcript, visual_notes, video_name, instructions
        )

        summary_path.write_text(summary.content, encoding="utf-8")
        analysis_path.write_text(analysis.content, encoding="utf-8")

        return summary, analysis
