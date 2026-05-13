"""Shared fixtures for ELLIE Trading test suite."""

import json
import pytest
from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch
from fastapi.testclient import TestClient

# ── Realistic mock data ────────────────────────────────────────────────────────

MOCK_ACCOUNT = {
    "equity": "105000.00",
    "last_equity": "104200.00",
    "cash": "47500.00",
    "portfolio_value": "105000.00",
    "buying_power": "95000.00",
    "status": "ACTIVE",
}

MOCK_POSITIONS = [
    {
        "symbol": "NVDA", "qty": "10", "market_value": "8750.00",
        "avg_entry_price": "815.00", "unrealized_pl": "350.00",
        "unrealized_plpc": "0.0429", "current_price": "875.00", "side": "long",
    },
    {
        "symbol": "AAPL", "qty": "25", "market_value": "4875.00",
        "avg_entry_price": "200.00", "unrealized_pl": "-125.00",
        "unrealized_plpc": "-0.0250", "current_price": "195.00", "side": "long",
    },
    {
        "symbol": "MSFT", "qty": "15", "market_value": "6300.00",
        "avg_entry_price": "390.00", "unrealized_pl": "450.00",
        "unrealized_plpc": "0.0769", "current_price": "420.00", "side": "long",
    },
]

MOCK_ORDERS = [
    {"id": "ord-nvda", "symbol": "NVDA", "side": "buy", "qty": "10",
     "status": "filled", "filled_avg_price": "815.00", "created_at": "2026-05-01T10:00:00Z"},
    {"id": "ord-aapl", "symbol": "AAPL", "side": "buy", "qty": "25",
     "status": "filled", "filled_avg_price": "200.00", "created_at": "2026-05-02T10:00:00Z"},
    {"id": "ord-msft", "symbol": "MSFT", "side": "buy", "qty": "15",
     "status": "filled", "filled_avg_price": "390.00", "created_at": "2026-05-03T10:00:00Z"},
]

MOCK_FUND_CONFIG = {
    "llm_provider": "google",
    "deep_think_llm": "gemini-2.5-pro",
    "quick_think_llm": "gemini-2.5-flash",
    "initial_stocks": 5,
    "position_pct": 5.0,
    "max_position_pct": 15.0,
    "weekly_new_buy": True,
}

# ── Fixtures ───────────────────────────────────────────────────────────────────

@pytest.fixture(autouse=True)
def isolate_state_files(tmp_path, monkeypatch):
    """Redirect all state file paths to tmp_path so tests never touch real files."""
    import api
    monkeypatch.setattr(api, "FUND_FILE",              tmp_path / "fund_state.json")
    monkeypatch.setattr(api, "MONITOR_FILE",           tmp_path / "monitors.json")
    monkeypatch.setattr(api, "SCOUT_FILE",             tmp_path / "scout.json")
    monkeypatch.setattr(api, "PORTFOLIO_HISTORY_FILE", tmp_path / "portfolio_history.json")
    monkeypatch.setattr(api, "APP_LOG_FILE",           tmp_path / "app.log")
    monkeypatch.setattr(api, "ALPACA_CONFIG_FILE",     tmp_path / "alpaca_config.json")
    return tmp_path


@pytest.fixture
def mock_alpaca():
    """Patch alpaca_client with realistic paper-trading mock data."""
    with patch("api.alpaca_client") as m:
        m.get_account.return_value = MOCK_ACCOUNT
        m.get_positions.return_value = MOCK_POSITIONS
        m.get_orders.return_value = MOCK_ORDERS
        m.submit_order.return_value = {"id": "ord-new-001", "status": "accepted"}
        m.close_position.return_value = {"id": "ord-close-001", "status": "accepted"}
        m.calculate_position_size.return_value = 5
        yield m


@pytest.fixture
def active_fund(isolate_state_files):
    """Write a healthy active fund state to the temp fund file."""
    import api
    now = datetime.utcnow()
    state = {
        "active": True,
        "launched_at": (now - timedelta(days=7)).isoformat() + "Z",
        "next_daily_review": (now + timedelta(hours=23)).isoformat() + "Z",
        "next_weekly_report": (now + timedelta(days=4)).isoformat() + "Z",
        "last_daily_review": (now - timedelta(hours=1)).isoformat() + "Z",
        "last_weekly_report": (now - timedelta(days=7)).isoformat() + "Z",
        "config": MOCK_FUND_CONFIG,
        "log": [],
    }
    api.FUND_FILE.parent.mkdir(parents=True, exist_ok=True)
    api.FUND_FILE.write_text(json.dumps(state))
    return state


@pytest.fixture
def captured_discord():
    """Intercept all _send_discord_webhook calls and collect arguments."""
    calls = []

    def fake_send(title, description, signal="", fields=None, footer=""):
        calls.append({
            "title": title, "description": description,
            "signal": signal, "fields": fields or [], "footer": footer,
        })

    with patch("api._send_discord_webhook", side_effect=fake_send):
        yield calls


@pytest.fixture
def mock_discord_url():
    """Inject a fake Discord webhook URL."""
    with patch.dict("os.environ", {"DISCORD_WEBHOOK_URL": "https://discord.com/api/webhooks/000/fake"}):
        yield


@pytest.fixture
def http_client(isolate_state_files):
    """FastAPI TestClient with full startup/shutdown lifecycle."""
    import api
    with TestClient(api.app, raise_server_exceptions=False) as c:
        yield c
