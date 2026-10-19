import json

import pytest

from copybot.broker import PaperBroker
from copybot.config import Config, CopyConfig, LeaderboardConfig, RiskConfig, load_config
from copybot.consensus import TraderPositions, build_targets, normalize_coin, parse_positions
from copybot.engine import CopyBot, plan_rebalance, round_down
from copybot.kraken import KrakenClient, PairInfo, Quote, build_universe
from copybot.leaderboard import RankedTrader, TraderStats, parse_rows, rank_traders, select_followed
from copybot.state import BotState, trade_log_path


def row(addr, acct, month_roi, week_roi=0.1, all_roi=1.0, all_pnl=1e6, month_vlm=1e7, name=None):
    perf = {
        "day": {"pnl": "0", "roi": "0", "vlm": "0"},
        "week": {"pnl": "1", "roi": str(week_roi), "vlm": "1"},
        "month": {"pnl": "1", "roi": str(month_roi), "vlm": str(month_vlm)},
        "allTime": {"pnl": str(all_pnl), "roi": str(all_roi), "vlm": "1"},
    }
    return {"ethAddress": addr, "accountValue": str(acct), "displayName": name,
            "windowPerformances": [[k, v] for k, v in perf.items()]}


def ch_state(acct, positions):
    return {
        "marginSummary": {"accountValue": str(acct)},
        "assetPositions": [
            {"position": {"coin": c, "szi": str(szi), "positionValue": str(abs(val))}} for c, szi, val in positions
        ],
    }


PAIRS = {
    "XXBTZUSD": {"altname": "XBTUSD", "wsname": "XBT/USD", "base": "XXBT", "lot_decimals": 8,
                 "pair_decimals": 1, "ordermin": "0.00005", "costmin": "0.5", "status": "online",
                 "aclass_base": "currency"},
    "XETHZUSD": {"altname": "ETHUSD", "wsname": "ETH/USD", "base": "XETH", "lot_decimals": 8,
                 "pair_decimals": 2, "ordermin": "0.002", "costmin": "0.5", "status": "online",
                 "aclass_base": "currency"},
    "SOLUSD": {"altname": "SOLUSD", "wsname": "SOL/USD", "base": "SOL", "lot_decimals": 8,
               "pair_decimals": 2, "ordermin": "0.02", "costmin": "0.5", "status": "online",
               "aclass_base": "currency"},
    "XXBTZEUR": {"altname": "XBTEUR", "wsname": "XBT/EUR", "base": "XXBT", "lot_decimals": 8,
                 "pair_decimals": 1, "ordermin": "0.00005", "costmin": "0.5", "status": "online",
                 "aclass_base": "currency"},
}


# --- Kraken -----------------------------------------------------------------

def test_kraken_signature_matches_documented_example():
    # Example from Kraken's REST authentication docs.
    secret = "kQH5HW/8p1uGOVjbgWA7FunAmGO8lsSUXNsu3eow76sz84Q18fWxnyRzBHCd3pd5nE9qa99HAZtuZuj6F1huXg=="
    data = {"nonce": "1616492376594", "ordertype": "limit", "pair": "XBTUSD",
            "price": 37500, "type": "buy", "volume": 1.25}
    expected = "4/dpxb3iT4tp/ZCVEwSnEsLxx0bqyhLpdfOpc6fn7OR8+UClSV5n9E6aSS8MPtnRfp32bAb0nmbRn6H8ndwLUQ=="
    assert KrakenClient.sign("/0/private/AddOrder", data, secret) == expected


def test_nonce_strictly_increases():
    client = KrakenClient()
    nonces = [client._nonce() for _ in range(50)]
    assert nonces == sorted(set(nonces))


def test_build_universe_maps_kraken_codes_and_filters_quote():
    u = build_universe(PAIRS, "USD")
    assert set(u) == {"BTC", "ETH", "SOL"}
    assert u["BTC"].altname == "XBTUSD" and u["BTC"].base_asset == "XXBT"


