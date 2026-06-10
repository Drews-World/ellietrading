#!/usr/bin/env python3
"""
tune_strategies.py — the "Claude writes and updates the logic" loop, made honest.

Grid-search strategy parameters against history with an in-sample /
out-of-sample split so we don't ship curve-fit numbers:

  1. Fetch bars ONCE per (symbol, timeframe), split chronologically
     (default 70% optimize / 30% validate).
  2. Replay every parameter variant through the SAME backtester the live
     engine code shares (strategies/backtest.py — no parallel implementation).
  3. Rank variants on the in-sample window, then report how the top ones
     held up on data they never saw. Pick winners from the OOS column only.

Usage (needs APCA_API_KEY_ID / APCA_API_SECRET_KEY in the environment):
    python scripts/tune_strategies.py --years 3 --split 0.7
"""

import argparse
import json
import sys
from copy import deepcopy
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from strategies import backtest as bt  # noqa: E402
from strategies import data as sdata   # noqa: E402
from strategies.rules import DEFAULT_CONFIG, STRATEGIES  # noqa: E402

INITIAL_EQUITY = 100_000.0
SLIPPAGE_BPS = 2.0

# Parameter grids. Kept deliberately small — a dozen variants per strategy is
# exploration; a thousand is curve-fitting with extra steps.
GRIDS = {
    "mean_reversion": [
        {"z_entry": z, "z_exit": x, "stop_atr_mult": s}
        for z in (-2.0, -2.5, -3.0)
        for x in (0.0, -0.5)
        for s in (2.0, 3.0)
    ],
    "momentum_breakout": [
        {"entry_lookback": e, "exit_lookback": x, "stop_atr_mult": s}
        for e in (55, 100, 168)
        for x in (20, 40)
        for s in (2.0, 3.0)
    ],
    "trend_following": [
        {},  # baseline only — it already works; don't fix it
    ],
}

MIN_TRADES_IS = 20  # below this the in-sample stats are noise


def fetch_cache(years: float) -> dict:
    cache = {}
    for params in DEFAULT_CONFIG["strategies"].values():
        for sym in params["symbols"]:
            key = (sym, params["timeframe"])
            if key not in cache:
                print(f"  fetching {sym} {params['timeframe']}…", flush=True)
                df = sdata.fetch_bars(sym, params["timeframe"], days=int(years * 365))
                cache[key] = df
                print(f"    {len(df)} bars")
    return cache


def run_variant(name: str, overrides: dict, frames: dict) -> dict:
    """Backtest one variant against the given pre-fetched frames."""
    cfg = deepcopy(DEFAULT_CONFIG)
    params = cfg["strategies"][name]
    params.update(overrides)

    real_fetch = sdata.fetch_bars
    sdata.fetch_bars = lambda symbol, timeframe, days=None, end=None: (
        frames.get((symbol, timeframe), bt.pd.DataFrame()).copy()
    )
    try:
        res = bt._backtest_strategy(
            name, STRATEGIES[name], params, cfg,
            years=0, initial_equity=INITIAL_EQUITY, slippage_bps=SLIPPAGE_BPS,
        )
    finally:
        sdata.fetch_bars = real_fetch
    return res.get("stats", {}) if not res.get("error") else {"error": res["error"]}


def fmt(stats: dict) -> str:
    if stats.get("error"):
        return f"ERROR: {stats['error']}"
    return (f"ret {stats.get('total_return_pct', 0):>7.2f}%  "
            f"dd {stats.get('max_drawdown_pct', 0):>5.2f}%  "
            f"win {stats.get('win_rate_pct') or 0:>5.1f}%  "
            f"pf {stats.get('profit_factor') or 0:>5.2f}  "
            f"shp {stats.get('sharpe') if stats.get('sharpe') is not None else 0:>6.2f}  "
            f"n {stats.get('trades', 0):>4}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--years", type=float, default=3.0)
    ap.add_argument("--split", type=float, default=0.7)
    ap.add_argument("--top", type=int, default=4, help="variants to validate OOS")
    args = ap.parse_args()

    print(f"Fetching {args.years}y of data…", flush=True)
    cache = fetch_cache(args.years)
    cut = {k: int(len(df) * args.split) for k, df in cache.items()}
    is_frames = {k: df.iloc[:cut[k]] for k, df in cache.items()}
    oos_frames = {k: df.iloc[cut[k]:] for k, df in cache.items()}

    report = {}
    for name, grid in GRIDS.items():
        print(f"\n══ {name} — {len(grid)} variant(s), in-sample ══", flush=True)
        scored = []
        for i, overrides in enumerate(grid):
            stats = run_variant(name, overrides, is_frames)
            label = json.dumps(overrides) if overrides else "(baseline)"
            print(f"  [{i + 1:>2}/{len(grid)}] {label:60} {fmt(stats)}", flush=True)
            if stats.get("error") or stats.get("trades", 0) < MIN_TRADES_IS:
                continue
            # Rank on profit factor with a sharpe tiebreak — both penalize
            # strategies that only look good through one lucky trade.
            score = (stats.get("profit_factor") or 0, stats.get("sharpe") or -9)
            scored.append((score, overrides, stats))

        scored.sort(key=lambda t: t[0], reverse=True)
        finalists = scored[:args.top]
        print(f"  ── validating top {len(finalists)} out-of-sample ──", flush=True)
        validated = []
        for score, overrides, is_stats in finalists:
            oos_stats = run_variant(name, overrides, oos_frames)
            label = json.dumps(overrides) if overrides else "(baseline)"
            print(f"  OOS {label:60} {fmt(oos_stats)}", flush=True)
            validated.append({"overrides": overrides,
                              "in_sample": is_stats, "out_of_sample": oos_stats})
        report[name] = validated

    out = Path(__file__).parent / "tune_results.json"
    out.write_text(json.dumps(report, indent=2, default=str))
    print(f"\nFull report → {out}", flush=True)


if __name__ == "__main__":
    main()
