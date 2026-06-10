"""
The three deterministic strategies. One contract, shared verbatim by the live
engine and the backtester so a backtest tests exactly the code that trades:

    prepare(df, params)          → df with indicator columns appended
    entry_signal(df, i, params)  → bool   (long entry on bar i's close)
    exit_signal(df, i, params, entry) → str | None  (exit reason, or hold)

All decisions read COMPLETED bars only; fills happen after the signal bar
(next bar's open in backtests, a market order at tick time live). The hard
ATR stop and max-hold are enforced uniformly by the engine/backtester, not
here — rules only express the strategy's own entry/exit logic.

Long-only by design: short selling adds borrow mechanics and unbounded risk
that don't belong in a v1 paper engine.
"""

from . import indicators as ind

# Instruments that express the same "risk-on" bet — the correlation filter
# (risk.py) caps how many of these can be held at once.
RISK_ON_GROUP = {"SPY", "QQQ", "BTC/USD"}

DEFAULT_CONFIG = {
    # Risk (engine-level, applies to every strategy)
    "risk_pct": 1.0,           # % of equity risked per trade — the hard 1%
    "stop_atr_mult": 2.0,      # stop distance = this many ATRs below entry
    "max_position_pct": 20.0,  # notional cap per position, % of equity
    "max_risk_on": 2,          # max concurrent positions within RISK_ON_GROUP
    "atr_window": 14,
    # Tuned 2026-06-10 via scripts/tune_strategies.py (3y, 70/30 IS/OOS split;
    # full numbers in scripts/tune_results.json). Only trend following
    # validated out-of-sample, so only it is enabled by default. The other two
    # carry their least-bad parameters in case they're re-enabled, but as
    # specified they did NOT earn the right to trade — every mean-reversion
    # variant lost money on both windows, and every breakout variant that
    # looked good in-sample collapsed out-of-sample (classic curve fit).
    "strategies": {
        "mean_reversion": {
            "enabled": False,        # all 12 tuned variants OOS-negative
            "symbols": ["SPY", "QQQ"],
            "timeframe": "15Min",
            "lookback": 20,          # z-score window
            "z_entry": -2.5,         # best variant found (still PF 0.84 OOS)
            "z_exit": 0.0,           # exit when price reverts to the mean
            "stop_atr_mult": 3.0,    # wider stop helped; dips run past 2xATR
            "trend_filter_bars": 200,  # only buy dips in an uptrend
            "max_hold_bars": 78,     # ~3 trading days of 15-min bars
        },
        "momentum_breakout": {
            "enabled": False,        # IS winners (PF 1.96) went PF 0.2-0.4 OOS
            "symbols": ["BTC/USD"],
            "timeframe": "1Hour",
            "entry_lookback": 168,   # best in-sample (1-week breakout)
            "exit_lookback": 40,     # Donchian exit window
            "trend_filter_bars": 200,
        },
        "trend_following": {
            "enabled": True,         # validated: PF 1.29 IS, PF 2.68 OOS
            "symbols": ["GLD", "USO"],
            "timeframe": "4Hour",
            "fast": 20,
            "slow": 100,
        },
    },
}


# ── Mean reversion (indices): buy 2σ dips in an uptrend, sell the mean ───────

def _mr_prepare(df, p):
    df = df.copy()
    df["z"] = ind.zscore(df["close"], p["lookback"])
    df["trend"] = ind.sma(df["close"], p["trend_filter_bars"])
    return df


def _mr_entry(df, i, p):
    row = df.iloc[i]
    if row[["z", "trend"]].isna().any():
        return False
    return row["z"] <= p["z_entry"] and row["close"] > row["trend"]


def _mr_exit(df, i, p, entry):
    z = df.iloc[i]["z"]
    if z == z and z >= p["z_exit"]:  # z==z filters NaN
        return "mean_revert"
    return None


# ── Momentum breakout (crypto): ride new highs, leave on broken lows ─────────

def _mb_prepare(df, p):
    df = df.copy()
    df["don_high"] = ind.donchian_high(df["high"], p["entry_lookback"])
    df["don_low"] = ind.donchian_low(df["low"], p["exit_lookback"])
    df["trend"] = ind.sma(df["close"], p["trend_filter_bars"])
    return df


def _mb_entry(df, i, p):
    row = df.iloc[i]
    if row[["don_high", "trend"]].isna().any():
        return False
    return row["close"] > row["don_high"] and row["close"] > row["trend"]


def _mb_exit(df, i, p, entry):
    row = df.iloc[i]
    if row["don_low"] == row["don_low"] and row["close"] < row["don_low"]:
        return "breakout_failed"
    return None


# ── Trend following (commodities): long while fast SMA > slow SMA ────────────

def _tf_prepare(df, p):
    df = df.copy()
    df["fast"] = ind.sma(df["close"], p["fast"])
    df["slow"] = ind.sma(df["close"], p["slow"])
    return df


def _tf_entry(df, i, p):
    row = df.iloc[i]
    if row[["fast", "slow"]].isna().any():
        return False
    return row["fast"] > row["slow"]


def _tf_exit(df, i, p, entry):
    row = df.iloc[i]
    if row["fast"] == row["fast"] and row["fast"] < row["slow"]:
        return "trend_flip"
    return None


STRATEGIES = {
    "mean_reversion": {
        "label": "Mean Reversion (indices)",
        "prepare": _mr_prepare,
        "entry": _mr_entry,
        "exit": _mr_exit,
    },
    "momentum_breakout": {
        "label": "Momentum Breakout (crypto)",
        "prepare": _mb_prepare,
        "entry": _mb_entry,
        "exit": _mb_exit,
    },
    "trend_following": {
        "label": "Trend Following (commodities)",
        "prepare": _tf_prepare,
        "exit": _tf_exit,
        "entry": _tf_entry,
    },
}
