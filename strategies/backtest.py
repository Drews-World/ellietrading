"""
Backtester — replays the exact same rules/risk code the live engine runs.

No strategy ships without this. Method notes (honesty matters more than
pretty numbers):

- Fills happen at the NEXT bar's open after a signal bar closes — no lookahead.
- The hard ATR stop is checked intrabar: if a bar's low crosses the stop, the
  trade exits at the stop price (or at the open when the bar gaps below it).
- Slippage (default 2 bps each way) is charged on every fill; no commissions
  (Alpaca is commission-free).
- Each strategy is tested as its own portfolio with its own starting equity,
  ATR-sized at the same risk% as live. The live correlation filter is a
  cross-strategy concern and is NOT simulated here.
- Stock data is split-adjusted SIP/IEX history from Alpaca; 15-min index data
  reaches back years on free accounts.

Results are persisted to ~/.tradingagents/strategy_backtests.json (last 8 runs).
"""

import json
import logging
import threading
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pandas as pd

from . import data, indicators as ind, risk
from .rules import STRATEGIES

logger = logging.getLogger("ellie")

BACKTEST_FILE = Path.home() / ".tradingagents" / "strategy_backtests.json"
_RESULTS_CAP = 8
_TRADES_CAP = 200
_CURVE_CAP = 600

_lock = threading.Lock()


def _load_store() -> dict:
    if BACKTEST_FILE.exists():
        try:
            return json.loads(BACKTEST_FILE.read_text())
        except Exception:  # noqa: BLE001
            pass
    return {"running": False, "error": None, "results": []}


def _save_store(store: dict):
    BACKTEST_FILE.parent.mkdir(parents=True, exist_ok=True)
    store["results"] = store["results"][:_RESULTS_CAP]
    BACKTEST_FILE.write_text(json.dumps(store, indent=2, default=str))


def get_results() -> dict:
    with _lock:
        return _load_store()


def _mark(running: bool, error: str | None = None, result: dict | None = None):
    with _lock:
        store = _load_store()
        store["running"] = running
        store["error"] = error
        if result is not None:
            store["results"].insert(0, result)
        _save_store(store)


def run_backtest(config: dict, strategy_names: list[str] | None = None,
                 years: int = 3, initial_equity: float = 100_000.0,
                 slippage_bps: float = 2.0) -> dict:
    """Blocking — run from a worker thread. Returns the stored result dict."""
    _mark(running=True)
    try:
        result = {
            "id": str(uuid.uuid4())[:8],
            "created_at": datetime.now(timezone.utc).isoformat(),
            "years": years,
            "initial_equity": initial_equity,
            "slippage_bps": slippage_bps,
            "config_snapshot": {
                k: config[k] for k in ("risk_pct", "stop_atr_mult", "max_position_pct")
            },
            "strategies": {},
        }
        names = strategy_names or list(config["strategies"].keys())
        for name in names:
            params = config["strategies"].get(name)
            spec = STRATEGIES.get(name)
            if params is None or spec is None:
                continue
            result["strategies"][name] = _backtest_strategy(
                name, spec, params, config, years, initial_equity, slippage_bps
            )
        _mark(running=False, result=result)
        return result
    except Exception as e:  # noqa: BLE001
        logger.error("[backtest] failed: %s", e)
        _mark(running=False, error=str(e))
        raise


