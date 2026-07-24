"""Shared configuration constants.

Single source of truth for repo-root-relative paths, importable by both
`server.py` (which still owns process wiring and the not-yet-migrated
video/recording routes) and `pipeline.presentation.composition_root`
(which wires the new Sessions feature) without either module importing
the other. `server.py` importing `composition_root`/`sessions_routes`
while `composition_root` also imports something from `server.py` would
be a circular import — this module breaks that cycle.
"""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
SESSIONS_FILE = ROOT / "sessions.json"

# Relocated verbatim from `pipeline/server.py` (Step 7) — the fallback
# instructions used by `StopRecordingUseCase` when neither an explicit
# override nor the session's own instructions are set. Moved here (rather
# than staying a `pipeline.application.recording.use_cases` constant) so
# it lives alongside the other config constants this module already
# centralizes, with a single source of truth instead of a second copy of
# the string.
DEFAULT_RECORD_INSTRUCTIONS = (
    "Analiza la grabación a detalle. A partir de la transcripción de audio (y las notas de "
    "pantalla si existen), genera un resumen ejecutivo, un análisis exhaustivo y una lista "
    "clara de puntos clave, decisiones tomadas y pendientes. No omitas información relevante, "
    "sé preciso con cifras, nombres y fechas."
)
