"""Persistent bot state: the capital sleeve the bot manages, plus a trade log."""

from __future__ import annotations

import json
import os
import tempfile
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path


def utcnow() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@dataclass
class BotState:
    cash_usd: float
    holdings: dict[str, float] = field(default_factory=dict)
    peak_equity: float = 0.0
    halted: bool = False
    halt_reason: str = ""
    last_cycle: str = ""
    last_equity: float = 0.0
    followed: list[str] = field(default_factory=list)
    created: str = field(default_factory=utcnow)

    @classmethod
    def fresh(cls, allocation_usd: float) -> "BotState":
        return cls(cash_usd=allocation_usd, peak_equity=allocation_usd, last_equity=allocation_usd)

    @classmethod
    def load(cls, path: str | Path, allocation_usd: float) -> "BotState":
        p = Path(path)
        if not p.exists():
            return cls.fresh(allocation_usd)
        return cls(**json.loads(p.read_text()))

    def save(self, path: str | Path) -> None:
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=p.parent, prefix=".state-")
        with os.fdopen(fd, "w") as fh:
            json.dump(asdict(self), fh, indent=2, sort_keys=True)
        os.replace(tmp, p)

    def equity(self, prices: dict[str, float]) -> float:
        return self.cash_usd + sum(qty * prices.get(coin, 0.0) for coin, qty in self.holdings.items())


def trade_log_path(state_path: str | Path) -> Path:
    p = Path(state_path)
    return p.with_name(p.stem + ".trades.jsonl")


def append_trade(state_path: str | Path, record: dict) -> None:
    p = trade_log_path(state_path)
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("a") as fh:
        fh.write(json.dumps({"ts": utcnow(), **record}) + "\n")
