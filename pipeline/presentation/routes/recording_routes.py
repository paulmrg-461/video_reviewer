"""Recording routes — the 4 endpoints migrated in Step 7 of the
hexagonal-architecture migration.

All 4 are use-case-backed (`start_recording`, `stop_recording`,
`delete_recording_file`) except `recording_status`, which is a pure read
of the registry — per the established pattern (Steps 3/4/6: pure reads
with no logic worth extracting go straight to the shared instance, no use
case).

Out of scope for this step (untouched, still in `pipeline/server.py`):
sessions/videos routes, `_worker`, `ProcessVideoUseCase`, `/api/progress`,
`/api/health`, `/`.
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request

from pipeline.application.recording.exceptions import (
    ConcurrentRecordingError,
    NotARecordingError,
    RecorderNotAvailableError,
    RecordingNotFoundError,
    RecordingPathTraversalError,
    RecordingSaveFailedError,
)
from pipeline.application.sessions.exceptions import SessionNotFoundError
from pipeline.application.videos.exceptions import VideoNotFoundError
from pipeline.presentation.composition_root import (
    active_recordings_registry,
    start_recording_use_case,
    stop_recording_use_case,
    delete_recording_file_use_case,
)

router = APIRouter()


@router.post("/api/sessions/{sid}/record/start")
async def start_recording(sid: str):
    try:
        recording = await start_recording_use_case.execute(sid)
    except SessionNotFoundError:
        raise HTTPException(404, "Sesión no encontrada")
    except ConcurrentRecordingError:
        raise HTTPException(409, "Ya hay una grabación activa para esta sesión")
    except RecorderNotAvailableError:
        raise HTTPException(500, "gpu-screen-recorder no está instalado")

    return {"recording_id": recording.id, "started_at": recording.started_at}


@router.post("/api/sessions/{sid}/record/{rid}/stop")
async def stop_recording(sid: str, rid: str, req: Request):
    try:
        body = await req.json()
    except Exception:
        body = {}
    language = body.get("language", "es")
    analyze_visual = bool(body.get("analyze_visual", True))
    instructions_override = body.get("instructions", "")

    try:
        video = await stop_recording_use_case.execute(
            session_id=sid,
            recording_id=rid,
            language=language,
            analyze_visual=analyze_visual,
            instructions_override=instructions_override,
        )
    except RecordingNotFoundError:
        raise HTTPException(404, "Grabación no encontrada")
    except RecordingSaveFailedError:
        raise HTTPException(500, "La grabación no se guardó correctamente")

    return {
        "video": {
            "id": video.id.value,
            "name": video.name,
            "original_path": video.original_path,
            "status": video.status.value,
            "instructions": video.instructions,
            "language": video.options.language,
            "analyze_visual": video.options.analyze_visual,
            "is_recording": video.is_recording,
            "output_dir": video.output_dir,
            "error": video.error,
        }
    }


@router.delete("/api/sessions/{sid}/videos/{vid}/recording")
async def delete_recording_file(sid: str, vid: str):
    try:
        await delete_recording_file_use_case.execute(sid, vid)
    except VideoNotFoundError:
        raise HTTPException(404, "Video no encontrado")
    except NotARecordingError:
        raise HTTPException(400, "Este video no es una grabación gestionada por la app")
    except RecordingPathTraversalError:
        raise HTTPException(400, "Ruta fuera del directorio de grabaciones")
    return {"ok": True}


@router.get("/api/record/status")
async def recording_status():
    return {
        r.id: {"session_id": r.session_id, "started_at": r.started_at}
        for r in active_recordings_registry.list_all()
    }
