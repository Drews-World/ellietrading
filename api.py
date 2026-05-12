"""FastAPI backend for TradingAgents control center."""

import asyncio
import concurrent.futures
import json
import os
import re
import threading
import uuid
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional

from dotenv import load_dotenv, set_key, dotenv_values
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from sse_starlette.sse import EventSourceResponse

load_dotenv()

import alpaca_client  # local module — safe to import even if alpaca-py not installed

app = FastAPI(title="TradingAgents Control Center")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:5174", "http://127.0.0.1:5173", "http://127.0.0.1:5174"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Paths ─────────────────────────────────────────────────────────────────────
ROOT = Path(__file__).parent
ENV_FILE = ROOT / ".env"
PORTFOLIO_FILE = Path.home() / ".tradingagents" / "ui_portfolio.json"
MONITOR_FILE   = Path.home() / ".tradingagents" / "ui_monitors.json"
SCOUT_FILE     = Path.home() / ".tradingagents" / "ui_scout.json"
FUND_FILE      = Path.home() / ".tradingagents" / "fund_state.json"
PORTFOLIO_FILE.parent.mkdir(parents=True, exist_ok=True)

_monitor_executor = concurrent.futures.ThreadPoolExecutor(max_workers=1, thread_name_prefix="monitor")

# ── Constants ─────────────────────────────────────────────────────────────────
TRACKED_KEYS = [
    "OPENAI_API_KEY",
    "ANTHROPIC_API_KEY",
    "GOOGLE_API_KEY",
    "XAI_API_KEY",
    "ALPHA_VANTAGE_API_KEY",
    "DEEPSEEK_API_KEY",
    "GROQ_API_KEY",
    "DISCORD_WEBHOOK_URL",
    "DISCORD_BOT_TOKEN",
    "DISCORD_CHANNEL_ID",
    "APCA_API_KEY_ID",
    "APCA_API_SECRET_KEY",
    "APCA_BASE_URL",
]

# ── Alpaca auto-trade config (persisted to disk) ───────────────────────────────
ALPACA_CONFIG_FILE = Path.home() / ".tradingagents" / "alpaca_config.json"

def _load_alpaca_config() -> dict:
    if ALPACA_CONFIG_FILE.exists():
        try:
            return json.loads(ALPACA_CONFIG_FILE.read_text())
        except Exception:
            pass
    return {
        "auto_trade": False,
        "auto_trade_signals": ["BUY"],   # which signals trigger a trade
        "position_pct": 5.0,             # % of portfolio per trade
        "max_position_pct": 10.0,        # never exceed this % in one stock
        "paper": True,
    }

def _save_alpaca_config(cfg: dict):
    ALPACA_CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)
    ALPACA_CONFIG_FILE.write_text(json.dumps(cfg, indent=2))

NODE_TO_AGENT = {
    "Fundamentals Analyst": "fundamentals",
    "Market Analyst":       "market",
    "Social Analyst":       "social",
    "News Analyst":         "news",
    "Bull Researcher":      "bull_researcher",
    "Bear Researcher":      "bear_researcher",
    "Research Manager":     "research_manager",
    "Trader":               "trader",
    "Aggressive Analyst":   "aggressive",
    "Conservative Analyst": "conservative",
    "Neutral Analyst":      "neutral",
    "Portfolio Manager":    "portfolio_manager",
}

NODE_REPORT_FIELDS = {
    "Fundamentals Analyst": ["fundamentals_report"],
    "Market Analyst":       ["market_report"],
    "Social Analyst":       ["sentiment_report"],
    "News Analyst":         ["news_report"],
    "Bull Researcher":      ["investment_debate_state.current_response"],
    "Bear Researcher":      ["investment_debate_state.current_response"],
    "Research Manager":     ["investment_debate_state.judge_decision"],
    "Trader":               ["trader_investment_plan"],
    "Aggressive Analyst":   ["risk_debate_state.current_aggressive_response"],
    "Conservative Analyst": ["risk_debate_state.current_conservative_response"],
    "Neutral Analyst":      ["risk_debate_state.current_neutral_response"],
    "Portfolio Manager":    ["final_trade_decision"],
}


# ── Helpers ───────────────────────────────────────────────────────────────────

def _load_portfolio() -> List[dict]:
    if PORTFOLIO_FILE.exists():
        try:
            return json.loads(PORTFOLIO_FILE.read_text())
        except Exception:
            return []
    return []


def _save_portfolio(runs: List[dict]):
    PORTFOLIO_FILE.write_text(json.dumps(runs, indent=2))


def _load_monitors() -> dict:
    if MONITOR_FILE.exists():
        try:
            return json.loads(MONITOR_FILE.read_text())
        except Exception:
            pass
    return {"monitors": [], "alerts": []}


def _save_monitors(data: dict):
    MONITOR_FILE.write_text(json.dumps(data, indent=2))


def _load_scout() -> dict:
    if SCOUT_FILE.exists():
        try:
            return json.loads(SCOUT_FILE.read_text())
        except Exception:
            pass
    return {
        "config": {
            "enabled": False,
            "interval_hours": 24.0,
            "llm_provider": "google",
            "deep_think_llm": "gemini-2.5-pro",
            "quick_think_llm": "gemini-2.5-flash",
            "theme": "",
            "max_stocks": 3,
        },
        "recommendations": [],
        "last_run": None,
        "next_run": None,
        "is_running": False,
        "last_error": None,
    }


def _save_scout(data: dict):
    SCOUT_FILE.write_text(json.dumps(data, indent=2))


def _load_fund() -> dict:
    if FUND_FILE.exists():
        try:
            return json.loads(FUND_FILE.read_text())
        except Exception:
            pass
    return {
        "active": False,
        "launched_at": None,
        "last_daily_review": None,
        "next_daily_review": None,
        "last_weekly_report": None,
        "next_weekly_report": None,
        "config": {
            "llm_provider": "google",
            "deep_think_llm": "gemini-2.5-pro",
            "quick_think_llm": "gemini-2.5-flash",
            "initial_stocks": 5,
            "position_pct": 5.0,
            "max_position_pct": 15.0,
            "weekly_new_buy": True,
        },
        "log": [],
    }


def _save_fund(data: dict):
    FUND_FILE.parent.mkdir(parents=True, exist_ok=True)
    FUND_FILE.write_text(json.dumps(data, indent=2))


def _first_n_words(text: str, n: int = 40) -> str:
    if not text:
        return ""
    words = text.split()
    snippet = " ".join(words[:n])
    return snippet + ("…" if len(words) > n else "")


def _extract_report(node_name: str, state_delta: dict) -> str:
    """Pull the relevant report text out of a node's state delta."""
    if not isinstance(state_delta, dict):
        return ""
    fields = NODE_REPORT_FIELDS.get(node_name, [])
    for field in fields:
        parts = field.split(".")
        val = state_delta
        for p in parts:
            if isinstance(val, dict):
                val = val.get(p, "")
            else:
                val = ""
                break
        if val and isinstance(val, str):
            return val
    return ""


def _get_price(ticker: str, date: str) -> Optional[float]:
    """Fetch close price for ticker on or just after date. Returns None on failure."""
    try:
        import yfinance as yf
        start = datetime.strptime(date, "%Y-%m-%d")
        end = start + timedelta(days=5)
        hist = yf.Ticker(ticker).history(start=date, end=end.strftime("%Y-%m-%d"))
        if not hist.empty:
            return round(float(hist["Close"].iloc[0]), 2)
    except Exception:
        pass
    return None


def _get_current_price(ticker: str) -> Optional[float]:
    try:
        import yfinance as yf
        t = yf.Ticker(ticker)
        info = t.fast_info
        price = getattr(info, "last_price", None)
        if price:
            return round(float(price), 2)
        hist = t.history(period="2d")
        if not hist.empty:
            return round(float(hist["Close"].iloc[-1]), 2)
    except Exception:
        pass
    return None


# ── Models ────────────────────────────────────────────────────────────────────

class AnalyzeRequest(BaseModel):
    ticker: str
    date: str
    llm_provider: str = "openai"
    deep_think_llm: str = "gpt-4o"
    quick_think_llm: str = "gpt-4o-mini"
    max_debate_rounds: int = 1


