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
]

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


@app.on_event("startup")
async def startup():
    asyncio.create_task(_monitor_scheduler())
    asyncio.create_task(_scout_scheduler())
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
