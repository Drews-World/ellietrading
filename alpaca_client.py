"""
alpaca_client.py — Alpaca brokerage client for ELLIE Trading
Uses the alpaca-py SDK (pip install alpaca-py).

Credentials are read from environment variables:
  APCA_API_KEY_ID       — Alpaca API key
  APCA_API_SECRET_KEY   — Alpaca API secret
  APCA_BASE_URL         — defaults to https://paper-api.alpaca.markets
"""

import os
import math
import logging
from typing import Optional

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Lazy imports — alpaca-py is optional; functions degrade gracefully if absent
# ---------------------------------------------------------------------------
try:
    from alpaca.trading.client import TradingClient
    from alpaca.trading.requests import MarketOrderRequest
    from alpaca.trading.enums import OrderSide, TimeInForce
    from alpaca.data.historical import StockHistoricalDataClient
    from alpaca.data.requests import StockLatestQuoteRequest
    _ALPACA_AVAILABLE = True
except ImportError:
    _ALPACA_AVAILABLE = False
    logger.warning(
        "alpaca-py not installed. Run: pip install alpaca-py  "
        "Alpaca functions will return empty values."
    )


# ---------------------------------------------------------------------------
# Client factory
# ---------------------------------------------------------------------------

def get_client() -> Optional["TradingClient"]:
    """
    Create and return an Alpaca TradingClient using environment variables.

    Returns None if credentials are missing or alpaca-py is not installed.
    """
    if not _ALPACA_AVAILABLE:
        return None

    api_key = os.getenv("APCA_API_KEY_ID", "")
    api_secret = os.getenv("APCA_API_SECRET_KEY", "")

    if not api_key or not api_secret:
        logger.warning("APCA_API_KEY_ID or APCA_API_SECRET_KEY not set.")
        return None

    base_url = os.getenv("APCA_BASE_URL", "https://paper-api.alpaca.markets")
    paper = "paper-api" in base_url

    try:
        client = TradingClient(
            api_key=api_key,
            secret_key=api_secret,
            paper=paper,
        )
        return client
    except Exception as exc:
        logger.error("Failed to create Alpaca TradingClient: %s", exc)
        return None


def _get_data_client() -> Optional["StockHistoricalDataClient"]:
    """Internal helper — create a StockHistoricalDataClient."""
    if not _ALPACA_AVAILABLE:
        return None

    api_key = os.getenv("APCA_API_KEY_ID", "")
    api_secret = os.getenv("APCA_API_SECRET_KEY", "")

    if not api_key or not api_secret:
        return None

    try:
        return StockHistoricalDataClient(api_key=api_key, secret_key=api_secret)
    except Exception as exc:
        logger.error("Failed to create StockHistoricalDataClient: %s", exc)
        return None


# ---------------------------------------------------------------------------
# Account
# ---------------------------------------------------------------------------

def get_account() -> dict:
    """
    Return a summary of the Alpaca account.

    Keys: portfolio_value, buying_power, cash, equity,
          pnl_today, pnl_today_pct
    Returns an empty dict with zero values on failure.
    """
    empty = {
        "portfolio_value": 0.0,
        "buying_power": 0.0,
        "cash": 0.0,
        "equity": 0.0,
        "pnl_today": 0.0,
        "pnl_today_pct": 0.0,
    }

    client = get_client()
    if client is None:
        return empty

    try:
        acct = client.get_account()

        equity = float(acct.equity or 0)
        last_equity = float(acct.last_equity or 0)
        pnl_today = equity - last_equity
        pnl_today_pct = (pnl_today / last_equity * 100) if last_equity else 0.0

        return {
            "portfolio_value": float(acct.portfolio_value or 0),
            "buying_power": float(acct.buying_power or 0),
            "cash": float(acct.cash or 0),
            "equity": equity,
            "pnl_today": round(pnl_today, 2),
            "pnl_today_pct": round(pnl_today_pct, 4),
        }
    except Exception as exc:
        logger.error("get_account failed: %s", exc)
        return empty


# ---------------------------------------------------------------------------
# Positions
# ---------------------------------------------------------------------------

def get_positions() -> list[dict]:
    """
    Return all open positions.

    Each dict: symbol, qty, avg_entry_price, current_price, market_value,
                unrealized_pl, unrealized_plpc, side
    """
    client = get_client()
    if client is None:
        return []

    try:
        positions = client.get_all_positions()
        result = []
        for p in positions:
            result.append({
                "symbol": str(p.symbol),
                "qty": float(p.qty or 0),
                "avg_entry_price": float(p.avg_entry_price or 0),
                "current_price": float(p.current_price or 0),
                "market_value": float(p.market_value or 0),
                "unrealized_pl": float(p.unrealized_pl or 0),
                "unrealized_plpc": float(p.unrealized_plpc or 0),
                "side": str(p.side.value) if hasattr(p.side, "value") else str(p.side),
            })
        return result
    except Exception as exc:
        logger.error("get_positions failed: %s", exc)
        return []


def get_position(symbol: str) -> Optional[dict]:
    """
    Return the open position for a single symbol, or None if not held.
    """
    client = get_client()
    if client is None:
        return None

    try:
        p = client.get_open_position(symbol.upper())
        return {
            "symbol": str(p.symbol),
            "qty": float(p.qty or 0),
            "avg_entry_price": float(p.avg_entry_price or 0),
            "current_price": float(p.current_price or 0),
            "market_value": float(p.market_value or 0),
            "unrealized_pl": float(p.unrealized_pl or 0),
            "unrealized_plpc": float(p.unrealized_plpc or 0),
            "side": str(p.side.value) if hasattr(p.side, "value") else str(p.side),
        }
    except Exception as exc:
        # 404 / position not found is normal — log at debug level
        logger.debug("get_position(%s) returned no result: %s", symbol, exc)
        return None


