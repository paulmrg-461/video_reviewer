"""Use case: extract frames from a video and describe each with a vision
model, producing `visual_notes.md`.

Ports the orchestration that used to live inline in `pipeline/visual.py`'s
`analizar_visual()`: skip-if-`visual_notes.md`-exists, extract frames into a
tempdir, describe each frame (swallowing per-frame description errors into a
placeholder note, matching today's behavior), build `VisualNote`/
`VisualNotes` domain objects, write `visual_notes.md` via
`visual_notes.to_markdown()`.

Return-value contract (documented choice — the spec flagged this as open
because today's `analizar_visual()` returns the existing `Path` on skip, not
`None`/a `VisualNotes`, and the only caller, `server.py`'s `_run_visual`,
ignores the return value entirely, so there is real freedom here):
  - `None` if `visual_notes.md` already exists (skip) — simplest option,
    avoids re-reading and parsing the file back into a `VisualNotes` object
    just to satisfy a return contract nothing consumes.
  - `None` if zero frames were extracted (matches today's `analizar_visual`
    returning `None` in that case — a legitimate outcome for short videos).
  - The `VisualNotes` object on a real, newly-produced run.
"""
from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory

from pipeline.application.visual_analysis.ports import (
    FrameExtractionPort,
    VisionAnalysisProvider,
)
from pipeline.domain.videos.visual_note import VisualNote, VisualNotes


def _fmt_ts(segundos: int) -> str:
    """Seconds -> 'HH:MM:SS' for the operator-visible progress log below.
    Copied from `visual.py`'s original `_fmt_ts` (also duplicated in
    `pipeline.domain.videos.visual_note` for the markdown-formatting
    concern) — kept local here rather than reaching into that module's
    private helper, since this one only serves console output."""
    s = int(segundos)
    h, s = divmod(s, 3600)
    m, s = divmod(s, 60)
    return f"{h:02d}:{m:02d}:{s:02d}"


class AnalyzeVisualUseCase:
    def __init__(
        self,
        frame_extractor: FrameExtractionPort,
        vision_provider: VisionAnalysisProvider,
    ) -> None:
        self._frame_extractor = frame_extractor
        self._vision_provider = vision_provider

    def execute(
        self,
        video: Path,
        out_dir: Path,
        vision_model: str,
        interval_seconds: int,
    ) -> VisualNotes | None:
        notes_path = out_dir / "visual_notes.md"
        if notes_path.exists():
            print(f"  [skip] notas visuales ya existen en {out_dir}")
            return None

        with TemporaryDirectory() as tmp:
            print(f"  extrayendo frames cada {interval_seconds}s...")
            frames = self._frame_extractor.extract_frames(video, Path(tmp), interval_seconds)
            if not frames:
                print("  (sin frames extraídos, se omite análisis visual)")
                return None

            print(f"  {len(frames)} frames a analizar con {vision_model}")
            notes: list[VisualNote] = []
            for i, frame in enumerate(frames):
                ts_seconds = i * interval_seconds
                print(f"    VISION frame {i + 1}/{len(frames)} [{_fmt_ts(ts_seconds)}]")
                try:
                    desc = self._vision_provider.describe(frame, vision_model)
                except Exception as exc:
                    desc = f"(error analizando frame: {exc})"
                notes.append(VisualNote(timestamp_seconds=ts_seconds, description=desc))

        visual_notes = VisualNotes(notes=tuple(notes))
        notes_path.write_text(visual_notes.to_markdown(), encoding="utf-8")
        print(f"  ✓ {notes_path.name} ({len(notes)} frames)")

        return visual_notes
