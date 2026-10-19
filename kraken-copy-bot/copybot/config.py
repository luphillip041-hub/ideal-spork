"""Configuration loading (TOML) with safe defaults."""

from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass, field, fields, is_dataclass
from pathlib import Path


@dataclass
class LeaderboardConfig:
    # Only follow traders with at least this much capital on the account.
    min_account_value: float = 250_000.0
    # Must be profitable over the month and all-time windows.
    min_month_roi: float = 0.0
    min_all_time_pnl: float = 0.0
    # Monthly volume / account value. Very high turnover means market making or
    # HFT, whose positions flip faster than we can copy them.
    max_month_turnover: float = 300.0
    # Score = weighted sum of percentiles among eligible traders. "month" etc. rank
    # by that window's ROI; "pnl_allTime" etc. rank by dollar PnL (track-record size).
    weights: dict[str, float] = field(
        default_factory=lambda: {"month": 0.35, "allTime": 0.25, "week": 0.15, "pnl_allTime": 0.25}
    )
    # Number of top-ranked traders to copy.
    top_n: int = 10
    # Addresses to always follow / never follow (lowercase 0x...).
    include: list[str] = field(default_factory=list)
    exclude: list[str] = field(default_factory=list)


@dataclass
class CopyConfig:
    # A coin is only bought when at least this many followed traders are long it.
    min_traders_agree: int = 2
    # Multiplier on the score-weighted consensus exposure.
    exposure_scale: float = 1.0
    # Hard cap on any single coin, as a fraction of bot equity.
    max_position_pct: float = 0.25
    # Hard cap on total invested fraction (spot: never above 1.0).
    max_total_exposure: float = 0.9
    # Restrict to / exclude these coins (Hyperliquid-style tickers, e.g. BTC).
    allowlist: list[str] = field(default_factory=list)
    denylist: list[str] = field(default_factory=list)


@dataclass
class RiskConfig:
    # Capital (USD) the bot manages. It never touches funds beyond this budget.
    allocation_usd: float = 1_000.0
    min_order_usd: float = 10.0
    # Skip rebalancing a coin unless its drift exceeds this fraction of equity.
    rebalance_threshold: float = 0.02
    max_orders_per_cycle: int = 10
    # Stop when equity falls this far below its peak.
    max_drawdown: float = 0.25
    # "halt" stops trading; "flatten" sells everything and then stops.
    on_drawdown: str = "halt"
    # Paper-trading fill model.
    paper_fee_rate: float = 0.004
    paper_slippage_bps: float = 10.0


@dataclass
class Config:
    mode: str = "paper"  # "paper" or "live"
    quote: str = "USD"
    state_path: str = "state/bot_state.json"
    interval_seconds: int = 900
    leaderboard: LeaderboardConfig = field(default_factory=LeaderboardConfig)
    copy: CopyConfig = field(default_factory=CopyConfig)
    risk: RiskConfig = field(default_factory=RiskConfig)

    def validate(self) -> None:
        if self.mode not in ("paper", "live"):
            raise ValueError(f"mode must be 'paper' or 'live', got {self.mode!r}")
        if self.risk.on_drawdown not in ("halt", "flatten"):
            raise ValueError("risk.on_drawdown must be 'halt' or 'flatten'")
        if not 0 < self.copy.max_total_exposure <= 1.0:
            raise ValueError("copy.max_total_exposure must be in (0, 1] for spot trading")
        if not 0 < self.copy.max_position_pct <= 1.0:
            raise ValueError("copy.max_position_pct must be in (0, 1]")
        if self.risk.allocation_usd <= 0:
            raise ValueError("risk.allocation_usd must be positive")
        if not 0 < self.risk.max_drawdown < 1:
            raise ValueError("risk.max_drawdown must be in (0, 1)")
        if self.leaderboard.top_n < 1 or self.copy.min_traders_agree < 1:
            raise ValueError("leaderboard.top_n and copy.min_traders_agree must be >= 1")
        if self.copy.min_traders_agree > self.leaderboard.top_n + len(self.leaderboard.include):
            raise ValueError("copy.min_traders_agree exceeds the number of followed traders")


def _merge(obj, data: dict, path: str = ""):
    known = {f.name: f for f in fields(obj)}
    for key, value in data.items():
        if key not in known:
            raise ValueError(f"unknown config key: {path}{key}")
        current = getattr(obj, key)
        if is_dataclass(current):
            if not isinstance(value, dict):
                raise ValueError(f"config section {path}{key} must be a table")
            _merge(current, value, f"{path}{key}.")
        else:
            setattr(obj, key, value)
    return obj


# Environment variables that override the config file, so hosted deployments
# (Railway, Docker) can be tuned without editing or mounting a file.
ENV_OVERRIDES = {
    "COPYBOT_MODE": ("", "mode", str),
    "COPYBOT_STATE_PATH": ("", "state_path", str),
    "COPYBOT_INTERVAL_SECONDS": ("", "interval_seconds", int),
    "COPYBOT_TOP_N": ("leaderboard", "top_n", int),
    "COPYBOT_MIN_TRADERS_AGREE": ("copy", "min_traders_agree", int),
    "COPYBOT_ALLOCATION_USD": ("risk", "allocation_usd", float),
    "COPYBOT_MAX_DRAWDOWN": ("risk", "max_drawdown", float),
}


def apply_env_overrides(cfg: Config, env=os.environ) -> None:
    for var, (section, key, cast) in ENV_OVERRIDES.items():
        raw = env.get(var, "").strip()
        if not raw:
            continue
        try:
            value = cast(raw)
        except ValueError:
            raise ValueError(f"{var}={raw!r} is not a valid {cast.__name__}") from None
        setattr(getattr(cfg, section) if section else cfg, key, value)


def load_config(path: str | Path | None, env=os.environ) -> Config:
    cfg = Config()
    if path:
        with open(path, "rb") as fh:
            _merge(cfg, tomllib.load(fh))
    apply_env_overrides(cfg, env)
    cfg.leaderboard.include = [a.lower() for a in cfg.leaderboard.include]
    cfg.leaderboard.exclude = [a.lower() for a in cfg.leaderboard.exclude]
    cfg.copy.allowlist = [c.upper() for c in cfg.copy.allowlist]
    cfg.copy.denylist = [c.upper() for c in cfg.copy.denylist]
    cfg.validate()
    return cfg