class SettingsUpdate(BaseModel):
    OPENAI_API_KEY: Optional[str] = None
    ANTHROPIC_API_KEY: Optional[str] = None
    GOOGLE_API_KEY: Optional[str] = None
    XAI_API_KEY: Optional[str] = None
    ALPHA_VANTAGE_API_KEY: Optional[str] = None
    DEEPSEEK_API_KEY: Optional[str] = None
    GROQ_API_KEY: Optional[str] = None
    DISCORD_WEBHOOK_URL: Optional[str] = None
    DISCORD_BOT_TOKEN: Optional[str] = None
    DISCORD_CHANNEL_ID: Optional[str] = None
    APCA_API_KEY_ID: Optional[str] = None
    APCA_API_SECRET_KEY: Optional[str] = None
    APCA_BASE_URL: Optional[str] = None


class AlpacaTradeConfig(BaseModel):
    auto_trade: bool = False
    auto_trade_signals: List[str] = ["BUY"]
    position_pct: float = 5.0
    max_position_pct: float = 10.0


class AlpacaOrderRequest(BaseModel):
    symbol: str
    side: str          # "buy" or "sell"
    qty: Optional[float] = None
    notional: Optional[float] = None


class DiscoverRequest(BaseModel):
    llm_provider: str = "google"
    model: str = "gemini-2.5-flash"
    theme: str = ""
    count: int = 5


class MonitorCreate(BaseModel):
    ticker: str
    llm_provider: str = "google"
    deep_think_llm: str = "gemini-2.5-pro"
    quick_think_llm: str = "gemini-2.5-flash"
    interval_hours: float = 24


class ScoutConfig(BaseModel):
    enabled: bool = False
    interval_hours: float = 24.0
    llm_provider: str = "google"
    deep_think_llm: str = "gemini-2.5-pro"
    quick_think_llm: str = "gemini-2.5-flash"
    theme: str = ""
    max_stocks: int = 3


class FundConfig(BaseModel):
    llm_provider: str = "google"
    deep_think_llm: str = "gemini-2.5-pro"
    quick_think_llm: str = "gemini-2.5-flash"
    initial_stocks: int = 5
    position_pct: float = 5.0
    max_position_pct: float = 15.0
    weekly_new_buy: bool = True


# ── Settings endpoints ────────────────────────────────────────────────────────

@app.get("/settings")
async def get_settings():
    """Return which API keys are configured (values masked)."""
    env_vals = dotenv_values(ENV_FILE) if ENV_FILE.exists() else {}
    result = {}
    for key in TRACKED_KEYS:
        val = env_vals.get(key) or os.getenv(key) or ""
        result[key] = {
            "set": bool(val.strip()),
            "preview": (val[:8] + "…") if len(val) > 8 else ("set" if val else ""),
        }
    return result


@app.post("/settings")
async def save_settings(data: SettingsUpdate):
    """Write API keys to .env file."""
    if not ENV_FILE.exists():
        ENV_FILE.write_text("")

    updates = data.model_dump(exclude_none=True)
    for key, value in updates.items():
        value = value.strip()
        if value:
            set_key(str(ENV_FILE), key, value)
            os.environ[key] = value

    load_dotenv(ENV_FILE, override=True)
    return {"ok": True, "updated": list(updates.keys())}


# ── Portfolio endpoints ───────────────────────────────────────────────────────

@app.get("/portfolio")
async def get_portfolio():
    """Return all past runs with current prices and P&L."""
    runs = _load_portfolio()

    enriched = []
    seen_tickers: Dict[str, Optional[float]] = {}

    for run in runs:
        ticker = run.get("ticker", "")

        # Fetch current price once per ticker
        if ticker not in seen_tickers:
            seen_tickers[ticker] = _get_current_price(ticker)
        current_price = seen_tickers[ticker]

        entry_price = run.get("entry_price")
        pnl_pct = None
        if entry_price and current_price:
            direction = 1 if run.get("signal") in ("Buy", "Overweight") else -1 if run.get("signal") in ("Sell", "Underweight") else 0
            raw_pnl = (current_price - entry_price) / entry_price * 100
            pnl_pct = round(raw_pnl * direction if direction else raw_pnl, 2)

        enriched.append({
            **run,
            "current_price": current_price,
            "pnl_pct": pnl_pct,
        })

    return {"runs": enriched}


@app.delete("/portfolio/{run_id}")
async def delete_portfolio_run(run_id: str):
    runs = _load_portfolio()
    runs = [r for r in runs if r.get("id") != run_id]
    _save_portfolio(runs)
    return {"ok": True}


# ── Discord integration ───────────────────────────────────────────────────────

SIGNAL_EMOJI = {
    "Buy": "🟢", "Overweight": "🟢",
    "Hold": "🟡",
    "Sell": "🔴", "Underweight": "🔴",
}
SIGNAL_PLAIN = {
    "Buy": "BUY ↑", "Overweight": "BUY ↑",
    "Hold": "HOLD →",
    "Sell": "SELL ↓", "Underweight": "SELL ↓",
}
SIGNAL_COLOR = {
    "Buy": 3066993, "Overweight": 3066993,   # green
    "Hold": 16776960,                          # yellow
    "Sell": 15158332, "Underweight": 15158332, # red
}


def _send_discord_webhook(title: str, description: str, signal: str = "", fields: list = None, footer: str = ""):
    """POST a rich embed to the configured Discord webhook. Fire-and-forget."""
    webhook_url = os.environ.get("DISCORD_WEBHOOK_URL", "").strip()
    if not webhook_url:
        return
    import urllib.request as ur
    color = SIGNAL_COLOR.get(signal, 5793266)
    embed = {"title": title, "description": description, "color": color}
    if fields:
        embed["fields"] = fields
    if footer:
        embed["footer"] = {"text": footer}
    payload = json.dumps({"embeds": [embed]}).encode()
    try:
        req = ur.Request(webhook_url, data=payload, headers={"Content-Type": "application/json"}, method="POST")
        ur.urlopen(req, timeout=10)
    except Exception:
        pass


def _discord_analysis_embed(ticker: str, signal: str, entry_price, reasoning: str, provider: str, date: str):
    emoji = SIGNAL_EMOJI.get(signal, "⬜")
    plain = SIGNAL_PLAIN.get(signal, signal)
    snippet = " ".join(reasoning.split()[:60]) + "…" if reasoning else "—"
    price_str = f"${entry_price:.2f}" if entry_price else "—"
    _send_discord_webhook(
        title=f"{emoji} {ticker} — {plain}",
        description=f"**Analysis complete** for {ticker} on {date}",
        signal=signal,
        fields=[
            {"name": "Signal",      "value": plain,     "inline": True},
            {"name": "Entry Price", "value": price_str, "inline": True},
            {"name": "Provider",    "value": provider,  "inline": True},
            {"name": "Key Insight", "value": snippet,   "inline": False},
        ],
        footer=f"TradingAgents · {date}",
    )


def _chat_with_llm(question: str) -> str:
    """Answer a question about the portfolio using LLM + portfolio context."""
    try:
        from tradingagents.llm_clients.factory import create_llm_client
        from langchain_core.messages import HumanMessage, SystemMessage

        provider = os.environ.get("_TA_DISCORD_PROVIDER", "google")
        model    = os.environ.get("_TA_DISCORD_MODEL",    "gemini-2.5-flash")
        client   = create_llm_client(provider, model)
        llm      = client.get_llm()

        runs  = _load_portfolio()[:10]
        summary = "\n".join(
            f"- {r['ticker']} ({r['trade_date']}): {r.get('signal','?')} @ ${r.get('entry_price') or '?'}"
            for r in runs
        ) or "No runs yet."

        system = (
            "You are a personal stock analysis assistant. You have access to the user's recent "
            "TradingAgents analysis results below. Answer questions clearly and concisely. "
            "Do not recommend illegal activity. Always remind the user this is not financial advice.\n\n"
            f"Recent analyses:\n{summary}"
        )
        response = llm.invoke([SystemMessage(content=system), HumanMessage(content=question)])
        return getattr(response, "content", str(response))[:1900]
    except Exception as exc:
        return f"Sorry, I couldn't process that: {exc}"


