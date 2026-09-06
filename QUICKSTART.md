# askGem - Quick Start (5 minutes)

Get askGem running in 5 minutes. Choose your path:

## Option A: Deploy to Render (Recommended for Continuous Deployment)

**Total time: 10 minutes**

**Note:** On Render's free tier the service spins down after 15 minutes without traffic. In webhook mode the next mention wakes it, with a ~1 minute cold start on that first message. For instant replies around the clock, use a paid always-on instance.

### 1. Get tokens (2 minutes)

**Telegram Bot Token:**
- Open Telegram → Message [@BotFather](https://t.me/botfather)
- Send: `/newbot`
- Follow prompts, copy token
- Important: Send `/mybots` → select your bot → Bot Settings → Group Privacy → **Turn OFF**

**Google Gemini API Key:**
- Go to https://aistudio.google.com/
- Click **Create API Key**
- Copy the key

**Your Telegram user ID:**
- Message [@userinfobot](https://t.me/userinfobot); it replies with your numeric ID

### 2. Deploy to Render (5 minutes)

1. Go to https://render.com, sign in with GitHub
2. Click **New** → **Web Service**
3. Connect your `askgem` repository
4. Set:
   - **Build Command**: `pip install -r requirements.txt`
   - **Start Command**: `python main.py`
   - **Environment**: Add variables:
     - `TELEGRAM_BOT_TOKEN` = your token
     - `GEMINI_API_KEY` = your key
     - `OWNER_ID` = your numeric Telegram user ID
     - `WEBHOOK_URL` = `https://<your-service>.onrender.com` (add after the URL is assigned)
     - `WEBHOOK_SECRET` = output of `openssl rand -hex 32`
5. Click **Create Web Service**
6. Wait 2-3 minutes for "Live" status; if you added `WEBHOOK_URL` after the first
   deploy, save it and let Render redeploy

### 3. Test it (2 minutes)

1. Open Telegram
2. Add your bot to a group **you** are in
3. Try: `@your_bot_name what's the weather?` ✅

(If the bot leaves the group immediately, whoever added it wasn't the `OWNER_ID` account — check the logs.)

**✅ Done!**

---

## Option B: Run Locally (For Development)

**Total time: 5 minutes**

### 1. Clone & Setup (2 minutes)

```bash
git clone https://github.com/winthrop1/askgem.git
cd askgem
python3 -m venv venv
source venv/bin/activate  # or: venv\Scripts\activate (Windows)
pip install -r requirements.txt
```

### 2. Configure (1 minute)

```bash
cp .env.example .env
```

Edit `.env`:
```
TELEGRAM_BOT_TOKEN=your_bot_token
GEMINI_API_KEY=your_gemini_key
OWNER_ID=your_numeric_telegram_user_id
```

Leave `WEBHOOK_URL` unset locally — the bot then runs in long-polling mode.
Get tokens from [Option A](#option-a-deploy-to-render-recommended-for-continuous-deployment) above.

### 3. Run (1 minute)

```bash
python main.py
```

You should see:
```
Bot username detected: @your_bot_name
Bot started in polling mode (WEBHOOK_URL not set)
```

### 4. Test (1 minute)

Add the bot to a group you are in, then:
```
@your_bot_name what's happening in AI today?
```

**Note**: Bot stops when you close the terminal. Use Option A (Render) for hosting.

---

## Next Steps

- 📖 **Usage Guide**: See [README.md](./README.md)
- 🚀 **Full Render Guide**: See [RENDER_DEPLOYMENT.md](./RENDER_DEPLOYMENT.md)
- 💻 **For Developers**: See [CONTRIBUTING.md](./CONTRIBUTING.md)
- 🏗️ **Architecture**: See [ARCHITECTURE.md](./ARCHITECTURE.md)

---

## Troubleshooting

### Bot doesn't respond

1. **Did it auto-leave the group?** It leaves any group not added by the `OWNER_ID` account. Check logs for `Leaving unauthorized group`.
2. **Did you mention correctly?** Try: `@your_bot_name hello`
3. **On Render:** the first mention after 15 min idle takes ~1 minute to wake.
4. **Check logs for errors** — especially API key issues

### API Key errors

- **Telegram**: Copy exact token from @BotFather, no spaces
- **Gemini**: Copy exact key from aistudio.google.com, test in their sandbox first

### Bot keeps crashing

1. Check Render/console logs for errors
2. Verify both API keys in `.env`
3. Verify your bot has Group Privacy **OFF** in BotFather

---

## Common Issues

| Issue | Solution |
|-------|----------|
| Bot leaves the group immediately | Whoever added it wasn't the `OWNER_ID` account |
| `OWNER_ID is missing` | Set `OWNER_ID` env var to your numeric Telegram user ID |
| "Invalid token" | Copy token exactly from BotFather (no spaces) |
| "API error" | Check Gemini free tier limit (60 RPM flash-lite) — use `/model` to switch |
| Logs say `polling mode` on Render | Set `WEBHOOK_URL` on the service |

---

## Features You Have

✅ Real-time web search with Gemini
✅ Conversation memory (last 5 messages)
✅ 3 Gemini models (switch with `/model`)
✅ Owner-only (auto-leaves groups you didn't add it to)
✅ Free hosting on Render (webhook mode)

---

**You're all set!** 🎉

Questions? Read the relevant `.md` file above.
