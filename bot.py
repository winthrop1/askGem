"""
gonk - A Telegram AI bot powered by Google Gemini 1.5 Flash.
Responds to @mentions in group chats with search-grounded answers.
"""

import os
import re
import time
import logging
from datetime import datetime, timezone, timedelta
from collections import deque

from dotenv import load_dotenv
from telegram import Update
from telegram.constants import ChatAction
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters,
)
from google import genai
from google.genai import types

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

load_dotenv()

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

BOT_USERNAME = "@gonkted_bot"
DAILY_LIMIT = 1500
WARNING_THRESHOLD = 1350  # 90% of daily limit
GEMINI_MODEL = "gemini-2.5-flash-lite"
TEMPERATURE = 0.3
MAX_OUTPUT_TOKENS = 500

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

# Daily analytics
daily_stats: dict = {
    "requests": 0,
    "errors": 0,
    "response_times": [],       # last 100 response times in seconds
    "last_reset": datetime.now(timezone.utc).date(),
    "warning_sent": False,
    "limit_reached": False,
}

# Gemini client — initialised in main()
gemini_client: genai.Client | None = None

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def check_daily_reset() -> None:
    """Reset daily stats if a new UTC day has started."""
    global daily_stats

    today = datetime.now(timezone.utc).date()
    if today != daily_stats["last_reset"]:
        logger.info(
            "Daily reset triggered. Previous day had %d requests and %d errors.",
            daily_stats["requests"],
            daily_stats["errors"],
        )
        daily_stats = {
            "requests": 0,
            "errors": 0,
            "response_times": [],
            "last_reset": today,
            "warning_sent": False,
            "limit_reached": False,
        }


