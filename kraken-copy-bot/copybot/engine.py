"""The copy-trading cycle: rank -> read positions -> target portfolio -> rebalance."""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass, field

from .broker import Fill, LiveBroker, PaperBroker
from .config import Config, RiskConfig
from .consensus import Target, TraderPositions, build_targets, parse_positions
from .kraken import KrakenClient, PairInfo, Quote, build_universe
from .leaderboard import HyperliquidClient, RankedTrader, parse_rows, rank_traders, select_followed
from .state import BotState, append_trade, utcnow

log = logging.getLogger(__name__)

# Headroom kept when sizing buys so fees and slippage never overdraw cash.
BUY_BUFFER = 0.01


def round_down(x: float, decimals: int) -> float:
    factor = 10**decimals
    return math.floor(x * factor + 1e-9) / factor


@dataclass
class PlannedOrder:
    coin: str
    side: str
    volume: float
    est_usd: float
    reason: str


@dataclass
class CycleReport:
    equity: float = 0.0
    peak_equity: float = 0.0
    drawdown: float = 0.0
    followed: list[RankedTrader] = field(default_factory=list)
    targets: dict[str, Target] = field(default_factory=dict)
    skipped: dict[str, str] = field(default_factory=dict)
    planned: list[PlannedOrder] = field(default_factory=list)
    fills: list[Fill] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    halted: bool = False
    note: str = ""


def plan_rebalance(
    weights: dict[str, float],
    state: BotState,
    quotes: dict[str, Quote],
    universe: dict[str, PairInfo],
    risk: RiskConfig,
) -> list[PlannedOrder]:
    prices = {c: q.mid for c, q in quotes.items()}
    equity = state.equity(prices)
    threshold = max(risk.min_order_usd, risk.rebalance_threshold * equity)
    sells: list[PlannedOrder] = []
    buys: list[PlannedOrder] = []

    held = {c for c, q in state.holdings.items() if q > 0}
    for coin in sorted(set(weights) | held):
        pair, quote = universe.get(coin), quotes.get(coin)
        if pair is None or quote is None:
            continue
        qty = state.holdings.get(coin, 0.0)
        target_w = weights.get(coin, 0.0)
        delta = target_w * equity - qty * quote.mid

        if delta < 0:
            exiting = target_w == 0
            if not exiting and -delta < threshold:
                continue
            volume = qty if exiting else min(qty, -delta / quote.bid)
            side, reason = "sell", "exit" if exiting else "trim"
        else:
            if delta < threshold:
                continue
            volume = delta / quote.ask
            side, reason = "buy", "enter" if qty == 0 else "add"

        volume = round_down(volume, pair.lot_decimals)
        est = volume * quote.mid
        if volume <= 0 or volume < pair.ordermin or est < pair.costmin:
            continue
        order = PlannedOrder(coin, side, volume, est, reason)
        (sells if side == "sell" else buys).append(order)

    buys.sort(key=lambda o: o.est_usd, reverse=True)
    return (sells + buys)[: risk.max_orders_per_cycle]


