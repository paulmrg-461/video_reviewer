"""Tests for `OllamaClient` (Step 5) — verifies both wire payload shapes
match the originals in `summarize.py`'s `_ollama_chat` and `visual.py`'s
`_describir_frame`, using a fake `urllib.request.urlopen`."""
from __future__ import annotations

import json
from contextlib import contextmanager

import pytest

from pipeline.infrastructure.ollama import ollama_client as ollama_client_module
from pipeline.infrastructure.ollama.ollama_client import OllamaClient


class _FakeResponse:
    def __init__(self, payload: dict) -> None:
        self._body = json.dumps(payload).encode("utf-8")

    def read(self) -> bytes:
        return self._body

    def __enter__(self) -> "_FakeResponse":
        return self

    def __exit__(self, *exc) -> None:
        return None


def test_chat_sends_system_user_and_num_ctx_and_strips_result(monkeypatch):
    captured = {}

    def fake_urlopen(req, timeout=None):
        captured["url"] = req.full_url
        captured["timeout"] = timeout
        captured["payload"] = json.loads(req.data.decode("utf-8"))
        captured["headers"] = req.headers
        return _FakeResponse({"message": {"content": "  hola  \n"}})

    monkeypatch.setattr(ollama_client_module.urllib.request, "urlopen", fake_urlopen)

    client = OllamaClient()
    result = client.chat("qwen2.5:14b", "sys prompt", "user prompt", num_ctx=16384)

    assert result == "hola"
    assert captured["url"] == "http://localhost:11434/api/chat"
    assert captured["timeout"] == 600
    assert captured["payload"] == {
        "model": "qwen2.5:14b",
        "messages": [
            {"role": "system", "content": "sys prompt"},
            {"role": "user", "content": "user prompt"},
        ],
        "stream": False,
        "options": {"num_ctx": 16384, "temperature": 0.2},
    }


def test_chat_default_num_ctx_is_8192(monkeypatch):
    captured = {}

    def fake_urlopen(req, timeout=None):
        captured["payload"] = json.loads(req.data.decode("utf-8"))
        return _FakeResponse({"message": {"content": "ok"}})

    monkeypatch.setattr(ollama_client_module.urllib.request, "urlopen", fake_urlopen)

    OllamaClient().chat("m", "s", "u")

    assert captured["payload"]["options"]["num_ctx"] == 8192


def test_chat_with_image_sends_images_field_no_system_no_num_ctx(monkeypatch):
    captured = {}

    def fake_urlopen(req, timeout=None):
        captured["timeout"] = timeout
        captured["payload"] = json.loads(req.data.decode("utf-8"))
        return _FakeResponse({"message": {"content": "  descripcion  "}})

    monkeypatch.setattr(ollama_client_module.urllib.request, "urlopen", fake_urlopen)

    client = OllamaClient()
    result = client.chat_with_image("gemma4:e4b", "prompt frame", b"fakejpegbytes")

    assert result == "descripcion"
    assert captured["timeout"] == 300
    payload = captured["payload"]
    assert payload["model"] == "gemma4:e4b"
    assert payload["stream"] is False
    assert payload["options"] == {"temperature": 0.2}
    assert "system" not in json.dumps(payload)  # no system role/field at all
    assert len(payload["messages"]) == 1
    msg = payload["messages"][0]
    assert msg["role"] == "user"
    assert msg["content"] == "prompt frame"
    import base64
    assert msg["images"] == [base64.b64encode(b"fakejpegbytes").decode("ascii")]


def test_base_url_is_configurable(monkeypatch):
    captured = {}

    def fake_urlopen(req, timeout=None):
        captured["url"] = req.full_url
        return _FakeResponse({"message": {"content": "ok"}})

    monkeypatch.setattr(ollama_client_module.urllib.request, "urlopen", fake_urlopen)

    OllamaClient(base_url="http://otherhost:1234").chat("m", "s", "u")

    assert captured["url"] == "http://otherhost:1234/api/chat"
