"""Markdown-document-shaped value objects produced by the analysis pipeline.

`Summary` and `AnalysisResult` are independent frozen dataclasses (not a
dataclass inheritance hierarchy) that both happen to wrap a single
`content: str` field. Python 3.12 frozen dataclasses can't cleanly mix
frozen/non-frozen bases, and inheriting one frozen dataclass from another
adds little here, so two independent types were chosen for clarity and to
keep `isinstance` checks meaningful (a `Summary` is never accidentally
usable where an `AnalysisResult` is expected).
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class MarkdownDocument:
    """Base shape for a markdown document produced by the pipeline."""

    content: str


@dataclass(frozen=True)
class Summary:
    """The executive summary markdown document (summary.md)."""

    content: str


@dataclass(frozen=True)
class AnalysisResult:
    """The exhaustive analysis markdown document (analysis.md)."""

    content: str
