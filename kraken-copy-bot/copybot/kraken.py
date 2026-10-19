"""Minimal Kraken REST client (public + signed private endpoints)."""

from __future__ import annotations

import base64
import hashlib
import hmac
import threading
import time
import urllib.parse
from dataclasses import dataclass

import requests

# Kraken's legacy asset codes -> common tickers.
KRAKEN_TO_COMMON = {"XBT": "BTC", "XDG": "DOGE"}


class KrakenAPIError(RuntimeError):
    pass


@dataclass
class PairInfo:
    coin: str  # common ticker, e.g. BTC
    key: str  # Kraken pair key, e.g. XXBTZUSD
    altname: str  # e.g. XBTUSD
    base_asset: str  # balance code, e.g. XXBT
    lot_decimals: int
    pair_decimals: int
    ordermin: float
    costmin: float


@dataclass
class Quote:
    bid: float
    ask: float

    @property
    def mid(self) -> float:
        return (self.bid + self.ask) / 2


class KrakenClient:
    BASE_URL = "https://api.kraken.com"

    def __init__(
        self,
        api_key: str | None = None,
        api_secret: str | None = None,
        session: requests.Session | None = None,
        timeout: float = 15.0,
    ):
        self.api_key = api_key
        self.api_secret = api_secret
        self.session = session or requests.Session()
        self.timeout = timeout
        self._nonce_lock = threading.Lock()
        self._last_nonce = 0

    @staticmethod
    def sign(url_path: str, data: dict, secret: str) -> str:
        postdata = urllib.parse.urlencode(data)
        message = url_path.encode() + hashlib.sha256((str(data["nonce"]) + postdata).encode()).digest()
        mac = hmac.new(base64.b64decode(secret), message, hashlib.sha512)
        return base64.b64encode(mac.digest()).decode()

    def _nonce(self) -> int:
        with self._nonce_lock:
            self._last_nonce = max(self._last_nonce + 1, int(time.time() * 1000))
            return self._last_nonce

    @staticmethod
    def _unwrap(payload: dict):
        if payload.get("error"):
            raise KrakenAPIError(", ".join(payload["error"]))
        return payload["result"]

    def public(self, method: str, params: dict | None = None):
        resp = self.session.get(f"{self.BASE_URL}/0/public/{method}", params=params, timeout=self.timeout)
        resp.raise_for_status()
        return self._unwrap(resp.json())

    def private(self, method: str, data: dict | None = None):
        if not (self.api_key and self.api_secret):
            raise KrakenAPIError("Kraken API key/secret not configured")
        path = f"/0/private/{method}"
        data = {"nonce": self._nonce(), **(data or {})}
        headers = {"API-Key": self.api_key, "API-Sign": self.sign(path, data, self.api_secret)}
        resp = self.session.post(f"{self.BASE_URL}{path}", data=data, headers=headers, timeout=self.timeout)
        resp.raise_for_status()
        return self._unwrap(resp.json())

    # --- public -------------------------------------------------------------
    def asset_pairs(self) -> dict:
        return self.public("AssetPairs")

    def quotes(self, pairs: list[PairInfo]) -> dict[str, Quote]:
        """Return coin -> Quote for the given pairs."""
        if not pairs:
            return {}
        result = self.public("Ticker", {"pair": ",".join(p.altname for p in pairs)})
        by_name = {}
        for p in pairs:
            by_name[p.key] = p
            by_name[p.altname] = p
        out = {}
        for name, tick in result.items():
            p = by_name.get(name)
            if p:
                out[p.coin] = Quote(bid=float(tick["b"][0]), ask=float(tick["a"][0]))
        return out

    # --- private ------------------------------------------------------------
    def balance(self) -> dict[str, float]:
        return {k: float(v) for k, v in self.private("Balance").items()}

    def add_market_order(self, pair: PairInfo, side: str, volume: str, validate: bool = False) -> list[str]:
        data = {"pair": pair.altname, "type": side, "ordertype": "market", "volume": volume}
        if validate:
            data["validate"] = "true"
        return self.private("AddOrder", data).get("txid", [])

    def cancel_order(self, txid: str) -> dict:
        return self.private("CancelOrder", {"txid": txid})

    def system_status(self) -> str:
        return self.public("SystemStatus")["status"]

    def query_orders(self, txids: list[str]) -> dict:
        return self.private("QueryOrders", {"txid": ",".join(txids), "trades": "false"})


def build_universe(asset_pairs: dict, quote: str = "USD") -> dict[str, PairInfo]:
    """Map common coin ticker -> online Kraken spot pair quoted in `quote`."""
    universe: dict[str, PairInfo] = {}
    for key, info in asset_pairs.items():
        wsname = info.get("wsname", "")
        if "/" not in wsname or info.get("status", "online") != "online":
            continue
        if info.get("aclass_base", "currency") != "currency":
            continue
        base, q = wsname.split("/", 1)
        if q != quote:
            continue
        coin = KRAKEN_TO_COMMON.get(base, base)
        universe[coin] = PairInfo(
            coin=coin,
            key=key,
            altname=info["altname"],
            base_asset=info["base"],
            lot_decimals=int(info["lot_decimals"]),
            pair_decimals=int(info["pair_decimals"]),
            ordermin=float(info.get("ordermin", 0) or 0),
            costmin=float(info.get("costmin", 0) or 0),
        )
    return universe
