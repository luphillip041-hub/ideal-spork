"""Order execution: a simulated paper broker and a live Kraken broker."""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass

from .kraken import KrakenAPIError, KrakenClient, PairInfo, Quote

log = logging.getLogger(__name__)


@dataclass
class Fill:
    coin: str
    side: str
    volume: float
    price: float
    cost: float  # quote currency, excluding fee
    fee: float
    txid: str = ""


def fmt_volume(volume: float, decimals: int) -> str:
    return f"{volume:.{decimals}f}"


class PaperBroker:
    live = False

    def __init__(self, fee_rate: float = 0.004, slippage_bps: float = 10.0):
        self.fee_rate = fee_rate
        self.slippage = slippage_bps / 10_000

    def balances(self, universe: dict[str, PairInfo]) -> tuple[float, dict[str, float]] | None:
        return None  # paper state is the source of truth

    def execute(self, pair: PairInfo, side: str, volume: float, quote: Quote) -> Fill:
        if side == "buy":
            price = quote.ask * (1 + self.slippage)
        else:
            price = quote.bid * (1 - self.slippage)
        cost = volume * price
        return Fill(pair.coin, side, volume, price, cost, cost * self.fee_rate, txid="paper")


class LiveBroker:
    live = True

    def __init__(self, client: KrakenClient, fill_timeout: float = 30.0, poll_interval: float = 1.0):
        self.client = client
        self.fill_timeout = fill_timeout
        self.poll_interval = poll_interval

    def balances(self, universe: dict[str, PairInfo]) -> tuple[float, dict[str, float]]:
        """Actual exchange balances: (usd, coin -> qty). Auto-earn '.F' balances are merged."""
        raw = self.client.balance()
        merged: dict[str, float] = {}
        for code, qty in raw.items():
            base = code.split(".", 1)[0]
            merged[base] = merged.get(base, 0.0) + qty
        usd = merged.get("ZUSD", 0.0) + merged.get("USD", 0.0)
        coins = {coin: merged.get(p.base_asset, 0.0) for coin, p in universe.items()}
        return usd, coins

    def execute(self, pair: PairInfo, side: str, volume: float, quote: Quote) -> Fill:
        txids = self.client.add_market_order(pair, side, fmt_volume(volume, pair.lot_decimals))
        if not txids:
            raise KrakenAPIError("AddOrder returned no txid")
        txid = txids[0]
        deadline = time.monotonic() + self.fill_timeout
        order = {}
        while time.monotonic() < deadline:
            order = self.client.query_orders([txid]).get(txid, {})
            if order.get("status") in ("closed", "canceled", "expired"):
                break
            time.sleep(self.poll_interval)
        vol_exec = float(order.get("vol_exec", 0) or 0)
        if order.get("status") != "closed":
            log.warning("order %s not fully closed (status=%s, vol_exec=%s)", txid, order.get("status"), vol_exec)
        cost = float(order.get("cost", 0) or 0)
        price = float(order.get("price", 0) or 0) or (cost / vol_exec if vol_exec else 0.0)
        return Fill(pair.coin, side, vol_exec, price, cost, float(order.get("fee", 0) or 0), txid=txid)
