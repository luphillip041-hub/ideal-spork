"""Turn the followed traders' live positions into a target Kraken spot portfolio."""

from __future__ import annotations

from dataclasses import dataclass, field

from .config import CopyConfig
from .leaderboard import RankedTrader


@dataclass
class TraderPositions:
    address: str
    account_value: float
    # coin -> signed notional / account value (e.g. 0.5 = long half the account)
    exposures: dict[str, float] = field(default_factory=dict)


@dataclass
class Target:
    coin: str
    weight: float  # fraction of bot equity to hold
    raw_exposure: float  # score-weighted consensus before caps
    longs: int
    shorts: int


def normalize_coin(coin: str) -> str | None:
    """Hyperliquid perp ticker -> plain asset ticker, or None if not mappable."""
    if ":" in coin or coin.startswith("@"):
        return None  # builder-dex or spot-index markets
    if len(coin) > 1 and coin[0] == "k" and coin[1:].isupper():
        return coin[1:]  # kPEPE is quoted per 1000 PEPE; notional is unaffected
    return coin.upper()


def parse_positions(address: str, state: dict) -> TraderPositions:
    account_value = float(state.get("marginSummary", {}).get("accountValue", 0) or 0)
    exposures: dict[str, float] = {}
    if account_value > 0:
        for item in state.get("assetPositions", []):
            pos = item.get("position", {})
            coin = normalize_coin(pos.get("coin", ""))
            try:
                size = float(pos["szi"])
                notional = abs(float(pos["positionValue"]))
            except (KeyError, TypeError, ValueError):
                continue
            if coin is None or size == 0:
                continue
            sign = 1.0 if size > 0 else -1.0
            exposures[coin] = exposures.get(coin, 0.0) + sign * notional / account_value
    return TraderPositions(address=address, account_value=account_value, exposures=exposures)


def build_targets(
    followed: list[tuple[RankedTrader, TraderPositions]],
    cfg: CopyConfig,
    tradable: set[str],
) -> tuple[dict[str, Target], dict[str, str]]:
    """Score-weighted consensus, long-only, capped. Returns (targets, skipped reasons)."""
    total_score = sum(r.score for r, _ in followed)
    if not followed or total_score <= 0:
        return {}, {}

    raw: dict[str, float] = {}
    longs: dict[str, int] = {}
    shorts: dict[str, int] = {}
    for trader, positions in followed:
        w = trader.score / total_score
        for coin, exp in positions.exposures.items():
            raw[coin] = raw.get(coin, 0.0) + w * exp
            if exp > 0:
                longs[coin] = longs.get(coin, 0) + 1
            elif exp < 0:
                shorts[coin] = shorts.get(coin, 0) + 1

    targets: dict[str, Target] = {}
    skipped: dict[str, str] = {}
    for coin, exp in raw.items():
        if exp <= 0:
            skipped[coin] = "net short/flat (spot is long-only)"
        elif longs.get(coin, 0) < cfg.min_traders_agree:
            skipped[coin] = f"only {longs.get(coin, 0)} trader(s) long"
        elif cfg.allowlist and coin not in cfg.allowlist:
            skipped[coin] = "not in allowlist"
        elif coin in cfg.denylist:
            skipped[coin] = "denylisted"
        elif coin not in tradable:
            skipped[coin] = "no Kraken spot market"
        else:
            weight = min(exp * cfg.exposure_scale, cfg.max_position_pct)
            targets[coin] = Target(coin, weight, exp, longs.get(coin, 0), shorts.get(coin, 0))

    gross = sum(t.weight for t in targets.values())
    if gross > cfg.max_total_exposure:
        factor = cfg.max_total_exposure / gross
        for t in targets.values():
            t.weight *= factor
    return targets, skipped
