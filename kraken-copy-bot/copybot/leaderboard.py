"""Trader leaderboard: pull public trader performance and rank who to copy.

Kraken does not publish other traders' accounts, so the signal source is the
public Hyperliquid leaderboard, where every account's positions are on-chain and
readable. The bot ranks those traders with its own scoring and mirrors the
consensus of the best ones onto Kraken spot.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import requests

from .config import LeaderboardConfig

WINDOWS = ("day", "week", "month", "allTime")


class HyperliquidClient:
    LEADERBOARD_URL = "https://stats-data.hyperliquid.xyz/Mainnet/leaderboard"
    INFO_URL = "https://api.hyperliquid.xyz/info"

    def __init__(self, session: requests.Session | None = None, timeout: float = 30.0):
        self.session = session or requests.Session()
        self.timeout = timeout

    def leaderboard(self) -> list[dict]:
        resp = self.session.get(self.LEADERBOARD_URL, timeout=self.timeout)
        resp.raise_for_status()
        return resp.json()["leaderboardRows"]

    def clearinghouse_state(self, address: str) -> dict:
        resp = self.session.post(
            self.INFO_URL,
            json={"type": "clearinghouseState", "user": address},
            timeout=self.timeout,
        )
        resp.raise_for_status()
        return resp.json()


@dataclass
class TraderStats:
    address: str
    display_name: str | None
    account_value: float
    roi: dict[str, float] = field(default_factory=dict)
    pnl: dict[str, float] = field(default_factory=dict)
    volume: dict[str, float] = field(default_factory=dict)

    @property
    def month_turnover(self) -> float:
        if self.account_value <= 0:
            return float("inf")
        return self.volume.get("month", 0.0) / self.account_value

    @property
    def label(self) -> str:
        short = f"{self.address[:6]}…{self.address[-4:]}"
        return f"{self.display_name} ({short})" if self.display_name else short


@dataclass
class RankedTrader:
    stats: TraderStats
    score: float
    rank: int = 0
    pinned: bool = False

    @property
    def address(self) -> str:
        return self.stats.address


def parse_rows(rows: list[dict]) -> list[TraderStats]:
    traders = []
    for row in rows:
        try:
            perf = {name: data for name, data in row["windowPerformances"]}
            traders.append(
                TraderStats(
                    address=row["ethAddress"].lower(),
                    display_name=row.get("displayName"),
                    account_value=float(row["accountValue"]),
                    roi={w: float(perf[w]["roi"]) for w in WINDOWS if w in perf},
                    pnl={w: float(perf[w]["pnl"]) for w in WINDOWS if w in perf},
                    volume={w: float(perf[w]["vlm"]) for w in WINDOWS if w in perf},
                )
            )
        except (KeyError, TypeError, ValueError):
            continue  # malformed row; skip rather than fail the whole cycle
    return traders


def ineligibility_reason(t: TraderStats, cfg: LeaderboardConfig) -> str | None:
    if t.address in cfg.exclude:
        return "excluded"
    if t.account_value < cfg.min_account_value:
        return "account too small"
    if t.roi.get("month", float("-inf")) <= cfg.min_month_roi:
        return "month ROI too low"
    if t.pnl.get("allTime", float("-inf")) <= cfg.min_all_time_pnl:
        return "all-time PnL too low"
    if t.volume.get("month", 0.0) <= 0:
        return "inactive this month"
    if t.month_turnover > cfg.max_month_turnover:
        return "turnover too high (MM/HFT)"
    return None


def _percentiles(values: list[float]) -> list[float]:
    """Map each value to its rank percentile in (0, 1]; ties share the higher rank."""
    n = len(values)
    if n == 0:
        return []
    order = sorted(values)
    out = []
    for v in values:
        # count of values <= v
        lo, hi = 0, n
        while lo < hi:
            mid = (lo + hi) // 2
            if order[mid] <= v:
                lo = mid + 1
            else:
                hi = mid
        out.append(lo / n)
    return out


def rank_traders(traders: list[TraderStats], cfg: LeaderboardConfig) -> list[RankedTrader]:
    """Score eligible traders by weighted percentiles; pinned traders are always kept.

    A weight key like "month" scores that window's ROI; "pnl_allTime" scores its dollar PnL.
    """
    eligible = [t for t in traders if ineligibility_reason(t, cfg) is None]
    pinned = [
        t for t in traders
        if t.address in cfg.include and t.address not in cfg.exclude and t not in eligible
    ]
    pool = eligible + pinned
    total_weight = sum(cfg.weights.values()) or 1.0
    scores = [0.0] * len(pool)
    for window, weight in cfg.weights.items():
        if window.startswith("pnl_"):
            values = [t.pnl.get(window[4:], 0.0) for t in pool]
        else:
            values = [t.roi.get(window, 0.0) for t in pool]
        pct = _percentiles(values)
        for i, p in enumerate(pct):
            scores[i] += weight * p / total_weight

    ranked = [
        RankedTrader(stats=t, score=s, pinned=t.address in cfg.include)
        for t, s in zip(pool, scores)
    ]
    ranked.sort(key=lambda r: (r.pinned, r.score, r.stats.roi.get("month", 0.0)), reverse=True)
    for i, r in enumerate(ranked, 1):
        r.rank = i
    return ranked


def select_followed(ranked: list[RankedTrader], cfg: LeaderboardConfig) -> list[RankedTrader]:
    pinned = [r for r in ranked if r.pinned]
    rest = [r for r in ranked if not r.pinned][: cfg.top_n]
    return pinned + rest