# --- leaderboard ------------------------------------------------------------

def test_rank_filters_and_orders():
    rows = [
        row("0xA", 1e6, 0.50),
        row("0xB", 1e6, 0.10),
        row("0xC", 1e3, 0.90),                 # too small
        row("0xD", 1e6, -0.10),                # losing month
        row("0xE", 1e6, 0.30, month_vlm=1e10),  # turnover 10000x: market maker
        row("0xF", 1e6, 0.20, all_pnl=-5),     # losing all-time
    ]
    cfg = LeaderboardConfig(min_account_value=1e5, weights={"month": 1.0})
    ranked = rank_traders(parse_rows(rows), cfg)
    assert [r.address for r in ranked] == ["0xa", "0xb"]
    assert ranked[0].score > ranked[1].score and ranked[0].rank == 1


def test_pinned_and_excluded_traders():
    rows = [row("0xA", 1e6, 0.5), row("0xB", 1e6, 0.4), row("0xSMALL", 10, 0.1)]
    cfg = LeaderboardConfig(min_account_value=1e5, top_n=1, include=["0xsmall"], exclude=["0xa"])
    followed = select_followed(rank_traders(parse_rows(rows), cfg), cfg)
    assert [r.address for r in followed] == ["0xsmall", "0xb"]


def test_pnl_weight_key_ranks_by_dollar_pnl():
    rows = [row("0xA", 1e6, 0.5, all_pnl=1e5), row("0xB", 1e6, 0.4, all_pnl=1e8)]
    cfg = LeaderboardConfig(min_account_value=1e5, weights={"pnl_allTime": 1.0})
    assert rank_traders(parse_rows(rows), cfg)[0].address == "0xb"


def test_malformed_rows_are_skipped():
    assert parse_rows([{"ethAddress": "0x1"}, row("0x2", 1e6, 0.1)])[0].address == "0x2"


# --- consensus --------------------------------------------------------------

def trader(addr, score):
    return RankedTrader(TraderStats(addr, None, 1e6), score)


def test_normalize_coin():
    assert normalize_coin("kPEPE") == "PEPE"
    assert normalize_coin("BTC") == "BTC"
    assert normalize_coin("xyz:GOLD") is None
    assert normalize_coin("@107") is None


def test_parse_positions_signed_exposure():
    p = parse_positions("0x1", ch_state(1000, [("BTC", 0.01, 500), ("ETH", -1, 250)]))
    assert p.exposures == {"BTC": 0.5, "ETH": -0.25}


def test_build_targets_consensus_caps_and_long_only():
    followed = [
        (trader("a", 2.0), TraderPositions("a", 1, {"BTC": 1.0, "ETH": 0.5, "SOL": -1.0})),
        (trader("b", 1.0), TraderPositions("b", 1, {"BTC": 0.5, "SOL": 0.2, "DOGE": 1.0})),
    ]
    cfg = CopyConfig(min_traders_agree=2, max_position_pct=0.5, max_total_exposure=0.9)
    targets, skipped = build_targets(followed, cfg, {"BTC", "ETH", "SOL"})
    # BTC raw = 2/3*1.0 + 1/3*0.5 = 0.833 -> capped to 0.5
    assert set(targets) == {"BTC"}
    assert targets["BTC"].weight == pytest.approx(0.5)
    assert "1 trader" in skipped["ETH"]
    assert "short" in skipped["SOL"]
    assert "1 trader" in skipped["DOGE"]


def test_build_targets_scales_down_gross_exposure():
    followed = [(trader("a", 1.0), TraderPositions("a", 1, {"BTC": 0.6, "ETH": 0.6}))]
    cfg = CopyConfig(min_traders_agree=1, max_position_pct=1.0, max_total_exposure=0.6)
    targets, _ = build_targets(followed, cfg, {"BTC", "ETH"})
    assert sum(t.weight for t in targets.values()) == pytest.approx(0.6)


# --- rebalancing ------------------------------------------------------------

