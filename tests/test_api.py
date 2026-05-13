"""Smoke tests for all HTTP endpoints via FastAPI TestClient."""

import json
import pytest
from unittest.mock import patch, MagicMock

from tests.conftest import MOCK_ACCOUNT, MOCK_POSITIONS, MOCK_ORDERS, MOCK_FUND_CONFIG


# ── /fund endpoints ────────────────────────────────────────────────────────────

class TestFundEndpoints:

    def test_get_fund_returns_state(self, http_client):
        r = http_client.get("/fund")
        assert r.status_code == 200
        data = r.json()
        assert "active" in data
        assert "config" in data

    def test_launch_starts_background_task(self, http_client):
        with patch("api._run_fund_launch"):
            r = http_client.post("/fund/launch")
        assert r.status_code == 200
        assert r.json()["ok"] is True

    def test_launch_rejected_when_already_active(self, http_client, active_fund):
        r = http_client.post("/fund/launch")
        assert r.status_code == 200
        assert r.json()["ok"] is False
        assert "already active" in r.json()["message"].lower()

    def test_pause_sets_inactive(self, http_client, active_fund):
        r = http_client.post("/fund/pause")
        assert r.status_code == 200
        state = http_client.get("/fund").json()
        assert state["active"] is False

    def test_resume_sets_active(self, http_client, active_fund):
        http_client.post("/fund/pause")
        r = http_client.post("/fund/resume")
        assert r.status_code == 200
        state = http_client.get("/fund").json()
        assert state["active"] is True

    def test_reset_clears_schedule(self, http_client, active_fund):
        r = http_client.post("/fund/reset")
        assert r.status_code == 200
        state = http_client.get("/fund").json()
        assert state["active"] is False
        assert state["next_daily_review"] is None
        assert state["next_weekly_report"] is None

    def test_manual_review_trigger(self, http_client, active_fund):
        with patch("api._run_daily_review"):
            r = http_client.post("/fund/review")
        assert r.status_code == 200

    def test_fund_log_returns_list(self, http_client, active_fund):
        r = http_client.get("/fund/log")
        assert r.status_code == 200
        assert isinstance(r.json(), list)


# ── /settings endpoints ────────────────────────────────────────────────────────

class TestSettingsEndpoints:

    def test_get_settings_returns_all_tracked_keys(self, http_client):
        r = http_client.get("/settings")
        assert r.status_code == 200
        data = r.json()
        assert "GOOGLE_API_KEY" in data
        assert "DISCORD_WEBHOOK_URL" in data
        assert "APCA_API_KEY_ID" in data

    def test_settings_values_are_masked(self, http_client):
        """Actual key values must never be returned in full."""
        r = http_client.get("/settings")
        for key, info in r.json().items():
            assert "set" in info
            assert "preview" in info
            # 'preview' should never contain a full API key
            assert len(info.get("preview", "")) < 20


# ── /discord endpoints ─────────────────────────────────────────────────────────

class TestDiscordEndpoints:

    def test_test_no_webhook_returns_400(self, http_client):
        with patch.dict("os.environ", {"DISCORD_WEBHOOK_URL": ""}):
            r = http_client.post("/discord/test")
        assert r.status_code == 400

    def test_test_with_webhook_calls_discord(self, http_client, mock_discord_url):
        def fake_open(req, **kw):
            m = MagicMock(); m.status = 204; return m

        with patch("urllib.request.urlopen", side_effect=fake_open):
            r = http_client.post("/discord/test")
        assert r.status_code == 200
        assert r.json()["ok"] is True


# ── /logs endpoint ─────────────────────────────────────────────────────────────

