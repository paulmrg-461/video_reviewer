"""Tests for `SummarizeVideoUseCase` (Step 5) using a fake
`SummarizationProvider` — no Ollama involved."""
from __future__ import annotations

from pipeline.application.summarization.summarize_video import SummarizeVideoUseCase
from pipeline.domain.videos.analysis import AnalysisResult, Summary
from pipeline.domain.videos.transcript import Segment, Transcript
from pipeline.domain.videos.visual_note import VisualNote, VisualNotes


class _FakeSummarizationProvider:
    def __init__(self, summary: Summary, analysis: AnalysisResult) -> None:
        self._summary = summary
        self._analysis = analysis
        self.calls: list[tuple] = []

    def summarize(self, model, transcript, visual_notes, video_name, instructions):
        self.calls.append((model, transcript, visual_notes, video_name, instructions))
        return self._summary, self._analysis


def _sample_transcript() -> Transcript:
    return Transcript(segments=(Segment(0.0, 1.0, "hola"),), language="es")


def test_execute_writes_summary_and_analysis_and_returns_tuple(tmp_path):
    summary = Summary(content="# Resumen\n")
    analysis = AnalysisResult(content="# Analisis\n")
    provider = _FakeSummarizationProvider(summary, analysis)
    use_case = SummarizeVideoUseCase(provider)

    result = use_case.execute(
        tmp_path, "qwen2.5:14b", _sample_transcript(), None, "video1", None
    )

    assert result == (summary, analysis)
    assert (tmp_path / "summary.md").read_text(encoding="utf-8") == summary.content
    assert (tmp_path / "analysis.md").read_text(encoding="utf-8") == analysis.content
    assert provider.calls[0] == ("qwen2.5:14b", _sample_transcript(), None, "video1", None)


def test_execute_passes_visual_notes_through_to_provider(tmp_path):
    summary = Summary(content="s\n")
    analysis = AnalysisResult(content="a\n")
    provider = _FakeSummarizationProvider(summary, analysis)
    use_case = SummarizeVideoUseCase(provider)
    notes = VisualNotes(notes=(VisualNote(0, "algo en pantalla"),))

    use_case.execute(tmp_path, "qwen2.5:14b", _sample_transcript(), notes, "video1", "instr")

    assert provider.calls[0][2] == notes
    assert provider.calls[0][4] == "instr"


def test_execute_skips_when_both_outputs_already_exist(tmp_path):
    (tmp_path / "summary.md").write_text("ya\n", encoding="utf-8")
    (tmp_path / "analysis.md").write_text("ya\n", encoding="utf-8")
    provider = _FakeSummarizationProvider(Summary("x"), AnalysisResult("y"))
    use_case = SummarizeVideoUseCase(provider)

    result = use_case.execute(
        tmp_path, "qwen2.5:14b", _sample_transcript(), None, "video1", None
    )

    assert result is None
    assert provider.calls == []
