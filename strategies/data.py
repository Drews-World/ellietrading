"""
Market data for the strategy engine — Alpaca bars + latest prices.

Stocks: free Alpaca accounts get full SIP history with a 15-minute delay, so we
always request bars ending 16 minutes ago; if the account still rejects SIP we
retry on the IEX feed. A ~16-minute lag is fine for 15-min/1-hour/4-hour
strategies (and this engine is paper-only validation anyway).

Crypto: no entitlement issues — bars up to now, 24/7.

Symbols containing "/" (e.g. "BTC/USD") are treated as crypto.
"""

import logging
import os
from datetime import datetime, timedelta, timezone
from typing import Optional

import pandas as pd

logger = logging.getLogger(__name__)

try:
    from alpaca.data.historical import CryptoHistoricalDataClient, StockHistoricalDataClient
    from alpaca.data.requests import (
        CryptoBarsRequest,
        CryptoLatestQuoteRequest,
        StockBarsRequest,
        StockLatestQuoteRequest,
    )
    from alpaca.data.timeframe import TimeFrame, TimeFrameUnit
    _ALPACA_DATA_AVAILABLE = True
except ImportError:
    _ALPACA_DATA_AVAILABLE = False
    logger.warning("alpaca-py not installed — strategy data layer disabled.")

# Strategy timeframe label → (alpaca TimeFrame args, minutes per bar)
TIMEFRAMES = {
    "15Min": ((15, "Minute"), 15),
    "1Hour": ((1, "Hour"), 60),
    "4Hour": ((4, "Hour"), 240),
}

# How far back to fetch per timeframe for live evaluation — enough bars for the
# longest indicator (200-bar trend filter) with healthy margin.
_LIVE_LOOKBACK_DAYS = {"15Min": 30, "1Hour": 90, "4Hour": 240}

# Free accounts see SIP data delayed 15 minutes; stay just behind that line.
_STOCK_DATA_DELAY_MIN = 16


def is_crypto(symbol: str) -> bool:
    return "/" in symbol


def _keys() -> tuple[str, str]:
    return os.getenv("APCA_API_KEY_ID", ""), os.getenv("APCA_API_SECRET_KEY", "")


def _timeframe(label: str) -> "TimeFrame":
    (amount, unit), _ = TIMEFRAMES[label]
    return TimeFrame(amount, getattr(TimeFrameUnit, unit))


def bar_minutes(label: str) -> int:
    return TIMEFRAMES[label][1]


def _to_frame(bars, symbol: str) -> pd.DataFrame:
    """alpaca-py BarSet → tz-aware OHLCV DataFrame indexed by timestamp."""
    df = bars.df
    if df is None or df.empty:
        return pd.DataFrame(columns=["open", "high", "low", "close", "volume"])
    if isinstance(df.index, pd.MultiIndex):
        df = df.xs(symbol, level="symbol")
    return df[["open", "high", "low", "close", "volume"]].sort_index()


def _drop_incomplete(df: pd.DataFrame, timeframe: str, now: datetime) -> pd.DataFrame:
    """Drop the last bar if its period hasn't fully elapsed (it's still forming)."""
    if df.empty:
        return df
    last_start = df.index[-1].to_pydatetime()
    if last_start + timedelta(minutes=bar_minutes(timeframe)) > now:
        return df.iloc[:-1]
    return df


def fetch_bars(symbol: str, timeframe: str, days: Optional[int] = None,
               end: Optional[datetime] = None) -> pd.DataFrame:
    """Historical OHLCV bars for one symbol, completed bars only.

    Returns an empty DataFrame on any failure — callers treat that as
    "no signal this tick" rather than an error.
    """
    if not _ALPACA_DATA_AVAILABLE:
        return pd.DataFrame()
    days = days or _LIVE_LOOKBACK_DAYS.get(timeframe, 90)
    now = datetime.now(timezone.utc)
    end = end or now
    key, secret = _keys()

    try:
        if is_crypto(symbol):
            client = CryptoHistoricalDataClient(api_key=key or None, secret_key=secret or None)
            req = CryptoBarsRequest(
                symbol_or_symbols=symbol,
                timeframe=_timeframe(timeframe),
                start=end - timedelta(days=days),
                end=end,
            )
            df = _to_frame(client.get_crypto_bars(req), symbol)
        else:
            client = StockHistoricalDataClient(api_key=key, secret_key=secret)
            stock_end = min(end, now - timedelta(minutes=_STOCK_DATA_DELAY_MIN))
            req_kwargs = dict(
                symbol_or_symbols=symbol,
                timeframe=_timeframe(timeframe),
                start=stock_end - timedelta(days=days),
                end=stock_end,
                adjustment="split",
            )
            try:
                df = _to_frame(client.get_stock_bars(StockBarsRequest(**req_kwargs)), symbol)
            except Exception as e:
                if "subscription" in str(e).lower() or "sip" in str(e).lower():
                    df = _to_frame(
                        client.get_stock_bars(StockBarsRequest(**req_kwargs, feed="iex")),
                        symbol,
                    )
                else:
                    raise
        return _drop_incomplete(df, timeframe, now)
    except Exception as e:  # noqa: BLE001 — data failures must not kill the tick
        logger.error("fetch_bars(%s, %s) failed: %s", symbol, timeframe, e)
        return pd.DataFrame()


def latest_price(symbol: str) -> Optional[float]:
    """Most recent quote midpoint (falls back to one side). Used for stop checks."""
    if not _ALPACA_DATA_AVAILABLE:
        return None
    key, secret = _keys()
    try:
        if is_crypto(symbol):
            client = CryptoHistoricalDataClient(api_key=key or None, secret_key=secret or None)
            q = client.get_crypto_latest_quote(
                CryptoLatestQuoteRequest(symbol_or_symbols=symbol)
            ).get(symbol)
        else:
            client = StockHistoricalDataClient(api_key=key, secret_key=secret)
            q = client.get_stock_latest_quote(
                StockLatestQuoteRequest(symbol_or_symbols=symbol)
            ).get(symbol)
        if q is None:
            return None
        bid = float(q.bid_price or 0)
        ask = float(q.ask_price or 0)
        if bid > 0 and ask > 0:
            return (bid + ask) / 2
        return ask or bid or None
    except Exception as e:  # noqa: BLE001
        logger.debug("latest_price(%s) failed: %s", symbol, e)
        return None


def market_open() -> bool:
    """Whether the US equity market is currently open (crypto ignores this)."""
    try:
        import alpaca_client
        client = alpaca_client.get_client()
        if client is None:
            return False
        return bool(client.get_clock().is_open)
    except Exception:  # noqa: BLE001
        return False