class CopyBot:
    def __init__(
        self,
        cfg: Config,
        hyperliquid: HyperliquidClient,
        kraken: KrakenClient,
        broker: PaperBroker | LiveBroker,
    ):
        self.cfg = cfg
        self.hl = hyperliquid
        self.kraken = kraken
        self.broker = broker

    # --- signal side --------------------------------------------------------
    def leaderboard(self) -> list[RankedTrader]:
        return rank_traders(parse_rows(self.hl.leaderboard()), self.cfg.leaderboard)

    def universe(self) -> dict[str, PairInfo]:
        return build_universe(self.kraken.asset_pairs(), self.cfg.quote)

    def compute_targets(self, universe: dict[str, PairInfo]):
        ranked = self.leaderboard()
        followed = select_followed(ranked, self.cfg.leaderboard)
        positions: list[tuple[RankedTrader, TraderPositions]] = []
        errors = []
        for trader in followed:
            try:
                state = self.hl.clearinghouse_state(trader.address)
                positions.append((trader, parse_positions(trader.address, state)))
            except Exception as exc:  # one bad fetch shouldn't kill the cycle
                errors.append(f"positions for {trader.stats.label}: {exc}")
                log.warning("failed to fetch positions for %s: %s", trader.address, exc)
        targets, skipped = build_targets(positions, self.cfg.copy, set(universe))
        return followed, positions, targets, skipped, errors

    # --- execution side -----------------------------------------------------
    def run_cycle(self, dry_run: bool = False) -> CycleReport:
        cfg, risk = self.cfg, self.cfg.risk
        state = BotState.load(cfg.state_path, risk.allocation_usd)
        report = CycleReport()

        universe = self.universe()
        followed, positions, targets, skipped, errors = self.compute_targets(universe)
        report.followed, report.targets, report.skipped, report.errors = followed, targets, skipped, errors

        coins = (set(targets) | {c for c, q in state.holdings.items() if q > 0}) & set(universe)
        quotes = self.kraken.quotes([universe[c] for c in sorted(coins)])
        prices = {c: q.mid for c, q in quotes.items()}
        missing = {c for c, q in state.holdings.items() if q > 0} - set(prices)
        if missing:
            report.note = f"no price for held coin(s) {sorted(missing)}; skipping cycle"
            return report

        equity = state.equity(prices)
        state.peak_equity = max(state.peak_equity, equity)
        state.last_equity = equity
        report.equity, report.peak_equity = equity, state.peak_equity
        report.drawdown = 1 - equity / state.peak_equity if state.peak_equity else 0.0

        weights = {c: t.weight for c, t in targets.items()}
        if state.halted:
            report.halted, report.note = True, f"halted: {state.halt_reason} (run `reset` to resume)"
            return report
        if report.drawdown >= risk.max_drawdown:
            state.halted = True
            state.halt_reason = f"drawdown {report.drawdown:.1%} >= {risk.max_drawdown:.1%} at {utcnow()}"
            report.halted = True
            report.note = state.halt_reason
            if risk.on_drawdown != "flatten":
                if not dry_run:
                    state.save(cfg.state_path)
                return report
            weights = {}  # flatten: sell everything
        elif len(positions) < cfg.copy.min_traders_agree:
            report.note = (
                f"only {len(positions)} trader position set(s) fetched; "
                "not rebalancing on incomplete data"
            )
            return report

        report.planned = plan_rebalance(weights, state, quotes, universe, risk)
        if dry_run:
            return report

        usd_balance, coin_balances = None, {}
        bal = self.broker.balances(universe)
        if bal is not None:
            usd_balance, coin_balances = bal

        for order in report.planned:
            pair, quote = universe[order.coin], quotes[order.coin]
            volume = order.volume
            if order.side == "buy":
                cash = state.cash_usd if usd_balance is None else min(state.cash_usd, usd_balance)
                affordable = cash / (quote.ask * (1 + BUY_BUFFER + risk.paper_fee_rate))
                volume = round_down(min(volume, affordable), pair.lot_decimals)
            elif usd_balance is not None:
                volume = round_down(min(volume, coin_balances.get(order.coin, 0.0)), pair.lot_decimals)
            if volume <= 0 or volume < pair.ordermin or volume * quote.mid < max(pair.costmin, 1e-9):
                continue
            try:
                fill = self.broker.execute(pair, order.side, volume, quote)
            except Exception as exc:
                report.errors.append(f"{order.side} {order.coin}: {exc}")
                log.error("order failed: %s %s %s: %s", order.side, volume, order.coin, exc)
                continue
            if fill.volume <= 0:
                continue
            self._apply_fill(state, fill)
            if usd_balance is not None:
                sign = 1 if fill.side == "buy" else -1
                usd_balance -= sign * fill.cost + fill.fee
                coin_balances[fill.coin] = coin_balances.get(fill.coin, 0.0) + sign * fill.volume
            report.fills.append(fill)
            append_trade(cfg.state_path, {
                "mode": cfg.mode, "coin": fill.coin, "side": fill.side, "volume": fill.volume,
                "price": fill.price, "cost": fill.cost, "fee": fill.fee, "txid": fill.txid,
                "reason": order.reason,
            })

        state.followed = [t.address for t in followed]
        state.last_cycle = utcnow()
        state.last_equity = state.equity(prices)
        state.save(cfg.state_path)
        return report

    @staticmethod
    def _apply_fill(state: BotState, fill: Fill) -> None:
        qty = state.holdings.get(fill.coin, 0.0)
        if fill.side == "buy":
            state.holdings[fill.coin] = qty + fill.volume
            state.cash_usd -= fill.cost + fill.fee
        else:
            state.holdings[fill.coin] = max(0.0, qty - fill.volume)
            state.cash_usd += fill.cost - fill.fee
        if state.holdings[fill.coin] <= 1e-12:
            del state.holdings[fill.coin]
