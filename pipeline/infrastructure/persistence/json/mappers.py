"""Pure dict <-> domain mapping functions for the JSON persistence gateway.

Defensive on missing keys throughout: real `sessions.json` entries predate
fields like `is_recording`/`original_deleted` (added by a later feature), so
every field beyond the always-present `id, name, original_path, status,
instructions` is read with `.get(key, default)`.
"""
from __future__ import annotations

from pipeline.domain.sessions.session import Session, SessionId
from pipeline.domain.videos.value_objects import ProcessingOptions, VideoId
from pipeline.domain.videos.video import ProcessingStatus, Video


def session_dict_to_domain(d: dict) -> Session:
    video_ids = [VideoId(v["id"]) for v in d.get("videos", [])]
    return Session(
        id=SessionId(d["id"]),
        name=d.get("name", ""),
        instructions=d.get("instructions", ""),
        created_at=d.get("created_at", ""),
        video_ids=video_ids,
    )


def video_dict_to_domain(d: dict, session_id: str) -> Video:
    """Rehydrate a `Video` aggregate from its persisted dict.

    Status-reconstruction approach (the tricky part of this mapper) and why:

    `Video`'s guarded lifecycle methods (`start_transcribing`,
    `mark_transcribed`, `start_summarizing`, `mark_done`, ...) require the
    real intermediate artifacts (a `Transcript`, a `Summary`, ...) to legally
    walk the state machine up to statuses like DONE. Those artifacts are NOT
    stored in this dict — they live on disk under `output_dir`
    (transcript.txt, summary.md, analysis.md, ...) and continue to be read
    directly by presentation-layer file-serving endpoints, unchanged, in
    later migration steps. Nothing built in Steps 1-2 reads
    `video.transcript`/`video.summary`/`video.visual_notes`/`video.analysis`
    off a rehydrated object, so reconstructing those value objects here
    would be pure ceremony with no consumer — and faking them with
    placeholder content would be worse (silently wrong data sitting behind
    a real-looking object).

    Chosen approach: `Video.__init__` is already public and already accepts
    `status` directly as a constructor parameter (see
    `pipeline/domain/videos/video.py`) — it is only sequencing convention
    (via `new_from_upload`/`new_from_recording`), not a private/mangled
    method, that normally keeps callers from using it directly. Rehydration
    calls `Video(...)` directly with `status` taken straight from storage,
    then patches in the few plain post-construction attributes
    (`error`, `output_dir`, `original_deleted`) that `__init__` always
    defaults and that aren't exposed as constructor parameters. This is the
    smallest correct option: it needs no change to
    `pipeline/domain/videos/video.py` (which this step must not touch), adds
    no new escape-hatch method to the domain, and does not bypass any guard
    that the constructor itself doesn't already bypass.
    """
    options = ProcessingOptions(
        language=d.get("language", "es"),
        analyze_visual=bool(d.get("analyze_visual", False)),
    )
    video = Video(
        id=VideoId(d["id"]),
        session_id=session_id,
        name=d.get("name", ""),
        original_path=d.get("original_path", ""),
        options=options,
        instructions=d.get("instructions", ""),
        status=ProcessingStatus(d.get("status", ProcessingStatus.QUEUED.value)),
        is_recording=bool(d.get("is_recording", False)),
    )
    video.error = d.get("error")
    video.output_dir = d.get("output_dir")
    video.original_deleted = bool(d.get("original_deleted", False))
    return video


def video_domain_to_dict(video: Video) -> dict:
    """Inverse of `video_dict_to_domain`. Produces the same dict shape/keys
    persisted today, plus `is_recording`/`original_deleted` always present
    (new keys are additive-safe — older code paths already tolerate unknown
    extra keys; they just didn't have them before)."""
    return {
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
        "original_deleted": video.original_deleted,
    }


def session_domain_to_dict(session: Session, videos: list[Video]) -> dict:
    """Reproduces the current nested
    `{id, name, instructions, created_at, videos: [...]}` shape. Needs the
    actual `Video` list (not just `session.video_ids`) since full video
    dicts are what's persisted alongside the session."""
    return {
        "id": session.id.value,
        "name": session.name,
        "instructions": session.instructions,
        "created_at": session.created_at,
        "videos": [video_domain_to_dict(v) for v in videos],
    }
