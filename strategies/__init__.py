"""
strategies — ELLIE's deterministic trading layer.

Pure-code strategies on Alpaca market data, sitting underneath the LLM crew:
the engine trades the rules every bar for free; the crew reviews the engine's
trade log weekly and recommends parameter changes (see api.py oversight).

Modules:
    indicators — ATR / SMA / z-score / Donchian (pandas, vectorized)
    data       — bar + latest-price fetching (stocks via IEX/SIP, crypto)
    rules      — the three strategies: mean reversion, momentum breakout,
                 trend following. Shared verbatim by live engine and backtester.
    risk       — ATR position sizing, hard 1%-risk stop, correlation filter
    engine     — the live (paper-only) engine: state, tick loop, execution
    backtest   — replays the same rules over years of historical bars
"""
