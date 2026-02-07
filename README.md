# gonk - Telegram AI Bot

A friendly Telegram bot powered by Google Gemini with Google Search grounding. Mention **@gonkted_bot** in any group chat and get search-backed answers.

## Features

- **Google Search grounding** — answers are backed by real-time web search
- **Conversation memory** — remembers the last 5 messages for context
- **Multi-model support** — cycle between 3 Gemini models with `/model`
- **Chat allowlist** — restrict bot to specific groups via `ALLOWED_CHAT_IDS`
- **Group-only** — responds to @mentions in groups, ignores DMs

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
git clone https://github.com/winthrop1/Telegram-AI-chatbot.git
cd Telegram-AI-chatbot
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

`ALLOWED_CHAT_IDS` is optional. Leave empty to allow all groups. To restrict, add comma-separated chat IDs (e.g., `-1001234567890,-1009876543210`). You can find your group's chat ID in the bot logs when it receives a mention.

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

| Command  | Description                            |
|----------|----------------------------------------|
| `/start`  | Welcome message and usage guide        |
| `/status` | Show current model                     |
| `/model`  | Cycle to the next Gemini model         |

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

| Setting           | Value                             |
|-------------------|-----------------------------------|
| **Environment**   | Python                            |
| **Build Command** | `pip install -r requirements.txt` |
| **Start Command** | `python bot.py`                   |

### 4. Add environment variables

In the Render dashboard, add:

- `TELEGRAM_BOT_TOKEN` — your Telegram bot token
- `GEMINI_API_KEY` — your Google Gemini API key
- `ALLOWED_CHAT_IDS` — (optional) comma-separated group chat IDs

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
- [Google GenAI SDK](https://github.com/googleapis/python-genai) — Gemini models with search grounding
- [python-dotenv](https://github.com/theskumar/python-dotenv) — environment variable management
