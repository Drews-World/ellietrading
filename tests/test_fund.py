"""Tests for fund state management, daily review, and weekly report."""

import json
import pytest
from datetime import datetime, timedelta
from unittest.mock import patch, MagicMock

import api
from tests.conftest import MOCK_FUND_CONFIG, MOCK_POSITIONS, MOCK_ACCOUNT


# ── Fund state ─────────────────────────────────────────────────────────────────

class TestFundState:

    def test_load_returns_defaults_when_file_missing(self):
        state = api._load_fund()
        assert state["active"] is False
        assert state["config"]["llm_provider"] == "google"
        assert state["log"] == []

    def test_save_and_load_roundtrip(self):
        original = api._load_fund()
        original["active"] = True
        original["config"]["position_pct"] = 7.5
        api._save_fund(original)
        reloaded = api._load_fund()
        assert reloaded["active"] is True
        assert reloaded["config"]["position_pct"] == 7.5

    def test_fund_log_prepends_entries(self):
        api._fund_log("first message")
        api._fund_log("second message")
        state = api._load_fund()
        assert state["log"][0]["msg"] == "second message"
        assert state["log"][1]["msg"] == "first message"

    def test_fund_log_capped_at_200(self):
        for i in range(250):
            api._fund_log(f"msg {i}")
        state = api._load_fund()
        assert len(state["log"]) == 200

    def test_fund_log_entries_have_utc_timestamp(self):
        api._fund_log("timestamped")
        entry = api._load_fund()["log"][0]
        assert "ts" in entry
        assert entry["ts"].endswith("Z")


# ── Fund launch ────────────────────────────────────────────────────────────────

class TestFundLaunch:

    def test_launch_sets_active_true_and_schedules(self, mock_alpaca, captured_discord):
        with patch("api._discover_stocks_sync", return_value=[{"ticker": "NVDA"}]):
            with patch("api._run_analysis_simple", return_value=("Buy", "Strong outlook.", 875.0)):
                api._run_fund_launch()

        state = api._load_fund()
        assert state["active"] is True
        assert state["next_daily_review"] is not None
        assert state["next_weekly_report"] is not None

    def test_launch_sends_discord_notification(self, mock_alpaca, captured_discord):
        with patch("api._discover_stocks_sync", return_value=[{"ticker": "NVDA"}]):
            with patch("api._run_analysis_simple", return_value=("Buy", "Strong.", 875.0)):
                api._run_fund_launch()

        titles = [c["title"] for c in captured_discord]
        assert any("Launched" in t or "Fund" in t for t in titles)

    def test_launch_skips_non_buy_signals(self, mock_alpaca, captured_discord):
        picks = [{"ticker": "NVDA"}, {"ticker": "AAPL"}, {"ticker": "MSFT"}]
        signals = [("Hold", "Neutral.", 100.0), ("Sell", "Bearish.", 200.0), ("Buy", "Bullish.", 300.0)]

        with patch("api._discover_stocks_sync", return_value=picks):
            with patch("api._run_analysis_simple", side_effect=signals):
                api._run_fund_launch()

        # Only MSFT should have been ordered
        assert mock_alpaca.submit_order.call_count == 1
        call_args = mock_alpaca.submit_order.call_args
        assert call_args[0][0] == "MSFT"

    def test_launch_error_keeps_active_true_for_monitoring(self, mock_alpaca, captured_discord):
        """If launch partially succeeds then errors, positions stay monitored."""
        # Buy one stock, then explode on second
        signals = [("Buy", "Go.", 875.0), Exception("API timeout")]

        with patch("api._discover_stocks_sync", return_value=[{"ticker": "NVDA"}, {"ticker": "AAPL"}]):
            with patch("api._run_analysis_simple", side_effect=signals):
                api._run_fund_launch()

        state = api._load_fund()
        # Must still be active so daily review fires for NVDA
        assert state["active"] is True
        assert state["next_daily_review"] is not None


# ── Daily review ───────────────────────────────────────────────────────────────

