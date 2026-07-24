"""Visual note value objects.

`to_markdown()` reproduces pipeline/visual.py's current
`"\\n\\n".join(lines) + "\\n"` format exactly, where each line is
`f"### [{ts}]\\n{desc}"` and `ts` is 'HH:MM:SS' (no milliseconds — distinct
from the transcript's SRT timestamp format, do not conflate the two).
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class VisualNote:
    timestamp_seconds: int
    description: str


def _fmt_ts(segundos: int) -> str:
    """Seconds -> 'HH:MM:SS' (no milliseconds). Copied from visual.py."""
    s = int(segundos)
    h, s = divmod(s, 3600)
    m, s = divmod(s, 60)
    return f"{h:02d}:{m:02d}:{s:02d}"


@dataclass(frozen=True)
class VisualNotes:
    notes: tuple[VisualNote, ...]

    def to_markdown(self) -> str:
        lines = [
            f"### [{_fmt_ts(note.timestamp_seconds)}]\n{note.description}"
            for note in self.notes
        ]
        return "\n\n".join(lines) + "\n"