UNIVERSE = build_universe(PAIRS, "USD")
QUOTES = {"BTC": Quote(99_990, 100_010), "ETH": Quote(3_999, 4_001), "SOL": Quote(199.9, 200.1)}


def test_round_down():
    assert round_down(1.23456789, 4) == 1.2345
    assert round_down(0.3, 1) == 0.3


def test_plan_buys_from_cash():
    state = BotState.fresh(1000)
    orders = plan_rebalance({"BTC": 0.5}, state, QUOTES, UNIVERSE, RiskConfig())
    assert len(orders) == 1 and orders[0].side == "buy"
    assert orders[0].est_usd == pytest.approx(500, rel=0.01)


def test_plan_exits_dropped_coins_and_sells_first():
    state = BotState(cash_usd=500, holdings={"ETH": 0.125})  # $500 of ETH
    orders = plan_rebalance({"BTC": 0.5}, state, QUOTES, UNIVERSE, RiskConfig())
    assert [(o.side, o.coin, o.reason) for o in orders] == [("sell", "ETH", "exit"), ("buy", "BTC", "enter")]
    assert orders[0].volume == 0.125


def test_plan_ignores_small_drift():
    state = BotState(cash_usd=500, holdings={"BTC": 0.0049})  # ~$490 vs $500 target
    assert plan_rebalance({"BTC": 0.5}, state, QUOTES, UNIVERSE, RiskConfig()) == []


def test_plan_respects_order_minimums():
    state = BotState.fresh(20)
    # $2 of ETH is below Kraken's 0.002 ETH ordermin
    assert plan_rebalance({"ETH": 0.1}, state, QUOTES, UNIVERSE, RiskConfig(min_order_usd=1)) == []


# --- full cycle -------------------------------------------------------------

class FakeHL:
    def __init__(self, rows, states):
        self.rows, self.states = rows, states

    def leaderboard(self):
        return self.rows

    def clearinghouse_state(self, address):
        if address not in self.states:
            raise RuntimeError("boom")
        return self.states[address]


class FakeKraken:
    def __init__(self, quotes):
        self._quotes = quotes

    def asset_pairs(self):
        return PAIRS

    def quotes(self, pairs):
        return {p.coin: self._quotes[p.coin] for p in pairs if p.coin in self._quotes}


def make_cfg(tmp_path, **risk):
    cfg = Config(state_path=str(tmp_path / "state.json"))
    cfg.leaderboard = LeaderboardConfig(min_account_value=1e5, top_n=2)
    cfg.copy = CopyConfig(min_traders_agree=2, max_position_pct=0.5)
    cfg.risk = RiskConfig(allocation_usd=1000, **risk)
    return cfg


def make_bot(cfg, states, quotes=QUOTES):
    hl = FakeHL([row("0xa", 1e6, 0.5), row("0xb", 1e6, 0.4)], states)
    return CopyBot(cfg, hl, FakeKraken(quotes), PaperBroker(0.004, 10))


BOTH_LONG_BTC = {
    "0xa": ch_state(1e6, [("BTC", 3, 3e5)]),
    "0xb": ch_state(1e6, [("BTC", 2, 2e5), ("ETH", -10, 4e4)]),
}


def test_cycle_buys_consensus_and_persists(tmp_path):
    cfg = make_cfg(tmp_path)
    report = make_bot(cfg, BOTH_LONG_BTC).run_cycle()
    assert [(f.side, f.coin) for f in report.fills] == [("buy", "BTC")]
    state = BotState.load(cfg.state_path, 1000)
    assert state.holdings["BTC"] > 0
    assert state.cash_usd == pytest.approx(1000 - report.fills[0].cost - report.fills[0].fee)
    assert json.loads(trade_log_path(cfg.state_path).read_text().splitlines()[0])["coin"] == "BTC"
    # A second cycle with unchanged signals trades nothing.
    assert make_bot(cfg, BOTH_LONG_BTC).run_cycle().fills == []


