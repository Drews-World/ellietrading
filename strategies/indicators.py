"""Vectorized indicators over OHLCV DataFrames (columns: open/high/low/close/volume)."""

import pandas as pd


def sma(series: pd.Series, window: int) -> pd.Series:
    return series.rolling(window, min_periods=window).mean()


def atr(df: pd.DataFrame, window: int = 14) -> pd.Series:
    """Average True Range — Wilder's smoothing approximated with EMA."""
    high, low, close = df["high"], df["low"], df["close"]
    prev_close = close.shift(1)
    tr = pd.concat(
        [(high - low), (high - prev_close).abs(), (low - prev_close).abs()],
        axis=1,
    ).max(axis=1)
    return tr.ewm(alpha=1.0 / window, min_periods=window, adjust=False).mean()


def zscore(series: pd.Series, window: int) -> pd.Series:
    """How many rolling standard deviations the value sits from its rolling mean."""
    mean = series.rolling(window, min_periods=window).mean()
    std = series.rolling(window, min_periods=window).std()
    return (series - mean) / std.replace(0, pd.NA)


def donchian_high(series: pd.Series, window: int) -> pd.Series:
    """Highest high of the PREVIOUS `window` bars (shifted — excludes current bar)."""
    return series.rolling(window, min_periods=window).max().shift(1)


def donchian_low(series: pd.Series, window: int) -> pd.Series:
    """Lowest low of the PREVIOUS `window` bars (shifted — excludes current bar)."""
    return series.rolling(window, min_periods=window).min().shift(1)
