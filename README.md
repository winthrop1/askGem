# askGem - AI-Powered Telegram Group Assistant

A friendly AI-powered Telegram bot that answers questions in group chats using Google Gemini with real-time web search grounding. Mention your bot in any group chat and get search-backed answers. It also produces an on-demand market summary covering global indices, crypto prices, top business headlines, and AI-generated commentary.

**Status**: Ready for deployment ✅

**Quick Links:**
- ⚡ [Quick Start (5 min)](./QUICKSTART.md) — Get running in minutes
- 🚀 [Deploy to Render (Free Tier)](./RENDER_DEPLOYMENT.md) — Production setup
- 📖 [Local Setup](#local-setup) — Development mode

## Features

- **Google Search grounding** — answers are backed by real-time web search
- **Conversation memory** — remembers the last 5 messages for context
- **Multi-model support** — cycle between 3 Gemini models with `/model`
- **On-demand market summary** — global indices, crypto, top headlines, AI commentary via `/marketsummary`
- **Owner-only** — the bot auto-leaves any group it was not added to by you
- **Group-only** — responds to @mentions in groups, ignores DMs

## Security Model

**Owner-only:** set `OWNER_ID` to your numeric Telegram user ID (get it from [@userinfobot](https://t.me/userinfobot)). Whenever the bot is added to a group, it checks who added it — if that isn't you, it **leaves immediately**. There is no per-group config and no redeploy needed to authorize a group: just add the bot to your own groups.

Notes:
- The check fires on the "added to group" event. If a stranger added the bot under an older build, remove it from that group manually once (Telegram gives bots no way to list their own chats).
- To let a trusted friend add the bot too, the code accepts a single `OWNER_ID`; extend `should_leave_chat` if you need multiple owners.

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

**Optional — Market Summary API keys:**
- **CoinGecko API key** (free at [coingecko.com/api](https://www.coingecko.com/en/api)) — improves crypto rate limits; works without a key
- **Newsdata.io API key** (free at [newsdata.io](https://newsdata.io/)) — required for business headlines section

### 5. Configure environment

```bash
cp .env.example .env
```

Edit `.env` with your keys:

```
TELEGRAM_BOT_TOKEN=your_actual_token
GEMINI_API_KEY=your_actual_key
OWNER_ID=your_numeric_telegram_user_id

# Optional — market summary
COINGECKO_API_KEY=
NEWSDATA_API_KEY=
```

Get your `OWNER_ID` by messaging [@userinfobot](https://t.me/userinfobot). Leave `WEBHOOK_URL` / `WEBHOOK_SECRET` unset for local use — the bot runs in long-polling mode when `WEBHOOK_URL` is empty.

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

| Command          | Description                                        |
|------------------|----------------------------------------------------|
| `/start`         | Welcome message and usage guide                    |
| `/status`        | Show current model                                 |
| `/model`         | Cycle to the next Gemini model (affects @mentions) |
| `/marketsummary` | On-demand market summary (indices, crypto, news)   |

## Deploy to Render (Free Tier)

askGem runs on Render's free **Web Service** tier (no credit card required) in **webhook mode**.

**Quick Start:**
1. Push your code to GitHub (this repo)
2. Go to [render.com](https://render.com) and sign in with GitHub
3. Click **New** > **Web Service**, connect your repo
4. Set environment variables: `TELEGRAM_BOT_TOKEN`, `GEMINI_API_KEY`, `OWNER_ID`, `WEBHOOK_URL` (the service's own `https://…onrender.com` URL), `WEBHOOK_SECRET` (`openssl rand -hex 32`)
5. Deploy, then add the bot to your groups

**Full Deployment Guide:**
See [RENDER_DEPLOYMENT.md](./RENDER_DEPLOYMENT.md) for complete step-by-step instructions, troubleshooting, and maintenance tips.

**Free-tier behaviour:** the service spins down after 15 minutes with no inbound traffic. The next mention's Telegram webhook POST wakes it, with a ~1 minute cold start on that first message (Telegram retries during the wake-up, so it is delivered). Webhook mode also avoids the `getUpdates` 409 conflicts that polling hit on overlapping deploys.

## Project Structure

```
askgem/
├── main.py             # Main application
├── requirements.txt    # Dependencies
├── .python-version     # Python version (Render + pyenv)
├── .env                # API keys (gitignored)
├── .env.example        # Template for .env
├── tests/              # Unit tests (pytest)
├── .gitignore          # Git ignore rules
└── README.md           # This file
```

## Tech Stack

- [python-telegram-bot](https://github.com/python-telegram-bot/python-telegram-bot) v21 — async Telegram Bot API (webhook mode via the `[webhooks]` extra)
- [Google GenAI SDK](https://github.com/googleapis/python-genai) — Gemini models with search grounding
- [yfinance](https://github.com/ranaroussi/yfinance) — global index data via Yahoo Finance
- [python-dotenv](https://github.com/theskumar/python-dotenv) — environment variable management