def _run_discord_bot():
    """Run a discord.py bot in its own event loop (called from a daemon thread)."""
    token      = os.environ.get("DISCORD_BOT_TOKEN", "").strip()
    channel_id = os.environ.get("DISCORD_CHANNEL_ID", "").strip()
    if not token:
        return

    try:
        import discord
    except ImportError:
        return

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    intents = discord.Intents.default()
    intents.message_content = True
    client = discord.Client(intents=intents)

    @client.event
    async def on_ready():
        print(f"[Discord] Bot online as {client.user}")

    @client.event
    async def on_message(message):
        if message.author == client.user:
            return

        text = message.content.strip()
        lower = text.lower()

        # Only respond in the configured channel (if set) or DMs
        if channel_id and str(message.channel.id) != channel_id:
            if not isinstance(message.channel, discord.DMChannel):
                return

        if lower.startswith("!analyze "):
            parts = text.split()
            ticker = parts[1].upper() if len(parts) > 1 else ""
            if not ticker:
                await message.channel.send("Usage: `!analyze TICKER`")
                return
            await message.channel.send(f"🔍 Analyzing **{ticker}**… This takes a few minutes. I'll post the result here.")
            # Run in the monitor executor (background thread)
            def _do_analyze():
                from tradingagents.graph.trading_graph import TradingAgentsGraph
                from tradingagents.default_config import DEFAULT_CONFIG
                from tradingagents.agents.utils.agent_states import InvestDebateState, RiskDebateState
                from tradingagents.dataflows.config import set_config
                provider = os.environ.get("_TA_DISCORD_PROVIDER", "google")
                deep     = os.environ.get("_TA_DISCORD_DEEP",     "gemini-2.5-pro")
                quick    = os.environ.get("_TA_DISCORD_QUICK",    "gemini-2.5-flash")
                config = DEFAULT_CONFIG.copy()
                config.update({"llm_provider": provider, "deep_think_llm": deep,
                               "quick_think_llm": quick, "max_debate_rounds": 1, "max_risk_discuss_rounds": 1})
                ta = TradingAgentsGraph(debug=False, config=config)
                set_config(config)
                date = datetime.utcnow().strftime("%Y-%m-%d")
                past_context = ta.memory_log.get_past_context(ticker)
                init_state = {
                    "messages": [("human", ticker)], "company_of_interest": ticker,
                    "trade_date": date, "past_context": past_context,
                    "investment_debate_state": InvestDebateState(
                        bull_history="", bear_history="", history="",
                        current_response="", judge_decision="", count=0),
                    "risk_debate_state": RiskDebateState(
                        aggressive_history="", conservative_history="", neutral_history="",
                        history="", latest_speaker="", current_aggressive_response="",
                        current_conservative_response="", current_neutral_response="",
                        judge_decision="", count=0),
                    "market_report": "", "fundamentals_report": "", "sentiment_report": "", "news_report": "",
                }
                final_state = None
                for chunk in ta.graph.stream(init_state, stream_mode="updates",
                                             config={"recursion_limit": config.get("max_recur_limit", 100)}):
                    for node_name, state_delta in chunk.items():
                        if node_name == "Portfolio Manager" and isinstance(state_delta, dict):
                            final_state = state_delta
                if not final_state:
                    return None, "Analysis produced no result."
                raw = final_state.get("final_trade_decision", "")
                sig = ta.process_signal(raw)
                price = _get_current_price(ticker)
                return {"signal": sig, "reasoning": raw, "price": price, "date": date}, None

            result, err = await loop.run_in_executor(_monitor_executor, _do_analyze)
            if err:
                await message.channel.send(f"❌ Error: {err}")
            else:
                emoji = SIGNAL_EMOJI.get(result["signal"], "⬜")
                plain = SIGNAL_PLAIN.get(result["signal"], result["signal"])
                price_str = f"${result['price']:.2f}" if result["price"] else "—"
                snippet = " ".join(result["reasoning"].split()[:80]) + "…"
                await message.channel.send(
                    f"{emoji} **{ticker} — {plain}** (@ {price_str})\n\n{snippet}"
                )

        elif lower.startswith("!portfolio"):
            runs = _load_portfolio()[:8]
            if not runs:
                await message.channel.send("📂 No analysis runs yet. Use `!analyze TICKER` to start.")
                return
            lines = [f"**Recent Analyses**"]
            for r in runs:
                emoji = SIGNAL_EMOJI.get(r.get("signal"), "⬜")
                lines.append(f"{emoji} **{r['ticker']}** ({r['trade_date']}) — {SIGNAL_PLAIN.get(r.get('signal',''), r.get('signal','?'))}")
            await message.channel.send("\n".join(lines))

        elif lower.startswith("!ask ") or lower.startswith("!chat "):
            question = text[5:].strip()
            await message.channel.send("💭 Thinking…")
            answer = await loop.run_in_executor(None, _chat_with_llm, question)
            await message.channel.send(f"💡 {answer}")

        elif lower == "!help":
            await message.channel.send(
                "**TradingAgents Bot Commands**\n"
                "`!analyze TICKER` — Run a full AI analysis\n"
                "`!portfolio` — Show recent analysis results\n"
                "`!ask <question>` — Ask anything about your portfolio\n"
                "`!help` — Show this message\n\n"
                "*Note: this is not financial advice.*"
            )

    try:
        loop.run_until_complete(client.start(token))
    except Exception as exc:
        print(f"[Discord] Bot error: {exc}")


# ── Market data endpoint ─────────────────────────────────────────────────────

@app.get("/market-data/{ticker}")
async def get_market_data(ticker: str, period: str = "3mo"):
    import yfinance as yf
    try:
        t = yf.Ticker(ticker.upper())
        hist = t.history(period=period)
        prices = [
            {
                "date": str(idx.date()),
                "open":  round(float(r["Open"]),  2),
                "high":  round(float(r["High"]),  2),
                "low":   round(float(r["Low"]),   2),
                "close": round(float(r["Close"]), 2),
                "volume": int(r["Volume"]),
            }
            for idx, r in hist.iterrows()
        ]
        info = t.info
        metrics = {
            "name":           info.get("longName", ticker),
            "current_price":  info.get("currentPrice") or info.get("regularMarketPrice"),
            "trailing_pe":    info.get("trailingPE"),
            "forward_pe":     info.get("forwardPE"),
            "market_cap":     info.get("marketCap"),
            "week_52_high":   info.get("fiftyTwoWeekHigh"),
            "week_52_low":    info.get("fiftyTwoWeekLow"),
            "beta":           info.get("beta"),
            "dividend_yield": info.get("dividendYield"),
            "profit_margins": info.get("profitMargins"),
            "revenue_growth": info.get("revenueGrowth"),
            "total_revenue":  info.get("totalRevenue"),
        }
        news_raw = t.news or []
        news = []
        for n in news_raw[:8]:
            c = n.get("content", {})
            title = c.get("title", "")
            source = c.get("provider", {}).get("displayName", "Yahoo Finance")
            url = c.get("canonicalUrl", {}).get("url", "")
            if title:
                news.append({"title": title, "source": source, "url": url})
        return {"ticker": ticker.upper(), "prices": prices, "metrics": metrics, "news": news}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


# ── Discover endpoint ─────────────────────────────────────────────────────────

