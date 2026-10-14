"""`pipeline.recorder` — process lifecycle guards (no real GPU recorder needed)."""
from __future__ import annotations

import shutil
import subprocess
import sys
from collections import namedtuple

import pytest

from pipeline import recorder

Usage = namedtuple("Usage", "total used free")


def test_iniciar_rejects_low_disk_space(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(shutil, "disk_usage", lambda _p: Usage(10, 10, 1024))
    with pytest.raises(recorder.RecorderError, match="Espacio"):
        recorder.iniciar(tmp_path / "rec.mp4")


def test_iniciar_reports_log_when_process_dies_on_launch(tmp_path, monkeypatch) -> None:
    real_popen = subprocess.Popen
    code = "import sys; sys.stderr.write('portal error'); sys.exit(1)"
    monkeypatch.setattr(
        subprocess, "Popen", lambda _cmd, **kw: real_popen([sys.executable, "-c", code], **kw)
    )
    monkeypatch.setattr(recorder, "STARTUP_GRACE_SECONDS", 1.0)

    with pytest.raises(recorder.RecorderError, match="portal error"):
        recorder.iniciar(tmp_path / "rec.mp4")


def test_detener_stops_chatty_process_that_would_fill_a_pipe(tmp_path) -> None:
    code = "import sys,time\nwhile True: sys.stderr.write('x'*65536); time.sleep(0.01)"
    log = (tmp_path / "log").open("wb")
    proc = subprocess.Popen([sys.executable, "-c", code], stdout=subprocess.DEVNULL, stderr=log)

    assert recorder.esta_vivo(proc)
    assert recorder.detener(proc, timeout=5)
    assert not recorder.esta_vivo(proc)
