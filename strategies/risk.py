"""
Risk layer — the part that keeps a losing streak survivable.

- ATR position sizing: every trade risks the same fraction of equity (default
  1%) regardless of the instrument's volatility. Stop distance is K×ATR, so
  qty = (equity × risk%) / (K × ATR): a quiet day on gold sizes bigger than a
  wild day on bitcoin, and hitting the stop always costs ~the same.
- Notional cap: low-ATR moments can imply huge positions; cap at a % of equity.
- Correlation filter: SPY + QQQ + BTC longs are mostly one risk-on bet —
  cap how many of that group can be open at once.
"""

import math

from .rules import RISK_ON_GROUP


def position_size(equity: float, price: float, atr_value: float, *,
                  risk_pct: float, stop_atr_mult: float,
                  max_position_pct: float, fractional: bool = False) -> float:
    """Quantity such that (stop hit ⇒ lose risk_pct% of equity), capped by notional.

    Returns 0.0 when inputs can't produce a sane size.
    """
    if equity <= 0 or price <= 0 or atr_value is None or atr_value <= 0:
        return 0.0
    risk_dollars = equity * (risk_pct / 100.0)
    stop_distance = stop_atr_mult * atr_value
    if stop_distance <= 0:
        return 0.0
    qty = risk_dollars / stop_distance

    max_notional = equity * (max_position_pct / 100.0)
    if qty * price > max_notional:
        qty = max_notional / price

    if fractional:
        return round(qty, 6)
    return float(math.floor(qty))


def stop_price(entry_price: float, atr_value: float, stop_atr_mult: float) -> float:
    """Hard stop for a long position: K ATRs below entry. No exceptions."""
    return round(entry_price - stop_atr_mult * atr_value, 4)


def correlation_blocked(symbol: str, open_symbols: set[str], max_risk_on: int) -> bool:
    """True when opening `symbol` would exceed the risk-on concurrency cap."""
    if symbol not in RISK_ON_GROUP:
        return False
    held_risk_on = len(open_symbols & RISK_ON_GROUP)
    return held_risk_on >= max_risk_on
