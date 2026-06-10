"""
The live strategy engine — deterministic, paper-only, starts paused.

Safety model (deliberate, do not loosen casually):
- PAPER ONLY: refuses to start, and pauses itself, unless APCA_BASE_URL points
  at paper-api. Going live someday is a deliberate code change, not a config flag.
- Starts paused: Drew explicitly starts it from the UI after reviewing backtests.
- Hard stop on every position (K×ATR at entry), swept every tick against the
  latest quote — not just on bar closes.
- Engine state lives in ~/.tradingagents/strategy_engine.json, same pattern as
  the fund. The engine only manages positions it opened itself; it never
  touches the LLM fund's positions.

A tick is cheap: it only acts when a NEW completed bar exists for a strategy's
timeframe, plus a quote-level stop sweep. The api.py scheduler calls tick()
every couple of minutes from a worker thread.
"""

import json
import logging
import os
import threading
import uuid
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path

import alpaca_client

from . import data, risk
from .rules import DEFAULT_CONFIG, STRATEGIES

logger = logging.getLogger("ellie")

STATE_FILE = Path.home() / ".tradingagents" / "strategy_engine.json"

_LOG_CAP = 400
_TRADES_CAP = 1000


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def is_paper() -> bool:
    return "paper" in os.getenv("APCA_BASE_URL", "https://paper-api.alpaca.markets")


def _default_state() -> dict:
    return {
        "active": False,
        "created_at": None,
        "config": deepcopy(DEFAULT_CONFIG),
        "positions": {},      # symbol -> open engine position
        "trades": [],         # completed round-trips, newest first
        "log": [],            # newest first
        "last_bar": {},       # "strategy:symbol" -> iso ts of last evaluated bar
        "last_tick": None,
        "last_review": None,
        "next_review": None,
        "review": None,       # latest LLM oversight review (set by api.py)
    }


