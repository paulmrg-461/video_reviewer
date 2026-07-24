"""Cross-feature application-layer ports (not specific to Sessions or
Videos). Implementations live in `pipeline.infrastructure.shared`.
"""
from __future__ import annotations

import typing


class IdProvider(typing.Protocol):
    """Mints new entity ids."""

    def new_id(self) -> str: ...


class Clock(typing.Protocol):
    """Provides the current time, injectable for deterministic tests."""

    def now_iso(self) -> str: ...
