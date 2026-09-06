"""Unit tests for pure helpers in main.py (formatter, run-mode select, auto-leave rule)."""

import os

import pytest

# Ensure module import never blocks on missing config.
os.environ.setdefault("TELEGRAM_BOT_TOKEN", "test:token")
os.environ.setdefault("GEMINI_API_KEY", "test-key")

import main  # noqa: E402


# ---------------------------------------------------------------------------
# format_market_message
# ---------------------------------------------------------------------------


def _empty_indices():
    return {name: None for name in main.INDICES}


def test_format_market_message_basic():
    indices = _empty_indices()
    indices["S&P 500"] = {"close": 5000.0, "change_pct": 1.234}
    indices["NASDAQ"] = {"close": 16000.0, "change_pct": -0.5}
    crypto = {"Bitcoin": {"price": 60000.0, "change_pct": 2.0}}
    news = [{"title": "Big <deal> & co", "source": "x", "link": "http://e.com/a"}]

    out = main.format_market_message(indices, crypto, news, "")

    assert "Daily Market Summary" in out
    assert "S&P 500: 5,000.00" in out
    assert "▲ +1.23%" in out
    assert "▼ -0.50%" in out
    assert "  Dow Jones: N/A" in out
    assert "₿ <b>Crypto</b>" in out
    assert "Bitcoin: $60,000.00" in out
    assert '<a href="http://e.com/a">Big &lt;deal&gt; &amp; co</a>' in out


def test_format_market_message_omits_empty_sections():
    out = main.format_market_message(_empty_indices(), {}, [], "")
    assert "Crypto" not in out
    assert "Top Business Headlines" not in out
    assert "Market Commentary" not in out


def test_format_market_message_narrative_preserves_links_escapes_rest():
    narrative = 'Markets rose <a href="https://x.com/y">on news</a> & hope <script>'
    out = main.format_market_message(_empty_indices(), {}, [], narrative)
    assert '<a href="https://x.com/y">on news</a>' in out
    assert "&amp; hope &lt;script&gt;" in out
    assert "💬 <b>Market Commentary</b>" in out


# ---------------------------------------------------------------------------
# resolve_run_mode
# ---------------------------------------------------------------------------


def test_resolve_run_mode_polling_when_no_url():
    assert main.resolve_run_mode("", "secret", "10000") == {"mode": "polling"}
    assert main.resolve_run_mode(None, None, None) == {"mode": "polling"}


def test_resolve_run_mode_webhook_with_secret():
    cfg = main.resolve_run_mode("https://x.onrender.com/", "s3cr3t", "8080")
    assert cfg["mode"] == "webhook"
    assert cfg["port"] == 8080
    assert cfg["url_path"] == "s3cr3t"
    assert cfg["webhook_url"] == "https://x.onrender.com/s3cr3t"
    assert cfg["secret_token"] == "s3cr3t"


def test_resolve_run_mode_webhook_without_secret_uses_default_path():
    cfg = main.resolve_run_mode("https://x.onrender.com", "", None)
    assert cfg["url_path"] == "telegram-webhook"
    assert cfg["webhook_url"] == "https://x.onrender.com/telegram-webhook"
    assert cfg["secret_token"] is None
    assert cfg["port"] == 10000


def test_resolve_run_mode_rejects_non_https_url():
    with pytest.raises(ValueError):
        main.resolve_run_mode("http://x.onrender.com", "s3cr3t", "10000")
    with pytest.raises(ValueError):
        main.resolve_run_mode("x.onrender.com", "s3cr3t", "10000")


def test_resolve_run_mode_rejects_bad_secret():
    with pytest.raises(ValueError):
        main.resolve_run_mode("https://x.onrender.com", "bad/secret", "10000")
    with pytest.raises(ValueError):
        main.resolve_run_mode("https://x.onrender.com", "with space", "10000")


# ---------------------------------------------------------------------------
# should_leave_chat (owner-only auto-leave rule)
# ---------------------------------------------------------------------------

OWNER = 111
CM = main.ChatMember


def _added(chat_type, new_status, added_by, old_status=None):
    return main.should_leave_chat(
        chat_type, old_status or CM.LEFT, new_status, added_by, OWNER
    )


def test_should_leave_when_stranger_adds_bot_to_group():
    assert _added("supergroup", CM.MEMBER, 999) is True
    assert _added("group", CM.ADMINISTRATOR, 999) is True


def test_should_stay_when_owner_adds_bot():
    assert _added("supergroup", CM.MEMBER, OWNER) is False


def test_should_ignore_non_group_chats():
    assert _added("private", CM.MEMBER, 999) is False


def test_should_ignore_bot_removal_events():
    assert main.should_leave_chat("group", CM.MEMBER, CM.LEFT, 999, OWNER) is False
    assert main.should_leave_chat("group", CM.ADMINISTRATOR, CM.BANNED, 999, OWNER) is False


def test_should_not_leave_on_promotion_or_demotion_by_non_owner():
    # co-admin promotes the bot in the owner's own group -> must NOT leave
    assert main.should_leave_chat("supergroup", CM.MEMBER, CM.ADMINISTRATOR, 999, OWNER) is False
    # demotion
    assert main.should_leave_chat("supergroup", CM.ADMINISTRATOR, CM.MEMBER, 999, OWNER) is False


def test_should_leave_when_adder_unknown():
    assert _added("group", CM.MEMBER, None) is True
