from pipeline.domain.videos.transcript import Segment, Transcript


def _sample_transcript() -> Transcript:
    return Transcript(
        segments=(
            Segment(start=0.0, end=1.5, text="Hola"),
            Segment(start=1.5, end=3.25, text="mundo"),
            Segment(start=3.25, end=10.0, text="como estas"),
        ),
        language="es",
    )


def test_plain_text_matches_transcribe_py_format():
    transcript = _sample_transcript()

    assert transcript.plain_text() == "Hola\nmundo\ncomo estas\n"


def test_to_srt_matches_transcribe_py_format():
    transcript = _sample_transcript()

    expected = (
        "1\n00:00:00,000 --> 00:00:01,500\nHola\n"
        "\n"
        "2\n00:00:01,500 --> 00:00:03,250\nmundo\n"
        "\n"
        "3\n00:00:03,250 --> 00:00:10,000\ncomo estas\n"
    )

    assert transcript.to_srt() == expected


def test_to_srt_single_segment_has_no_trailing_blank_line():
    transcript = Transcript(
        segments=(Segment(start=0.0, end=2.0, text="unico"),),
        language="es",
    )

    assert transcript.to_srt() == "1\n00:00:00,000 --> 00:00:02,000\nunico\n"
