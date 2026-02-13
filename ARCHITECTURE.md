# askGem - Architecture & Implementation

Technical documentation for developers wanting to understand or extend askGem.

## Overview

askGem is a single-file Telegram bot (`main.py`) that:
1. Listens for @mentions in Telegram group chats
2. Queries Google Gemini with search grounding
3. Maintains conversation context (last 5 messages)
4. Supports model cycling between 3 Gemini variants
5. Auto-detects bot username at startup (clone-friendly)

**Language**: Python 3.13
**Framework**: python-telegram-bot v21 (async)
**AI API**: Google Gemini (google-genai SDK)
**Deployment**: Render.com (polling mode)

## Key Design Decisions

### 1. Auto-Detected Bot Username (Clone-Friendly)

**Problem**: Original code hardcoded `BOT_USERNAME = "@gonkted_bot"`, breaking for clones.

**Solution**: Auto-detect at startup using `bot.get_me()`

```python
async def post_init(application: Application) -> None:
    """Auto-detect bot username at startup (clone-friendly)."""
    global BOT_USERNAME
    bot_info = await application.bot.get_me()
    BOT_USERNAME = f"@{bot_info.username}"
    logger.info("Bot username detected: %s", BOT_USERNAME)
```

**Why**: Users can clone, change their bot token in `.env`, and the bot works without code changes.

### 2. Secure-by-Default (Allowlist)

**Problem**: Bots can spam groups. Original approach was permissive.

**Solution**: Empty `ALLOWED_CHAT_IDS` means reject all groups.

```python
# Empty by default = secure
ALLOWED_CHAT_IDS: set[int] = {
    int(cid.strip()) for cid in _raw_ids.split(",") if cid.strip()
}

# In handler:
if not ALLOWED_CHAT_IDS:
    logger.warning("Chat %d blocked: ALLOWED_CHAT_IDS is empty (secure-by-default)", chat_id)
    return
```

**Why**: Users explicitly authorize groups. Prevents accidental spam.

### 3. Conversation History (In-Memory, Shared)

**Implementation**: `deque(maxlen=5)` stores last 5 messages globally.

```python
conversation_history: deque = deque(maxlen=5)

# Append on each response
conversation_history.append(f"User: {user_text}")
conversation_history.append(f"Assistant: {response_text}")
```

**Trade-off**:
- ✅ Simple, no database
- ⚠️ History shared across all groups (not per-group)
- ⚠️ Lost on restart

**Why**: v1 design — good enough for typical use.

### 4. Search Grounding via Google Gemini

**Implementation**: Pass `tools=[types.Tool(google_search=types.GoogleSearch())]`

```python
response = gemini_client.models.generate_content(
    model=model,
    contents=prompt,
    config=types.GenerateContentConfig(
        temperature=TEMPERATURE,
        max_output_tokens=MAX_OUTPUT_TOKENS,
        tools=[types.Tool(google_search=types.GoogleSearch())],
    ),
)
```

**Why**: Gemini internally decides when to search. No manual API calls needed.

### 5. Model Cycling (No Persistence)

**Implementation**: Global `current_model_index` cycles through list.

```python
GEMINI_MODELS = [
    "gemini-2.5-flash-lite",  # Fast, 1000 RPD free tier
    "gemini-2.5-flash",        # Balanced, 250 RPD free tier
    "gemini-2.5-pro",          # Best quality, 100 RPD free tier
]

# On /model command:
current_model_index = (current_model_index + 1) % len(GEMINI_MODELS)
```

**Why**: If one model hits rate limit, user can switch. State lost on restart is acceptable.

### 6. Polling Mode (Not Webhooks)

**Implementation**: `application.run_polling()`

**Why**:
- ✅ Works on free Render tier (no public HTTPS required)
- ✅ Simpler security (no need to verify Telegram signatures)
- ⚠️ Slightly higher latency (~1-2 sec)
- ⚠️ Higher bandwidth (constant polling)

For a small bot, polling is fine.

### 7. Health Check Server

**Implementation**: Separate HTTP server on port 10000.

```python
class HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"OK")

server = HTTPServer(("0.0.0.0", port), HealthHandler)
threading.Thread(target=server.serve_forever, daemon=True).start()
```

**Why**: Render uses HTTP health checks to verify bot is running and restart if needed.

## Code Flow