class TestLogsEndpoint:

    def test_returns_empty_list_when_no_log_file(self, http_client):
        r = http_client.get("/logs")
        assert r.status_code == 200
        assert r.json() == []

    def test_returns_entries_after_fund_activity(self, http_client):
        import api
        api._fund_log("test log entry")
        r = http_client.get("/logs")
        assert r.status_code == 200
        entries = r.json()
        assert any("test log entry" in e.get("msg", "") for e in entries)

    def test_entries_have_required_fields(self, http_client):
        import api
        api._fund_log("field check")
        entries = http_client.get("/logs").json()
        if entries:
            entry = entries[0]
            assert "ts" in entry
            assert "level" in entry
            assert "msg" in entry


# ── /monitor endpoints ─────────────────────────────────────────────────────────

class TestMonitorEndpoints:

    def test_get_monitor_returns_structure(self, http_client):
        r = http_client.get("/monitor")
        assert r.status_code == 200
        data = r.json()
        assert "monitors" in data
        assert "alerts" in data

    def test_add_monitor(self, http_client):
        r = http_client.post("/monitor", json={
            "ticker": "NVDA",
            "interval_hours": 24,
            "llm_provider": "google",
            "deep_think_llm": "gemini-2.5-pro",
            "quick_think_llm": "gemini-2.5-flash",
        })
        assert r.status_code == 200
        monitors = http_client.get("/monitor").json()["monitors"]
        assert any(m["ticker"] == "NVDA" for m in monitors)

    def test_delete_monitor(self, http_client):
        http_client.post("/monitor", json={
            "ticker": "TSLA", "interval_hours": 24,
            "llm_provider": "google", "deep_think_llm": "gemini-2.5-pro",
            "quick_think_llm": "gemini-2.5-flash",
        })
        monitors = http_client.get("/monitor").json()["monitors"]
        mid = monitors[0]["id"]
        r = http_client.delete(f"/monitor/{mid}")
        assert r.status_code == 200
        remaining = http_client.get("/monitor").json()["monitors"]
        assert not any(m["id"] == mid for m in remaining)


# ── /alpaca endpoints ──────────────────────────────────────────────────────────

class TestAlpacaEndpoints:

    def test_account_returns_data(self, http_client):
        with patch("api.alpaca_client.get_account", return_value=MOCK_ACCOUNT):
            r = http_client.get("/alpaca/account")
        assert r.status_code == 200
        assert "equity" in r.json()

    def test_positions_returns_list(self, http_client):
        with patch("api.alpaca_client.get_positions", return_value=MOCK_POSITIONS):
            r = http_client.get("/alpaca/positions")
        assert r.status_code == 200
        assert isinstance(r.json(), list)

    def test_orders_returns_list(self, http_client):
        with patch("api.alpaca_client.get_orders", return_value=MOCK_ORDERS):
            r = http_client.get("/alpaca/orders")
        assert r.status_code == 200
        assert isinstance(r.json(), list)


# ── /preview endpoints ─────────────────────────────────────────────────────────

class TestPreviewEndpoints:

    def test_weekly_report_preview_structure(self, http_client):
        with patch("api.alpaca_client.get_account", return_value=MOCK_ACCOUNT):
            with patch("api.alpaca_client.get_positions", return_value=MOCK_POSITIONS):
                with patch("api.alpaca_client.get_orders", return_value=MOCK_ORDERS):
                    r = http_client.get("/preview/weekly-report")
        assert r.status_code == 200
        data = r.json()
        assert "embed" in data
        assert "title" in data["embed"]
        assert "description" in data["embed"]
        assert "NVDA" in data["embed"]["description"]
        assert "$105,000.00" in data["embed"]["description"]

    def test_daily_review_preview_structure(self, http_client):
        r = http_client.get("/preview/daily-review")
        assert r.status_code == 200
        data = r.json()
        assert "embed" in data
        assert "Daily Review" in data["embed"]["title"]

    def test_signals_preview_returns_all_types(self, http_client):
        r = http_client.get("/preview/signals")
        assert r.status_code == 200
        data = r.json()
        signal_types = {e["signal"] for e in data}
        assert "Buy" in signal_types
        assert "Sell" in signal_types
        assert "Hold" in signal_types
