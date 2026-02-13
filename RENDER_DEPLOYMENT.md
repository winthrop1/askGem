# Deploying askGem to Render (Free Tier)

A complete guide to deploy askGem to Render's free tier for 24/7 hosting.

## What You'll Get

- **Free Tier Benefits**:
  - Always-on bot (no spinning down)
  - Auto-restart on failure
  - Custom domain support
  - Easy environment variable management
  - Git integration for auto-deployments

- **Requirements**:
  - GitHub account (for git integration)
  - Render account (free at https://render.com)
  - Telegram bot token (from @BotFather)
  - Google Gemini API key (from https://aistudio.google.com/)

## Step 1: Prepare Your GitHub Repository

### 1.1 Make sure your code is pushed

```bash
# From your local project directory
git status  # Check everything is committed
git push origin main  # Push to GitHub
```

### 1.2 Verify required files exist

Your repository should have:
- `main.py` — bot application
- `requirements.txt` — Python dependencies
- `.env.example` — template for environment variables (gitignored)
- `README.md` — documentation

**Key**: Never commit `.env` (contains API keys). Render will set these via dashboard.

## Step 2: Create a Render Web Service

### 2.1 Sign up / Log in to Render

1. Go to https://render.com
2. Sign up with GitHub or email
3. Click **Dashboard** after login

### 2.2 Create a new Web Service

1. Click **New** → **Web Service**
2. Choose **Connect a repository**
3. Find and select your `askgem` repository
4. Click **Connect**

### 2.3 Configure the service

**Basic settings:**

| Field | Value |
|-------|-------|
| **Name** | `askgem` (or any name you prefer) |
| **Environment** | `Python 3` |
| **Region** | Pick closest to you (e.g., `Oregon`, `Frankfurt`) |
| **Branch** | `main` |

**Build & Start settings:**

| Field | Value |
|-------|-------|
| **Build Command** | `pip install -r requirements.txt` |
| **Start Command** | `python main.py` |

**Instance Type:**

- Select the **Free** tier
- This gives you a shared instance (plenty for a bot)

### 2.4 Add Environment Variables

Before clicking "Create Web Service", scroll down to **Environment Variables** section.

Add these variables (copy the exact keys):

```
TELEGRAM_BOT_TOKEN = your_actual_bot_token_here
GEMINI_API_KEY = your_actual_api_key_here
ALLOWED_CHAT_IDS = (leave empty for secure-by-default, or add chat IDs like: -1001234567890,-1009876543210)
PORT = 10000
```

**How to get these:**

- **TELEGRAM_BOT_TOKEN**: Message [@BotFather](https://t.me/botfather) → `/newbot` → copy token
- **GEMINI_API_KEY**: Go to [Google AI Studio](https://aistudio.google.com/) → Create API key
- **ALLOWED_CHAT_IDS**: Leave blank initially. After deploying, check logs for chat IDs

## Step 3: Deploy

### 3.1 Create the service

1. Click **Create Web Service**
2. Render will start building and deploying
3. You'll see logs in real-time
4. Wait for status to show **Live** (usually 2-3 minutes)

### 3.2 Verify deployment

The logs should show:
```
✅ Access control enabled. Allowed chats: (or empty - secure-by-default)
Gemini client initialised (models: ...)
Bot username detected: @your_bot_name
Bot started. Polling...
Health check server running on port 10000
```

**Important**: If you see `SECURITY WARNING: ALLOWED_CHAT_IDS is empty`, this is correct — it's secure-by-default. The bot will reject all groups until you add chat IDs.

## Step 4: Authorize Your Groups

### 4.1 Add bot to a group

1. Open Telegram
2. Create a test group or use an existing one
3. Add your bot to the group (e.g., `@your_bot_name`)
4. Mention the bot: `@your_bot_name test`

### 4.2 Check logs for chat ID

1. Go back to Render dashboard
2. Click your `askgem` service
3. Click **Logs** tab
4. Look for a message like:
   ```
   Chat -1001234567890 blocked: ALLOWED_CHAT_IDS is empty (secure-by-default).
   Add chat IDs to .env to enable bot access.
   ```
5. Copy the chat ID (e.g., `-1001234567890`)

### 4.3 Update ALLOWED_CHAT_IDS

1. Go to your Render service
2. Click **Environment** tab
3. Edit `ALLOWED_CHAT_IDS`
4. Add the chat ID: `-1001234567890` (or multiple: `-1001234567890,-1009876543210`)
5. Click **Save**

Render will auto-redeploy. Check logs to confirm the update took effect.

### 4.4 Test the bot

In your Telegram group:
```
@your_bot_name What's the weather today?
```

The bot should respond with a search-grounded answer! 🎉

## Step 5: Maintenance

### Viewing Logs

1. Go to Render dashboard
2. Click your service
3. Click **Logs** tab
4. Filter by date/time if needed

### Common Log Messages

| Message | Meaning |
|---------|---------|
| `Bot username detected: @your_bot_name` | ✅ Bot started successfully |
| `Calling model: gemini-2.5-flash-lite` | ✅ Processing a query |
| `Chat <ID> not in allowlist` | ⚠️ Someone mentioned bot in unauthorized group |
| `SECURITY WARNING: ALLOWED_CHAT_IDS is empty` | ℹ️ Normal (secure-by-default) |

### Auto-Restarts

Render automatically restarts your bot if it crashes. You'll see in logs:
```
Service restarted at 2026-02-13 14:30:00 UTC
```

### Updating Code

When you push changes to GitHub:
```bash
git commit -m "your message"
git push origin main
```

Render will detect the push and auto-deploy (you can disable auto-deploy in settings if needed).

## Troubleshooting

### Bot doesn't respond to mentions

**Check:**
1. Is chat ID in `ALLOWED_CHAT_IDS`? (Check logs)
2. Is bot added to the group?
3. Did you mention the bot with its actual username?
4. Check recent logs for errors

### API rate limits hit

**Solution**: Use `/model` command to switch to a less-used Gemini model

### Bot keeps restarting

**Check logs for errors**. Common issues:
- Invalid API keys (check Environment variables)
- Missing `requirements.txt` file
- Syntax errors in `main.py`

### Port 10000 already in use

The bot uses port 10000 for health checks. Render handles this automatically, so this shouldn't be an issue. If it appears in logs, contact Render support.

## Advanced: Custom Domain

To add a custom domain (optional):

1. Go to Render service
2. Click **Settings** tab
3. Scroll to **Custom Domain**
4. Add your domain (e.g., `askgem.yourdomain.com`)
5. Follow DNS setup instructions

**Note**: This is optional for the bot to work. The bot uses Telegram's servers for communication, not HTTP.

## Cost

**Free Tier is completely free:**
- ✅ 750 compute hours/month (bot runs 24/7 = ~730 hours)
- ✅ No credit card required (unless you upgrade)
- ✅ Auto-redeploy on git push
- ✅ SSL certificate included

**You pay for:**
- Telegram API (free)
- Google Gemini API (free tier: 60 RPM for flash-lite)

## Next Steps

1. ✅ Deploy to Render
2. ✅ Add your group chat IDs
3. ✅ Test the bot in your groups
4. ✅ Share the bot with friends (but remember: secure-by-default means you must authorize each group)

## Support

- **Render Docs**: https://render.com/docs
- **Bot Stuck?**: Check logs first, then check `.env` variables
- **Telegram Bot API**: https://core.telegram.org/bots
- **Google Gemini API**: https://ai.google.dev/

Happy botting! 🤖
