"""Tests for `OllamaGpuScheduler` (Step 5) — no consumer wires it in yet
(that's Step 6), but it must work standalone: correct subprocess args, and
`FileNotFoundError` swallowed (mirrors `_liberar_ollama`/`liberar_ollama`)."""
from __future__ import annotations

from pipeline.infrastructure.gpu import ollama_gpu_scheduler as mod
from pipeline.infrastructure.gpu.ollama_gpu_scheduler import OllamaGpuScheduler


def test_release_calls_ollama_stop_with_model_name(monkeypatch):
    captured = {}

    def fake_run(cmd, check, stdout, stderr):
        captured["cmd"] = cmd
        captured["check"] = check
        captured["stdout"] = stdout
        captured["stderr"] = stderr

    monkeypatch.setattr(mod.subprocess, "run", fake_run)

    OllamaGpuScheduler().release("qwen2.5:14b")

    assert captured["cmd"] == ["ollama", "stop", "qwen2.5:14b"]
    assert captured["check"] is False
    assert captured["stdout"] is mod.subprocess.DEVNULL
    assert captured["stderr"] is mod.subprocess.DEVNULL


def test_release_swallows_file_not_found_error(monkeypatch):
    def fake_run(*args, **kwargs):
        raise FileNotFoundError("ollama binary not found")

    monkeypatch.setattr(mod.subprocess, "run", fake_run)

    OllamaGpuScheduler().release("qwen2.5:14b")  # must not raise