def _discover_stocks_sync(llm_provider: str, model: str, theme: str, count: int) -> list:
    from tradingagents.llm_clients.factory import create_llm_client
    from langchain_core.messages import HumanMessage

    client = create_llm_client(llm_provider, model)
    llm = client.get_llm()

    theme_line = (
        f"Focus on: {theme.strip()}."
        if theme.strip()
        else "Cover a diverse mix of sectors and market caps."
    )
    today = datetime.utcnow().strftime("%Y-%m-%d")

    prompt = f"""You are a senior equity analyst. Today is {today}.
{theme_line}
Identify {count} US-listed stocks that are worth a deep fundamental analysis RIGHT NOW.
Consider recent earnings, upcoming catalysts, sector momentum, news events, and valuation.

Respond ONLY with a JSON array — no markdown, no explanation, just the array:
[
  {{"ticker":"AAPL","company":"Apple Inc","sector":"Technology","reason":"One concise sentence explaining why this stock is worth analyzing today"}},
  ...
]"""

    response = llm.invoke([HumanMessage(content=prompt)])
    content = getattr(response, "content", str(response))

    match = re.search(r'\[.*?\]', content, re.DOTALL)
    if not match:
        return []
    try:
        picks = json.loads(match.group())
        return [
            {
                "ticker": p.get("ticker", "").upper().strip(),
                "company": p.get("company", ""),
                "sector": p.get("sector", ""),
                "reason": p.get("reason", ""),
            }
            for p in picks
            if p.get("ticker")
        ][:count]
    except Exception:
        return []


@app.post("/discover")
async def discover_stocks(request: DiscoverRequest):
    loop = asyncio.get_event_loop()
    picks = await loop.run_in_executor(
        None,
        _discover_stocks_sync,
        request.llm_provider,
        request.model,
        request.theme,
        request.count,
    )
    return {"picks": picks}


# ── Monitor background runner ─────────────────────────────────────────────────

def _run_analysis_for_monitor(monitor_id: str):
    """Synchronously run a full analysis for a monitor entry, update state + alerts."""
    try:
        mon = _load_monitors()
        monitor = next((m for m in mon["monitors"] if m["id"] == monitor_id), None)
        if not monitor:
            return

        from tradingagents.graph.trading_graph import TradingAgentsGraph
        from tradingagents.default_config import DEFAULT_CONFIG
        from tradingagents.agents.utils.agent_states import InvestDebateState, RiskDebateState
        from tradingagents.dataflows.config import set_config

        ticker = monitor["ticker"]
        date = datetime.utcnow().strftime("%Y-%m-%d")

        config = DEFAULT_CONFIG.copy()
        config["llm_provider"]       = monitor["llm_provider"]
        config["deep_think_llm"]     = monitor["deep_think_llm"]
        config["quick_think_llm"]    = monitor["quick_think_llm"]
        config["max_debate_rounds"]  = 1
        config["max_risk_discuss_rounds"] = 1

        ta = TradingAgentsGraph(debug=False, config=config)
        set_config(config)

        past_context = ta.memory_log.get_past_context(ticker)
        init_state = {
            "messages": [("human", ticker)],
            "company_of_interest": ticker,
            "trade_date": date,
            "past_context": past_context,
            "investment_debate_state": InvestDebateState(
                bull_history="", bear_history="", history="",
                current_response="", judge_decision="", count=0,
            ),
            "risk_debate_state": RiskDebateState(
                aggressive_history="", conservative_history="", neutral_history="",
                history="", latest_speaker="", current_aggressive_response="",
                current_conservative_response="", current_neutral_response="",
                judge_decision="", count=0,
            ),
            "market_report": "", "fundamentals_report": "",
            "sentiment_report": "", "news_report": "",
        }

        final_state = None
        for chunk in ta.graph.stream(init_state, stream_mode="updates",
                                     config={"recursion_limit": config.get("max_recur_limit", 100)}):
            for node_name, state_delta in chunk.items():
                if node_name == "Portfolio Manager" and isinstance(state_delta, dict):
                    final_state = state_delta

        if final_state is None:
            raise RuntimeError("No final state from graph")

        raw_decision = final_state.get("final_trade_decision", "")
        signal = ta.process_signal(raw_decision)
        current_price = _get_current_price(ticker)
        now = datetime.utcnow()

        mon = _load_monitors()
        prev_signal = None
        for m in mon["monitors"]:
            if m["id"] == monitor_id:
                prev_signal = m.get("last_signal")
                m["last_checked_at"] = now.isoformat()
                m["next_check_at"]   = (now + timedelta(hours=monitor["interval_hours"])).isoformat()
                m["last_signal"]     = signal
                m["last_price"]      = current_price
                m["is_running"]      = False
                m.pop("last_error", None)
                break

        signal_changed = prev_signal is None or prev_signal != signal
        if signal_changed:
            verb = "signal detected" if prev_signal is None else f"changed from {prev_signal} to {signal}"
            mon.setdefault("alerts", []).insert(0, {
                "id":         str(uuid.uuid4()),
                "monitor_id": monitor_id,
                "ticker":     ticker,
                "signal":     signal,
                "prev_signal": prev_signal,
                "price":      current_price,
                "ts":         now.isoformat(),
                "read":       False,
                "message":    f"{ticker} {verb}",
            })
            mon["alerts"] = mon["alerts"][:100]

        _save_monitors(mon)

        # Send Discord alert when signal changes
        if signal_changed:
            _discord_analysis_embed(
                ticker, signal, current_price, raw_decision,
                monitor["llm_provider"], date,
            )

    except Exception as exc:
        now = datetime.utcnow()
        try:
            mon = _load_monitors()
            for m in mon["monitors"]:
                if m["id"] == monitor_id:
                    m["is_running"]    = False
                    m["next_check_at"] = (now + timedelta(hours=1)).isoformat()
                    m["last_error"]    = str(exc)[:300]
            _save_monitors(mon)
        except Exception:
            pass


async def _monitor_scheduler():
    """Every 5 min: find due monitors and run them in the thread pool."""
    loop = asyncio.get_event_loop()
    while True:
        await asyncio.sleep(300)
        try:
            mon = _load_monitors()
            now = datetime.utcnow()
            due_ids = []
            for m in mon["monitors"]:
                if m.get("is_running"):
                    continue
                nxt = m.get("next_check_at")
                if not nxt or datetime.fromisoformat(nxt) <= now:
                    due_ids.append(m["id"])

            if due_ids:
                mon = _load_monitors()
                for m in mon["monitors"]:
                    if m["id"] in due_ids:
                        m["is_running"] = True
                _save_monitors(mon)
                for mid in due_ids:
                    await loop.run_in_executor(_monitor_executor, _run_analysis_for_monitor, mid)
        except Exception:
            pass


# ── Scout / Autonomous Agent ──────────────────────────────────────────────────

