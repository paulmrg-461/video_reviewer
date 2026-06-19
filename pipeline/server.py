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
import re
import shutil
import subprocess
import sys
import time
import traceback
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

ROOT = Path(__file__).resolve().parent.parent
SESSIONS_FILE = ROOT / "sessions.json"
FRONTEND_DIR = ROOT / "frontend"

VIDEOS_DIR_DEFAULT = ROOT / "videos"

OLLAMA_URL = "http://localhost:11434"


def _slug(nombre: str) -> str:
    s = re.sub(r"\.[^.]+$", "", nombre)
    s = re.sub(r"[^\w\-]+", "_", s)
    return s.strip("_")


class SessionStore:
    def __init__(self, path: Path):
        self.path = path
        self._lock = asyncio.Lock()

    def _load(self) -> dict:
        if self.path.exists():
            return json.loads(self.path.read_text())
        return {"sessions": {}}

    def _save(self, data: dict) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(data, ensure_ascii=False, indent=2))

    async def list_sessions(self) -> list[dict]:
        async with self._lock:
            data = self._load()
        return sorted(data["sessions"].values(), key=lambda s: s["created_at"], reverse=True)

    async def get_session(self, sid: str) -> dict | None:
        async with self._lock:
            data = self._load()
        return data["sessions"].get(sid)

    async def create_session(self, name: str, instructions: str = "") -> dict:
        sid = uuid.uuid4().hex[:12]
        session = {
            "id": sid,
            "name": name.strip(),
            "instructions": instructions.strip(),
            "created_at": datetime.now(timezone.utc).isoformat(),
            "videos": [],
        }
        async with self._lock:
            data = self._load()
            data["sessions"][sid] = session
            self._save(data)
        return session

    async def delete_session(self, sid: str) -> bool:
        async with self._lock:
            data = self._load()
            if sid not in data["sessions"]:
                return False
            del data["sessions"][sid]
            self._save(data)
        return True

    async def update_video(self, sid: str, video: dict) -> bool:
        async with self._lock:
            data = self._load()
            session = data["sessions"].get(sid)
            if not session:
                return False
            for i, v in enumerate(session["videos"]):
                if v["id"] == video["id"]:
                    session["videos"][i] = video
                    self._save(data)
                    return True
            session["videos"].append(video)
            self._save(data)
            return True

    async def get_video(self, sid: str, vid: str) -> dict | None:
        session = await self.get_session(sid)
        if not session:
            return None
        for v in session["videos"]:
            if v["id"] == vid:
                return v
        return None


store = SessionStore(SESSIONS_FILE)

app = FastAPI(title="Video Reviewer", version="1.0.0")

processing_queue: asyncio.Queue[dict] = asyncio.Queue()
progress_events: dict[str, asyncio.Event] = {}
progress_data: dict[str, dict] = {}


async def _emit_progress(sid: str, vid: str, data: dict) -> None:
    key = f"{sid}:{vid}"
    progress_data[key] = data
    event = progress_events.get(key)
    if event:
        event.set()


def _run_transcribe(
    video_path: Path, out_dir: Path, whisper_model: str,
    device: str, compute_type: str, language: str,
) -> None:
    from transcribe import transcribir
    out_dir.mkdir(parents=True, exist_ok=True)
    transcribir(video_path, out_dir, whisper_model, device, compute_type, language)


def _run_summarize(
    out_dir: Path, llm_model: str, nombre: str, instructions: str | None,
) -> None:
    from summarize import resumir
    resumir(out_dir, llm_model, nombre, instructions)