def get_system_prompt() -> str:
    """Return the system prompt that defines gonk's personality."""
    return (
        "You are gonk, a friendly and helpful AI assistant in a Telegram group chat.\n"
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
    """Send a prompt to Gemini 1.5 Flash with Google Search grounding."""
    response = gemini_client.models.generate_content(
        model=GEMINI_MODEL,
        contents=prompt,
        config=types.GenerateContentConfig(
            temperature=TEMPERATURE,
            max_output_tokens=MAX_OUTPUT_TOKENS,
            tools=[types.Tool(google_search=types.GoogleSearch())],
        ),
    )
    return response.text


# ---------------------------------------------------------------------------
# Telegram handlers
# ---------------------------------------------------------------------------


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle the /start command."""
    welcome = (
        "Hey there! I'm gonk, your friendly AI assistant.\n\n"
        "How to use me:\n"
        f"  Mention me in a group chat: {BOT_USERNAME} your question here\n\n"
        "I use Google Search to give you up-to-date info, and I remember "
        "the last few messages for context.\n\n"
        "Note: I only respond to mentions in groups, not DMs.\n\n"
        "Commands:\n"
        "  /start  - This welcome message\n"
        "  /usage  - See analytics and rate-limit status\n\n"
        "Let's chat!"
    )
    await update.message.reply_text(welcome)


async def usage_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle the /usage command — show analytics."""
    check_daily_reset()

    requests = daily_stats["requests"]
    errors = daily_stats["errors"]
    remaining = max(0, DAILY_LIMIT - requests)
    usage_pct = (requests / DAILY_LIMIT) * 100

    # Progress bar
    filled = int(usage_pct / 5)  # 20 chars total
    bar = "█" * filled + "░" * (20 - filled)

    # Average response time
    times = daily_stats["response_times"]
    avg_time = sum(times) / len(times) if times else 0.0

    # Error rate
    total_attempts = requests + errors
    error_rate = (errors / total_attempts * 100) if total_attempts else 0.0

    # Next reset
    tomorrow = daily_stats["last_reset"] + timedelta(days=1)
    reset_str = f"{tomorrow} 00:00 UTC"

    text = (
        "📊 Bot Analytics\n\n"
        f"Rate Limit:\n"
        f"  {bar} {usage_pct:.1f}%\n"
        f"  Requests today: {requests} / {DAILY_LIMIT}\n"
        f"  Remaining: {remaining} ({100 - usage_pct:.1f}%)\n\n"
        f"Performance:\n"
        f"  Avg response time: {avg_time:.2f}s\n"
        f"  Error rate: {error_rate:.1f}%\n\n"
        f"Resets at: {reset_str}"
    )

    if daily_stats["warning_sent"]:
        text += "\n\n⚠️ Warning: approaching daily limit!"
    if daily_stats["limit_reached"]:
        text += "\n\n🛑 Daily limit reached — bot paused until reset."

    await update.message.reply_text(text)


async def handle_mention(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Respond when the bot is @mentioned in a group chat."""
    message = update.message
    if not message or not message.text:
        return

    logger.info("Received message in %s: %r", message.chat.type, message.text)

    # Only respond if this bot is mentioned
    if BOT_USERNAME.lower() not in message.text.lower():
        logger.info("Bot not mentioned, ignoring. Looking for %r", BOT_USERNAME.lower())
        return

    logger.info("Bot mentioned! Processing...")

    chat_id = message.chat_id
    searching_msg = None

    try:
        # --- Daily reset check ---
        check_daily_reset()

        # --- Rate limit check ---
        if daily_stats["limit_reached"]:
            tomorrow = daily_stats["last_reset"] + timedelta(days=1)
            await message.reply_text(
                f"⚠️ Daily limit reached ({DAILY_LIMIT} requests). "
                f"Resets at {tomorrow} 00:00 UTC."
            )
            return

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
        start = time.time()
        prompt = build_prompt(user_text)
        response_text = query_gemini(prompt)
        elapsed = time.time() - start

        # --- Delete searching message and send response ---
        await searching_msg.delete()
        searching_msg = None
        await message.reply_text(response_text)

        # --- Update conversation history ---
        conversation_history.append(f"User: {user_text}")
        conversation_history.append(f"Assistant: {response_text}")

        # --- Update analytics ---
        daily_stats["requests"] += 1
        daily_stats["response_times"].append(elapsed)
        if len(daily_stats["response_times"]) > 100:
            daily_stats["response_times"] = daily_stats["response_times"][-100:]

        logger.info(
            "Request #%d processed in %.2fs", daily_stats["requests"], elapsed
        )

        # --- Threshold warnings ---
        if (
            daily_stats["requests"] >= WARNING_THRESHOLD
            and not daily_stats["warning_sent"]
        ):
            tomorrow = daily_stats["last_reset"] + timedelta(days=1)
            await context.bot.send_message(
                chat_id=chat_id,
                text=(
                    f"⚠️ Heads up! We've used {daily_stats['requests']}/{DAILY_LIMIT} "
                    f"requests today. Resets at {tomorrow} 00:00 UTC."
                ),
            )
            daily_stats["warning_sent"] = True
            logger.info("Daily warning threshold reached: %d", daily_stats["requests"])

        if daily_stats["requests"] >= DAILY_LIMIT:
            daily_stats["limit_reached"] = True
            tomorrow = daily_stats["last_reset"] + timedelta(days=1)
            await context.bot.send_message(
                chat_id=chat_id,
                text=(
                    f"🛑 Daily limit of {DAILY_LIMIT} requests reached. "
                    f"I'll be back at {tomorrow} 00:00 UTC!"
                ),
            )
            logger.info("Daily limit reached: %d", daily_stats["requests"])

    except Exception as e:
        logger.error("Error handling mention: %s", e, exc_info=True)
        daily_stats["errors"] += 1

        # Try to clean up searching message
        if searching_msg:
            try:
                await searching_msg.delete()
            except Exception:
                pass

        await message.reply_text(f"Error: {e}. Please try again.")


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

    # Initialise Gemini client
    gemini_client = genai.Client(api_key=GEMINI_API_KEY)
    logger.info("Gemini client initialised (model: %s)", GEMINI_MODEL)

    # Build Telegram application
    application = Application.builder().token(TELEGRAM_BOT_TOKEN).build()

    # Debug handler — logs ALL incoming messages (remove after debugging)
    async def debug_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        msg = update.message or update.edited_message or update.channel_post
        if msg:
            logger.info(
                "DEBUG — chat_type=%s, chat_id=%s, text=%r",
                msg.chat.type, msg.chat.id, msg.text,
            )

    # Register handlers (commands first, then message handler)
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("usage", usage_command))
    application.add_handler(
        MessageHandler(
            filters.ChatType.GROUPS & filters.TEXT & ~filters.COMMAND,
            handle_mention,
        )
    )
    # Catch-all debug handler (group=1 so it runs alongside other handlers)
    application.add_handler(
        MessageHandler(filters.ALL, debug_handler), group=1
    )

    logger.info("Bot started. Listening for mentions as %s", BOT_USERNAME)
    application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
