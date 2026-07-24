"""Video entity and its processing status state machine."""
from __future__ import annotations

from enum import Enum

from .analysis import AnalysisResult, Summary
from .exceptions import InvalidVideoStateTransitionError
from .transcript import Transcript
from .value_objects import ProcessingOptions, VideoId
from .visual_note import VisualNotes


class ProcessingStatus(str, Enum):
    """String values are the wire format polled by the frontend via SSE —
    they must not change."""

    QUEUED = "queued"
    EXTRACTING_AUDIO = "extracting_audio"
    TRANSCRIBING = "transcribing"
    ANALYZING_VISUAL = "analyzing_visual"
    SUMMARIZING = "summarizing"
    DONE = "done"
    ERROR = "error"


class Video:
    """Mutable entity encapsulating a video's processing lifecycle.

    Not constructed directly — use `new_from_upload` or
    `new_from_recording` so every instance starts from a valid, consistent
    state (this is the invariant-enforcing point of the class: no public
    constructor lets a caller set an arbitrary status directly).
    """

    _ALLOWED_TRANSITIONS: dict[ProcessingStatus, frozenset[ProcessingStatus]] = {
        ProcessingStatus.QUEUED: frozenset(
            {ProcessingStatus.EXTRACTING_AUDIO, ProcessingStatus.ERROR}
        ),
        ProcessingStatus.EXTRACTING_AUDIO: frozenset(
            {ProcessingStatus.TRANSCRIBING, ProcessingStatus.ERROR}
        ),
        ProcessingStatus.TRANSCRIBING: frozenset(
            {
                ProcessingStatus.ANALYZING_VISUAL,
                ProcessingStatus.SUMMARIZING,
                ProcessingStatus.ERROR,
            }
        ),
        ProcessingStatus.ANALYZING_VISUAL: frozenset(
            {ProcessingStatus.SUMMARIZING, ProcessingStatus.ERROR}
        ),
        ProcessingStatus.SUMMARIZING: frozenset(
            {ProcessingStatus.DONE, ProcessingStatus.ERROR}
        ),
        ProcessingStatus.DONE: frozenset(),
        ProcessingStatus.ERROR: frozenset({ProcessingStatus.QUEUED}),
    }

    def __init__(
        self,
        id: VideoId,
        session_id: str,
        name: str,
        original_path: str,
        options: ProcessingOptions,
        instructions: str,
        status: ProcessingStatus,
        is_recording: bool,
    ) -> None:
        self.id = id
        self.session_id = session_id
        self.name = name
        self.original_path = original_path
        self.options = options
        self.instructions = instructions
        self.status = status
        self.is_recording = is_recording

        self.error: str | None = None
        self.output_dir: str | None = None
        self.transcript: Transcript | None = None
        self.visual_notes: VisualNotes | None = None
        self.summary: Summary | None = None
        self.analysis: AnalysisResult | None = None
        self.original_deleted: bool = False

    @classmethod
    def new_from_upload(
        cls,
        id: VideoId,
        session_id: str,
        name: str,
        original_path: str,
        options: ProcessingOptions,
        instructions: str,
    ) -> "Video":
        return cls(
            id=id,
            session_id=session_id,
            name=name,
            original_path=original_path,
            options=options,
            instructions=instructions,
            status=ProcessingStatus.QUEUED,
            is_recording=False,
        )

    @classmethod
    def new_from_recording(
        cls,
        id: VideoId,
        session_id: str,
        name: str,
        original_path: str,
        options: ProcessingOptions,
        instructions: str,
    ) -> "Video":
        return cls(
            id=id,
            session_id=session_id,
            name=name,
            original_path=original_path,
            options=options,
            instructions=instructions,
            status=ProcessingStatus.QUEUED,
            is_recording=True,
        )

    def _transition(self, new_status: ProcessingStatus) -> None:
        if new_status not in self._ALLOWED_TRANSITIONS[self.status]:
            raise InvalidVideoStateTransitionError(self.id, self.status, new_status)
        self.status = new_status

    def start_extracting_audio(self) -> None:
        self._transition(ProcessingStatus.EXTRACTING_AUDIO)

    def start_transcribing(self) -> None:
        self._transition(ProcessingStatus.TRANSCRIBING)

    def mark_transcribed(self, transcript: Transcript) -> None:
        # Mirrors `mark_visual_analyzed`: records the result without moving
        # status by itself. Call `start_transcribing()` first (before the
        # blocking whisper call) so the UI's "transcribiendo..." status is
        # visible while it runs, then call this once the transcript is
        # ready.
        self.transcript = transcript

    def start_visual_analysis(self) -> None:
        if self.transcript is None:
            raise ValueError("cannot analyze visual without a transcript")
        self._transition(ProcessingStatus.ANALYZING_VISUAL)

    def mark_visual_analyzed(self, notes: VisualNotes | None) -> None:
        # None is explicitly legal — mirrors `analizar_visual()` returning
        # None when no frames could be extracted. Status does not move here;
        # it only advances to SUMMARIZING via `start_summarizing()`.
        self.visual_notes = notes

    def start_summarizing(self) -> None:
        if self.transcript is None:
            raise ValueError("cannot summarize without a transcript")
        self._transition(ProcessingStatus.SUMMARIZING)

    def mark_done(self, summary: Summary, analysis: AnalysisResult, output_dir: str) -> None:
        if self.transcript is None:
            raise ValueError("cannot mark done without a transcript")
        self.summary = summary
        self.analysis = analysis
        self.output_dir = output_dir
        self._transition(ProcessingStatus.DONE)

    def mark_error(self, message: str) -> None:
        # Legal from any non-terminal status (i.e. every status except
        # DONE) — bypasses the normal transition graph, which does not
        # encode "from anywhere".
        if self.status is ProcessingStatus.DONE:
            raise InvalidVideoStateTransitionError(
                self.id, self.status, ProcessingStatus.ERROR
            )
        self.error = message
        self.status = ProcessingStatus.ERROR

    def requeue(self) -> None:
        # Only legal from ERROR (enforced by the normal transition graph).
        # This is the fix for the known retry-race bug: today's
        # `retry_video` endpoint blindly requeues regardless of current
        # status, which could race two pipeline runs against the same
        # video if it's mid-processing.
        self._transition(ProcessingStatus.QUEUED)
        self.error = None
