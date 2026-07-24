import pytest

from pipeline.domain.videos.analysis import AnalysisResult, Summary
from pipeline.domain.videos.exceptions import InvalidVideoStateTransitionError
from pipeline.domain.videos.transcript import Segment, Transcript
from pipeline.domain.videos.value_objects import ProcessingOptions, VideoId
from pipeline.domain.videos.video import ProcessingStatus, Video
from pipeline.domain.videos.visual_note import VisualNotes


def _new_video(**overrides) -> Video:
    defaults = dict(
        id=VideoId("vid-1"),
        session_id="sess-1",
        name="clip.mp4",
        original_path="/videos/clip.mp4",
        options=ProcessingOptions(),
        instructions="",
    )
    defaults.update(overrides)
    return Video.new_from_upload(**defaults)


def _sample_transcript() -> Transcript:
    return Transcript(segments=(Segment(0.0, 1.0, "hola"),), language="es")


def test_new_from_upload_starts_queued_with_empty_state():
    video = _new_video()

    assert video.status == ProcessingStatus.QUEUED
    assert video.error is None
    assert video.transcript is None
    assert video.visual_notes is None
    assert video.summary is None
    assert video.analysis is None
    assert video.output_dir is None
    assert video.is_recording is False
    assert video.original_deleted is False


def test_new_from_recording_sets_is_recording_true():
    video = Video.new_from_recording(
        id=VideoId("vid-2"),
        session_id="sess-1",
        name="rec.mp4",
        original_path="/videos/rec.mp4",
        options=ProcessingOptions(),
        instructions="",
    )

    assert video.is_recording is True
    assert video.status == ProcessingStatus.QUEUED


def test_full_legal_happy_path_without_visual_analysis_succeeds():
    video = _new_video()

    video.start_extracting_audio()
    assert video.status == ProcessingStatus.EXTRACTING_AUDIO

    video.start_transcribing()
    assert video.status == ProcessingStatus.TRANSCRIBING

    transcript = _sample_transcript()
    video.mark_transcribed(transcript)
    assert video.transcript is transcript

    video.start_summarizing()
    assert video.status == ProcessingStatus.SUMMARIZING

    video.mark_done(Summary("resumen"), AnalysisResult("analisis"), "/out/vid-1")
    assert video.status == ProcessingStatus.DONE
    assert video.summary == Summary("resumen")
    assert video.analysis == AnalysisResult("analisis")
    assert video.output_dir == "/out/vid-1"


def test_full_legal_happy_path_through_visual_analysis_succeeds():
    video = _new_video()

    video.start_extracting_audio()
    video.start_transcribing()
    video.mark_transcribed(_sample_transcript())

    video.start_visual_analysis()
    assert video.status == ProcessingStatus.ANALYZING_VISUAL

    notes = VisualNotes(notes=())
    video.mark_visual_analyzed(notes)
    assert video.visual_notes is notes
    # mark_visual_analyzed does not move status by itself.
    assert video.status == ProcessingStatus.ANALYZING_VISUAL

    video.start_summarizing()
    assert video.status == ProcessingStatus.SUMMARIZING

    video.mark_done(Summary("s"), AnalysisResult("a"), "/out")
    assert video.status == ProcessingStatus.DONE


def test_mark_visual_analyzed_with_none_does_not_raise():
    video = _new_video()
    video.start_extracting_audio()
    video.start_transcribing()
    video.mark_transcribed(_sample_transcript())
    video.start_visual_analysis()

    video.mark_visual_analyzed(None)

    assert video.visual_notes is None


def test_illegal_jump_mark_done_without_transcript_raises_value_error():
    video = _new_video()

    with pytest.raises(ValueError):
        video.mark_done(Summary("s"), AnalysisResult("a"), "/out")


def test_start_summarizing_without_transcript_raises_value_error():
    video = _new_video()
    video.start_extracting_audio()

    with pytest.raises(ValueError):
        video.start_summarizing()


def test_start_visual_analysis_without_transcript_raises_value_error():
    video = _new_video()
    video.start_extracting_audio()

    with pytest.raises(ValueError):
        video.start_visual_analysis()


def test_illegal_state_transition_raises_domain_error():
    video = _new_video()

    # QUEUED -> SUMMARIZING is not a legal direct jump.
    with pytest.raises(InvalidVideoStateTransitionError):
        video._transition(ProcessingStatus.SUMMARIZING)


def test_requeue_only_legal_from_error():
    video = _new_video()
    video.start_extracting_audio()
    video.mark_error("boom")

    video.requeue()

    assert video.status == ProcessingStatus.QUEUED
    assert video.error is None


def test_requeue_from_queued_raises():
    video = _new_video()

    with pytest.raises(InvalidVideoStateTransitionError):
        video.requeue()


def test_requeue_from_done_raises():
    video = _new_video()
    video.start_extracting_audio()
    video.start_transcribing()
    video.mark_transcribed(_sample_transcript())
    video.start_summarizing()
    video.mark_done(Summary("s"), AnalysisResult("a"), "/out")

    with pytest.raises(InvalidVideoStateTransitionError):
        video.requeue()


@pytest.mark.parametrize(
    "advance_to",
    [
        "queued",
        "extracting_audio",
        "transcribing",
        "analyzing_visual",
        "summarizing",
    ],
)
def test_mark_error_works_from_several_non_done_statuses(advance_to: str):
    video = _new_video()

    if advance_to in ("extracting_audio", "transcribing", "analyzing_visual", "summarizing"):
        video.start_extracting_audio()
    if advance_to in ("transcribing", "analyzing_visual", "summarizing"):
        video.start_transcribing()
        video.mark_transcribed(_sample_transcript())
    if advance_to == "analyzing_visual":
        video.start_visual_analysis()
    if advance_to == "summarizing":
        video.start_summarizing()

    video.mark_error("something went wrong")

    assert video.status == ProcessingStatus.ERROR
    assert video.error == "something went wrong"


def test_mark_error_from_done_raises():
    video = _new_video()
    video.start_extracting_audio()
    video.start_transcribing()
    video.mark_transcribed(_sample_transcript())
    video.start_summarizing()
    video.mark_done(Summary("s"), AnalysisResult("a"), "/out")

    with pytest.raises(InvalidVideoStateTransitionError):
        video.mark_error("too late")
