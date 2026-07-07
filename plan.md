# Anti-Forward-Tag Telegram Bot — Production Plan (Multi-Tenant)

## 1. What it does
Public bot. Any user adds it as **admin** to their channel (with delete + post permissions). When someone forwards a post into that channel, the bot deletes the original and reposts the same content instantly — no "Forwarded from X" header. Works across unlimited channels simultaneously.

---

## 2. Auth clarification (important)
- **No `api_id` / `api_hash` needed.** Those are only for Telegram *user/client* libraries (Telethon, Pyrogram user-mode — logging in as a real account).
- aiogram is a **Bot API** wrapper — only needs a **Bot Token** from **@BotFather**:
  1. DM @BotFather → `/newbot` → set name + username
  2. Copy token (`123456789:AAF...`)
  3. Put in `.env` as `BOT_TOKEN`
- That's the only credential required.

---

## 3. Tech Stack

| Component | Choice | Version |
|---|---|---|
| Language | Python | 3.12+ |
| Bot framework | aiogram | 3.29.1 |
| DB | PostgreSQL (production-grade, multi-tenant needs real concurrency) | 16 |
| ORM | SQLAlchemy (async) + `asyncpg` driver | 2.x |
| Migrations | Alembic | latest |
| Cache/Buffer (media groups, rate limit) | Redis | 7.x |
| Task scheduling (debounce albums) | `asyncio` + Redis TTL keys | — |
| Config | `pydantic-settings` + `.env` | 2.x |
| Logging | `loguru` (structured, rotated file logs) | latest |
| Process manager | `systemd` (or Docker Compose) | — |
| Containerization | Docker + Docker Compose (bot + postgres + redis) | — |
| Monitoring | systemd/journalctl logs (v1), optional Sentry later | — |

No deprecated libs — aiogram 2.x, raw `sqlite3`, or sync drivers avoided; everything async end-to-end.

---

## 4. Why Postgres + Redis instead of SQLite (v1 sqlite plan upgraded)
Since this is public/multi-tenant and production-grade:
- Multiple channels writing/reading settings concurrently → SQLite locks under load, Postgres doesn't
- Redis handles: media-group buffering (short-lived keys), per-channel flood/rate-limiting, and can later cache channel settings to reduce DB hits

---

## 5. Features

### Core (all tenants)
- Auto-onboarding: bot detects it was added as admin via `my_chat_member` → auto-registers channel in DB, no manual setup
- Detects forwarded posts (`forward_origin`) in any registered channel
- Deletes original, reposts clean copy via `copy_message`
- Handles text, photo, video, document, audio, voice, sticker, gif, and media groups (albums) via Redis-buffered reassembly
- Leaves non-forwarded (original) posts untouched
- Permission self-check: if bot lacks delete rights, DMs the admin who added it with a warning + instructions to fix
- Per-channel on/off toggle (owner can pause the bot without removing it)
- Flood-safe: per-channel queue + rate limiting to respect Telegram's ~20 msgs/min per channel limit

### Bot commands (DM only)
- `/start` — intro + how to add to a channel
- `/help` — usage instructions
- `/mychannels` — list channels this user has added the bot to, with status (active/paused/missing permissions)
- `/pause <channel>` / `/resume <channel>`
- `/stats` — (owner-only, i.e. you) global usage stats: total channels, messages processed

### Production hardening
- Graceful error handling per-update (one bad message never crashes the dispatcher)
- Structured logging with rotation (`loguru`, daily rotation, 14-day retention)
- Retry logic with exponential backoff for Telegram API rate-limit (`429`) responses
- Health check: simple `/health` internal script or systemd watchdog
- Dockerized so it's portable off Webdock if you ever migrate

---

## 6. Architecture Flow

```
Any Telegram Channel (bot added as admin)
         │
         ▼
my_chat_member update ──► auto-register channel in DB (owner_id, channel_id, permissions)
         │
channel_post update
         │
   has forward_origin? ── No ──► ignore
         │
        Yes
         │
   part of media_group_id?
     │            │
    Yes           No
     │             ▼
Buffer in Redis   copy_message() directly
(TTL debounce ~1.5s)      │
     │                    │
combine parts             │
     ▼                    │
send_media_group() ◄──────┘
     ▼
delete_message() on all originals
     ▼
log event (channel_id, msg_type, success/fail)
```

---

## 7. Production Folder Structure

