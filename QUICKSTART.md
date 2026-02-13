# askGem - Quick Start (5 minutes)

Get askGem running in 5 minutes. Choose your path:

## Option A: Deploy to Render (Recommended for Always-On Bot)

**Total time: 10 minutes**

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
     - `ALLOWED_CHAT_IDS` = (leave blank for now)
5. Click **Create Web Service**
6. Wait 2-3 minutes for "Live" status

### 3. Test it (3 minutes)

1. Open Telegram
2. Add your bot to a group
3. Mention it: `@your_bot_name test`
4. Check Render logs for chat ID (message like `Chat -1001234567890 blocked`)
5. Add chat ID to `ALLOWED_CHAT_IDS` in Render Environment Variables
6. Render auto-redeploys
7. Try: `@your_bot_name what's the weather?` ✅

**✅ Done!** Bot runs 24/7 on free tier.

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
ALLOWED_CHAT_IDS=
```

Get tokens from [Option A](#option-a-deploy-to-render-recommended-for-always-on-bot) above.

### 3. Run (1 minute)

```bash
python main.py
```

You should see:
```
Bot username detected: @your_bot_name
Bot started. Polling...
```

### 4. Test (1 minute)

In Telegram group:
```
@your_bot_name what's happening in AI today?
```

Check console logs for chat ID, add to `.env`, restart, and test again.

**Note**: Bot stops when you close the terminal. Use Option A (Render) for 24/7.

---

## Next Steps

- 📖 **Usage Guide**: See [README.md](./README.md)
- 🚀 **Full Render Guide**: See [RENDER_DEPLOYMENT.md](./RENDER_DEPLOYMENT.md)
- 💻 **For Developers**: See [CONTRIBUTING.md](./CONTRIBUTING.md)
- 🏗️ **Architecture**: See [ARCHITECTURE.md](./ARCHITECTURE.md)

---

## Troubleshooting

### Bot doesn't respond

1. **Is it in ALLOWED_CHAT_IDS?** If empty, bot blocks all groups. Add your chat ID.
2. **Did you mention correctly?** Try: `@your_bot_name hello`
3. **Check logs for errors** — especially API key issues

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
| "Chat blocked" message | Add chat ID to `ALLOWED_CHAT_IDS` |
| "Invalid token" | Copy token exactly from BotFather (no spaces) |
| "API error" | Check Gemini free tier limit (60 RPM flash-lite) — use `/model` to switch |
| Bot not in groups | Re-add bot to group after BotFather Group Privacy change |
| Port already in use | Change `PORT` in Render Environment Variables |

---

## Features You Have

✅ Real-time web search with Gemini
✅ Conversation memory (last 5 messages)
✅ 3 Gemini models (switch with `/model`)
✅ Secure by default (allowlist-based)
✅ Free hosting on Render

---

**You're all set!** 🎉

Questions? Read the relevant `.md` file above.
