# askGem - AI-Powered Telegram Group Assistant

A friendly AI-powered Telegram bot that answers questions in group chats using Google Gemini with real-time web search grounding. Mention your bot in any group chat and get search-backed answers.

## Features

- **Google Search grounding** — answers are backed by real-time web search
- **Conversation memory** — remembers the last 5 messages for context
- **Multi-model support** — cycle between 3 Gemini models with `/model`
- **Chat allowlist** — restrict bot to specific groups via `ALLOWED_CHAT_IDS`
- **Group-only** — responds to @mentions in groups, ignores DMs

## Security Model

**Secure-by-default:** The bot rejects all groups unless explicitly authorized via `ALLOWED_CHAT_IDS` in `.env`. This is a private-use bot designed for specific groups only.

To authorize a group:
1. Add the bot to your Telegram group
2. Mention the bot (it will be rejected with a logged chat ID)
3. Add the chat ID to `.env`:
   ```
   ALLOWED_CHAT_IDS=-1001234567890,-1009876543210
   ```
4. Restart the bot

## Available Models

| Model | Speed | Free Tier Limit |
|-------|-------|-----------------|
| gemini-2.5-flash-lite (default) | Fastest | 1,000 RPD |
| gemini-2.5-flash | Balanced | 250 RPD |
| gemini-2.5-pro | Best quality | 100 RPD |

Use `/model` to cycle between them. If one model hits its rate limit, switch to another.

## Local Setup

### 1. Clone the repo

```bash
git clone https://github.com/winthrop1/askgem.git
cd askgem
```

### 2. Create a virtual environment

```bash
python3 -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
```

### 3. Install dependencies

```bash
pip install -r requirements.txt
```

### 4. Get your API keys

**Telegram Bot Token:**
1. Message [@BotFather](https://t.me/botfather) on Telegram
2. Send `/newbot` and follow the prompts
3. Copy the token
4. **Important:** Send `/mybots` > select your bot > Bot Settings > Group Privacy > Turn off

**Google Gemini API Key:**
1. Go to [Google AI Studio](https://aistudio.google.com/)
2. Create an API key
3. Copy the key

### 5. Configure environment

```bash
cp .env.example .env
```

Edit `.env` and replace the placeholder values with your actual keys:

```
TELEGRAM_BOT_TOKEN=your_actual_token
GEMINI_API_KEY=your_actual_key
ALLOWED_CHAT_IDS=
```

`ALLOWED_CHAT_IDS` controls which groups can use the bot (secure-by-default):
- **Empty (default):** Bot REJECTS all groups (recommended for private use)
- **With chat IDs:** Only allows specified groups (e.g., `-1001234567890,-1009876543210`)

To find your group's chat ID: Add the bot to a group, mention it, and check the logs for "Chat <ID> blocked" message.

### 6. Run the bot

```bash
python main.py
```

## Usage

### In group chats

Add the bot to your Telegram group, then mention it with a question:

```
@your_bot_name what's happening in tech news today?
@your_bot_name explain quantum computing
@your_bot_name who won the match last night?
```

(Replace `@your_bot_name` with your actual bot username from BotFather)

### Commands

| Command  | Description                            |
|----------|----------------------------------------|
| `/start`  | Welcome message and usage guide        |
| `/status` | Show current model                     |
| `/model`  | Cycle to the next Gemini model         |

## Deploy to Render.com

### 1. Push to GitHub

```bash
git remote add origin https://github.com/YOUR_USERNAME/askgem.git
git push -u origin main
```

### 2. Create a Web Service on Render

1. Go to [render.com](https://render.com) and sign in
2. Click **New** > **Web Service**
3. Connect your GitHub repo

### 3. Configure the service

| Setting           | Value                             |
|-------------------|-----------------------------------|
| **Environment**   | Python                            |
| **Build Command** | `pip install -r requirements.txt` |
| **Start Command** | `python main.py`                   |

### 4. Add environment variables

In the Render dashboard, add:

- `TELEGRAM_BOT_TOKEN` — your Telegram bot token
- `GEMINI_API_KEY` — your Google Gemini API key
- `ALLOWED_CHAT_IDS` — (optional) comma-separated group chat IDs

### 5. Deploy

Click **Create Web Service**. Render will build and start the bot automatically.

## Project Structure

```
askgem/
├── main.py             # Main application
├── requirements.txt    # Dependencies
├── .env                # API keys (gitignored)
├── .env.example        # Template for .env
├── .gitignore          # Git ignore rules
└── README.md           # This file
```

## Tech Stack

- [python-telegram-bot](https://github.com/python-telegram-bot/python-telegram-bot) v21 — async Telegram Bot API
- [Google GenAI SDK](https://github.com/googleapis/python-genai) — Gemini models with search grounding
- [python-dotenv](https://github.com/theskumar/python-dotenv) — environment variable management
