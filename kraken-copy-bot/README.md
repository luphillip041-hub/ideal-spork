# Kraken Leaderboard Copy-Trading Bot

Ranks top traders on a public leaderboard, reads their live positions, and
mirrors the **consensus of the best traders** onto your **Kraken spot** account.

> ⚠️ This is experimental software that can lose money. It runs in **paper mode by
> default**. Past leaderboard performance does not predict future returns. Use a
> dedicated Kraken sub-account and an allocation you can afford to lose.

## How it works

```
Hyperliquid leaderboard ──► filter + score ──► top N traders
                                                    │
                                live positions (public on-chain)
                                                    ▼
                         score-weighted consensus exposure per coin
                                                    │
                   long-only · min agreement · per-coin & total caps
                                                    ▼
                    target weights ──► rebalance Kraken spot (USD pairs)
```

**Why Hyperliquid?** Kraken does not publish other users' trades or a
copy-trading leaderboard. Hyperliquid's leaderboard is public, and every
account's positions can be read from its API. The bot uses it as the signal
source and executes on Kraken.

1. **Leaderboard.** The bot pulls every ranked account, drops the ones that are too
   small, losing over the month, unprofitable all-time, or turning over so fast
   (market makers/HFT) that copying is pointless. It then scores each remaining
   trader by weighted percentile ranks: month/all-time/week ROI plus all-time dollar
   PnL by default.
2. **Consensus.** For the top `top_n` traders (plus any pinned addresses) it reads
   their perp positions as *notional / account value*, weights each trader by
   score, and sums per coin.
3. **Targets.** Kraken spot can't short, so net-short coins stay in cash. A coin
   is bought only if at least `min_traders_agree` followed traders are long it
   and Kraken has an online USD pair for it. Per-coin weight is capped by
   `max_position_pct` and the total by `max_total_exposure`.
4. **Rebalance.** It sells first (exits, then trims) and then buys. Drift below
   `rebalance_threshold` is ignored, and Kraken's `ordermin`/`costmin`/lot
   precision are respected.

### Safety rails
- **Sleeve accounting.** The bot only manages `allocation_usd` and the coins it
  bought itself. It never sells holdings it didn't buy. In live mode, every order
  is also clamped to your real Kraken balances.
- **Drawdown kill switch.** When equity falls `max_drawdown` from its peak, the
  bot halts (or sells everything first, with `on_drawdown = "flatten"`). It stays
  halted until you run `reset`.
- **Incomplete-data guard.** The bot won't rebalance if too few trader positions
  could be fetched, so an API outage can't liquidate you.
- **Live mode needs three switches:** `mode = "live"` in the config,
  `KRAKEN_API_KEY`/`KRAKEN_API_SECRET` in the environment, and the
  `--confirm-live` flag.

## Quick start

```bash
cd kraken-copy-bot
pip install -r requirements.txt
cp config.example.toml config.toml

python -m copybot -c config.toml leaderboard     # ranked traders, who is followed
python -m copybot -c config.toml explain         # why big earners were filtered out
python -m copybot -c config.toml plan            # targets + orders, no trading
python -m copybot -c config.toml once            # one paper-trading cycle
python -m copybot -c config.toml run             # loop every interval_seconds
python -m copybot -c config.toml status          # cash, holdings, halt state
python -m copybot -c config.toml reset           # clear a drawdown halt
python -m copybot -c config.toml check           # test connectivity + API key (no orders)
```

State is stored in `state/bot_state.json`, and every fill is appended to
`state/bot_state.trades.jsonl`.

## Going live

1. Create a Kraken API key with **Query Funds**, **Query Open Orders & Trades**,
   and **Create & Modify Orders** only. Do **not** grant withdrawal permission.
2. Fund the account with USD and set `risk.allocation_usd` to the amount the bot
   may use.
3. Verify the key without trading. `check` reads your balance and has Kraken
   *validate* a tiny BTC order without placing it:

```bash
export KRAKEN_API_KEY=... KRAKEN_API_SECRET=...
python -m copybot -c config.toml check
```

4. Paper-trade first with your exact config, then switch to live with a **fresh**
   `state_path`, so paper holdings aren't treated as real:

```bash
# config.toml: mode = "live", state_path = "state/live.json"
python -m copybot -c config.toml plan                      # see what it would do
python -m copybot -c config.toml once --confirm-live       # one real cycle
```

A market order that isn't fully filled within 30 seconds has the rest
cancelled, and only the filled part is booked, so no order is ever left working.

### Docker

```bash
docker build -t kraken-copybot .
docker run -d --name copybot --restart unless-stopped \
  -v $PWD/config.toml:/app/config.toml:ro -v $PWD/state:/app/state \
  -e KRAKEN_API_KEY -e KRAKEN_API_SECRET \
  kraken-copybot run --confirm-live      # omit --confirm-live for paper mode
```

## Configuration

See [`config.example.toml`](config.example.toml). Every key is documented there
and optional. Unknown keys are rejected so typos fail loudly.

## Tests

```bash
pip install pytest && python -m pytest -q
```

The tests cover Kraken request signing (against Kraken's documented example),
leaderboard filtering and scoring, consensus and caps, rebalance planning, full
paper cycles, the incomplete-data guard, both drawdown modes, and the live
broker's fill booking, cancel-on-timeout, balance merging, and balance clamping
(against a fake Kraken).

## Limitations
- Spot only, so the bot is long-only. Shorts from copied traders mean "hold cash".
- Market orders. Thin Kraken pairs can slip more than the paper model assumes.
- Copying happens per cycle (default 15 min), not tick by tick, so very fast
  traders won't be reproduced faithfully. The turnover filter helps avoid them.