async def _process_video(task: dict) -> None:
    sid, vid = task["session_id"], task["video_id"]
    key = f"{sid}:{vid}"

    try:
        video = await store.get_video(sid, vid)
        if not video:
            return

        video_path = Path(video["original_path"])
        if not video_path.exists():
            await _emit_progress(sid, vid, {"status": "error", "msg": f"No existe: {video_path}"})
            video["status"] = "error"
            video["error"] = f"Archivo no encontrado: {video_path}"
            await store.update_video(sid, video)
            return

        video["status"] = "extracting_audio"
        await store.update_video(sid, video)
        await _emit_progress(sid, vid, {"status": "extracting_audio",
                                         "msg": "Extrayendo audio..."})

        out_dir = ROOT / "sessions" / sid / vid
        out_dir.mkdir(parents=True, exist_ok=True)

        instructions_file = out_dir / "instructions.txt"
        instructions = video.get("instructions") or task.get("instructions") or ""
        instructions_file.write_text(instructions)

        language = video.get("language", "es")
        whisper_model = task.get("whisper_model", "large-v3")
        device = task.get("device", "cuda")
        compute_type = task.get("compute_type", "int8_float16")
        llm_model = task.get("llm_model", "qwen2.5:14b")

        video["status"] = "transcribing"
        await store.update_video(sid, video)
        await _emit_progress(sid, vid, {"status": "transcribing",
                                         "msg": "Transcribiendo..."})

        loop = asyncio.get_running_loop()
        await loop.run_in_executor(
            None, _run_transcribe, video_path, out_dir,
            whisper_model, device, compute_type, language,
        )

        video["status"] = "summarizing"
        await store.update_video(sid, video)
        await _emit_progress(sid, vid, {"status": "summarizing",
                                         "msg": "Analizando transcripción..."})

        await loop.run_in_executor(
            None, _run_summarize, out_dir, llm_model,
            video["name"], instructions or None,
        )

        video["status"] = "done"
        video["output_dir"] = str(out_dir)
        await store.update_video(sid, video)
        await _emit_progress(sid, vid, {"status": "done", "msg": "Completado",
                                         "output_dir": str(out_dir)})

    except Exception as exc:
        traceback.print_exc()
        video = await store.get_video(sid, vid)
        if video:
            video["status"] = "error"
            video["error"] = str(exc)
            await store.update_video(sid, video)
        await _emit_progress(sid, vid, {"status": "error", "msg": str(exc)})


async def _worker() -> None:
    while True:
        task = await processing_queue.get()
        await _process_video(task)
        processing_queue.task_done()


@app.on_event("startup")
async def startup() -> None:
    asyncio.create_task(_worker())


@app.get("/api/sessions")
async def list_sessions():
    return await store.list_sessions()


@app.post("/api/sessions")
async def create_session(req: Request):
    body = await req.json()
    name = body.get("name", "").strip()
    if not name:
        raise HTTPException(400, "El nombre de la sesión es obligatorio")
    instructions = body.get("instructions", "")
    session = await store.create_session(name, instructions)
    return session


@app.get("/api/sessions/{sid}")
async def get_session(sid: str):
    session = await store.get_session(sid)
    if not session:
        raise HTTPException(404, "Sesión no encontrada")
    return session


@app.delete("/api/sessions/{sid}")
async def delete_session(sid: str):
    ok = await store.delete_session(sid)
    if not ok:
        raise HTTPException(404, "Sesión no encontrada")
    session_dir = ROOT / "sessions" / sid
    if session_dir.exists():
        shutil.rmtree(session_dir)
    return {"ok": True}


@app.post("/api/sessions/{sid}/videos")
async def add_video(sid: str, req: Request):
    session = await store.get_session(sid)
    if not session:
        raise HTTPException(404, "Sesión no encontrada")

    body = await req.json()
    paths = body.get("paths", [])
    if isinstance(paths, str):
        paths = [paths]
    instructions = body.get("instructions", "")
    language = body.get("language", "es")

    added = []
    for p in paths:
        p = p.strip()
        if not p:
            continue
        vp = Path(p)
        if not vp.exists():
            continue
        vid = uuid.uuid4().hex[:12]
        video = {
            "id": vid,
            "name": vp.name,
            "original_path": str(vp),
            "status": "queued",
            "instructions": instructions.strip() or session.get("instructions", ""),
            "language": language,
            "output_dir": str(ROOT / "sessions" / sid / vid),
            "error": None,
        }
        await store.update_video(sid, video)
        await processing_queue.put({
            "session_id": sid,
            "video_id": vid,
            "instructions": video["instructions"],
            "language": language,
        })
        added.append(video)

    return {"added": added}


