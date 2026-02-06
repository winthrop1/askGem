# gonk - Telegram AI Bot

A friendly Telegram bot powered by Google Gemini 1.5 Flash with Google Search grounding. Mention **@gonkted_bot** in any group chat and get search-backed answers.

## Features

- **Google Search grounding** — answers are backed by real-time web search
- **Conversation memory** — remembers the last 5 messages for context
- **Rate limit tracking** — monitors daily usage against Gemini's 1,500 request limit
- **Built-in analytics** — `/usage` command shows requests, error rate, and response times
- **Group-only** — responds to @mentions in groups, ignores DMs

## Local Setup

### 1. Clone the repo

```bash
git clone https://github.com/YOUR_USERNAME/telegram-ai-bot.git
cd telegram-ai-bot
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
```

### 6. Run the bot

```bash
python bot.py
```

## Usage

### In group chats

Add @gonkted_bot to your Telegram group, then mention it with a question:

```
@gonkted_bot what's happening in tech news today?
@gonkted_bot explain quantum computing
@gonkted_bot who won the match last night?
```

### Commands

| Command  | Description                          |
|----------|--------------------------------------|
| `/start` | Welcome message and usage guide      |
| `/usage` | Analytics: requests, errors, uptime  |

### Rate Limits

- **Daily limit:** 1,500 requests (Gemini free tier)
- **Warning:** Notification sent at 90% usage (1,350 requests)
- **Reset:** Daily at 00:00 UTC

## Deploy to Render.com

### 1. Push to GitHub

```bash
git remote add origin https://github.com/YOUR_USERNAME/telegram-ai-bot.git
git push -u origin main
```

### 2. Create a Web Service on Render

1. Go to [render.com](https://render.com) and sign in
2. Click **New** > **Web Service**
3. Connect your GitHub repo

### 3. Configure the service

| Setting         | Value                          |
|-----------------|--------------------------------|
| **Environment** | Python                         |
| **Build Command** | `pip install -r requirements.txt` |
| **Start Command** | `python bot.py`               |

### 4. Add environment variables

In the Render dashboard, add:

- `TELEGRAM_BOT_TOKEN` — your Telegram bot token
- `GEMINI_API_KEY` — your Google Gemini API key

### 5. Deploy

Click **Create Web Service**. Render will build and start the bot automatically.

## Project Structure

```
telegram-ai-bot/
├── bot.py              # Main application
├── requirements.txt    # Dependencies
├── .env                # API keys (gitignored)
├── .env.example        # Template for .env
├── .gitignore          # Git ignore rules
└── README.md           # This file
```

## Tech Stack

- [python-telegram-bot](https://github.com/python-telegram-bot/python-telegram-bot) v21 — async Telegram Bot API
- [Google GenAI SDK](https://github.com/googleapis/python-genai) — Gemini 1.5 Flash with search grounding
- [python-dotenv](https://github.com/theskumar/python-dotenv) — environment variable management
