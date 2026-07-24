"""
server.py — FastAPI backend for the Video Reviewer tool.

Serves the HTML frontend and exposes REST API + SSE for:
  - Session CRUD (named groups of videos with custom instructions)
  - Video processing queue (transcribe + analyze in background)
  - Real-time progress via SSE
  - Result viewing and export
"""

from __future__ import annotations

import asyncio
import json
import subprocess
import sys
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

ROOT = Path(__file__).resolve().parent.parent
SESSIONS_FILE = ROOT / "sessions.json"
FRONTEND_DIR = ROOT / "frontend"


# `server.py` runs with its own directory (pipeline/) as cwd — both
# `uvicorn server:app` (via run.sh) and `python3 -c "import server"` — so
# the repo root (parent of the `pipeline` namespace package) is not on
# `sys.path` by default. Insert it before importing anything from
# `pipeline.*` below. `ROOT` above already *is* the repo root.
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from pipeline.presentation.composition_root import (  # noqa: E402
    gateway,
    processing_queue,
    worker,
)
from pipeline.presentation.routes import (  # noqa: E402
    recording_routes,
    sessions_routes,
    videos_routes,
)

# Shared dict-based gateway (Step 2's `SessionsJsonGateway`, a verbatim
# drop-in port of the old in-file `SessionStore`) used by every
# not-yet-migrated video/recording route below, via the exact same
# dict-in/dict-out method names (`get_session`, `update_video`, ...).
# This is the SAME instance the Sessions use cases/routes use (imported
# from the composition root) — never construct a second one, or the
# video routes and the Sessions feature would hold independent
# `asyncio.Lock`s over one file.
store = gateway

app = FastAPI(title="Video Reviewer", version="1.0.0")
app.include_router(sessions_routes.router)
app.include_router(videos_routes.router)
app.include_router(recording_routes.router)
app.mount("/assets", StaticFiles(directory=FRONTEND_DIR / "assets"), name="assets")


@app.on_event("startup")
async def startup() -> None:
    asyncio.create_task(worker())


@app.get("/api/progress")
async def progress_stream(req: Request):
    async def event_generator():
        while True:
            if await req.is_disconnected():
                break
            sessions = await store.list_sessions()
            yield f"data: {json.dumps(sessions)}\n\n"
            await asyncio.sleep(1)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
        },
    )


@app.get("/api/health")
async def health():
    try:
        subprocess.run(["ollama", "list"], capture_output=True, timeout=5, check=False)
        ollama_ok = True
    except Exception:
        ollama_ok = False

    try:
        subprocess.run(["ffmpeg", "-version"], capture_output=True, timeout=5, check=False)
        ffmpeg_ok = True
    except Exception:
        ffmpeg_ok = False

    return {
        "ollama": ollama_ok,
        "ffmpeg": ffmpeg_ok,
        "queue_size": processing_queue.qsize(),
    }


@app.get("/")
async def serve_frontend():
    index = FRONTEND_DIR / "index.html"
    if index.exists():
        return HTMLResponse(index.read_text(encoding="utf-8"))
    return HTMLResponse("<h1>Frontend no encontrado en frontend/index.html</h1>", 404)
