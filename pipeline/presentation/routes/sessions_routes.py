"""Sessions CRUD routes — the 4 endpoints migrated in Step 3 of the
hexagonal-architecture migration.

`GET /api/sessions` and `GET /api/sessions/{sid}` intentionally keep
reading the raw dict straight from the shared gateway instead of routing
through the `Session` domain object/use case: the frontend depends on
the exact today's-shape response with a full nested `videos: [...]`
list, and `Session` (per this migration's confirmed aggregate boundary)
only holds `video_ids` — `Video` isn't migrated until Step 4, so that
response shape can't be produced from the domain object yet. Only the
two routes with actual logic worth extracting — create's name
validation, delete's cascade file removal — go through use cases.
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request

from pipeline.application.sessions.exceptions import (
    EmptySessionNameError,
    SessionNotFoundError,
)
from pipeline.domain.sessions.session import SessionId
from pipeline.presentation.composition_root import (
    create_session_use_case,
    delete_session_use_case,
    gateway,
)

router = APIRouter()


@router.get("/api/sessions")
async def list_sessions():
    return await gateway.list_sessions()


@router.post("/api/sessions")
async def create_session(req: Request):
    body = await req.json()
    name = body.get("name", "")
    instructions = body.get("instructions", "")
    try:
        session = await create_session_use_case.execute(name, instructions)
    except EmptySessionNameError:
        raise HTTPException(400, "El nombre de la sesión es obligatorio")

    # A brand-new session always has zero videos, so this hand-mapped
    # shape is safe/exact against today's `create_session` response
    # (the domain `Session` only carries `video_ids`, not full video
    # dicts, so it can't be serialized directly into today's shape).
    return {
        "id": session.id.value,
        "name": session.name,
        "instructions": session.instructions,
        "created_at": session.created_at,
        "videos": [],
    }


@router.get("/api/sessions/{sid}")
async def get_session(sid: str):
    session = await gateway.get_session(sid)
    if not session:
        raise HTTPException(404, "Sesión no encontrada")
    return session


@router.delete("/api/sessions/{sid}")
async def delete_session(sid: str):
    try:
        await delete_session_use_case.execute(SessionId(sid))
    except SessionNotFoundError:
        raise HTTPException(404, "Sesión no encontrada")
    return {"ok": True}
