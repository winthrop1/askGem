"""
askGem - AI-powered Telegram group assistant with Google Gemini.
Responds to @mentions in group chats with search-grounded answers.
Supports multiple Gemini models (cycle with /model).
Daily market summary via /marketsummary or scheduled job.
"""

import asyncio
import datetime
import html
import logging
import os
import re
import threading
from collections import deque
from http.server import BaseHTTPRequestHandler, HTTPServer
from zoneinfo import ZoneInfo

import requests
from dotenv import load_dotenv
from google import genai
from google.genai import types
from telegram import Update
from telegram.constants import ChatAction
from telegram.ext import (
    Application,
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

# Chat allowlist — comma-separated chat IDs in .env, empty = reject all (secure-by-default)
_raw_ids = os.getenv("ALLOWED_CHAT_IDS", "")
ALLOWED_CHAT_IDS: set[int] = {
    int(cid.strip()) for cid in _raw_ids.split(",") if cid.strip()
}

BOT_USERNAME: str = ""  # Auto-detected at startup
GEMINI_MODELS = [
    "gemini-2.5-flash-lite",  # Fast, 1000 RPD free tier
    "gemini-2.5-flash",        # Balanced, 250 RPD free tier
    "gemini-2.5-pro",          # Best quality, 100 RPD free tier
]
TEMPERATURE = 0.3
MAX_OUTPUT_TOKENS = 500

# Market summary config
COINGECKO_API_KEY = os.getenv("COINGECKO_API_KEY", "")
NEWSDATA_API_KEY = os.getenv("NEWSDATA_API_KEY", "")
MARKET_SUMMARY_HOUR = int(os.getenv("MARKET_SUMMARY_HOUR", "8"))
MARKET_SUMMARY_MINUTE = int(os.getenv("MARKET_SUMMARY_MINUTE", "0"))
MARKET_SUMMARY_TIMEZONE = os.getenv("MARKET_SUMMARY_TIMEZONE", "UTC")
_raw_summary_ids = os.getenv("MARKET_SUMMARY_CHAT_IDS", "")
MARKET_SUMMARY_CHAT_IDS: set[int] = {
    int(cid.strip()) for cid in _raw_summary_ids.split(",") if cid.strip()
}

# Stooq tickers for each index (confirmed working via pandas-datareader)
STOOQ_INDICES: dict[str, str] = {
    "S&P 500":     "^SPX",
    "NASDAQ":      "^NDQ",
    "Dow Jones":   "^DJI",
    "FTSE 100":    "^UK100",
    "DAX":         "^DAX",
    "CAC 40":      "^CAC",
    "Nikkei 225":  "^NKX",
    "Hang Seng":   "^HSI",
    "STI":         "^STI",
    "SSE":         "^SHC",
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


def fetch_stooq_indices() -> dict[str, dict | None]:
    """Fetch previous-day closing prices and % change for all indices via Stooq."""
    try:
        import pandas_datareader as pdr
    except ImportError:
        logger.error("pandas-datareader is not installed. Run: pip install pandas-datareader lxml")
        return {name: None for name in STOOQ_INDICES}

    end = datetime.date.today()
    start = end - datetime.timedelta(days=10)  # Buffer covers weekends + holidays
    results: dict[str, dict | None] = {}

    for name, ticker in STOOQ_INDICES.items():
        try:
            df = pdr.get_data_stooq(ticker, start=start, end=end)
            if df is None or df.empty or len(df) < 2:
                logger.warning("Insufficient data for %s (%s)", name, ticker)
                results[name] = None
                continue
            df = df.sort_index()
            latest_close = float(df["Close"].iloc[-1])
            prev_close = float(df["Close"].iloc[-2])
            pct_change = ((latest_close - prev_close) / prev_close) * 100
            results[name] = {"close": latest_close, "change_pct": pct_change}
            logger.info("Fetched %s: %.2f (%+.2f%%)", name, latest_close, pct_change)
        except Exception as e:
            logger.warning("Failed to fetch %s (%s): %s", name, ticker, e)
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
                "size": 5,
            },
            timeout=10,
        )
        r.raise_for_status()
        articles = r.json().get("results", [])
        return [
            {"title": a.get("title", ""), "source": a.get("source_id", "")}
            for a in articles[:5]
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

    news_lines = [f"- {a['title']}" for a in news[:3]]

    prompt = (
        "You are a concise financial analyst. Based on the following market data, "
        "write exactly 2–3 sentences summarising the overall market mood and key themes. "
        "Be direct and insightful. Do not repeat the raw numbers verbatim.\n\n"
        "Market data:\n" + "\n".join(data_lines)
        + ("\n\nTop headlines:\n" + "\n".join(news_lines) if news_lines else "")
    )

    try:
        model = GEMINI_MODELS[current_model_index]
        response = gemini_client.models.generate_content(
            model=model,
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
            parts.append(f"  {i}. {html.escape(article['title'])}")
        parts.append("")

    # Gemini commentary
    if narrative:
        parts.append("💬 <b>Market Commentary</b>")
        parts.append(html.escape(narrative))

    return "\n".join(parts)


# ---------------------------------------------------------------------------
# Market summary command and scheduled job
# ---------------------------------------------------------------------------


async def _collect_market_data() -> tuple[dict, dict, list, str]:
    """Fetch all market data concurrently and generate narrative. Returns (indices, crypto, news, narrative)."""
    indices, crypto, news = await asyncio.gather(
        asyncio.to_thread(fetch_stooq_indices),
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

    chat_id = message.chat_id
    # Allowlist check (empty = reject all, secure-by-default)
    if not ALLOWED_CHAT_IDS:
        logger.warning(
            "Chat %d blocked: ALLOWED_CHAT_IDS is empty (secure-by-default). "
            "Add chat IDs to .env to enable bot access.",
            chat_id,
        )
        return
    if chat_id not in ALLOWED_CHAT_IDS:
        logger.info("Chat %d not in allowlist, ignoring /marketsummary", chat_id)
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


async def send_daily_market_summary(context: ContextTypes.DEFAULT_TYPE) -> None:
    """Job callback: send the daily market summary to configured chats."""
    chat_ids = MARKET_SUMMARY_CHAT_IDS or ALLOWED_CHAT_IDS
    if not chat_ids:
        logger.warning("No chat IDs configured for daily market summary")
        return

    logger.info("Running daily market summary job for %d chat(s)", len(chat_ids))
    try:
        indices, crypto, news, narrative = await _collect_market_data()
        summary = format_market_message(indices, crypto, news, narrative)

        for chat_id in chat_ids:
            try:
                await context.bot.send_message(chat_id=chat_id, text=summary, parse_mode="HTML")
                logger.info("Sent daily market summary to chat %d", chat_id)
            except Exception as e:
                logger.error("Failed to send market summary to chat %d: %s", chat_id, e)
    except Exception as e:
        logger.error("Error in daily market summary job: %s", e, exc_info=True)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


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
    tz_label = MARKET_SUMMARY_TIMEZONE
    if MARKET_SUMMARY_HOUR >= 0:
        schedule = f"{MARKET_SUMMARY_HOUR:02d}:{MARKET_SUMMARY_MINUTE:02d} {tz_label}"
    else:
        schedule = "disabled"
    text = (
        "📊 Bot Status\n\n"
        f"Current model: {model}\n"
        f"Available models: {len(GEMINI_MODELS)}\n"
        f"Daily market summary: {schedule}\n\n"
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

    # Allowlist check (empty = reject all, secure-by-default)
    if not ALLOWED_CHAT_IDS:
        logger.warning(
            "Chat %d blocked: ALLOWED_CHAT_IDS is empty (secure-by-default). "
            "Add chat IDs to .env to enable bot access.",
            chat_id
        )
        return

    if chat_id not in ALLOWED_CHAT_IDS:
        logger.info("Chat %d not in allowlist, ignoring", chat_id)
        return

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
    """Validate configuration, register handlers, and start polling."""
    global gemini_client

    # Validate environment variables
    if not TELEGRAM_BOT_TOKEN or TELEGRAM_BOT_TOKEN.startswith("paste_"):
        logger.error("TELEGRAM_BOT_TOKEN is missing or not configured in .env")
        return
    if not GEMINI_API_KEY or GEMINI_API_KEY.startswith("paste_"):
        logger.error("GEMINI_API_KEY is missing or not configured in .env")
        return

    # Validate and warn about access control configuration
    if not ALLOWED_CHAT_IDS:
        logger.warning(
            "⚠️  SECURITY WARNING: ALLOWED_CHAT_IDS is empty.\n"
            "    Bot will REJECT all group chats (secure-by-default).\n"
            "    To enable, add chat IDs to .env:\n"
            "      ALLOWED_CHAT_IDS=-1001234567890,-1009876543210\n"
            "    Find chat IDs in logs when bot is mentioned in a group."
        )
    else:
        logger.info(
            "✅ Access control enabled. Allowed chats: %s",
            ", ".join(str(cid) for cid in ALLOWED_CHAT_IDS)
        )

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
    application.add_handler(CommandHandler("marketsummary", market_summary_command))
    application.add_handler(
        MessageHandler(
            filters.ChatType.GROUPS & filters.TEXT & ~filters.COMMAND,
            handle_mention,
        )
    )

    # Schedule daily market summary job (disabled if MARKET_SUMMARY_HOUR < 0)
    if MARKET_SUMMARY_HOUR >= 0:
        try:
            tz = ZoneInfo(MARKET_SUMMARY_TIMEZONE)
        except Exception:
            logger.warning(
                "Invalid MARKET_SUMMARY_TIMEZONE '%s', falling back to UTC",
                MARKET_SUMMARY_TIMEZONE,
            )
            tz = ZoneInfo("UTC")

        summary_time = datetime.time(
            hour=MARKET_SUMMARY_HOUR,
            minute=MARKET_SUMMARY_MINUTE,
            tzinfo=tz,
        )
        application.job_queue.run_daily(send_daily_market_summary, time=summary_time)
        logger.info(
            "Daily market summary scheduled at %02d:%02d %s",
            MARKET_SUMMARY_HOUR,
            MARKET_SUMMARY_MINUTE,
            MARKET_SUMMARY_TIMEZONE,
        )
    else:
        logger.info("Daily market summary job disabled (MARKET_SUMMARY_HOUR < 0)")

    # Start health check server for Render (responds to HTTP health checks)
    port = int(os.getenv("PORT", 10000))

    class HealthHandler(BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"OK")

        def log_message(self, *args):
            pass  # Suppress noisy HTTP logs

    server = HTTPServer(("0.0.0.0", port), HealthHandler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    logger.info("Health check server running on port %d", port)

    logger.info("Bot started. Listening for mentions as %s", BOT_USERNAME)
    application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
