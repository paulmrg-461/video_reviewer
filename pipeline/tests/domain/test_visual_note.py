from pipeline.domain.videos.visual_note import VisualNote, VisualNotes


def test_to_markdown_matches_visual_py_format():
    notes = VisualNotes(
        notes=(
            VisualNote(timestamp_seconds=0, description="Escritorio vacio."),
            VisualNote(timestamp_seconds=15, description="Editor de codigo abierto."),
            VisualNote(timestamp_seconds=3661, description="Terminal con logs."),
        )
    )

    expected = (
        "### [00:00:00]\nEscritorio vacio.\n\n"
        "### [00:00:15]\nEditor de codigo abierto.\n\n"
        "### [01:01:01]\nTerminal con logs.\n"
    )

    assert notes.to_markdown() == expected


def test_to_markdown_single_note_has_trailing_newline_only():
    notes = VisualNotes(notes=(VisualNote(timestamp_seconds=0, description="Solo esto."),))

    assert notes.to_markdown() == "### [00:00:00]\nSolo esto.\n"