def _run_scout_cycle():
    """Discover candidate stocks and run full analysis; save BUY recommendations."""
    scout = _load_scout()
    cfg = scout["config"]

    try:
        from tradingagents.graph.trading_graph import TradingAgentsGraph
        from tradingagents.default_config import DEFAULT_CONFIG
        from tradingagents.agents.utils.agent_states import InvestDebateState, RiskDebateState
        from tradingagents.dataflows.config import set_config

        date = datetime.utcnow().strftime("%Y-%m-%d")

        # Discover ~2x the target count so we have extras if some fail
        discover_count = min(int(cfg.get("max_stocks", 3)) * 2, 10)
        picks = _discover_stocks_sync(
            cfg["llm_provider"], cfg["quick_think_llm"],
            cfg.get("theme", ""), discover_count,
        )

        new_recs = []

        for pick in picks[:int(cfg.get("max_stocks", 3))]:
            ticker = pick.get("ticker", "").upper().strip()
            if not ticker:
                continue
            try:
                ta_cfg = DEFAULT_CONFIG.copy()
                ta_cfg.update({
                    "llm_provider":            cfg["llm_provider"],
                    "deep_think_llm":          cfg["deep_think_llm"],
                    "quick_think_llm":         cfg["quick_think_llm"],
                    "max_debate_rounds":       1,
                    "max_risk_discuss_rounds": 1,
                })
                ta = TradingAgentsGraph(debug=False, config=ta_cfg)
                set_config(ta_cfg)

                past_context = ta.memory_log.get_past_context(ticker)
                init_state = {
                    "messages": [("human", ticker)],
                    "company_of_interest": ticker,
                    "trade_date": date,
                    "past_context": past_context,
                    "investment_debate_state": InvestDebateState(
                        bull_history="", bear_history="", history="",
                        current_response="", judge_decision="", count=0,
                    ),
                    "risk_debate_state": RiskDebateState(
                        aggressive_history="", conservative_history="", neutral_history="",
                        history="", latest_speaker="", current_aggressive_response="",
                        current_conservative_response="", current_neutral_response="",
                        judge_decision="", count=0,
                    ),
                    "market_report": "", "fundamentals_report": "",
                    "sentiment_report": "", "news_report": "",
                }

                final_state = None
                for chunk in ta.graph.stream(
                    init_state, stream_mode="updates",
                    config={"recursion_limit": ta_cfg.get("max_recur_limit", 100)},
                ):
                    for node_name, state_delta in chunk.items():
                        if node_name == "Portfolio Manager" and isinstance(state_delta, dict):
                            final_state = state_delta

                if not final_state:
                    continue

                raw = final_state.get("final_trade_decision", "")
                signal = ta.process_signal(raw)
                price = _get_current_price(ticker)
                run_id = str(uuid.uuid4())
                now_iso = datetime.utcnow().isoformat()

                # Always persist to portfolio
                runs = _load_portfolio()
                runs.insert(0, {
                    "id": run_id, "ticker": ticker, "trade_date": date,
                    "signal": signal, "reasoning": raw, "entry_price": price,
                    "timestamp": now_iso,
                    "provider": cfg["llm_provider"], "deep_model": cfg["deep_think_llm"],
                })
                _save_portfolio(runs[:200])

                # Only surface BUY signals as recommendations
                if signal in ("Buy", "Overweight"):
                    new_recs.append({
                        "id":      run_id,
                        "ticker":  ticker,
                        "company": pick.get("company", ""),
                        "sector":  pick.get("sector", ""),
                        "signal":  signal,
                        "price":   price,
                        "reasoning": raw,
                        "ts":      now_iso,
                    })
                    _discord_analysis_embed(ticker, signal, price, raw, cfg["llm_provider"], date)

            except Exception:
                continue

        now = datetime.utcnow()
        scout = _load_scout()
        scout["recommendations"] = (new_recs + scout.get("recommendations", []))[:100]
        scout["last_run"]   = now.isoformat()
        scout["next_run"]   = (now + timedelta(hours=float(cfg["interval_hours"]))).isoformat()
        scout["is_running"] = False
        scout["last_error"] = None
        _save_scout(scout)

    except Exception as exc:
        scout = _load_scout()
        scout["is_running"] = False
        scout["last_error"] = str(exc)[:300]
        _save_scout(scout)


async def _scout_scheduler():
    """Every 5 min: check if the scout cycle is due."""
    loop = asyncio.get_event_loop()
    while True:
        await asyncio.sleep(300)
        try:
            scout = _load_scout()
            if not scout["config"].get("enabled"):
                continue
            if scout.get("is_running"):
                continue
            next_run = scout.get("next_run")
            if next_run and datetime.fromisoformat(next_run) > datetime.utcnow():
                continue
            scout["is_running"] = True
            _save_scout(scout)
            await loop.run_in_executor(_monitor_executor, _run_scout_cycle)
        except Exception:
            pass


# ── Fund helper functions ─────────────────────────────────────────────────────

_fund_executor = concurrent.futures.ThreadPoolExecutor(max_workers=2, thread_name_prefix="fund")


def _fund_log(msg: str):
    """Append a timestamped log entry to the fund state, capped at 200 entries."""
    fund = _load_fund()
    entry = {"ts": datetime.utcnow().isoformat(), "msg": msg}
    fund.setdefault("log", []).insert(0, entry)
    fund["log"] = fund["log"][:200]
    _save_fund(fund)


def _run_analysis_simple(ticker: str, cfg: dict, max_retries: int = 3):
    """
    Run TradingAgentsGraph for a single ticker using cfg's llm settings.
    Returns (signal, raw_decision, price).
    Automatically retries on Gemini 429 RESOURCE_EXHAUSTED with backoff.
    """
    import time
    from tradingagents.graph.trading_graph import TradingAgentsGraph
    from tradingagents.default_config import DEFAULT_CONFIG
    from tradingagents.agents.utils.agent_states import InvestDebateState, RiskDebateState
    from tradingagents.dataflows.config import set_config

    date = datetime.utcnow().strftime("%Y-%m-%d")

    ta_cfg = DEFAULT_CONFIG.copy()
    ta_cfg.update({
        "llm_provider":            cfg.get("llm_provider", "google"),
        "deep_think_llm":          cfg.get("deep_think_llm", "gemini-2.5-pro"),
        "quick_think_llm":         cfg.get("quick_think_llm", "gemini-2.5-flash"),
        "max_debate_rounds":       1,
        "max_risk_discuss_rounds": 1,
    })

    for attempt in range(max_retries):
        try:
            ta = TradingAgentsGraph(debug=False, config=ta_cfg)
            set_config(ta_cfg)

            past_context = ta.memory_log.get_past_context(ticker)
            init_state = {
                "messages": [("human", ticker)],
                "company_of_interest": ticker,
                "trade_date": date,
                "past_context": past_context,
                "investment_debate_state": InvestDebateState(
                    bull_history="", bear_history="", history="",
                    current_response="", judge_decision="", count=0,
                ),
                "risk_debate_state": RiskDebateState(
                    aggressive_history="", conservative_history="", neutral_history="",
                    history="", latest_speaker="", current_aggressive_response="",
                    current_conservative_response="", current_neutral_response="",
                    judge_decision="", count=0,
                ),
                "market_report": "", "fundamentals_report": "",
                "sentiment_report": "", "news_report": "",
            }

            final_state = None
            for chunk in ta.graph.stream(
                init_state, stream_mode="updates",
                config={"recursion_limit": ta_cfg.get("max_recur_limit", 100)},
            ):
                for node_name, state_delta in chunk.items():
                    if node_name == "Portfolio Manager" and isinstance(state_delta, dict):
                        final_state = state_delta

            if not final_state:
                raise RuntimeError(f"No final state from graph for {ticker}")

            raw_decision = final_state.get("final_trade_decision", "")
            signal = ta.process_signal(raw_decision)
            price = _get_current_price(ticker)
            return signal, raw_decision, price

        except Exception as exc:
            exc_str = str(exc)
            is_rate_limit = "RESOURCE_EXHAUSTED" in exc_str or "429" in exc_str or "quota" in exc_str.lower()
            if is_rate_limit and attempt < max_retries - 1:
                # Parse retry delay from error if available, default to 90s
                wait = 90
                import re as _re
                m = _re.search(r'retry.*?(\d+)s', exc_str, _re.IGNORECASE)
                if m:
                    wait = max(int(m.group(1)) + 15, 60)
                _fund_log(f"{ticker}: rate limited (429) — waiting {wait}s before retry {attempt + 2}/{max_retries}…")
                time.sleep(wait)
            else:
                raise