```
forward-remover-bot/
├── app/
│   ├── __init__.py
│   ├── main.py                     # entrypoint: bot + dispatcher bootstrap
│   ├── config.py                   # pydantic-settings, loads .env
│   ├── bot_instance.py             # Bot/Dispatcher singletons, middlewares registered
│   │
│   ├── handlers/
│   │   ├── __init__.py
│   │   ├── commands.py             # /start /help /mychannels /pause /resume /stats
│   │   ├── chat_member.py          # my_chat_member → auto onboarding
│   │   └── channel_posts.py        # core forward-detection + repost logic
│   │
│   ├── services/
│   │   ├── __init__.py
│   │   ├── forward_service.py      # decides copy vs album flow
│   │   ├── media_buffer.py         # Redis-based album buffering
│   │   ├── permissions.py          # checks bot's admin rights in a channel
│   │   └── rate_limiter.py         # per-channel flood control
│   │
│   ├── db/
│   │   ├── __init__.py
│   │   ├── base.py                 # SQLAlchemy async engine/session
│   │   ├── models.py                # Channel, ChannelSettings, EventLog tables
│   │   └── crud.py                  # DB access functions
│   │
│   ├── middlewares/
│   │   ├── __init__.py
│   │   ├── error_handler.py         # catches/logs per-update exceptions
│   │   └── logging_middleware.py    # structured request logging
│   │
│   └── utils/
│       ├── __init__.py
│       └── retry.py                 # backoff wrapper for Telegram 429s
│
├── alembic/                          # DB migrations
│   ├── versions/
│   └── env.py
├── tests/
│   ├── test_forward_detection.py
│   └── test_media_buffer.py
│
├── docker-compose.yml                # bot + postgres + redis
├── Dockerfile
├── requirements.txt
├── alembic.ini
├── .env.example
├── forward_bot.service                # systemd unit (non-Docker deploy option)
└── README.md
```

---

## 8. Database Schema (v1)

**channels**
| column | type |
|---|---|
| id | PK |
| channel_id | bigint, unique |
| owner_user_id | bigint |
| title | text |
| status | enum(active, paused, permission_error) |
| created_at | timestamp |

**event_logs** (for `/stats` + debugging)
| column | type |
|---|---|
| id | PK |
| channel_id | FK |
| message_type | text |
| success | bool |
| created_at | timestamp |

---

## 9. requirements.txt (all current, no legacy)
```
aiogram==3.29.1
pydantic-settings==2.6.1
SQLAlchemy==2.0.36
asyncpg==0.30.0
alembic==1.14.0
redis==5.2.0
loguru==0.7.2
tenacity==9.0.0
```

---

## 10. Hosting / Deployment (Webdock VPS, Docker-based)

**docker-compose.yml services:**
- `bot` — Python app container
- `postgres` — DB
- `redis` — buffering/cache

**Steps:**
1. `git clone` repo to VPS
2. Fill `.env` (`BOT_TOKEN`, `DATABASE_URL`, `REDIS_URL`)
3. `docker compose up -d --build`
4. `docker compose logs -f bot` to monitor
5. Alembic migrations run automatically on container start (or via `docker compose exec bot alembic upgrade head`)

**Why Docker over raw systemd here:** production-grade, multi-service (bot+db+redis), easy to redeploy/rollback, isolates Python env from your VPS's other projects.

Fallback: if you'd rather skip Docker, `forward_bot.service` (systemd) is included for running the bot process directly, but Postgres/Redis would then need to be installed natively on the VPS.

---

## 11. Edge Cases Handled
- Non-forwarded posts → untouched
- Bot lacks delete permission → channel marked `permission_error`, owner DMed once with fix instructions
- Media groups → Redis-buffered, reassembled as one album post
- Telegram flood limits → rate-limiter queues sends per channel, retries with backoff on `429`
- Bot restarted mid-album-buffer → incomplete buffer expires via Redis TTL (rare, acceptable loss)
- Owner removes bot from channel → `my_chat_member` update sets channel status to `removed`, stops processing

---

## 12. Build Order (once you confirm)
1. Project scaffold + Docker + config
2. DB models + Alembic migration
3. `my_chat_member` auto-onboarding handler
4. Core forward-detection + copy/delete logic (text + single media first)
5. Media group (album) buffering via Redis
6. Commands (`/start /help /mychannels /pause /resume /stats`)
7. Rate limiting + retry/backoff
8. Logging + error middleware
9. Test on a real test channel
10. Deploy to Webdock VPS via Docker Compose

---

## Next Step
Confirm this structure looks good and I'll start scaffolding the actual code (Step 1: project setup + Docker + config).
