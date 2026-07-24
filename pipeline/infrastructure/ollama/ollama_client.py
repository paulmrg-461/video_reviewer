"""Thin HTTP client wrapping calls to a local Ollama server.

Extracted from the duplicated request/response handling that used to live
inline in `pipeline/summarize.py`'s `_ollama_chat` and `pipeline/visual.py`'s
`_describir_frame`. The two methods below intentionally keep the two
distinct wire payload shapes those functions used — text chat includes
`system` + `num_ctx`, vision chat sends a single user message with an
`images` field and no `system`/`num_ctx` — rather than forcing a single
signature onto two genuinely different request shapes.
"""
from __future__ import annotations

import base64
import json
import urllib.request


class OllamaClient:
    def __init__(self, base_url: str = "http://localhost:11434") -> None:
        self._chat_url = f"{base_url}/api/chat"

    def chat(self, model: str, system: str, user: str, num_ctx: int = 8192) -> str:
        """Ports `summarize.py`'s `_ollama_chat` exactly (same payload shape,
        same timeout, same `.strip()` on the result)."""
        payload = {
            "model": model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "stream": False,
            "options": {"num_ctx": num_ctx, "temperature": 0.2},
        }
        req = urllib.request.Request(
            self._chat_url,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=600) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        return data["message"]["content"].strip()

    def chat_with_image(self, model: str, prompt: str, image_bytes: bytes) -> str:
        """Ports `visual.py`'s `_describir_frame` exactly (same payload
        shape, same timeout, same `.strip()` on the result)."""
        b64 = base64.b64encode(image_bytes).decode("ascii")
        payload = {
            "model": model,
            "messages": [{"role": "user", "content": prompt, "images": [b64]}],
            "stream": False,
            "options": {"temperature": 0.2},
        }
        req = urllib.request.Request(
            self._chat_url,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=300) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        return data["message"]["content"].strip()
