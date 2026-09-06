"""
askGem - AI-powered Telegram group assistant with Google Gemini.
Responds to @mentions in group chats with search-grounded answers.
Supports multiple Gemini models (cycle with /model).
On-demand market summary via /marketsummary.

Runs in webhook mode when WEBHOOK_URL is set (production on Render),
otherwise falls back to long polling (local development).
Access control: the bot auto-leaves any group it was not added to by OWNER_ID.
"""

import asyncio
import datetime
import html
import logging
import os
import re
from collections import deque

import requests
from dotenv import load_dotenv
from google import genai
from google.genai import types
from telegram import ChatMember, Update
from telegram.constants import ChatAction
from telegram.ext import (
    Application,
    ChatMemberHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

load_dotenv()

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

# Access control — numeric Telegram user ID of the bot owner (get it from @userinfobot).
# The bot auto-leaves any group it was not added to by this user.
OWNER_ID = int(os.getenv("OWNER_ID", "0"))

BOT_USERNAME: str = ""  # Auto-detected at startup
GEMINI_MODELS = [
    "gemini-2.5-flash-lite",  # Fast, 1000 RPD free tier
    "gemini-2.5-flash",        # Balanced, 250 RPD free tier
    "gemini-2.5-pro",          # Best quality, 100 RPD free tier
]
TEMPERATURE = 0.3
MAX_OUTPUT_TOKENS = 500

# Market summary config (on-demand via /marketsummary)
COINGECKO_API_KEY = os.getenv("COINGECKO_API_KEY", "")
NEWSDATA_API_KEY = os.getenv("NEWSDATA_API_KEY", "")

# Yahoo Finance tickers for each index (via yfinance)
INDICES: dict[str, str] = {
    "S&P 500":     "^GSPC",
    "NASDAQ":      "^IXIC",
    "Dow Jones":   "^DJI",
    "FTSE 100":    "^FTSE",
    "DAX":         "^GDAXI",
    "CAC 40":      "^FCHI",
    "Nikkei 225":  "^N225",
    "Hang Seng":   "^HSI",
    "STI":         "^STI",
    "SSE":         "000001.SS",
}

# Regional groupings for display
INDEX_REGIONS: list[tuple[str, list[str]]] = [
    ("🇺🇸 United States", ["S&P 500", "NASDAQ", "Dow Jones"]),
    ("🇬🇧🇪🇺 Europe",       ["FTSE 100", "DAX", "CAC 40"]),
    ("🌏 Asia-Pacific",    ["Nikkei 225", "Hang Seng", "STI", "SSE"]),
]

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Global state
# ---------------------------------------------------------------------------

# Shared conversation history (last 5 exchanges)
conversation_history: deque = deque(maxlen=5)

# Current model index (cycles through GEMINI_MODELS)
current_model_index: int = 0

# Gemini client — initialised in main()
gemini_client: genai.Client | None = None

# ---------------------------------------------------------------------------
# Market data fetchers (blocking — call via asyncio.to_thread)
# ---------------------------------------------------------------------------


def fetch_indices() -> dict[str, dict | None]:
    """Fetch previous close and % change for all indices via Yahoo Finance (batch download)."""
    import yfinance as yf

    symbols = list(INDICES.values())
    results: dict[str, dict | None] = {}
    try:
        data = yf.download(symbols, period="5d", progress=False, group_by="ticker", auto_adjust=True)
    except Exception as e:
        logger.warning("Failed to download index data: %s", e)
        return {name: None for name in INDICES}

    for name, ticker in INDICES.items():
        try:
            closes = data[ticker]["Close"].dropna()
            if len(closes) < 2:
                logger.warning("Insufficient data for %s (%s): %d rows", name, ticker, len(closes))
                results[name] = None
                continue
            latest_close = float(closes.iloc[-1])
            prev_close = float(closes.iloc[-2])
            pct_change = ((latest_close - prev_close) / prev_close) * 100
            results[name] = {"close": latest_close, "change_pct": pct_change}
            logger.info("Fetched %s: %.2f (%+.2f%%)", name, latest_close, pct_change)
        except Exception as e:
            logger.warning("Failed to parse %s (%s): %s", name, ticker, e)
            results[name] = None

    return results


def fetch_crypto() -> dict[str, dict]:
    """Fetch BTC and ETH price + 24h % change from CoinGecko."""
    url = "https://api.coingecko.com/api/v3/simple/price"
    params = {
        "ids": "bitcoin,ethereum",
        "vs_currencies": "usd",
        "include_24hr_change": "true",
    }
    headers = {}
    if COINGECKO_API_KEY:
        headers["x-cg-demo-api-key"] = COINGECKO_API_KEY

    try:
        r = requests.get(url, params=params, headers=headers, timeout=10)
        r.raise_for_status()
        data = r.json()
        return {
            "Bitcoin": {
                "price": data["bitcoin"]["usd"],
                "change_pct": data["bitcoin"].get("usd_24h_change", 0.0),
            },
            "Ethereum": {
                "price": data["ethereum"]["usd"],
                "change_pct": data["ethereum"].get("usd_24h_change", 0.0),
            },
        }
    except Exception as e:
        logger.warning("Failed to fetch crypto prices: %s", e)
        return {}


def fetch_news() -> list[dict]:
    """Fetch top business headlines from Newsdata.io (requires NEWSDATA_API_KEY)."""
    if not NEWSDATA_API_KEY:
        return []

    try:
        r = requests.get(
            "https://newsdata.io/api/1/news",
            params={
                "apikey": NEWSDATA_API_KEY,
                "category": "business",
                "language": "en",
                "size": 10,
            },
            timeout=10,
        )
        r.raise_for_status()
        articles = r.json().get("results", [])
        return [
            {
                "title": a.get("title", ""),
                "source": a.get("source_id", ""),
                "link": a.get("link", ""),
            }
            for a in articles[:10]
            if a.get("title")
        ]
    except Exception as e:
        logger.warning("Failed to fetch news: %s", e)
        return []


def generate_market_narrative(
    indices: dict[str, dict | None],
    crypto: dict[str, dict],
    news: list[dict],
) -> str:
    """Ask Gemini (no search grounding) to write a brief narrative from the data."""
    if not gemini_client:
        return ""

    data_lines: list[str] = []
    for name, data in indices.items():
        if data:
            data_lines.append(f"{name}: {data['close']:,.2f} ({data['change_pct']:+.2f}%)")
    for name, data in crypto.items():
        data_lines.append(f"{name}: ${data['price']:,.2f} ({data['change_pct']:+.2f}%)")

    news_lines = [f"- {a['title']} ({a.get('link', 'no link')})" for a in news[:3]]

    prompt = (
        "You are a concise financial analyst. Based on the following market data, "
        "write exactly 2–3 sentences summarising the overall market mood and key themes. "
        "Be direct and insightful. Do not repeat the raw numbers verbatim. "
        "Reference relevant headlines by linking to them in HTML format "
        '(e.g. <a href="URL">short description</a>).\n\n'
        "Market data:\n" + "\n".join(data_lines)
        + ("\n\nTop headlines:\n" + "\n".join(news_lines) if news_lines else "")
    )

    try:
        response = gemini_client.models.generate_content(
            model="gemini-2.5-pro",
            contents=prompt,
            config=types.GenerateContentConfig(
                temperature=0.5,
                max_output_tokens=200,
            ),
        )
        return response.text.strip()
    except Exception as e:
        logger.warning("Failed to generate market narrative: %s", e)
        return ""


# ---------------------------------------------------------------------------
# Message formatter
# ---------------------------------------------------------------------------


def _arrow(pct: float) -> str:
    return "▲" if pct >= 0 else "▼"


def format_market_message(
    indices: dict[str, dict | None],
    crypto: dict[str, dict],
    news: list[dict],
    narrative: str,
) -> str:
    """Build the HTML-formatted market summary message."""
    today = datetime.date.today().strftime("%A, %d %B %Y")
    parts = [f"📊 <b>Daily Market Summary — {today}</b>\n"]

    # Indices by region
    for region_label, index_names in INDEX_REGIONS:
        parts.append(f"{region_label}")
        for name in index_names:
            data = indices.get(name)
            if data:
                sign = "+" if data["change_pct"] >= 0 else ""
                parts.append(
                    f"  {name}: {data['close']:,.2f}  "
                    f"{_arrow(data['change_pct'])} {sign}{data['change_pct']:.2f}%"
                )
            else:
                parts.append(f"  {name}: N/A")
        parts.append("")  # Blank line between regions

    # Crypto
    if crypto:
        parts.append("₿ <b>Crypto</b>")
        for name, data in crypto.items():
            sign = "+" if data["change_pct"] >= 0 else ""
            parts.append(
                f"  {name}: ${data['price']:,.2f}  "
                f"{_arrow(data['change_pct'])} {sign}{data['change_pct']:.2f}%"
            )
        parts.append("")

    # News headlines
    if news:
        parts.append("📰 <b>Top Business Headlines</b>")
        for i, article in enumerate(news, 1):
            title = html.escape(article["title"])
            link = article.get("link", "")
            if link:
                parts.append(f'  {i}. <a href="{html.escape(link)}">{title}</a>')
            else:
                parts.append(f"  {i}. {title}")
        parts.append("")

    # Gemini commentary (allow <a href="..."> links, escape everything else)
    if narrative:
        parts.append("💬 <b>Market Commentary</b>")
        # Preserve <a href="...">...</a> tags from Gemini, escape the rest
        _link_re = re.compile(r'<a\s+href="(https?://[^"]+)">(.*?)</a>')
        _placeholders: list[str] = []

        def _stash_link(m: re.Match) -> str:
            _placeholders.append(m.group(0))
            return f"\x00LINK{len(_placeholders) - 1}\x00"

        safe = _link_re.sub(_stash_link, narrative)
        safe = html.escape(safe)
        for i, link_html in enumerate(_placeholders):
            safe = safe.replace(f"\x00LINK{i}\x00", link_html)
        parts.append(safe)

    return "\n".join(parts)


# ---------------------------------------------------------------------------
# Market summary command
# ---------------------------------------------------------------------------


async def _collect_market_data() -> tuple[dict, dict, list, str]:
    """Fetch all market data concurrently and generate narrative. Returns (indices, crypto, news, narrative)."""
    indices, crypto, news = await asyncio.gather(
        asyncio.to_thread(fetch_indices),
        asyncio.to_thread(fetch_crypto),
        asyncio.to_thread(fetch_news),
    )
    narrative = await asyncio.to_thread(generate_market_narrative, indices, crypto, news)
    return indices, crypto, news, narrative


async def market_summary_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle the /marketsummary command."""
    message = update.message
    if not message:
        return

    status_msg = await message.reply_text("📊 Fetching market data, please wait…")
    try:
        indices, crypto, news, narrative = await _collect_market_data()
        summary = format_market_message(indices, crypto, news, narrative)
        await status_msg.delete()
        await message.reply_text(summary, parse_mode="HTML")
    except Exception as e:
        logger.error("Error generating market summary: %s", e, exc_info=True)
        await status_msg.edit_text("❌ Failed to fetch market summary. Please try again later.")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


_SECRET_RE = re.compile(r"^[A-Za-z0-9_-]{1,256}$")


def resolve_run_mode(
    webhook_url: str | None,
    webhook_secret: str | None,
    port: str | None,
) -> dict:
    """Decide polling vs webhook from env values. Pure — no side effects.

    Returns {"mode": "polling"} when WEBHOOK_URL is unset, otherwise a dict of
    keyword arguments for Application.run_webhook. Raises ValueError on a
    malformed WEBHOOK_URL / WEBHOOK_SECRET so a bad deploy fails loudly.
    """
    url = (webhook_url or "").rstrip("/")
    if not url:
        return {"mode": "polling"}
    if not url.startswith("https://"):
        raise ValueError(
            "WEBHOOK_URL must start with https:// (Telegram only accepts HTTPS webhooks)"
        )

    secret = webhook_secret or ""
    if secret and not _SECRET_RE.match(secret):
        raise ValueError("WEBHOOK_SECRET must match [A-Za-z0-9_-]{1,256}")
    path = secret or "telegram-webhook"
    return {
        "mode": "webhook",
        "listen": "0.0.0.0",
        "port": int(port or "10000"),
        "url_path": path,
        "webhook_url": f"{url}/{path}",
        "secret_token": secret or None,
    }


# Bot statuses that mean "already in the chat" (so a fresh update is a change, not a join)
_IN_CHAT_STATUSES = (ChatMember.MEMBER, ChatMember.ADMINISTRATOR, ChatMember.OWNER, ChatMember.RESTRICTED)


def should_leave_chat(
    chat_type: str,
    old_status: str,
    new_status: str,
    added_by_id: int | None,
    owner_id: int,
) -> bool:
    """True only when a non-owner has just ADDED the bot to a group.

    Guards against acting on unrelated ``my_chat_member`` updates (promotion,
    demotion, permission changes), which would otherwise evict the bot from the
    owner's own groups.
    """
    if chat_type not in ("group", "supergroup"):
        return False
    was_added = old_status not in _IN_CHAT_STATUSES and new_status in (
        ChatMember.MEMBER,
        ChatMember.ADMINISTRATOR,
    )
    return was_added and added_by_id != owner_id


def get_system_prompt() -> str:
    """Return the system prompt that defines the bot's personality."""
    return (
        "You are a friendly and helpful AI assistant in a Telegram group chat.\n"
        "Guidelines:\n"
        "- Be casual and conversational, like chatting with a friend\n"
        "- Use occasional emojis (1-2 per response) to keep things friendly\n"
        "- Keep answers to 1-2 short paragraphs\n"
        "- Be direct and helpful — get to the point\n"
        "- When you use web search, briefly mention what you found\n"
        "- Stay respectful and inclusive\n"
    )


def build_prompt(user_message: str) -> str:
    """Combine system prompt, conversation history, and the current message."""
    parts = [get_system_prompt(), "\n--- Recent conversation ---"]

    if conversation_history:
        for entry in conversation_history:
            parts.append(entry)
    else:
        parts.append("(No previous conversation)")

    parts.append("\n--- Current message ---")
    parts.append(f"User: {user_message}")
    parts.append("\nAssistant:")
    return "\n".join(parts)


def query_gemini(prompt: str) -> str:
    """Send a prompt to Gemini with Google Search grounding."""
    model = GEMINI_MODELS[current_model_index]
    logger.info("Calling model: %s", model)
    response = gemini_client.models.generate_content(
        model=model,
        contents=prompt,
        config=types.GenerateContentConfig(
            temperature=TEMPERATURE,
            max_output_tokens=MAX_OUTPUT_TOKENS,
            tools=[types.Tool(google_search=types.GoogleSearch())],
        ),
    )
    logger.info("Model response: %s", response.text)
    return response.text


# ---------------------------------------------------------------------------
# Telegram handlers
# ---------------------------------------------------------------------------


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle the /start command."""
    bot_name = BOT_USERNAME.lstrip('@') if BOT_USERNAME else 'your AI assistant'
    welcome = (
        f"Hey there! I'm {bot_name}, your friendly AI assistant.\n\n"
        "How to use me:\n"
        f"  Mention me in a group chat: {BOT_USERNAME} your question here\n\n"
        "I use Google Search to give you up-to-date info, and I remember "
        "the last few messages for context.\n\n"
        "Note: I only respond to mentions in groups, not DMs.\n\n"
        "Commands:\n"
        "  /start         - This welcome message\n"
        "  /status        - Show current model\n"
        "  /model         - Switch to next model\n"
        "  /marketsummary - Get today's global market summary\n\n"
        "Let's chat!"
    )
    await update.message.reply_text(welcome)


async def status_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle the /status command — show current model."""
    model = GEMINI_MODELS[current_model_index]
    text = (
        "📊 Bot Status\n\n"
        f"Current model: {model}\n"
        f"Available models: {len(GEMINI_MODELS)}\n\n"
        "Use /model to cycle through models.\n"
        "Use /marketsummary for an on-demand market summary."
    )
    await update.message.reply_text(text)


async def handle_mention(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Respond when the bot is @mentioned in a group chat."""
    message = update.message
    if not message or not message.text:
        return

    # Only respond if this bot is mentioned
    if BOT_USERNAME.lower() not in message.text.lower():
        return

    chat_id = message.chat_id
    logger.info("Bot mentioned in chat %d", chat_id)

    searching_msg = None

    try:
        # --- Extract user message (remove bot mention) ---
        user_text = re.sub(
            re.escape(BOT_USERNAME), "", message.text, flags=re.IGNORECASE
        ).strip()

        if not user_text:
            await message.reply_text(
                "Hey, you mentioned me but didn't ask anything! "
                "Try again with a question 😊"
            )
            return

        # --- Typing indicator + searching message ---
        await context.bot.send_chat_action(chat_id=chat_id, action=ChatAction.TYPING)
        searching_msg = await message.reply_text("🔍 Searching...")

        # --- Query Gemini ---
        prompt = build_prompt(user_text)
        response_text = query_gemini(prompt)

        # --- Delete searching message and send response ---
        await searching_msg.delete()
        searching_msg = None
        await message.reply_text(response_text)

        # --- Update conversation history ---
        conversation_history.append(f"User: {user_text}")
        conversation_history.append(f"Assistant: {response_text}")

    except Exception as e:
        logger.error("Error handling mention: %s", e, exc_info=True)

        # Try to clean up searching message
        if searching_msg:
            try:
                await searching_msg.delete()
            except Exception:
                pass

        await message.reply_text(
            "Oops, I hit a snag! 😅 This might be a temporary API issue. "
            "Try again in a moment, or use /model to switch models."
        )


async def model_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle the /model command — cycle to next Gemini model."""
    global current_model_index

    old_model = GEMINI_MODELS[current_model_index]

    # Cycle to next model
    current_model_index = (current_model_index + 1) % len(GEMINI_MODELS)
    new_model = GEMINI_MODELS[current_model_index]

    await update.message.reply_text(
        f"🔄 Model changed!\n\n"
        f"Was: {old_model}\n"
        f"Now: {new_model}\n\n"
        f"({current_model_index + 1}/{len(GEMINI_MODELS)} available)"
    )
    logger.info("Model switched: %s → %s", old_model, new_model)


async def on_my_chat_member(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Leave any group the bot was just added to by someone other than OWNER_ID."""
    cm = update.my_chat_member
    if not cm:
        return

    chat = cm.chat
    added_by = cm.from_user
    added_by_id = added_by.id if added_by else None
    old_status = cm.old_chat_member.status
    new_status = cm.new_chat_member.status

    if should_leave_chat(chat.type, old_status, new_status, added_by_id, OWNER_ID):
        logger.warning(
            "Leaving unauthorized group %s (%s); added by %s (id=%s)",
            chat.id,
            chat.title,
            added_by.username if added_by else "unknown",
            added_by_id,
        )
        try:
            await context.bot.leave_chat(chat.id)
        except Exception as e:
            logger.error("Failed to leave chat %s: %s", chat.id, e)
    elif (
        added_by_id == OWNER_ID
        and old_status not in _IN_CHAT_STATUSES
        and new_status in (ChatMember.MEMBER, ChatMember.ADMINISTRATOR)
    ):
        logger.info("Joined authorized group %s (%s)", chat.id, chat.title)


async def post_init(application: Application) -> None:
    """Auto-detect bot username at startup (clone-friendly)."""
    global BOT_USERNAME
    bot_info = await application.bot.get_me()
    BOT_USERNAME = f"@{bot_info.username}"
    logger.info("Bot username detected: %s", BOT_USERNAME)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> None:
    """Validate configuration, register handlers, and start the bot."""
    global gemini_client

    # Validate environment variables — exit non-zero so a bad deploy fails visibly
    if not TELEGRAM_BOT_TOKEN or TELEGRAM_BOT_TOKEN.startswith("paste_"):
        logger.error("TELEGRAM_BOT_TOKEN is missing or not configured in .env")
        raise SystemExit(1)
    if not GEMINI_API_KEY or GEMINI_API_KEY.startswith("paste_"):
        logger.error("GEMINI_API_KEY is missing or not configured in .env")
        raise SystemExit(1)
    if not OWNER_ID:
        logger.error(
            "OWNER_ID is missing. Set it to your numeric Telegram user ID "
            "(get it from @userinfobot). The bot auto-leaves any group it was "
            "not added to by this user."
        )
        raise SystemExit(1)

    logger.info("✅ Access control: owner-only. OWNER_ID=%d", OWNER_ID)

    # Warn about optional market summary API keys
    if not NEWSDATA_API_KEY:
        logger.info(
            "ℹ️  NEWSDATA_API_KEY not set — news section will be omitted from market summaries."
        )
    if not COINGECKO_API_KEY:
        logger.info(
            "ℹ️  COINGECKO_API_KEY not set — using CoinGecko public rate-limited endpoint."
        )

    # Initialise Gemini client
    gemini_client = genai.Client(api_key=GEMINI_API_KEY)
    logger.info("Gemini client initialised (models: %s)", GEMINI_MODELS)

    # Build Telegram application
    application = Application.builder().token(TELEGRAM_BOT_TOKEN).build()

    # Auto-detect bot username at startup
    application.post_init = post_init

    # Register handlers (commands first, then message handler)
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("status", status_command))
    application.add_handler(CommandHandler("model", model_command))
    # /marketsummary fans out to several rate-limited APIs — restrict to group chats
    application.add_handler(
        CommandHandler(
            "marketsummary", market_summary_command, filters=filters.ChatType.GROUPS
        )
    )
    application.add_handler(
        MessageHandler(
            filters.ChatType.GROUPS & filters.TEXT & ~filters.COMMAND,
            handle_mention,
        )
    )
    # Auto-leave groups the owner did not add the bot to
    application.add_handler(
        ChatMemberHandler(on_my_chat_member, ChatMemberHandler.MY_CHAT_MEMBER)
    )

    # Webhook mode in production (WEBHOOK_URL set), long polling for local dev
    run_mode = resolve_run_mode(
        os.getenv("WEBHOOK_URL"),
        os.getenv("WEBHOOK_SECRET"),
        os.getenv("PORT"),
    )
    if run_mode["mode"] == "webhook":
        logger.info("Bot started in webhook mode on port %d", run_mode["port"])
        application.run_webhook(
            listen=run_mode["listen"],
            port=run_mode["port"],
            url_path=run_mode["url_path"],
            webhook_url=run_mode["webhook_url"],
            secret_token=run_mode["secret_token"],
            allowed_updates=Update.ALL_TYPES,
            drop_pending_updates=True,
        )
    else:
        logger.info("Bot started in polling mode (WEBHOOK_URL not set)")
        application.run_polling(
            allowed_updates=Update.ALL_TYPES,
            drop_pending_updates=True,
        )


if __name__ == "__main__":
    main()