class TestDailyReview:

    def test_sell_signal_closes_position(self, active_fund, captured_discord):
        positions = [MOCK_POSITIONS[0]]   # NVDA only
        with patch("api.alpaca_client.get_positions", return_value=positions):
            with patch("api.alpaca_client.get_account", return_value=MOCK_ACCOUNT):
                with patch("api._run_analysis_simple", return_value=("Sell", "Downtrend.", 850.0)):
                    api._run_daily_review()

        with patch("api.alpaca_client.close_position") as mock_close:
            with patch("api.alpaca_client.get_positions", return_value=positions):
                with patch("api.alpaca_client.get_account", return_value=MOCK_ACCOUNT):
                    with patch("api._run_analysis_simple", return_value=("Sell", "Downtrend.", 850.0)):
                        api._run_daily_review()
            mock_close.assert_called_once_with("NVDA")

    def test_hold_signal_makes_no_trade(self, active_fund, mock_alpaca, captured_discord):
        mock_alpaca.get_positions.return_value = [MOCK_POSITIONS[0]]
        with patch("api._run_analysis_simple", return_value=("Hold", "Neutral.", 875.0)):
            api._run_daily_review()

        mock_alpaca.submit_order.assert_not_called()
        mock_alpaca.close_position.assert_not_called()

    def test_buy_signal_adds_to_position_under_max(self, active_fund, mock_alpaca, captured_discord):
        """BUY signal on existing position adds shares when under max_position_pct."""
        mock_alpaca.get_positions.return_value = [MOCK_POSITIONS[0]]   # NVDA at ~8.3% of 105k
        with patch("api._run_analysis_simple", return_value=("Buy", "Bullish.", 875.0)):
            api._run_daily_review()

        mock_alpaca.submit_order.assert_called_once()

    def test_reschedules_next_daily_review(self, active_fund, mock_alpaca, captured_discord):
        with patch("api._run_analysis_simple", return_value=("Hold", "Neutral.", 100.0)):
            api._run_daily_review()

        state = api._load_fund()
        assert state["last_daily_review"] is not None
        next_dt = datetime.fromisoformat(state["next_daily_review"].replace("Z", ""))
        assert next_dt > datetime.utcnow()

    def test_review_sends_discord_summary(self, active_fund, mock_alpaca, captured_discord):
        with patch("api._run_analysis_simple", return_value=("Hold", "Neutral.", 100.0)):
            api._run_daily_review()

        titles = [c["title"] for c in captured_discord]
        assert any("Daily Review" in t for t in titles)

    def test_review_with_no_positions_skips_gracefully(self, active_fund, captured_discord):
        with patch("api.alpaca_client.get_positions", return_value=[]):
            api._run_daily_review()

        state = api._load_fund()
        assert state["last_daily_review"] is not None   # still logs the timestamp


# ── Weekly report ──────────────────────────────────────────────────────────────

class TestWeeklyReport:

    def test_report_contains_portfolio_value(self, active_fund, mock_alpaca, captured_discord):
        with patch("api._discover_stocks_sync", return_value=[]):
            api._run_weekly_report()

        report = next(c for c in captured_discord if "Weekly Report" in c["title"])
        assert "$105,000.00" in report["description"]

    def test_report_contains_cash(self, active_fund, mock_alpaca, captured_discord):
        with patch("api._discover_stocks_sync", return_value=[]):
            api._run_weekly_report()

        report = next(c for c in captured_discord if "Weekly Report" in c["title"])
        assert "$47,500.00" in report["description"]

    def test_report_lists_all_positions(self, active_fund, mock_alpaca, captured_discord):
        with patch("api._discover_stocks_sync", return_value=[]):
            api._run_weekly_report()

        report = next(c for c in captured_discord if "Weekly Report" in c["title"])
        for sym in ["NVDA", "AAPL", "MSFT"]:
            assert sym in report["description"]

    def test_report_shows_daily_pnl(self, active_fund, mock_alpaca, captured_discord):
        """equity(105000) - last_equity(104200) = +$800 today P&L."""
        with patch("api._discover_stocks_sync", return_value=[]):
            api._run_weekly_report()

        report = next(c for c in captured_discord if "Weekly Report" in c["title"])
        assert "+$800.00" in report["description"]

    def test_report_shows_position_pnl(self, active_fund, mock_alpaca, captured_discord):
        with patch("api._discover_stocks_sync", return_value=[]):
            api._run_weekly_report()

        report = next(c for c in captured_discord if "Weekly Report" in c["title"])
        assert "+$350.00" in report["description"]    # NVDA unrealized
        assert "-$125.00" in report["description"]    # AAPL unrealized

    def test_report_reschedules_next_sunday(self, active_fund, mock_alpaca, captured_discord):
        with patch("api._discover_stocks_sync", return_value=[]):
            api._run_weekly_report()

        state = api._load_fund()
        assert state["last_weekly_report"] is not None
        next_dt = datetime.fromisoformat(state["next_weekly_report"].replace("Z", ""))
        assert next_dt > datetime.utcnow()
        assert next_dt.weekday() == 6   # Sunday

    def test_report_triggers_new_buy_when_enabled(self, active_fund, mock_alpaca, captured_discord):
        new_pick = {"ticker": "AMD"}
        with patch("api._discover_stocks_sync", return_value=[new_pick]):
            with patch("api._run_analysis_simple", return_value=("Buy", "Hot.", 150.0)):
                api._run_weekly_report()

        mock_alpaca.submit_order.assert_called_once()

    def test_report_skips_new_buy_when_disabled(self, active_fund, mock_alpaca, captured_discord):
        import api as api_mod
        state = api_mod._load_fund()
        state["config"]["weekly_new_buy"] = False
        api_mod._save_fund(state)

        with patch("api._discover_stocks_sync", return_value=[]) as mock_disc:
            api._run_weekly_report()
            mock_disc.assert_not_called()