@app.post("/api/sessions/{sid}/videos/{vid}/retry")
async def retry_video(sid: str, vid: str):
    session = await store.get_session(sid)
    if not session:
        raise HTTPException(404, "Sesión no encontrada")
    video = None
    for v in session["videos"]:
        if v["id"] == vid:
            video = v
            break
    if not video:
        raise HTTPException(404, "Video no encontrado")
    video["status"] = "queued"
    video["error"] = None
    await store.update_video(sid, video)
    await processing_queue.put({
        "session_id": sid,
        "video_id": vid,
        "instructions": video.get("instructions", ""),
        "language": video.get("language", "es"),
    })
    return {"ok": True}


@app.delete("/api/sessions/{sid}/videos/{vid}")
async def delete_video(sid: str, vid: str):
    session = await store.get_session(sid)
    if not session:
        raise HTTPException(404, "Sesión no encontrada")
    session["videos"] = [v for v in session["videos"] if v["id"] != vid]
    async with store._lock:
        data = store._load()
        if sid in data["sessions"]:
            data["sessions"][sid]["videos"] = session["videos"]
            store._save(data)
    video_dir = ROOT / "sessions" / sid / vid
    if video_dir.exists():
        shutil.rmtree(video_dir)
    return {"ok": True}


@app.get("/api/sessions/{sid}/videos/{vid}/transcript")
async def get_transcript(sid: str, vid: str):
    out_dir = ROOT / "sessions" / sid / vid
    txt = out_dir / "transcript.txt"
    if not txt.exists():
        raise HTTPException(404, "Transcripción no disponible")
    return {"text": txt.read_text(encoding="utf-8")}


@app.get("/api/sessions/{sid}/videos/{vid}/srt")
async def get_srt(sid: str, vid: str):
    out_dir = ROOT / "sessions" / sid / vid
    srt = out_dir / "transcript.srt"
    if not srt.exists():
        raise HTTPException(404, "SRT no disponible")
    return {"text": srt.read_text(encoding="utf-8")}


@app.get("/api/sessions/{sid}/videos/{vid}/summary")
async def get_summary(sid: str, vid: str):
    out_dir = ROOT / "sessions" / sid / vid
    summary = out_dir / "summary.md"
    if not summary.exists():
        raise HTTPException(404, "Resumen no disponible")
    return {"text": summary.read_text(encoding="utf-8"), "path": str(summary)}


@app.get("/api/sessions/{sid}/videos/{vid}/analysis")
async def get_analysis(sid: str, vid: str):
    out_dir = ROOT / "sessions" / sid / vid
    analysis = out_dir / "analysis.md"
    if not analysis.exists():
        raise HTTPException(404, "Análisis no disponible")
    return {"text": analysis.read_text(encoding="utf-8"), "path": str(analysis)}


@app.post("/api/sessions/{sid}/videos/{vid}/save")
async def save_output(sid: str, vid: str, req: Request):
    out_dir = ROOT / "sessions" / sid / vid
    body = await req.json()
    target = body.get("target_dir", "").strip()
    files = body.get("files", ["summary.md", "analysis.md", "transcript.txt"])

    if not target:
        raise HTTPException(400, "Directorio destino requerido")

    target_path = Path(target)
    target_path.mkdir(parents=True, exist_ok=True)

    saved = []
    for fname in files:
        src = out_dir / fname
        if src.exists():
            dst = target_path / f"{_slug(video_name(sid, vid))}_{fname}"
            shutil.copy2(src, dst)
            saved.append(str(dst))

    return {"saved": saved}


def video_name(sid: str, vid: str) -> str:
    import asyncio
    async def _get():
        v = await store.get_video(sid, vid)
        return v["name"] if v else vid
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        return vid
    future = asyncio.run_coroutine_threadsafe(_get(), loop)
    return future.result(timeout=5)


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
