"""Tests for Discord embed building and delivery."""

import json
import pytest
from unittest.mock import MagicMock, patch

import api


# ── Webhook delivery ───────────────────────────────────────────────────────────

class TestWebhookDelivery:

    def test_skips_when_no_url_set(self):
        """No HTTP call when DISCORD_WEBHOOK_URL is missing."""
        with patch.dict("os.environ", {}, clear=True):
            with patch("urllib.request.urlopen") as mock_open:
                api._send_discord_webhook("Title", "Desc")
                mock_open.assert_not_called()

    def test_sends_correct_json_structure(self, mock_discord_url):
        """Embed payload matches Discord's expected schema."""
        captured = []

        def capture(req, **kwargs):
            captured.append(json.loads(req.data.decode()))
            r = MagicMock(); r.status = 204; return r

        with patch("urllib.request.urlopen", side_effect=capture):
            api._send_discord_webhook(
                title="Test Title",
                description="Test description",
                signal="Buy",
                fields=[{"name": "F1", "value": "V1", "inline": True}],
                footer="Test footer",
            )

        assert len(captured) == 1
        embed = captured[0]["embeds"][0]
        assert embed["title"] == "Test Title"
        assert embed["description"] == "Test description"
        assert embed["color"] == api.SIGNAL_COLOR["Buy"]
        assert embed["fields"][0]["name"] == "F1"
        assert embed["footer"]["text"] == "Test footer"

    def test_includes_discordbot_user_agent(self, mock_discord_url):
        """Cloudflare blocks requests without the DiscordBot User-Agent."""
        captured_headers = {}

        def capture(req, **kwargs):
            captured_headers.update(dict(req.headers))
            r = MagicMock(); r.status = 204; return r

        with patch("urllib.request.urlopen", side_effect=capture):
            api._send_discord_webhook("T", "D")

        assert "DiscordBot" in captured_headers.get("User-Agent", "")

    def test_signal_colors(self, mock_discord_url):
        """Each signal maps to the correct Discord embed color."""
        cases = [
            ("Buy",        api.SIGNAL_COLOR["Buy"]),
            ("Sell",       api.SIGNAL_COLOR["Sell"]),
            ("Hold",       api.SIGNAL_COLOR["Hold"]),
            ("Overweight", api.SIGNAL_COLOR["Overweight"]),
            ("unknown",    5793266),   # fallback grey
        ]
        for signal, expected_color in cases:
            captured = []
            def capture(req, **kw):
                captured.append(json.loads(req.data.decode()))
                r = MagicMock(); r.status = 204; return r

            with patch("urllib.request.urlopen", side_effect=capture):
                api._send_discord_webhook("T", "D", signal=signal)

            assert captured[0]["embeds"][0]["color"] == expected_color, f"Color wrong for signal={signal}"

    def test_handles_http_error_gracefully(self, mock_discord_url):
        """A failed HTTP call logs the error but does not raise."""
        import urllib.error
        with patch("urllib.request.urlopen", side_effect=urllib.error.HTTPError(
            url=None, code=403, msg="Forbidden", hdrs=None, fp=None
        )):
            # Should not raise
            api._send_discord_webhook("Title", "Desc")


# ── Analysis signal embeds ─────────────────────────────────────────────────────

class TestAnalysisEmbed:

    def test_buy_embed_structure(self, captured_discord):
        api._discord_analysis_embed(
            ticker="NVDA",
            signal="Buy",
            entry_price=875.50,
            reasoning="Strong AI chip demand with robust data center tailwinds.",
            provider="google",
            date="2026-05-13",
        )
        assert len(captured_discord) == 1
        call = captured_discord[0]
        assert "NVDA" in call["title"]
        assert call["signal"] == "Buy"
        fields = {f["name"]: f["value"] for f in call["fields"]}
        assert "$875.50" in fields["Entry Price"]
        assert "google" in fields["Provider"]
        assert "Key Insight" in fields

    def test_sell_embed_signal(self, captured_discord):
        api._discord_analysis_embed("TSLA", "Sell", 180.00, "Bearish reversal.", "google", "2026-05-13")
        assert captured_discord[0]["signal"] == "Sell"

    def test_hold_embed_signal(self, captured_discord):
        api._discord_analysis_embed("AAPL", "Hold", 195.00, "Neutral outlook.", "google", "2026-05-13")
        assert captured_discord[0]["signal"] == "Hold"

    def test_reasoning_is_truncated_to_snippet(self, captured_discord):
        """Key Insight field uses first 60 words, not full reasoning text."""
        long_text = " ".join(["word"] * 200)
        api._discord_analysis_embed("MSFT", "Buy", 420.00, long_text, "google", "2026-05-13")
        fields = {f["name"]: f["value"] for f in captured_discord[0]["fields"]}
        snippet = fields["Key Insight"]
        assert len(snippet.split()) <= 65   # 60 words + ellipsis tolerance
        assert snippet.endswith("…")

    def test_no_entry_price_shows_dash(self, captured_discord):
        api._discord_analysis_embed("XYZ", "Buy", None, "No price.", "google", "2026-05-13")
        fields = {f["name"]: f["value"] for f in captured_discord[0]["fields"]}
        assert fields["Entry Price"] == "—"


# ── /discord/test endpoint ─────────────────────────────────────────────────────

class TestDiscordTestEndpoint:

    def test_returns_400_when_webhook_not_configured(self, http_client):
        with patch.dict("os.environ", {"DISCORD_WEBHOOK_URL": ""}):
            r = http_client.post("/discord/test")
        assert r.status_code == 400
        assert "not configured" in r.json()["detail"].lower()

    def test_returns_200_on_success(self, http_client, mock_discord_url):
        def fake_send(req, **kw):
            r = MagicMock(); r.status = 204; return r

        with patch("urllib.request.urlopen", side_effect=fake_send):
            r = http_client.post("/discord/test")

        assert r.status_code == 200
        assert r.json()["ok"] is True

    def test_returns_502_on_webhook_http_error(self, http_client, mock_discord_url):
        import urllib.error
        with patch("urllib.request.urlopen", side_effect=urllib.error.HTTPError(
            url=None, code=403, msg="Forbidden", hdrs=None, fp=None
        )):
            r = http_client.post("/discord/test")
        assert r.status_code == 502