def _backtest_strategy(name, spec, params, config, years, initial_equity,
                       slippage_bps) -> dict:
    slip = slippage_bps / 10_000.0
    end = datetime.now(timezone.utc)
    days = int(years * 365)

    # Prepare per-symbol frames once (vectorized), then walk a merged timeline.
    frames: dict[str, pd.DataFrame] = {}
    for symbol in params["symbols"]:
        df = data.fetch_bars(symbol, params["timeframe"], days=days, end=end)
        if df.empty or len(df) < 50:
            logger.warning("[backtest] %s/%s: insufficient data (%d bars)",
                           name, symbol, len(df))
            continue
        df = spec["prepare"](df, params)
        df["atr"] = ind.atr(df, config["atr_window"])
        frames[symbol] = df

    if not frames:
        return {"label": spec["label"], "symbols": params["symbols"],
                "error": "no historical data available"}

    # Merged event timeline: (timestamp, symbol, row index).
    events = sorted(
        (ts, sym, i)
        for sym, df in frames.items()
        for i, ts in enumerate(df.index)
    )

    cash = initial_equity
    positions: dict[str, dict] = {}
    trades: list[dict] = []
    pending: dict[str, dict] = {}  # symbol -> action to fill at next bar open
    curve: list[tuple[str, float]] = []
    last_equity = initial_equity

    def equity_now(ts_prices: dict[str, float]) -> float:
        eq = cash
        for sym, pos in positions.items():
            eq += pos["qty"] * ts_prices.get(sym, pos["entry_price"])
        return eq

    last_price: dict[str, float] = {}

    for ts, symbol, i in events:
        df = frames[symbol]
        row = df.iloc[i]
        o, h, l, c = float(row["open"]), float(row["high"]), float(row["low"]), float(row["close"])
        last_price[symbol] = c
        pos = positions.get(symbol)

        # 1. Fill any action queued from the previous bar at this bar's open.
        act = pending.pop(symbol, None)
        if act is not None:
            if act["type"] == "enter" and pos is None:
                atr_value = act["atr"]
                fill = o * (1 + slip)
                qty = risk.position_size(
                    last_equity, fill, atr_value,
                    risk_pct=config["risk_pct"],
                    stop_atr_mult=config["stop_atr_mult"],
                    max_position_pct=config["max_position_pct"],
                    fractional=data.is_crypto(symbol),
                )
                if qty > 0:
                    cash -= qty * fill
                    positions[symbol] = {
                        "qty": qty, "entry_price": fill, "entry_time": str(ts),
                        "stop": risk.stop_price(fill, atr_value, config["stop_atr_mult"]),
                        "bars_held": 0,
                    }
                    pos = positions[symbol]
            elif act["type"] == "exit" and pos is not None:
                fill = o * (1 - slip)
                cash_box = [cash]
                _close(trades, positions, cash_box, symbol, fill, str(ts), act["reason"])
                cash = cash_box[0]
                pos = None

        # 2. Intrabar hard stop.
        if pos is not None and l <= pos["stop"]:
            fill = (o if o < pos["stop"] else pos["stop"]) * (1 - slip)
            cash_box = [cash]
            _close(trades, positions, cash_box, symbol, fill, str(ts), "hard_stop")
            cash = cash_box[0]
            pos = None

        # 3. Signals on this bar's close → queue for next bar's open.
        if pos is not None:
            pos["bars_held"] += 1
            reason = spec["exit"](df, i, params, pos)
            max_hold = params.get("max_hold_bars")
            if reason is None and max_hold and pos["bars_held"] >= max_hold:
                reason = "max_hold"
            if reason:
                pending[symbol] = {"type": "exit", "reason": reason}
        else:
            atr_value = float(row["atr"]) if row["atr"] == row["atr"] else 0.0
            if atr_value > 0 and spec["entry"](df, i, params):
                pending[symbol] = {"type": "enter", "atr": atr_value}

        last_equity = equity_now(last_price)
        curve.append((str(ts), round(last_equity, 2)))

    # Liquidate whatever is still open at the last seen price (mark-to-market).
    for symbol in list(positions.keys()):
        cash_box = [cash]
        _close(trades, positions, cash_box, symbol,
               last_price.get(symbol, positions[symbol]["entry_price"]),
               curve[-1][0] if curve else "", "end_of_test")
        cash = cash_box[0]

    return {
        "label": spec["label"],
        "symbols": list(frames.keys()),
        "timeframe": params["timeframe"],
        "bars_tested": {sym: len(df) for sym, df in frames.items()},
        "stats": _stats(trades, curve, initial_equity),
        "equity_curve": _downsample(curve),
        "trades": trades[-_TRADES_CAP:],
    }


def _close(trades, positions, cash_box, symbol, fill, ts, reason):
    pos = positions.pop(symbol)
    cash_box[0] += pos["qty"] * fill
    pnl = round((fill - pos["entry_price"]) * pos["qty"], 2)
    trades.append({
        "symbol": symbol,
        "qty": round(pos["qty"], 6),
        "entry_price": round(pos["entry_price"], 4),
        "entry_time": pos["entry_time"],
        "exit_price": round(fill, 4),
        "exit_time": ts,
        "pnl": pnl,
        "pnl_pct": round((fill / pos["entry_price"] - 1) * 100, 3),
        "reason": reason,
        "bars_held": pos["bars_held"],
    })


def _stats(trades: list[dict], curve: list[tuple[str, float]],
           initial_equity: float) -> dict:
    if not curve:
        return {"trades": 0}
    final = curve[-1][1]
    total_return_pct = round((final / initial_equity - 1) * 100, 2)

    # Max drawdown over the equity curve.
    peak, max_dd = initial_equity, 0.0
    for _, eq in curve:
        peak = max(peak, eq)
        max_dd = max(max_dd, (peak - eq) / peak)

    wins = [t for t in trades if t["pnl"] > 0]
    losses = [t for t in trades if t["pnl"] <= 0]
    gross_win = sum(t["pnl"] for t in wins)
    gross_loss = abs(sum(t["pnl"] for t in losses))

    # CAGR + Sharpe from daily equity samples.
    cagr = sharpe = None
    try:
        ser = pd.Series(
            {pd.Timestamp(ts): eq for ts, eq in curve}
        ).resample("1D").last().dropna()
        if len(ser) > 30:
            years_elapsed = (ser.index[-1] - ser.index[0]).days / 365.25
            if years_elapsed > 0:
                cagr = round(((final / initial_equity) ** (1 / years_elapsed) - 1) * 100, 2)
            rets = ser.pct_change().dropna()
            if rets.std() and rets.std() > 0:
                sharpe = round(float(rets.mean() / rets.std() * (252 ** 0.5)), 2)
    except Exception:  # noqa: BLE001
        pass

    return {
        "trades": len(trades),
        "total_return_pct": total_return_pct,
        "final_equity": round(final, 2),
        "cagr_pct": cagr,
        "max_drawdown_pct": round(max_dd * 100, 2),
        "win_rate_pct": round(len(wins) / len(trades) * 100, 1) if trades else None,
        "profit_factor": round(gross_win / gross_loss, 2) if gross_loss > 0 else None,
        "avg_win": round(gross_win / len(wins), 2) if wins else None,
        "avg_loss": round(-gross_loss / len(losses), 2) if losses else None,
        "sharpe": sharpe,
        "stops_hit": sum(1 for t in trades if t["reason"] == "hard_stop"),
    }


def _downsample(curve: list[tuple[str, float]]) -> list[list]:
    if len(curve) <= _CURVE_CAP:
        return [list(p) for p in curve]
    step = len(curve) / _CURVE_CAP
    sampled = [curve[int(k * step)] for k in range(_CURVE_CAP)]
    sampled[-1] = curve[-1]
    return [list(p) for p in sampled]
