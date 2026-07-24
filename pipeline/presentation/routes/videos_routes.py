"""Videos routes — the 9 endpoints migrated in Step 4 of the
hexagonal-architecture migration.

4 routes are use-case-backed (`add_video`, `retry_video`, `delete_video`,
`save_output`); the other 5 (`transcript`, `visual`, `srt`, `summary`,
`analysis`) are pure file reads with no logic worth extracting — moved
here verbatim, same as Step 3's precedent in `sessions_routes.py` for its
own pure-read routes.

Out of scope for this step (still in `pipeline/server.py`): recording
routes, `_process_video`/`_worker`/`processing_queue`.
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request

from pipeline.application.videos.exceptions import VideoNotFoundError
from pipeline.domain.videos.exceptions import InvalidVideoStateTransitionError
from pipeline.presentation.composition_root import (
    add_videos_use_case,
    delete_video_use_case,
    gateway,
    retry_video_use_case,
    save_artifacts_use_case,
)
from pipeline.shared.config import ROOT

router = APIRouter()


@router.post("/api/sessions/{sid}/videos")
async def add_video(sid: str, req: Request):
    session = await gateway.get_session(sid)
    if not session:
        raise HTTPException(404, "Sesión no encontrada")

    body = await req.json()
    paths = body.get("paths", [])
    if isinstance(paths, str):
        paths = [paths]
    instructions = body.get("instructions", "")
    language = body.get("language", "es")
    analyze_visual = bool(body.get("analyze_visual", False))

    videos = await add_videos_use_case.execute(
        session_id=sid,
        paths=paths,
        instructions=instructions,
        language=language,
        analyze_visual=analyze_visual,
        session_instructions_fallback=session.get("instructions", ""),
    )

    added = [
        {
            "id": v.id.value,
            "name": v.name,
            "original_path": v.original_path,
            "status": v.status.value,
            "instructions": v.instructions,
            "language": v.options.language,
            "analyze_visual": v.options.analyze_visual,
            "output_dir": v.output_dir,
            "error": v.error,
        }
        for v in videos
    ]
    return {"added": added}


@router.post("/api/sessions/{sid}/videos/{vid}/retry")
async def retry_video(sid: str, vid: str):
    session = await gateway.get_session(sid)
    if not session:
        raise HTTPException(404, "Sesión no encontrada")

    try:
        await retry_video_use_case.execute(sid, vid)
    except VideoNotFoundError:
        raise HTTPException(404, "Video no encontrado")
    except InvalidVideoStateTransitionError as exc:
        # Behavior change from today (which silently double-enqueues
        # regardless of status) — this is the fix for the retry-race bug.
        raise HTTPException(
            409,
            f"No se puede reintentar un video en estado '{exc.from_status.value}': "
            "solo se puede reintentar un video en estado 'error'",
        )
    return {"ok": True}


@router.delete("/api/sessions/{sid}/videos/{vid}")
async def delete_video(sid: str, vid: str):
    session = await gateway.get_session(sid)
    if not session:
        raise HTTPException(404, "Sesión no encontrada")

    await delete_video_use_case.execute(sid, vid)
    return {"ok": True}


@router.get("/api/sessions/{sid}/videos/{vid}/transcript")
async def get_transcript(sid: str, vid: str):
    out_dir = ROOT / "sessions" / sid / vid
    txt = out_dir / "transcript.txt"
    if not txt.exists():
        raise HTTPException(404, "Transcripción no disponible")
    return {"text": txt.read_text(encoding="utf-8")}


@router.get("/api/sessions/{sid}/videos/{vid}/visual")
async def get_visual_notes(sid: str, vid: str):
    out_dir = ROOT / "sessions" / sid / vid
    notes = out_dir / "visual_notes.md"
    if not notes.exists():
        raise HTTPException(404, "Notas visuales no disponibles")
    return {"text": notes.read_text(encoding="utf-8")}


@router.get("/api/sessions/{sid}/videos/{vid}/srt")
async def get_srt(sid: str, vid: str):
    out_dir = ROOT / "sessions" / sid / vid
    srt = out_dir / "transcript.srt"
    if not srt.exists():
        raise HTTPException(404, "SRT no disponible")
    return {"text": srt.read_text(encoding="utf-8")}


@router.get("/api/sessions/{sid}/videos/{vid}/summary")
async def get_summary(sid: str, vid: str):
    out_dir = ROOT / "sessions" / sid / vid
    summary = out_dir / "summary.md"
    if not summary.exists():
        raise HTTPException(404, "Resumen no disponible")
    return {"text": summary.read_text(encoding="utf-8"), "path": str(summary)}


@router.get("/api/sessions/{sid}/videos/{vid}/analysis")
async def get_analysis(sid: str, vid: str):
    out_dir = ROOT / "sessions" / sid / vid
    analysis = out_dir / "analysis.md"
    if not analysis.exists():
        raise HTTPException(404, "Análisis no disponible")
    return {"text": analysis.read_text(encoding="utf-8"), "path": str(analysis)}


@router.post("/api/sessions/{sid}/videos/{vid}/save")
async def save_output(sid: str, vid: str, req: Request):
    body = await req.json()
    target = body.get("target_dir", "").strip()
    files = body.get("files", ["summary.md", "analysis.md", "transcript.txt"])

    if not target:
        raise HTTPException(400, "Directorio destino requerido")

    saved = await save_artifacts_use_case.execute(sid, vid, target, files)
    return {"saved": saved}
