"""Command-line entry point: `python -m copybot <command>`."""

from __future__ import annotations

import argparse
import logging
import os
import signal
import sys
import time

from .broker import LiveBroker, PaperBroker
from .config import Config, load_config
from .engine import CopyBot, CycleReport
from .kraken import KrakenClient, build_universe
from .leaderboard import HyperliquidClient, ineligibility_reason, parse_rows, select_followed
from .state import BotState

log = logging.getLogger("copybot")


def make_bot(cfg: Config, confirm_live: bool) -> CopyBot:
    if cfg.mode == "live":
        key, secret = os.environ.get("KRAKEN_API_KEY"), os.environ.get("KRAKEN_API_SECRET")
        if not (key and secret):
            sys.exit("live mode needs KRAKEN_API_KEY and KRAKEN_API_SECRET in the environment")
        if not confirm_live:
            sys.exit("live mode places real orders; re-run with --confirm-live to proceed")
        kraken = KrakenClient(key, secret)
        broker = LiveBroker(kraken)
    else:
        kraken = KrakenClient()
        broker = PaperBroker(cfg.risk.paper_fee_rate, cfg.risk.paper_slippage_bps)
    return CopyBot(cfg, HyperliquidClient(), kraken, broker)


def run_check(cfg: Config) -> int:
    """Verify connectivity and Kraken credentials without placing any order."""
    key, secret = os.environ.get("KRAKEN_API_KEY"), os.environ.get("KRAKEN_API_SECRET")
    client = KrakenClient(key, secret)
    broker = LiveBroker(client)
    failures = 0
    ctx: dict = {}

    def step(name, fn):
        nonlocal failures
        try:
            print(f"  ok    {name}: {fn()}")
        except Exception as exc:
            failures += 1
            print(f"  FAIL  {name}: {exc}")

    def universe():
        ctx["universe"] = build_universe(client.asset_pairs(), cfg.quote)
        return f"{len(ctx['universe'])} online {cfg.quote} spot pairs"

    print("public:")
    step("Kraken status", client.system_status)
    step("Kraken markets", universe)
    step("Hyperliquid leaderboard", lambda: f"{len(HyperliquidClient().leaderboard())} traders")

    if not (key and secret):
        print("private: skipped (set KRAKEN_API_KEY and KRAKEN_API_SECRET to check your key)")
        return 1 if failures else 0

    def balances():
        usd, coins = broker.balances(ctx["universe"])
        held = {c: q for c, q in coins.items() if q > 0}
        note = "" if usd >= cfg.risk.allocation_usd else (
            f" -- below allocation_usd ${cfg.risk.allocation_usd:,.2f}; buys will be capped"
        )
        return f"${usd:,.2f} {cfg.quote} available{note}; other holdings: {held or 'none'}"

    def can_trade():
        pair = ctx["universe"]["BTC"]
        broker.validate_order(pair, "buy", pair.ordermin)
        return f"validate-only buy of {pair.ordermin} BTC accepted (nothing was placed)"

    print("private:")
    step("balance (Query Funds)", balances)
    step("order permission (Create & Modify Orders)", can_trade)
    print("\nall checks passed" if not failures else f"\n{failures} check(s) failed")
    return 1 if failures else 0


def pct(x: float) -> str:
    return f"{x * 100:+.1f}%"


def print_leaderboard(bot: CopyBot, limit: int) -> None:
    ranked = bot.leaderboard()
    followed = {r.address for r in select_followed(ranked, bot.cfg.leaderboard)}
    print(f"{'#':>3}  {'trader':<34} {'score':>6} {'acct $':>14} {'week':>8} {'month':>8} {'allTime':>9}  follow")
    for r in ranked[:limit]:
        s = r.stats
        print(
            f"{r.rank:>3}  {s.label[:34]:<34} {r.score:6.3f} {s.account_value:14,.0f} "
            f"{pct(s.roi.get('week', 0)):>8} {pct(s.roi.get('month', 0)):>8} {pct(s.roi.get('allTime', 0)):>9}  "
            f"{'yes' + (' (pinned)' if r.pinned else '') if r.address in followed else ''}"
        )
    print(f"\n{len(ranked)} eligible traders; following {len(followed)}.")


