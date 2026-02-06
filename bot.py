"""
gonk - A Telegram AI bot powered by Google Gemini 1.5 Flash.
Responds to @mentions in group chats with search-grounded answers.
"""

import os
import re
import logging
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
GEMINI_MODELS = [
    "gemini-2.5-flash-lite",  # Fast, 1000 RPD free tier
    "gemini-2.5-flash",        # Balanced, 250 RPD free tier
    "gemini-2.5-pro",          # Best quality, 100 RPD free tier
]
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

# Current model index (cycles through GEMINI_MODELS)
current_model_index: int = 0

# Gemini client — initialised in main()
gemini_client: genai.Client | None = None

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------




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
    welcome = (
        "Hey there! I'm gonk, your friendly AI assistant.\n\n"
        "How to use me:\n"
        f"  Mention me in a group chat: {BOT_USERNAME} your question here\n\n"
        "I use Google Search to give you up-to-date info, and I remember "
        "the last few messages for context.\n\n"
        "Note: I only respond to mentions in groups, not DMs.\n\n"
        "Commands:\n"
        "  /start  - This welcome message\n"
        "  /usage  - Show current model\n"
        "  /model  - Switch to next model\n\n"
        "Let's chat!"
    )
    await update.message.reply_text(welcome)


async def usage_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle the /usage command — show current model."""
    model = GEMINI_MODELS[current_model_index]
    text = (
        "📊 Bot Status\n\n"
        f"Current model: {model}\n"
        f"Available models: {len(GEMINI_MODELS)}\n\n"
        "Use /model to cycle through models."
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

    logger.info("Bot mentioned! Processing...")

    chat_id = message.chat_id
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
    logger.info("Gemini client initialised (models: %s)", GEMINI_MODELS)

    # Build Telegram application
    application = Application.builder().token(TELEGRAM_BOT_TOKEN).build()

    # Register handlers (commands first, then message handler)
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("usage", usage_command))
    application.add_handler(CommandHandler("model", model_command))
    application.add_handler(
        MessageHandler(
            filters.ChatType.GROUPS & filters.TEXT & ~filters.COMMAND,
            handle_mention,
        )
    )

    logger.info("Bot started. Listening for mentions as %s", BOT_USERNAME)
    application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