def _run_fund_launch():
    """Discover stocks, analyze them, buy BUY signals. Runs in thread pool."""
    try:
        fund = _load_fund()
        cfg = fund["config"]

        fund["active"] = True
        fund["launched_at"] = datetime.utcnow().isoformat()
        _save_fund(fund)
        _fund_log("Fund launch started")

        # Enable auto_trade in alpaca config
        alpaca_cfg = _load_alpaca_config()
        alpaca_cfg["auto_trade"] = True
        alpaca_cfg["position_pct"] = cfg.get("position_pct", 5.0)
        _save_alpaca_config(alpaca_cfg)

        initial_count = int(cfg.get("initial_stocks", 5))
        picks = _discover_stocks_sync(
            cfg.get("llm_provider", "google"),
            cfg.get("quick_think_llm", "gemini-2.5-flash"),
            "high growth momentum stocks",
            initial_count * 2,  # request more so we have extras after filtering
        )

        bought = 0
        for i, pick in enumerate(picks[:initial_count]):
            ticker = pick.get("ticker", "").upper().strip()
            if not ticker:
                continue
            # Cooldown between analyses to avoid Gemini rate limits (1M tokens/min cap)
            if i > 0:
                import time as _time
                _fund_log(f"Cooling down 75s before next analysis…")
                _time.sleep(75)
            try:
                _fund_log(f"Analyzing {ticker}…")
                signal, raw_decision, price = _run_analysis_simple(ticker, cfg)
                _fund_log(f"{ticker}: signal={signal}, price=${price}")

                if signal in ("Buy", "Overweight"):
                    position_pct = cfg.get("position_pct", 5.0)
                    qty = alpaca_client.calculate_position_size(ticker, position_pct / 100)
                    if qty > 0:
                        order = alpaca_client.submit_order(ticker, "buy", qty=qty)
                        bought += 1
                        _fund_log(f"Bought {qty} shares of {ticker} (order {order.get('id', '?')})")
                        _send_discord_webhook(
                            title=f"🏦 ELLIE Fund — BUY {ticker}",
                            description=f"Purchased **{qty} shares** of {ticker} @ ${price or '?'}",
                            signal="Buy",
                            fields=[
                                {"name": "Order ID", "value": order.get("id", "?"), "inline": True},
                                {"name": "Position %", "value": f"{position_pct}%", "inline": True},
                            ],
                        )
                    else:
                        _fund_log(f"Skipped {ticker}: calculated qty = 0")
                else:
                    _fund_log(f"Skipped {ticker}: signal was {signal}")
            except Exception as exc:
                _fund_log(f"Error analyzing {ticker}: {exc}")
                continue

        now = datetime.utcnow()
        next_daily = (now + timedelta(hours=24)).isoformat()
        # Next Sunday midnight UTC
        days_until_sunday = (6 - now.weekday()) % 7 or 7
        next_sunday = (now + timedelta(days=days_until_sunday)).replace(
            hour=0, minute=0, second=0, microsecond=0
        ).isoformat()

        fund = _load_fund()
        fund["active"] = True
        fund["next_daily_review"] = next_daily
        fund["next_weekly_report"] = next_sunday
        _save_fund(fund)

        _fund_log(f"Fund launch complete — purchased {bought} position(s)")
        _send_discord_webhook(
            title="🚀 ELLIE Fund Launched",
            description=f"Autonomous fund is live — purchased **{bought}** initial position(s).",
            signal="Buy",
            footer=f"Next daily review: {next_daily[:10]}",
        )

    except Exception as exc:
        _fund_log(f"Fund launch error: {exc}")
        try:
            fund = _load_fund()
            fund["active"] = False
            _save_fund(fund)
        except Exception:
            pass


def _run_daily_review():
    """Review all positions, rebalance based on fresh signals. Runs in thread pool."""
    try:
        fund = _load_fund()
        cfg = fund["config"]
        _fund_log("Daily review started")

        positions = alpaca_client.get_positions()
        if not positions:
            _fund_log("Daily review: no open positions to review")
            fund = _load_fund()
            now = datetime.utcnow()
            fund["last_daily_review"] = now.isoformat()
            fund["next_daily_review"] = (now + timedelta(hours=24)).isoformat()
            _save_fund(fund)
            return

        # Get portfolio value for position sizing checks
        account = alpaca_client.get_account()
        portfolio_value = float(account.get("portfolio_value") or account.get("equity") or 0)

        decisions = []
        for i, pos in enumerate(positions):
            symbol = pos.get("symbol", "")
            if not symbol:
                continue
            # Cooldown between analyses to avoid Gemini rate limits
            if i > 0:
                import time as _time
                _fund_log(f"Cooling down 75s before analyzing {symbol}…")
                _time.sleep(75)
            try:
                signal, raw_decision, price = _run_analysis_simple(symbol, cfg)
                market_value = float(pos.get("market_value") or 0)
                current_pct = (market_value / portfolio_value * 100) if portfolio_value > 0 else 0

                if signal in ("Sell", "Underweight"):
                    order = alpaca_client.close_position(symbol)
                    decisions.append(f"SELL {symbol} (signal={signal})")
                    _fund_log(f"Closed position in {symbol} — signal={signal}")
                elif signal in ("Buy", "Overweight"):
                    max_pct = cfg.get("max_position_pct", 15.0)
                    if current_pct < max_pct:
                        add_pct = min(cfg.get("position_pct", 5.0), max_pct - current_pct)
                        qty = alpaca_client.calculate_position_size(symbol, add_pct / 100)
                        if qty > 0:
                            alpaca_client.submit_order(symbol, "buy", qty=qty)
                            decisions.append(f"ADD {symbol} +{qty} shares (signal={signal})")
                            _fund_log(f"Added {qty} shares to {symbol} — signal={signal}")
                        else:
                            decisions.append(f"HOLD {symbol} (BUY signal, at max position)")
                            _fund_log(f"Holding {symbol} — already at max position")
                    else:
                        decisions.append(f"HOLD {symbol} (BUY signal, at max position {max_pct}%)")
                        _fund_log(f"Holding {symbol} — at max position {max_pct}%")
                else:
                    decisions.append(f"HOLD {symbol} (signal={signal})")
                    _fund_log(f"Holding {symbol} — signal={signal}")
            except Exception as exc:
                decisions.append(f"ERROR {symbol}: {exc}")
                _fund_log(f"Error reviewing {symbol}: {exc}")
                continue

        now = datetime.utcnow()
        summary = "\n".join(decisions) if decisions else "No changes made."
        _send_discord_webhook(
            title="📋 ELLIE Daily Review Complete",
            description=summary[:1900],
            footer=f"Reviewed {len(positions)} position(s) · {now.strftime('%Y-%m-%d %H:%M')} UTC",
        )

        fund = _load_fund()
        fund["last_daily_review"] = now.isoformat()
        fund["next_daily_review"] = (now + timedelta(hours=24)).isoformat()
        _save_fund(fund)
        _fund_log("Daily review complete")

    except Exception as exc:
        _fund_log(f"Daily review error: {exc}")


def _run_weekly_report():
    """Build and send a weekly performance report. Runs in thread pool."""
    try:
        fund = _load_fund()
        cfg = fund["config"]
        _fund_log("Weekly report started")

        account = alpaca_client.get_account()
        positions = alpaca_client.get_positions()
        orders = alpaca_client.get_orders(limit=50)

        portfolio_value = account.get("portfolio_value") or account.get("equity") or 0
        cash = account.get("cash") or 0
        daily_pnl = account.get("equity") and account.get("last_equity") and (
            float(account["equity"]) - float(account["last_equity"])
        )

        lines = [
            f"**Portfolio Value:** ${float(portfolio_value):,.2f}",
            f"**Cash:** ${float(cash):,.2f}",
            f"**Today P&L:** ${daily_pnl:+,.2f}" if daily_pnl is not None else "**Today P&L:** —",
            "",
            f"**Open Positions ({len(positions)}):**",
        ]
        for pos in positions:
            sym = pos.get("symbol", "?")
            unrl = pos.get("unrealized_pl") or 0
            unrl_pct = pos.get("unrealized_plpc") or 0
            lines.append(
                f"  • {sym}: ${float(pos.get('market_value') or 0):,.2f} "
                f"(P&L: ${float(unrl):+,.2f} / {float(unrl_pct)*100:+.1f}%)"
            )

        report_body = "\n".join(lines)

        _send_discord_webhook(
            title="📊 ELLIE Weekly Report",
            description=report_body[:1900],
            footer=f"Generated {datetime.utcnow().strftime('%Y-%m-%d %H:%M')} UTC",
        )
        _fund_log("Weekly report sent to Discord")

        # Optional: discover and buy a new stock
        if cfg.get("weekly_new_buy", True):
            try:
                _fund_log("Discovering new stock for weekly buy…")
                new_picks = _discover_stocks_sync(
                    cfg.get("llm_provider", "google"),
                    cfg.get("quick_think_llm", "gemini-2.5-flash"),
                    "high growth momentum stocks",
                    3,
                )
                for j, pick in enumerate(new_picks):
                    ticker = pick.get("ticker", "").upper().strip()
                    if not ticker:
                        continue
                    # Skip if already holding
                    held_symbols = {p.get("symbol", "") for p in positions}
                    if ticker in held_symbols:
                        continue
                    if j > 0:
                        import time as _time
                        _fund_log(f"Cooling down 75s before analyzing {ticker}…")
                        _time.sleep(75)
                    signal, raw_decision, price = _run_analysis_simple(ticker, cfg)
                    if signal in ("Buy", "Overweight"):
                        qty = alpaca_client.calculate_position_size(
                            ticker, cfg.get("position_pct", 5.0) / 100
                        )
                        if qty > 0:
                            order = alpaca_client.submit_order(ticker, "buy", qty=qty)
                            _fund_log(f"Weekly new buy: {qty} shares of {ticker}")
                            _send_discord_webhook(
                                title=f"🏦 ELLIE Weekly New Buy — {ticker}",
                                description=f"Purchased **{qty} shares** of {ticker} @ ${price or '?'}",
                                signal="Buy",
                            )
                        break
            except Exception as exc:
                _fund_log(f"Weekly new buy error: {exc}")

        now = datetime.utcnow()
        days_until_sunday = (6 - now.weekday()) % 7 or 7
        next_sunday = (now + timedelta(days=days_until_sunday)).replace(
            hour=0, minute=0, second=0, microsecond=0
        ).isoformat()

        fund = _load_fund()
        fund["last_weekly_report"] = now.isoformat()
        fund["next_weekly_report"] = next_sunday
        _save_fund(fund)
        _fund_log("Weekly report complete")

    except Exception as exc:
        _fund_log(f"Weekly report error: {exc}")