class StrategyEngine:
    """Singleton — all mutation goes through the lock so the tick thread and
    API handlers never interleave a load-modify-save."""

    def __init__(self):
        self._lock = threading.Lock()

    # ── State persistence ────────────────────────────────────────────────────

    def _load(self) -> dict:
        if STATE_FILE.exists():
            try:
                state = json.loads(STATE_FILE.read_text())
                # Merge any new default config keys into older state files.
                merged = _default_state()
                merged.update(state)
                for k, v in DEFAULT_CONFIG.items():
                    merged["config"].setdefault(k, deepcopy(v))
                for name, params in DEFAULT_CONFIG["strategies"].items():
                    merged["config"]["strategies"].setdefault(name, deepcopy(params))
                    for pk, pv in params.items():
                        merged["config"]["strategies"][name].setdefault(pk, pv)
                return merged
            except Exception:  # noqa: BLE001
                logger.error("[engine] state file corrupt — starting fresh")
        return _default_state()

    def _save(self, state: dict):
        STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
        state["log"] = state["log"][:_LOG_CAP]
        state["trades"] = state["trades"][:_TRADES_CAP]
        STATE_FILE.write_text(json.dumps(state, indent=2, default=str))

    def _log(self, state: dict, msg: str):
        state["log"].insert(0, {"ts": _now(), "msg": msg})
        logger.info("[engine] %s", msg)

    # ── Public API (called from FastAPI handlers) ────────────────────────────

    def status(self) -> dict:
        with self._lock:
            state = self._load()
        return {
            "active": state["active"],
            "paper": is_paper(),
            "config": state["config"],
            "positions": state["positions"],
            "trades": state["trades"][:50],
            "trade_count": len(state["trades"]),
            "log": state["log"][:60],
            "last_tick": state["last_tick"],
            "last_review": state["last_review"],
            "next_review": state["next_review"],
            "review": state["review"],
        }

    def start(self) -> dict:
        if not is_paper():
            return {"error": "Refusing to start: APCA_BASE_URL is not the paper API. "
                             "The strategy engine is paper-only by design."}
        with self._lock:
            state = self._load()
            if state["active"]:
                return {"ok": True, "already": True}
            state["active"] = True
            state["created_at"] = state["created_at"] or _now()
            self._log(state, "Engine STARTED (paper account)")
            self._save(state)
        return {"ok": True}

    def pause(self) -> dict:
        with self._lock:
            state = self._load()
            state["active"] = False
            self._log(state, "Engine PAUSED — open positions keep their hard stops "
                             "swept on every tick")
            self._save(state)
        return {"ok": True}

    def update_config(self, patch: dict) -> dict:
        """Shallow-merge engine-level keys; per-strategy params merge one level deeper."""
        with self._lock:
            state = self._load()
            cfg = state["config"]
            for key, value in (patch or {}).items():
                if key == "strategies" and isinstance(value, dict):
                    for name, params in value.items():
                        if name in cfg["strategies"] and isinstance(params, dict):
                            cfg["strategies"][name].update(params)
                elif key in cfg and not isinstance(cfg[key], dict):
                    cfg[key] = value
            self._log(state, f"Config updated: {json.dumps(patch, default=str)[:200]}")
            self._save(state)
            return cfg

    def set_review(self, review: dict):
        with self._lock:
            state = self._load()
            state["review"] = review
            state["last_review"] = _now()
            self._save(state)

    def get_state(self) -> dict:
        with self._lock:
            return self._load()

    def save_fields(self, **fields):
        with self._lock:
            state = self._load()
            state.update(fields)
            self._save(state)

    # ── The tick (blocking; run from a worker thread) ────────────────────────

    def tick(self) -> dict:
        with self._lock:
            state = self._load()
            try:
                return self._tick_inner(state)
            finally:
                state["last_tick"] = _now()
                self._save(state)

    def _tick_inner(self, state: dict) -> dict:
        if not is_paper():
            if state["active"]:
                state["active"] = False
                self._log(state, "SAFETY: APCA_BASE_URL is not paper — engine paused itself")
            return {"skipped": "not paper"}

        actions = []

        # 1. Hard-stop sweep on every engine position, even while paused —
        #    a position without a working stop is never acceptable.
        for symbol in list(state["positions"].keys()):
            pos = state["positions"][symbol]
            price = data.latest_price(symbol)
            if price is not None and price <= pos["stop"]:
                self._close_position(state, symbol, price, "hard_stop")
                actions.append(f"STOP {symbol} @ {price}")

        if not state["active"]:
            return {"skipped": "paused", "actions": actions}

        equity = alpaca_client.get_account().get("equity", 0.0)
        cfg = state["config"]
        stocks_open = data.market_open()

        # 2. Per-strategy bar evaluation — only when a new completed bar exists.
        for name, params in cfg["strategies"].items():
            if not params.get("enabled"):
                continue
            spec = STRATEGIES.get(name)
            if spec is None:
                continue
            for symbol in params["symbols"]:
                try:
                    self._evaluate_symbol(state, name, spec, params, symbol,
                                          cfg, equity, stocks_open, actions)
                except Exception as e:  # noqa: BLE001 — one symbol never kills the tick
                    self._log(state, f"ERROR evaluating {name}/{symbol}: {e}")

        return {"ok": True, "actions": actions}

    def _evaluate_symbol(self, state, name, spec, params, symbol, cfg,
                         equity, stocks_open, actions):
        if not data.is_crypto(symbol) and not stocks_open:
            return

        df = data.fetch_bars(symbol, params["timeframe"])
        if df.empty:
            return

        bar_key = f"{name}:{symbol}"
        last_ts = df.index[-1].isoformat()
        if state["last_bar"].get(bar_key) == last_ts:
            return  # no new completed bar since last evaluation
        state["last_bar"][bar_key] = last_ts

        df = spec["prepare"](df, params)
        i = len(df) - 1
        pos = state["positions"].get(symbol)

        if pos is not None:
            if pos["strategy"] != name:
                return  # symbol owned by another strategy's position
            pos["bars_held"] = pos.get("bars_held", 0) + 1
            reason = spec["exit"](df, i, params, pos)
            max_hold = params.get("max_hold_bars")
            if reason is None and max_hold and pos["bars_held"] >= max_hold:
                reason = "max_hold"
            if reason:
                price = data.latest_price(symbol) or float(df.iloc[i]["close"])
                self._close_position(state, symbol, price, reason)
                actions.append(f"EXIT {symbol} ({reason}) @ {price}")
            return

        # Flat — look for an entry.
        if not spec["entry"](df, i, params):
            return
        open_symbols = set(state["positions"].keys())
        if risk.correlation_blocked(symbol, open_symbols, cfg["max_risk_on"]):
            self._log(state, f"SKIP {symbol} entry — correlation filter "
                             f"(risk-on cap {cfg['max_risk_on']} reached)")
            return

        atr_value = self._atr(df, cfg["atr_window"])
        price = data.latest_price(symbol) or float(df.iloc[i]["close"])
        qty = risk.position_size(
            equity, price, atr_value,
            risk_pct=cfg["risk_pct"], stop_atr_mult=cfg["stop_atr_mult"],
            max_position_pct=cfg["max_position_pct"],
            fractional=data.is_crypto(symbol),
        )
        if qty <= 0:
            return

        tif = "gtc" if data.is_crypto(symbol) else "day"
        order = alpaca_client.submit_order(symbol, "buy", qty=qty, tif=tif)
        if order.get("error"):
            self._log(state, f"ORDER FAILED buy {qty} {symbol}: {order['error']}")
            return

        state["positions"][symbol] = {
            "strategy": name,
            "qty": qty,
            "entry_price": price,
            "entry_time": _now(),
            "atr": round(atr_value, 4),
            "stop": risk.stop_price(price, atr_value, cfg["stop_atr_mult"]),
            "bars_held": 0,
            "order_id": order.get("id"),
        }
        self._log(state, f"ENTER {name} long {qty} {symbol} @ ~{price} "
                         f"(stop {state['positions'][symbol]['stop']})")
        actions.append(f"ENTER {symbol} @ {price}")

    @staticmethod
    def _atr(df, window: int) -> float:
        from . import indicators as ind
        series = ind.atr(df, window)
        val = series.iloc[-1]
        return float(val) if val == val else 0.0

    def _close_position(self, state: dict, symbol: str, price: float, reason: str):
        pos = state["positions"].get(symbol)
        if pos is None:
            return
        tif = "gtc" if data.is_crypto(symbol) else "day"
        order = alpaca_client.submit_order(symbol, "sell", qty=pos["qty"], tif=tif)
        if order.get("error"):
            self._log(state, f"ORDER FAILED sell {pos['qty']} {symbol}: {order['error']}")
            return
        pnl = round((price - pos["entry_price"]) * pos["qty"], 2)
        pnl_pct = round((price / pos["entry_price"] - 1) * 100, 3) if pos["entry_price"] else 0
        state["trades"].insert(0, {
            "id": str(uuid.uuid4())[:8],
            "symbol": symbol,
            "strategy": pos["strategy"],
            "qty": pos["qty"],
            "entry_price": pos["entry_price"],
            "entry_time": pos["entry_time"],
            "exit_price": price,
            "exit_time": _now(),
            "pnl": pnl,
            "pnl_pct": pnl_pct,
            "reason": reason,
            "bars_held": pos.get("bars_held", 0),
        })
        del state["positions"][symbol]
        self._log(state, f"CLOSE {symbol} ({reason}) @ ~{price} — P&L ${pnl} ({pnl_pct}%)")


engine = StrategyEngine()
