# Deploying askGem to Render (Free Tier)

A complete guide to deploy askGem to Render's free **Web Service** tier in **webhook mode**.

## How it runs

askGem runs as a Render **Web Service**. When `WEBHOOK_URL` is set it starts in
webhook mode: Telegram delivers each update as an HTTPS POST to the service, so
there is no `getUpdates` polling loop (and no 409 conflicts on overlapping
deploys). With `WEBHOOK_URL` unset the same code falls back to long polling,
which is what you use for local development.

- **Free Tier Benefits**:
  - No credit card required
  - Auto-restart on failure
  - Managed TLS on `*.onrender.com`
  - Easy environment variable management
  - Git integration for auto-deployments

- **Limitations**:
  - The service spins down after **15 minutes** with no inbound traffic
  - The first mention after spin-down triggers a **~1 minute** cold start;
    Telegram retries the webhook during the wake-up, so the message is still
    delivered, just delayed
  - 750 free instance hours per month per workspace

- **Requirements**:
  - GitHub account (for git integration)
  - Render account (free at https://render.com)
  - Telegram bot token (from @BotFather)
  - Google Gemini API key (from https://aistudio.google.com/)
  - Your numeric Telegram user ID (from [@userinfobot](https://t.me/userinfobot))

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
- `.python-version` — Python version pin (Render reads this; `3.13` = latest 3.13.x)
- `.env.example` — template for environment variables
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
GEMINI_API_KEY     = your_actual_api_key_here
OWNER_ID           = your_numeric_telegram_user_id
WEBHOOK_URL        = https://<your-service>.onrender.com
WEBHOOK_SECRET     = <output of: openssl rand -hex 32>
```

**How to get these:**

- **TELEGRAM_BOT_TOKEN**: Message [@BotFather](https://t.me/botfather) → `/newbot` → copy token
- **GEMINI_API_KEY**: Go to [Google AI Studio](https://aistudio.google.com/) → Create API key
- **OWNER_ID**: Message [@userinfobot](https://t.me/userinfobot); it replies with your numeric ID
- **WEBHOOK_URL**: your service's own URL, shown at the top of the Render service page
  (e.g. `https://askgem.onrender.com`) — no trailing slash. You can add it right
  after the first deploy and save; Render redeploys automatically.
- **WEBHOOK_SECRET**: any random token matching `[A-Za-z0-9_-]{1,256}`. It is used
  both as the secret webhook path and the `X-Telegram-Bot-Api-Secret-Token` header.

Do **not** set `PORT` — Render injects it and the bot reads it automatically.

Leave **Health Check Path** empty. In webhook mode the bot only answers the
secret webhook path; a health check against `/` returns 404 and Render would mark
the deploy unhealthy and restart it in a loop. (Render still detects the open
port, which is all it needs to consider the service live.)

## Step 3: Deploy

### 3.1 Create the service

1. Click **Create Web Service**
2. Render will start building and deploying
3. You'll see logs in real-time
4. Wait for status to show **Live** (usually 2-3 minutes)

### 3.2 Verify deployment

The logs should show:
```
✅ Access control: owner-only. OWNER_ID=123456789
Gemini client initialised (models: ...)
Bot username detected: @your_bot_name
Bot started in webhook mode on port 10000
```

If you see `OWNER_ID is missing`, set the `OWNER_ID` environment variable and redeploy.

## Step 4: Add the Bot to Your Groups

No per-group configuration is needed. The bot checks who added it: if that
account is not `OWNER_ID`, it leaves the group immediately.

1. Open Telegram
2. Add your bot to any group **you** are in (e.g., `@your_bot_name`)
3. Mention it: `@your_bot_name What's the weather today?`

The bot should respond with a search-grounded answer. 🎉

If you add it to a group and it leaves right away, check the logs for
`Leaving unauthorized group …` — it means the `from_user` id of whoever added
it did not match `OWNER_ID`.

## Step 5: Maintenance

### Viewing Logs

1. Go to Render dashboard
2. Click your service
3. Click **Logs** tab
4. Filter by date/time if needed

### Common Log Messages

| Message | Meaning |
|---------|---------|
| `Bot started in webhook mode on port …` | ✅ Bot started successfully |
| `Bot username detected: @your_bot_name` | ✅ Username auto-detected |
| `Calling model: gemini-2.5-flash-lite` | ✅ Processing a query |
| `Joined authorized chat <ID>` | ℹ️ You added the bot to a group |
| `Leaving unauthorized group <ID>` | ⚠️ Someone else added the bot; it left |

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
1. Is the bot still in the group, or did it auto-leave? (logs: `Leaving unauthorized group …`)
2. Was the bot added by the `OWNER_ID` account?
3. Did you mention the bot with its actual username?
4. First message after 15 min idle: allow ~1 minute for the cold start
5. Check recent logs for errors

### Webhook not receiving updates

- `WEBHOOK_URL` must be the exact public HTTPS URL of the service, no trailing slash
- `WEBHOOK_SECRET` must match `[A-Za-z0-9_-]{1,256}`
- Look for `Bot started in webhook mode` in the logs; if you see `polling mode`
  instead, `WEBHOOK_URL` is not set on the service

### API rate limits hit

**Solution**: Use `/model` command to switch to a less-used Gemini model

### Bot keeps restarting

**Check logs for errors**. Common issues:
- Invalid API keys or missing `OWNER_ID` (check Environment variables)
- Missing `requirements.txt` file
- Syntax errors in `main.py`

## Advanced: Custom Domain

To add a custom domain (optional):

1. Go to Render service
2. Click **Settings** tab
3. Scroll to **Custom Domain**
4. Add your domain (e.g., `askgem.yourdomain.com`)
5. Follow DNS setup instructions

**Note**: A custom domain is optional. If you use one, set `WEBHOOK_URL` to that
domain so Telegram delivers updates there.

## Cost

**Free Tier is completely free:**
- ✅ 750 free instance hours/month per workspace
- ✅ Service spins down after 15 minutes without inbound traffic
- ✅ No credit card required (unless you upgrade)
- ✅ Auto-redeploy on git push
- ✅ Managed TLS certificate included

**Uptime Notes:**
- **Free tier**: the first mention after a 15-minute idle wakes the service with
  a ~1 minute cold start; Telegram retries the webhook so the message still lands.
  Fine for casual group use.
- **Paid tier**: an always-on instance (no spin-down) if you need instant replies
  around the clock.

**You pay for:**
- Telegram API (free)
- Google Gemini API (free tier: 60 RPM for flash-lite)

## Next Steps

1. ✅ Deploy to Render with `OWNER_ID`, `WEBHOOK_URL`, `WEBHOOK_SECRET`
2. ✅ Add the bot to your own groups (it auto-leaves any it wasn't added to by you)
3. ✅ Test with a mention and `/marketsummary`

## Support

- **Render Docs**: https://render.com/docs
- **Bot Stuck?**: Check logs first, then check `.env` variables
- **Telegram Bot API**: https://core.telegram.org/bots
- **Google Gemini API**: https://ai.google.dev/

Happy botting! 🤖