# ---------------------------------------------------------------------------
# Orders
# ---------------------------------------------------------------------------

def get_orders(limit: int = 20) -> list[dict]:
    """
    Return recent orders (open + closed).

    Each dict: id, symbol, side, qty, status, filled_avg_price, submitted_at
    """
    client = get_client()
    if client is None:
        return []

    try:
        from alpaca.trading.requests import GetOrdersRequest

        request = GetOrdersRequest(limit=limit)
        orders = client.get_orders(filter=request)
        result = []
        for o in orders:
            result.append({
                "id": str(o.id),
                "symbol": str(o.symbol),
                "side": str(o.side.value) if hasattr(o.side, "value") else str(o.side),
                "qty": float(o.qty or 0),
                "status": str(o.status.value) if hasattr(o.status, "value") else str(o.status),
                "filled_avg_price": float(o.filled_avg_price) if o.filled_avg_price else None,
                "submitted_at": o.submitted_at.isoformat() if o.submitted_at else None,
            })
        return result
    except Exception as exc:
        logger.error("get_orders failed: %s", exc)
        return []


# ---------------------------------------------------------------------------
# Submit order
# ---------------------------------------------------------------------------

def submit_order(
    symbol: str,
    side: str,
    qty: float = None,
    notional: float = None,
) -> dict:
    """
    Submit a market order.

    Args:
        symbol:   Ticker symbol (e.g. "AAPL").
        side:     "buy" or "sell".
        qty:      Number of shares (fractional supported). Mutually exclusive
                  with notional.
        notional: Dollar amount to buy/sell. Mutually exclusive with qty.

    Returns the submitted order as a dict, or an error dict on failure.
    """
    client = get_client()
    if client is None:
        return {"error": "Alpaca client not available"}

    if qty is None and notional is None:
        return {"error": "Either qty or notional must be provided"}

    try:
        order_side = OrderSide.BUY if side.lower() == "buy" else OrderSide.SELL

        request_kwargs = dict(
            symbol=symbol.upper(),
            side=order_side,
            time_in_force=TimeInForce.DAY,
        )
        if qty is not None:
            request_kwargs["qty"] = qty
        else:
            request_kwargs["notional"] = notional

        order_request = MarketOrderRequest(**request_kwargs)
        order = client.submit_order(order_data=order_request)

        return {
            "id": str(order.id),
            "symbol": str(order.symbol),
            "side": str(order.side.value) if hasattr(order.side, "value") else str(order.side),
            "qty": float(order.qty or 0),
            "notional": float(order.notional) if order.notional else None,
            "status": str(order.status.value) if hasattr(order.status, "value") else str(order.status),
            "submitted_at": order.submitted_at.isoformat() if order.submitted_at else None,
        }
    except Exception as exc:
        logger.error("submit_order(%s %s) failed: %s", side, symbol, exc)
        return {"error": str(exc)}


# ---------------------------------------------------------------------------
# Close position
# ---------------------------------------------------------------------------

def close_position(symbol: str) -> dict:
    """
    Close the entire open position for symbol.

    Returns the closing order dict, or an error dict on failure.
    """
    client = get_client()
    if client is None:
        return {"error": "Alpaca client not available"}

    try:
        order = client.close_position(symbol.upper())
        return {
            "id": str(order.id),
            "symbol": str(order.symbol),
            "side": str(order.side.value) if hasattr(order.side, "value") else str(order.side),
            "qty": float(order.qty or 0),
            "status": str(order.status.value) if hasattr(order.status, "value") else str(order.status),
            "submitted_at": order.submitted_at.isoformat() if order.submitted_at else None,
        }
    except Exception as exc:
        logger.error("close_position(%s) failed: %s", symbol, exc)
        return {"error": str(exc)}


# ---------------------------------------------------------------------------
# Position sizing
# ---------------------------------------------------------------------------

def calculate_position_size(
    symbol: str,
    pct_of_portfolio: float = 0.05,
) -> float:
    """
    Calculate how many shares of symbol equal pct_of_portfolio of the
    current portfolio value at the latest ask price.

    Uses whole shares by default (math.floor). If the account is a
    fractional-trading account and the current price is above $1, this
    still returns whole shares for safety — callers can pass the result
    directly to submit_order(qty=...).

    Returns 0.0 on any failure.
    """
    if pct_of_portfolio <= 0 or pct_of_portfolio > 1:
        logger.warning("pct_of_portfolio must be between 0 and 1; got %s", pct_of_portfolio)
        return 0.0

    try:
        acct = get_account()
        portfolio_value = acct.get("portfolio_value", 0.0)
        if portfolio_value <= 0:
            logger.warning("Portfolio value is 0 or unavailable.")
            return 0.0

        dollar_amount = portfolio_value * pct_of_portfolio

        # Fetch the latest quote for current price
        data_client = _get_data_client()
        if data_client is None:
            logger.warning("Data client unavailable; cannot fetch quote for %s", symbol)
            return 0.0

        request = StockLatestQuoteRequest(symbol_or_symbols=symbol.upper())
        quotes = data_client.get_stock_latest_quote(request)
        quote = quotes.get(symbol.upper())
        if quote is None:
            logger.warning("No quote returned for %s", symbol)
            return 0.0

        # Use ask price; fall back to bid if ask is zero
        price = float(quote.ask_price or 0) or float(quote.bid_price or 0)
        if price <= 0:
            logger.warning("Price is 0 for %s", symbol)
            return 0.0

        qty = math.floor(dollar_amount / price)
        return float(qty)

    except Exception as exc:
        logger.error("calculate_position_size(%s) failed: %s", symbol, exc)
        return 0.0
