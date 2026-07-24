"""Videos use cases.

Pure application logic sitting between the presentation routes and the
`VideoRepository` port: no FastAPI, no raw dict/JSON handling.

Two of these use cases (`AddVideosToSessionUseCase`, `RetryVideoUseCase`)
also need to enqueue background processing work. `processing_queue` still
lives in `pipeline/server.py` (it is not migrated until Step 6), so these
use cases accept an injected `enqueue: Callable[[dict], Awaitable[None]]`
rather than depending on any concrete queue — see
`pipeline.presentation.composition_root` for how that callable is wired
in without a circular import.
"""
from __future__ import annotations

import re
import shutil
import typing
from pathlib import Path

from pipeline.application.videos.exceptions import VideoNotFoundError
from pipeline.application.videos.ports import VideoRepository
from pipeline.application.shared.ports import IdProvider
from pipeline.domain.sessions.session import SessionId
from pipeline.domain.videos.value_objects import ProcessingOptions, VideoId
from pipeline.domain.videos.video import Video

Enqueue = typing.Callable[[dict], typing.Awaitable[None]]


def _slug(nombre: str) -> str:
    """Relocated verbatim from `pipeline/server.py` (was defined at the top
    of that file). `save_output` — its only caller — is fully migrated to
    `SaveArtifactsUseCase` in this step, so nothing in `server.py` calls it
    anymore; this is a *move*, not a duplication. Kept here rather than
    imported from `pipeline.server` because `pipeline.presentation.
    composition_root` (which constructs this use case) has an established,
    documented rule against importing anything from `pipeline.server` —
    doing so here would reintroduce exactly the circular-import hazard
    that rule exists to prevent (server.py -> composition_root -> this
    module -> back into server.py, which is a different module identity
    than the one already partially initialized when run as `python3 -c
    "import server"` or `uvicorn server:app`, both of which import the
    file as top-level `server`, not `pipeline.server`)."""
    s = re.sub(r"\.[^.]+$", "", nombre)
    s = re.sub(r"[^\w\-]+", "_", s)
    return s.strip("_")


class AddVideosToSessionUseCase:
    """Mirrors today's `add_video` route loop in `pipeline/server.py`
    exactly: skips blank/non-existent paths, builds a `Video` for each
    valid one, persists it, and enqueues a processing task."""

    def __init__(
        self,
        video_repo: VideoRepository,
        id_provider: IdProvider,
        sessions_root: Path,
        enqueue: Enqueue,
    ) -> None:
        self._video_repo = video_repo
        self._id_provider = id_provider
        self._sessions_root = sessions_root
        self._enqueue = enqueue

    async def execute(
        self,
        session_id: str,
        paths: list[str],
        instructions: str,
        language: str,
        analyze_visual: bool,
        session_instructions_fallback: str,
    ) -> list[Video]:
        added: list[Video] = []
        for raw_path in paths:
            p = raw_path.strip()
            if not p:
                continue
            vp = Path(p)
            if not vp.exists():
                continue

            video = Video.new_from_upload(
                id=VideoId(self._id_provider.new_id()),
                session_id=session_id,
                name=vp.name,
                original_path=str(vp),
                options=ProcessingOptions(language=language, analyze_visual=analyze_visual),
                instructions=(instructions.strip() or session_instructions_fallback),
            )
            # Deliberate, documented exception to the "only `mark_done`
            # sets `output_dir`" domain convention: today's app sets this
            # field at creation time (before any processing) to keep the
            # persisted dict shape matching all pre-existing videos'
            # shape. Harmless: nothing enforces immutability on this
            # attribute, and nothing reads it as authoritative before
            # completion — output paths are always recomputed directly
            # from `session_id`/`video_id` elsewhere.
            video.output_dir = str(self._sessions_root / session_id / video.id.value)

            await self._video_repo.add(video)
            await self._enqueue({
                "session_id": session_id,
                "video_id": video.id.value,
                "instructions": video.instructions,
                "language": language,
                "analyze_visual": analyze_visual,
            })
            added.append(video)

        return added


class RetryVideoUseCase:
    """Fixes today's real retry-race bug: `retry_video` in
    `pipeline/server.py` blindly sets `status="queued"` regardless of the
    video's current status, which could double-enqueue a video that is
    already mid-processing. Routing through `Video.requeue()` makes this
    only legal from `ERROR` — any other status raises
    `InvalidVideoStateTransitionError`, which the router translates to an
    HTTP 409."""

    def __init__(self, video_repo: VideoRepository, enqueue: Enqueue) -> None:
        self._video_repo = video_repo
        self._enqueue = enqueue

    async def execute(self, session_id: str, video_id: str) -> Video:
        video = await self._video_repo.get(SessionId(session_id), VideoId(video_id))
        if video is None:
            raise VideoNotFoundError(session_id, video_id)

        video.requeue()  # raises InvalidVideoStateTransitionError unless ERROR
        await self._video_repo.update(video)
        await self._enqueue({
            "session_id": session_id,
            "video_id": video_id,
            "instructions": video.instructions,
            "language": video.options.language,
            "analyze_visual": video.options.analyze_visual,
        })
        return video


class DeleteVideoUseCase:
    """Ports today's `delete_video` route, replacing its direct
    `store._lock`/`store._load()`/`store._save()` access (a private-API
    violation) with `VideoRepository.remove()`.

    Preserves today's permissive behavior on purpose: the current route
    never checks whether the video actually existed before returning
    `{"ok": True}` (its list-comprehension filter is a silent no-op if the
    id isn't present). This use case keeps that permissiveness — it does
    NOT raise if `remove()` reports nothing was removed — to avoid a
    behavior change nobody asked for in this step. Tightening this into a
    `VideoNotFoundError` is a reasonable future change, but out of scope
    here.
    """

    def __init__(self, video_repo: VideoRepository, sessions_root: Path) -> None:
        self._video_repo = video_repo
        self._sessions_root = sessions_root

    async def execute(self, session_id: str, video_id: str) -> None:
        await self._video_repo.remove(SessionId(session_id), VideoId(video_id))
        video_dir = self._sessions_root / session_id / video_id
        if video_dir.exists():
            shutil.rmtree(video_dir)


class SaveArtifactsUseCase:
    """Ports today's `save_output` route logic exactly: copies the
    requested artifact files (if present) into `target_dir`, prefixed with
    a slugified video name."""

    def __init__(self, video_repo: VideoRepository, sessions_root: Path) -> None:
        self._video_repo = video_repo
        self._sessions_root = sessions_root

    async def execute(
        self, session_id: str, video_id: str, target_dir: str, files: list[str]
    ) -> list[str]:
        out_dir = self._sessions_root / session_id / video_id
        target_path = Path(target_dir)
        target_path.mkdir(parents=True, exist_ok=True)

        video = await self._video_repo.get(SessionId(session_id), VideoId(video_id))
        prefix = _slug(video.name) if video else video_id

        saved: list[str] = []
        for fname in files:
            src = out_dir / fname
            if src.exists():
                dst = target_path / f"{prefix}_{fname}"
                shutil.copy2(src, dst)
                saved.append(str(dst))

        return saved