def test_cycle_exits_when_traders_close(tmp_path):
    cfg = make_cfg(tmp_path)
    make_bot(cfg, BOTH_LONG_BTC).run_cycle()
    flat = {"0xa": ch_state(1e6, []), "0xb": ch_state(1e6, [])}
    report = make_bot(cfg, flat).run_cycle()
    assert [(f.side, f.coin) for f in report.fills] == [("sell", "BTC")]
    assert BotState.load(cfg.state_path, 1000).holdings == {}


def test_cycle_does_not_trade_on_incomplete_data(tmp_path):
    cfg = make_cfg(tmp_path)
    make_bot(cfg, BOTH_LONG_BTC).run_cycle()
    report = make_bot(cfg, {"0xa": ch_state(1e6, [])}).run_cycle()  # 0xb fetch fails
    assert report.fills == [] and "incomplete" in report.note
    assert BotState.load(cfg.state_path, 1000).holdings["BTC"] > 0


def test_dry_run_does_not_touch_state(tmp_path):
    cfg = make_cfg(tmp_path)
    report = make_bot(cfg, BOTH_LONG_BTC).run_cycle(dry_run=True)
    assert report.planned and not report.fills
    assert not (tmp_path / "state.json").exists()


@pytest.mark.parametrize("mode,expect_holdings", [("halt", True), ("flatten", False)])
def test_drawdown_halts(tmp_path, mode, expect_holdings):
    cfg = make_cfg(tmp_path, max_drawdown=0.2, on_drawdown=mode)
    make_bot(cfg, BOTH_LONG_BTC).run_cycle()
    crashed = dict(QUOTES, BTC=Quote(1_000, 1_001))  # BTC -99% with ~25% of equity in it
    report = make_bot(cfg, BOTH_LONG_BTC, crashed).run_cycle()
    assert report.halted
    state = BotState.load(cfg.state_path, 1000)
    assert state.halted
    assert bool(state.holdings) is expect_holdings
    # Stays halted on later cycles.
    assert make_bot(cfg, BOTH_LONG_BTC, crashed).run_cycle().fills == []


def test_load_config_example_and_validation(tmp_path):
    import pathlib
    example = pathlib.Path(__file__).parent.parent / "config.example.toml"
    cfg = load_config(example)
    assert cfg.mode == "paper" and cfg.leaderboard.weights["pnl_allTime"] == 0.25
    bad = tmp_path / "bad.toml"
    bad.write_text('[risk]\nnot_a_key = 1\n')
    with pytest.raises(ValueError):
        load_config(bad)
    bad.write_text('mode = "yolo"\n')
    with pytest.raises(ValueError):
        load_config(bad)


# --- live broker (fake Kraken private API) ----------------------------------

from copybot.broker import LiveBroker


class FakePrivateKraken:
    def __init__(self, statuses, balance=None):
        self.statuses = list(statuses)  # successive QueryOrders statuses
        self.balance_data = balance or {}
        self.placed, self.cancelled = [], []

    def balance(self):
        return self.balance_data

    def add_market_order(self, pair, side, volume, validate=False):
        self.placed.append((pair.altname, side, volume, validate))
        return [] if validate else ["TX1"]

    def query_orders(self, txids):
        status = self.statuses.pop(0) if len(self.statuses) > 1 else self.statuses[0]
        filled = {"closed": "0.01", "canceled": "0.004"}.get(status, "0.004")
        return {"TX1": {"status": status, "vol_exec": filled, "cost": str(float(filled) * 100_000),
                        "fee": "1.5", "price": "100000"}}

    def cancel_order(self, txid):
        self.cancelled.append(txid)
        self.statuses = ["canceled"]


def test_live_broker_books_closed_fill():
    client = FakePrivateKraken(["open", "closed"])
    fill = LiveBroker(client, fill_timeout=5, poll_interval=0).execute(UNIVERSE["BTC"], "buy", 0.01, QUOTES["BTC"])
    assert client.placed == [("XBTUSD", "buy", "0.01000000", False)]
    assert (fill.volume, fill.cost, fill.fee, fill.txid) == (0.01, 1000.0, 1.5, "TX1")
    assert client.cancelled == []


