# ✨ Anti-Forward-Tag Telegram Bot ✨

<p align="center">
  <img src="https://img.shields.io/badge/Python-3.12+-blue?style=for-the-badge&logo=python&logoColor=white" alt="Python Version" />
  <img src="https://img.shields.io/badge/aiogram-3.x-teal?style=for-the-badge&logo=telegram&logoColor=white" alt="aiogram Version" />
  <img src="https://img.shields.io/badge/PostgreSQL-16-blue?style=for-the-badge&logo=postgresql&logoColor=white" alt="PostgreSQL Version" />
  <img src="https://img.shields.io/badge/Redis-7.x-red?style=for-the-badge&logo=redis&logoColor=white" alt="Redis Version" />
  <img src="https://img.shields.io/badge/Docker-Supported-blue?style=for-the-badge&logo=docker&logoColor=white" alt="Docker Support" />
</p>

An enterprise-grade, multi-tenant Telegram Bot designed to automatically strip the annoying **"Forwarded from..."** headers from posts in Telegram channels. Once added as an administrator, the bot replicates and reposts forwarded content cleanly, deleting the original post in real-time.

---

## 🚀 Core Features

*   🔄 **Auto-Onboarding:** Simply add the bot as an administrator to your channel. It automatically detects addition, runs permission checks, registers settings in PostgreSQL, and activates.
*   🛡️ **Clean Reposting:** Automatically removes forward tag headers from all standard formats:
    *   Plain Text
    *   Photos & Gifs
    *   Videos & Video Notes (Round Videos)
    *   Documents & Audio Files
    *   Voice Notes & Stickers
*   📦 **Redis-Backed Album Reassembly (Media Groups):** Debounces, orders, and bundles multi-photo/video albums into single media groups to preserve original layouts and caption mappings.
*   ⏸️ **Pause & Resume Controls:** Allows channel owners to pause and resume protection directly in DMs without having to remove the bot.
*   ⚡ **Rate Limiting & Retry Backoffs:** Built-in per-channel token spacing (3.0s delay between posts) and tenacity-based retry loops that dynamically sleep for Telegram `retry_after` durations when hitting flood limits (429).
*   📊 **Analytics Dashboard:** Bot owner can run `/stats` to monitor global channel registration metrics and processing success rates.

---

## 🛠️ Technology Stack

| Component | Choice | Description |
| :--- | :--- | :--- |
| **Language** | Python 3.12+ | Async programming paradigm |
| **Bot API** | aiogram 3.x | Lightweight, robust bot framework |
| **Database** | PostgreSQL 16 | Concurrency-safe relational DB for multi-tenant channels |
| **Cache & Queue** | Redis 7.x | Debounce album buffering and per-channel rate locks |
| **ORM** | SQLAlchemy 2.x | Asynchronous database transactions and models |
| **Migrations** | Alembic | Versioned database schema changes |
| **Robustness** | Tenacity | Smart backoff wrappers for API calls |
| **Containerization** | Docker | Portable docker-compose stack |

---

## ⚡ Bot Commands (Strictly DM Only)

All managing commands are private DM-only to prevent group-chat pollution:

*   `/start` & `/help` — Welcomes user and lists administrator requirements.
*   `/mychannels` — Lists your registered channels, IDs, and protection statuses.
*   `/pause <id>` — Pauses protection for a channel (accepts DB index or raw Telegram ID).
*   `/resume <id>` — Resumes protection, re-verifies bot admin permissions, and activates.
*   `/stats` — *(Owner-Only)* Shows global registered channels, active status, and successful/failed message metrics.

---

## 📦 Local Setup (Docker)

To run the complete bot, database, and Redis cache stack locally:

1.  **Clone the Repository:**
    ```bash
    git clone https://github.com/GauravFrr/anti-forward-bot.git
    cd anti-forward-bot
    ```
2.  **Configure environment:** Create a `.env` file in the root directory:
    ```env
    BOT_TOKEN=your_bot_token_here
    OWNER_ID=your_telegram_numeric_id_here
    LOG_LEVEL=INFO
    ```
3.  **Start Services:**
    ```bash
    docker compose up -d --build
    ```
4.  **Check logs:**
    ```bash
    docker compose logs -f bot
    ```

---

## 🎛️ Production Deployment (VPS)

The project includes a helper deployment script `deploy.sh` and a complete setup manual. Refer to the deployment guide in the repository for detailed guides on setting up on Webdock or other Ubuntu host machines.

To pull latest code updates and rebuild/re-deploy on your VPS:
```bash
chmod +x deploy.sh
./deploy.sh
```

---

## 👨‍💻 Developer & Contact

Created and maintained by **MikeyyFrr**. 

💡 **Need custom Telegram bots, suggestions, or queries?**
*   **Telegram DM:** [@MikeyyFrr](https://t.me/MikeyyFrr)