async def _fund_scheduler():
    """Every 5 min: check if daily review or weekly report is due."""
    loop = asyncio.get_event_loop()
    while True:
        await asyncio.sleep(300)
        try:
            fund = _load_fund()
            if not fund.get("active"):
                continue

            now = datetime.utcnow()

            # Daily review
            next_daily = fund.get("next_daily_review")
            if next_daily and datetime.fromisoformat(next_daily) <= now:
                await loop.run_in_executor(_fund_executor, _run_daily_review)

            # Weekly report
            next_weekly = fund.get("next_weekly_report")
            if next_weekly and datetime.fromisoformat(next_weekly) <= now:
                await loop.run_in_executor(_fund_executor, _run_weekly_report)

        except Exception:
            pass


@app.on_event("startup")
async def startup():
    asyncio.create_task(_monitor_scheduler())
    asyncio.create_task(_scout_scheduler())
    asyncio.create_task(_fund_scheduler())
    token = os.environ.get("DISCORD_BOT_TOKEN", "").strip()
    if token:
        t = threading.Thread(target=_run_discord_bot, daemon=True)
        t.name = "discord-bot"
        t.start()
        print("[Discord] Bot thread started")


# ── Scout endpoints ───────────────────────────────────────────────────────────

@app.get("/scout")
async def get_scout():
    return _load_scout()


@app.post("/scout/config")
async def update_scout_config(data: ScoutConfig):
    scout = _load_scout()
    scout["config"] = data.model_dump()
    if data.enabled and not scout.get("next_run"):
        scout["next_run"] = datetime.utcnow().isoformat()
    _save_scout(scout)
    return scout


@app.post("/scout/run")
async def trigger_scout_run():
    scout = _load_scout()
    if scout.get("is_running"):
        return {"ok": False, "message": "Already running"}
    scout["is_running"] = True
    _save_scout(scout)
    loop = asyncio.get_event_loop()
    loop.run_in_executor(_monitor_executor, _run_scout_cycle)
    return {"ok": True}


@app.delete("/scout/recommendations/{rec_id}")
async def delete_scout_recommendation(rec_id: str):
    scout = _load_scout()
    scout["recommendations"] = [r for r in scout.get("recommendations", []) if r.get("id") != rec_id]
    _save_scout(scout)
    return {"ok": True}


# ── Monitor endpoints ─────────────────────────────────────────────────────────

@app.get("/monitor")
async def get_monitors():
    return _load_monitors()


@app.post("/monitor")
async def create_monitor(data: MonitorCreate):
    mon = _load_monitors()
    entry = {
        "id":             str(uuid.uuid4()),
        "ticker":         data.ticker.upper().strip(),
        "llm_provider":   data.llm_provider,
        "deep_think_llm": data.deep_think_llm,
        "quick_think_llm": data.quick_think_llm,
        "interval_hours": data.interval_hours,
        "last_checked_at": None,
        "next_check_at":  datetime.utcnow().isoformat(),  # run immediately
        "last_signal":    None,
        "last_price":     None,
        "is_running":     False,
    }
    mon["monitors"].append(entry)
    _save_monitors(mon)
    return entry


@app.delete("/monitor/{monitor_id}")
async def delete_monitor(monitor_id: str):
    mon = _load_monitors()
    mon["monitors"] = [m for m in mon["monitors"] if m["id"] != monitor_id]
    _save_monitors(mon)
    return {"ok": True}


@app.post("/monitor/{monitor_id}/run")
async def trigger_monitor_run(monitor_id: str):
    """Immediately kick off an analysis run for a monitor."""
    mon = _load_monitors()
    found = next((m for m in mon["monitors"] if m["id"] == monitor_id), None)
    if not found:
        raise HTTPException(status_code=404, detail="Monitor not found")
    if found.get("is_running"):
        return {"ok": False, "message": "Already running"}
    found["is_running"] = True
    _save_monitors(mon)
    loop = asyncio.get_event_loop()
    loop.run_in_executor(_monitor_executor, _run_analysis_for_monitor, monitor_id)
    return {"ok": True}


@app.post("/monitor/alerts/read-all")
async def mark_all_alerts_read():
    mon = _load_monitors()
    for a in mon.get("alerts", []):
        a["read"] = True
    _save_monitors(mon)
    return {"ok": True}


# ── Run lookup (tab-switch resilience) ───────────────────────────────────────

@app.get("/run/{run_id}")
async def get_run(run_id: str):
    """Return a completed run by ID (used for tab-switch recovery)."""
    runs = _load_portfolio()
    run = next((r for r in runs if r.get("id") == run_id), None)
    if not run:
        raise HTTPException(status_code=404, detail="Run not found yet")
    return run


# ── Analyze endpoint (SSE) ────────────────────────────────────────────────────