def test_live_broker_cancels_unfilled_remainder():
    client = FakePrivateKraken(["open"])
    fill = LiveBroker(client, fill_timeout=0, poll_interval=0).execute(UNIVERSE["BTC"], "buy", 0.01, QUOTES["BTC"])
    assert client.cancelled == ["TX1"]
    assert fill.volume == 0.004  # only the part that actually filled is booked


def test_live_broker_balances_merge_earn_and_usd_codes():
    client = FakePrivateKraken(["closed"], {"ZUSD": 100.0, "USD.F": 5.0, "XXBT": 0.1, "XXBT.F": 0.05, "SOL": 2.0})
    usd, coins = LiveBroker(client).balances(UNIVERSE)
    assert usd == 105.0
    assert coins["BTC"] == pytest.approx(0.15) and coins["SOL"] == 2.0 and coins["ETH"] == 0.0


def test_live_broker_validate_places_nothing():
    client = FakePrivateKraken(["closed"])
    LiveBroker(client).validate_order(UNIVERSE["BTC"], "buy", 0.00005)
    assert client.placed == [("XBTUSD", "buy", "0.00005000", True)]


def test_live_cycle_clamps_sells_to_real_balance(tmp_path):
    cfg = make_cfg(tmp_path)
    make_bot(cfg, BOTH_LONG_BTC).run_cycle()  # paper-buy BTC into state
    held = BotState.load(cfg.state_path, 1000).holdings["BTC"]

    class Recorder(PaperBroker):
        live = True
        def __init__(self):
            super().__init__(0.004, 10)
            self.sold = []
        def balances(self, universe):
            return 10_000.0, {"BTC": held / 2}  # user moved half the BTC away
        def execute(self, pair, side, volume, quote):
            self.sold.append(volume)
            return super().execute(pair, side, volume, quote)

    broker = Recorder()
    bot = CopyBot(cfg, FakeHL([row("0xa", 1e6, 0.5), row("0xb", 1e6, 0.4)],
                              {"0xa": ch_state(1e6, []), "0xb": ch_state(1e6, [])}), FakeKraken(QUOTES), broker)
    bot.run_cycle()
    assert broker.sold == [round_down(held / 2, 8)]


def test_env_overrides(tmp_path):
    import pathlib
    example = pathlib.Path(__file__).parent.parent / "config.example.toml"
    env = {"COPYBOT_MODE": "live", "COPYBOT_ALLOCATION_USD": "250", "COPYBOT_TOP_N": "5",
           "COPYBOT_STATE_PATH": "/data/s.json", "COPYBOT_INTERVAL_SECONDS": " "}
    cfg = load_config(example, env)
    assert (cfg.mode, cfg.risk.allocation_usd, cfg.leaderboard.top_n, cfg.state_path) == ("live", 250.0, 5, "/data/s.json")
    assert cfg.interval_seconds == 900  # blank values are ignored
    with pytest.raises(ValueError, match="COPYBOT_TOP_N"):
        load_config(example, {"COPYBOT_TOP_N": "ten"})
    with pytest.raises(ValueError):
        load_config(example, {"COPYBOT_MODE": "yolo"})  # still validated


def test_live_mode_requires_confirmation(monkeypatch, tmp_path):
    from copybot.cli import make_bot
    cfg = make_cfg(tmp_path)
    cfg.mode = "live"
    monkeypatch.setenv("KRAKEN_API_KEY", "k")
    monkeypatch.setenv("KRAKEN_API_SECRET", "c2VjcmV0")
    monkeypatch.delenv("COPYBOT_CONFIRM_LIVE", raising=False)
    with pytest.raises(SystemExit):
        make_bot(cfg, confirm_live=False)
    monkeypatch.setenv("COPYBOT_CONFIRM_LIVE", "yes")
    assert isinstance(make_bot(cfg, confirm_live=False).broker, LiveBroker)