```
main()
  ├─ Load .env variables
  ├─ Validate TELEGRAM_BOT_TOKEN, GEMINI_API_KEY
  ├─ Init Gemini client
  ├─ Build Application
  ├─ Register post_init callback (auto-detect username)
  ├─ Register handlers:
  │  ├─ /start → start_command
  │  ├─ /status → status_command
  │  ├─ /model → model_command
  │  └─ (group messages) → handle_mention
  ├─ Start health check server
  └─ Run polling loop

handle_mention(update, context)
  ├─ Check if BOT_USERNAME in message
  ├─ Check if chat_id in ALLOWED_CHAT_IDS
  ├─ Extract user message (remove @mention)
  ├─ Send "🔍 Searching..." message
  ├─ Build prompt with conversation history
  ├─ Call query_gemini()
  ├─ Delete "Searching..." message
  ├─ Send response
  ├─ Update conversation_history
  └─ Catch exceptions & clean up
```

## File Structure

```
askgem/
├── main.py                  # Single-file bot implementation
├── requirements.txt         # Dependencies
├── .env.example             # Template for .env
├── .env                     # (gitignored) API keys
├── .gitignore               # Standard Python gitignore
├── README.md                # User documentation
├── RENDER_DEPLOYMENT.md     # Deployment guide
├── ARCHITECTURE.md          # This file
├── PROJECTS.md              # Project requirements (local)
└── STATE.md                 # Development state (local)
```

## Dependencies

**Python Packages:**

| Package | Version | Why |
|---------|---------|-----|
| `python-telegram-bot` | 21.0.1 | Telegram Bot API (async) |
| `google-genai` | >=1.0.0 | Google Gemini SDK (pinned in requirements) |
| `python-dotenv` | 1.0.1 | Environment variable loading |

**External APIs:**

| API | Free Tier | Quota |
|-----|-----------|-------|
| Telegram | Yes | Unlimited |
| Google Gemini | Yes | 60 RPM (flash-lite), 250 RPM (flash), 100 RPM (pro) |

## Extension Points

### Add a New Command

1. Create handler function:
```python
async def my_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text("Response")
```

2. Register in `main()`:
```python
application.add_handler(CommandHandler("mycommand", my_command))
```

### Add Per-Group Settings

Replace global `current_model_index` with per-chat storage:

```python
# Instead of:
current_model_index: int = 0

# Use:
chat_settings: dict = {}  # chat_id → settings

def get_model_for_chat(chat_id: int) -> str:
    if chat_id not in chat_settings:
        chat_settings[chat_id] = {"model_index": 0}
    return GEMINI_MODELS[chat_settings[chat_id]["model_index"]]
```

### Add Database Persistence

```python
import sqlite3

def save_to_db(chat_id, model_index):
    conn = sqlite3.connect("bot_state.db")
    conn.execute("INSERT INTO settings VALUES (?, ?)", (chat_id, model_index))
    conn.commit()
    conn.close()
```

## Performance Considerations

### Latency
- Response time: 2-5 seconds (including Gemini API + search)
- Render latency: +1-2 seconds (if geographically distant)

### Bandwidth
- Polling: ~1 request/second = ~86 MB/month (negligible)
- Per query: ~5-10 KB request, ~2-5 KB response

### Rate Limits
- Gemini free tier: 60 RPM (flash-lite) → ~5 people/minute
- If hit: User can `/model` to switch to less-used variant

### Cost on Free Tier
- Render: Free (750 compute hours/month covers 24/7)
- Telegram: Free
- Gemini: Free tier sufficient for small group

## Troubleshooting for Developers

### Bot not detecting username
**Check**: `post_init` is registered and `BOT_USERNAME` global is set
```python
application.post_init = post_init
```

### Group chat not responding
**Check**:
1. `BOT_USERNAME in message.text.lower()` — is mention working?
2. `chat_id in ALLOWED_CHAT_IDS` — is group authorized?
3. Both checks pass → query_gemini() called

### Search not working
**Check**: Gemini SDK returns raw response text. Search is automatic if available.

### Rate limit errors
**Check**: Gemini API returns 429. User should `/model` to switch variants.

## Future Improvements (Not Implemented)

1. **Database for persistence**: Per-chat settings, conversation history
2. **Webhook mode**: Lower latency, but requires public HTTPS
3. **Image handling**: Parse images from group chats
4. **Admin commands**: /ban, /reset_history, /set_model_default
5. **Metrics**: Track which models used, query counts

**Note**: These violate the "v1 only" principle. Add only if proven needed.

## License

MIT — See LICENSE file

---

**Questions?** Check README.md for usage, or RENDER_DEPLOYMENT.md for hosting.