def _run_graph(request: AnalyzeRequest, queue: asyncio.Queue, loop: asyncio.AbstractEventLoop):
    """Execute TradingAgentsGraph in a thread, pushing SSE events to the queue."""
    try:
        from tradingagents.graph.trading_graph import TradingAgentsGraph
        from tradingagents.default_config import DEFAULT_CONFIG
        from tradingagents.agents.utils.agent_states import AgentState, InvestDebateState, RiskDebateState
        from tradingagents.dataflows.config import set_config

        run_id = str(uuid.uuid4())

        config = DEFAULT_CONFIG.copy()
        config["llm_provider"] = request.llm_provider
        config["deep_think_llm"] = request.deep_think_llm
        config["quick_think_llm"] = request.quick_think_llm
        config["max_debate_rounds"] = request.max_debate_rounds
        config["max_risk_discuss_rounds"] = 1

        def emit(event_type: str, data: dict):
            asyncio.run_coroutine_threadsafe(
                queue.put({"event": event_type, "data": data}), loop
            )

        emit("run_started", {"run_id": run_id})
        emit("status", {"message": "Initializing agents…"})

        ta = TradingAgentsGraph(debug=False, config=config)
        set_config(config)

        past_context = ta.memory_log.get_past_context(request.ticker)

        init_state = {
            "messages": [("human", request.ticker)],
            "company_of_interest": request.ticker,
            "trade_date": request.date,
            "past_context": past_context,
            "investment_debate_state": InvestDebateState(
                bull_history="", bear_history="", history="",
                current_response="", judge_decision="", count=0,
            ),
            "risk_debate_state": RiskDebateState(
                aggressive_history="", conservative_history="", neutral_history="",
                history="", latest_speaker="", current_aggressive_response="",
                current_conservative_response="", current_neutral_response="",
                judge_decision="", count=0,
            ),
            "market_report": "",
            "fundamentals_report": "",
            "sentiment_report": "",
            "news_report": "",
        }

        graph_args = {
            "stream_mode": "updates",
            "config": {"recursion_limit": config.get("max_recur_limit", 100)},
        }

        emit("status", {"message": f"Running analysis for {request.ticker} on {request.date}…"})

        final_state = None
        seen_nodes: set = set()

        for chunk in ta.graph.stream(init_state, **graph_args):
            for node_name, state_delta in chunk.items():
                if node_name.startswith("Msg Clear") or node_name.startswith("tools_"):
                    continue

                agent_id = NODE_TO_AGENT.get(node_name)
                if not agent_id:
                    continue

                # Emit "agent_running" the first time we see this node
                if node_name not in seen_nodes:
                    emit("agent_running", {"agent": agent_id, "node": node_name})

                seen_nodes.add(node_name)

                # Extract report content
                report = _extract_report(node_name, state_delta if isinstance(state_delta, dict) else {})

                emit("agent_complete", {
                    "agent": agent_id,
                    "node": node_name,
                    "snippet": _first_n_words(report),
                    "report": report,
                })

                if node_name == "Portfolio Manager" and isinstance(state_delta, dict):
                    final_state = state_delta

        if final_state is None:
            emit("error", {"message": "Graph completed but produced no final state."})
            return

        raw_decision = final_state.get("final_trade_decision", "")
        signal = ta.process_signal(raw_decision)

        # Fetch entry price for portfolio tracking
        entry_price = _get_price(request.ticker, request.date)

        run_record = {
            "id": run_id,
            "ticker": request.ticker,
            "trade_date": request.date,
            "signal": signal,
            "reasoning": raw_decision,
            "entry_price": entry_price,
            "timestamp": datetime.utcnow().isoformat(),
            "provider": request.llm_provider,
            "deep_model": request.deep_think_llm,
        }

        # Persist to portfolio
        runs = _load_portfolio()
        runs.insert(0, run_record)
        _save_portfolio(runs[:200])  # cap at 200 entries

        emit("final_decision", {
            "signal": signal,
            "reasoning": raw_decision,
            "ticker": request.ticker,
            "date": request.date,
            "entry_price": entry_price,
            "run_id": run_id,
        })

        # Discord notification (fire-and-forget)
        threading.Thread(
            target=_discord_analysis_embed,
            args=(request.ticker, signal, entry_price, raw_decision, request.llm_provider, request.date),
            daemon=True,
        ).start()

        # Alpaca auto-trade (fire-and-forget)
        threading.Thread(
            target=_maybe_auto_trade,
            args=(request.ticker, signal),
            daemon=True,
        ).start()

    except Exception as exc:
        import traceback
        asyncio.run_coroutine_threadsafe(
            queue.put({"event": "error", "data": {"message": str(exc), "detail": traceback.format_exc()}}),
            loop,
        )
    finally:
        asyncio.run_coroutine_threadsafe(queue.put(None), loop)


@app.post("/analyze")
async def analyze(request: AnalyzeRequest):
    queue: asyncio.Queue = asyncio.Queue()
    loop = asyncio.get_event_loop()
    asyncio.get_event_loop().run_in_executor(None, _run_graph, request, queue, loop)

    async def event_generator():
        while True:
            item = await queue.get()
            if item is None:
                break
            yield {"event": item["event"], "data": json.dumps(item["data"])}

    return EventSourceResponse(event_generator())


@app.get("/health")
async def health():
    return {"status": "ok", "timestamp": datetime.utcnow().isoformat()}


# ══════════════════════════════════════════════════════════════════════════════
#  ALPACA BROKERAGE
# ══════════════════════════════════════════════════════════════════════════════

def _maybe_auto_trade(ticker: str, signal: str):
    """Called after every analysis. Submits a market order if auto-trade is on."""
    try:
        cfg = _load_alpaca_config()
        if not cfg.get("auto_trade"):
            return
        if signal not in cfg.get("auto_trade_signals", ["BUY"]):
            return

        if signal == "BUY":
            qty = alpaca_client.calculate_position_size(ticker, cfg.get("position_pct", 5.0) / 100)
            if qty <= 0:
                return
            order = alpaca_client.submit_order(ticker, "buy", qty=qty)
            _send_discord_webhook(
                title=f"🤖 Auto-Trade Executed — {ticker}",
                description=f"**BUY** {qty} shares of {ticker}",
                signal="BUY",
                fields=[
                    {"name": "Order ID", "value": order.get("id", "?"), "inline": True},
                    {"name": "Status",   "value": order.get("status", "?"), "inline": True},
                ],
                footer="ELLIE Auto-Trader • Paper Trading" if cfg.get("paper") else "ELLIE Auto-Trader • LIVE",
            )
        elif signal == "SELL":
            pos = alpaca_client.get_position(ticker)
            if pos:
                order = alpaca_client.close_position(ticker)
                _send_discord_webhook(
                    title=f"🤖 Auto-Trade Executed — {ticker}",
                    description=f"**SELL** entire position in {ticker}",
                    signal="SELL",
                    footer="ELLIE Auto-Trader",
                )
    except Exception as e:
        print(f"[auto-trade] error for {ticker}: {e}")


@app.get("/alpaca/account")
async def alpaca_account():
    return alpaca_client.get_account()


@app.get("/alpaca/positions")
async def alpaca_positions():
    return alpaca_client.get_positions()


@app.get("/alpaca/orders")
async def alpaca_orders(limit: int = 20):
    return alpaca_client.get_orders(limit=limit)


@app.post("/alpaca/order")
async def alpaca_order(req: AlpacaOrderRequest):
    try:
        result = alpaca_client.submit_order(
            symbol=req.symbol,
            side=req.side,
            qty=req.qty,
            notional=req.notional,
        )
        return result
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.delete("/alpaca/positions/{symbol}")
async def alpaca_close_position(symbol: str):
    try:
        return alpaca_client.close_position(symbol)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.get("/alpaca/config")
async def get_alpaca_config():
    return _load_alpaca_config()


@app.post("/alpaca/config")
async def save_alpaca_config(data: AlpacaTradeConfig):
    cfg = _load_alpaca_config()
    cfg.update({
        "auto_trade":         data.auto_trade,
        "auto_trade_signals": data.auto_trade_signals,
        "position_pct":       data.position_pct,
        "max_position_pct":   data.max_position_pct,
    })
    _save_alpaca_config(cfg)
    return cfg


# ══════════════════════════════════════════════════════════════════════════════
#  AUTONOMOUS FUND
# ══════════════════════════════════════════════════════════════════════════════

@app.get("/fund")
async def get_fund():
    """Return current fund state."""
    return _load_fund()


@app.post("/fund/launch")
async def launch_fund():
    """Begin the autonomous fund — discover stocks, analyze, buy BUY signals."""
    fund = _load_fund()
    if fund.get("active"):
        return {"ok": False, "message": "Fund is already active"}
    loop = asyncio.get_event_loop()
    loop.run_in_executor(_fund_executor, _run_fund_launch)
    return {"ok": True}


@app.post("/fund/pause")
async def pause_fund():
    """Pause the fund (stop scheduled reviews; disable auto_trade)."""
    fund = _load_fund()
    fund["active"] = False
    _save_fund(fund)
    alpaca_cfg = _load_alpaca_config()
    alpaca_cfg["auto_trade"] = False
    _save_alpaca_config(alpaca_cfg)
    _fund_log("Fund paused by user")
    return {"ok": True}


@app.post("/fund/resume")
async def resume_fund():
    """Resume a paused fund (re-enable scheduled reviews and auto_trade)."""
    fund = _load_fund()
    fund["active"] = True
    _save_fund(fund)
    alpaca_cfg = _load_alpaca_config()
    alpaca_cfg["auto_trade"] = True
    _save_alpaca_config(alpaca_cfg)
    _fund_log("Fund resumed by user")
    return {"ok": True}


@app.post("/fund/config")
async def update_fund_config(data: FundConfig):
    """Update fund configuration."""
    fund = _load_fund()
    fund["config"] = data.model_dump()
    _save_fund(fund)
    return fund


@app.post("/fund/review")
async def trigger_fund_review():
    """Manually trigger an immediate daily review."""
    loop = asyncio.get_event_loop()
    loop.run_in_executor(_fund_executor, _run_daily_review)
    return {"ok": True}


@app.get("/fund/log")
async def get_fund_log():
    """Return the fund activity log."""
    fund = _load_fund()
    return fund.get("log", [])
