# Anti-Forward-Tag Telegram Bot

A production-grade, multi-tenant Telegram Bot that detects forwarded posts in registered channels, deletes them, and reposts clean copies instantly (removing "Forwarded from X" headers).

## Features
- Multi-tenant support with auto-onboarding when bot is added as admin.
- Buffers media groups (albums) via Redis for proper reassembly.
- Flood-safe rate limiting.
- Graceful error handling and loguru structured logging.

## Tech Stack
- **Language**: Python 3.12+
- **Bot Framework**: aiogram 3.29.1
- **Database**: PostgreSQL 16
- **ORM**: SQLAlchemy + asyncpg
- **Migrations**: Alembic
- **Cache/Buffer**: Redis

## Setup & Running
1. Copy `.env.example` to `.env` and fill in your details:
   ```bash
   cp .env.example .env
   ```
2. Build and run using Docker Compose:
   ```bash
   docker compose up -d --build
   ```
