"""Transcript value objects.

Formats reproduce pipeline/transcribe.py's current output byte-for-byte:
  - `plain_text()` mirrors `txt_path.write_text("\\n".join(txt_lines) + "\\n")`
  - `to_srt()` mirrors `srt_path.write_text("\\n".join(srt_lines))`, where each
    `srt_lines` entry is already `f"{i}\\n{start} --> {end}\\n{text}\\n"`
    (note the trailing "\\n" baked into each entry, and NO extra trailing
    "\\n" appended after the final join — unlike `plain_text()`).
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Segment:
    start: float
    end: float
    text: str


def _fmt_ts(segundos: float) -> str:
    """Seconds -> 'HH:MM:SS,mmm' (SRT format). Copied from transcribe.py."""
    ms = int(round(segundos * 1000))
    h, ms = divmod(ms, 3_600_000)
    m, ms = divmod(ms, 60_000)
    s, ms = divmod(ms, 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


@dataclass(frozen=True)
class Transcript:
    segments: tuple[Segment, ...]
    language: str

    def plain_text(self) -> str:
        return "\n".join(seg.text for seg in self.segments) + "\n"

    def to_srt(self) -> str:
        srt_lines = [
            f"{i}\n{_fmt_ts(seg.start)} --> {_fmt_ts(seg.end)}\n{seg.text}\n"
            for i, seg in enumerate(self.segments, start=1)
        ]
        return "\n".join(srt_lines)