def print_report(report: CycleReport, mode: str) -> None:
    print(f"[{mode}] equity ${report.equity:,.2f}  peak ${report.peak_equity:,.2f}  drawdown {report.drawdown:.1%}")
    if report.followed:
        print("following: " + ", ".join(t.stats.label for t in report.followed))
    if report.targets:
        print("\ntarget portfolio:")
        for t in sorted(report.targets.values(), key=lambda t: -t.weight):
            print(f"  {t.coin:<8} {t.weight:6.1%}  (consensus {t.raw_exposure:+.2f}x, {t.longs} long / {t.shorts} short)")
    else:
        print("\ntarget portfolio: all cash")
    if report.skipped:
        print("skipped: " + "; ".join(f"{c}: {why}" for c, why in sorted(report.skipped.items())[:15]))
    if report.planned:
        print("\norders planned:")
        for o in report.planned:
            print(f"  {o.side:<4} {o.volume:>16.8f} {o.coin:<8} ~${o.est_usd:,.2f} ({o.reason})")
    for f in report.fills:
        print(f"  filled {f.side} {f.volume:.8f} {f.coin} @ {f.price:,.6f}  fee ${f.fee:.2f}  {f.txid}")
    for e in report.errors:
        print(f"  error: {e}")
    if report.note:
        print(f"\nnote: {report.note}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="copybot", description="Leaderboard copy-trading bot for Kraken spot")
    parser.add_argument("-c", "--config", default=os.environ.get("COPYBOT_CONFIG"), help="TOML config file")
    parser.add_argument("-v", "--verbose", action="store_true")
    sub = parser.add_subparsers(dest="command", required=True)
    lb = sub.add_parser("leaderboard", help="show the ranked trader leaderboard")
    lb.add_argument("-n", "--limit", type=int, default=25)
    sub.add_parser("plan", help="compute targets and orders without trading")
    once = sub.add_parser("once", help="run one trading cycle")
    once.add_argument("--confirm-live", action="store_true")
    run = sub.add_parser("run", help="trade continuously every interval_seconds")
    run.add_argument("--confirm-live", action="store_true")
    sub.add_parser("status", help="show the saved bot state")
    sub.add_parser("reset", help="clear a drawdown halt (keeps holdings and peak reset to current equity)")
    sub.add_parser("explain", help="show why top leaderboard traders were filtered out")
    sub.add_parser("check", help="test connectivity and Kraken API key permissions (places no orders)")
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    cfg = load_config(args.config)

    if args.command == "status":
        state = BotState.load(cfg.state_path, cfg.risk.allocation_usd)
        print(f"mode={cfg.mode} cash=${state.cash_usd:,.2f} last_equity=${state.last_equity:,.2f} "
              f"peak=${state.peak_equity:,.2f} halted={state.halted} {state.halt_reason}")
        for coin, qty in sorted(state.holdings.items()):
            print(f"  {coin:<8} {qty:.8f}")
        print(f"last cycle: {state.last_cycle or 'never'}")
        return 0
    if args.command == "reset":
        state = BotState.load(cfg.state_path, cfg.risk.allocation_usd)
        state.halted, state.halt_reason = False, ""
        state.peak_equity = state.last_equity or state.cash_usd
        state.save(cfg.state_path)
        print("halt cleared; peak equity reset to last equity")
        return 0

    if args.command == "check":
        return run_check(cfg)

    bot = make_bot(cfg, getattr(args, "confirm_live", False))

    if args.command == "leaderboard":
        print_leaderboard(bot, args.limit)
    elif args.command == "explain":
        traders = sorted(parse_rows(bot.hl.leaderboard()), key=lambda t: -t.pnl.get("month", 0))[:30]
        for t in traders:
            why = ineligibility_reason(t, cfg.leaderboard) or "eligible"
            print(f"  {t.label[:34]:<34} month pnl ${t.pnl.get('month', 0):>14,.0f}  -> {why}")
    elif args.command == "plan":
        print_report(bot.run_cycle(dry_run=True), cfg.mode + ", dry run")
    elif args.command == "once":
        print_report(bot.run_cycle(), cfg.mode)
    elif args.command == "run":
        stop = {"flag": False}

        def _stop(*_):
            stop["flag"] = True
            log.info("shutdown requested; finishing current cycle")

        signal.signal(signal.SIGINT, _stop)
        signal.signal(signal.SIGTERM, _stop)
        while not stop["flag"]:
            try:
                print_report(bot.run_cycle(), cfg.mode)
            except Exception:
                log.exception("cycle failed; will retry next interval")
            deadline = time.monotonic() + cfg.interval_seconds
            while not stop["flag"] and time.monotonic() < deadline:
                time.sleep(1)
    return 0


if __name__ == "__main__":
    sys.exit(main())
