# 🌐 VPS Hosting & Deployment Guide

This guide details how to host, run, and maintain the **Anti-Forward-Tag Telegram Bot** on a Linux VPS (such as Webdock, DigitalOcean, or Linode) using Docker Compose.

---

## 📋 Table of Contents
1. [Prerequisites & Host Setup](#1-prerequisites--host-setup)
2. [Deployment Steps](#2-deployment-steps)
3. [Database Administration & Backups](#3-database-administration--backups)
4. [Updates & Maintenance](#4-updates--maintenance)
5. [Rollback & Recovery (Emergency)](#5-rollback--recovery-emergency)

---

## 1. Prerequisites & Host Setup

Before deploying, ensure Docker and Docker Compose are installed on your VPS.

### Install Docker Engine (Ubuntu/Debian)
Run the following script to install the Docker runtime on your VPS:
```bash
# Update package index & install pre-requisites
sudo apt-get update
sudo apt-get install -y ca-certificates curl gnupg

# Add Docker's official GPG key
sudo install -m 0755 -d /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/ubuntu/gpg | sudo gpg --dearmor -o /etc/apt/keyrings/docker.gpg
sudo chmod a+r /etc/apt/keyrings/docker.gpg

# Add Docker repository to APT sources
echo \
  "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/ubuntu \
  $(. /etc/os-release && echo "$VERSION_CODENAME") stable" | \
  sudo tee /etc/apt/sources.list.d/docker.list > /dev/null

# Install Docker packages
sudo apt-get update
sudo apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
```

Verify installation:
```bash
docker --version
docker compose version
```

---

## 2. Deployment Steps

### Step 1: Clone the Repository
Clone the codebase into your preferred hosting folder (e.g., `/var/www/`):
```bash
git clone https://github.com/GauravFrr/anti-forward-bot.git /var/www/anti-forward-bot
cd /var/www/anti-forward-bot
```

### Step 2: Configure Environment Variables
Copy the template and create your production environment configuration:
```bash
cp .env.example .env
nano .env
```
Fill in the parameters:
```ini
# Telegram Bot Token from @BotFather
BOT_TOKEN=8366861081:AAHwALxXHoXvI_IQKAc_6DPUMKmMlAj6VBk

# Your Telegram account ID (Owner of the bot)
OWNER_ID=6447766151

# Logger verbosity level
LOG_LEVEL=INFO
```

> [!CAUTION]
> **Security Warning:** Never commit your live production `.env` containing credentials or bot tokens to Git. The project's `.gitignore` is pre-configured to exclude `.env` files.

### Step 3: Run the Application Stack
Execute the automated deployment script to build the image, run database migrations, and start communication polling in the background:
```bash
# Make the script executable
chmod +x deploy.sh

# Run the deployment
./deploy.sh
```

### Step 4: Verify Service Health
Check that all 3 services are active:
```bash
docker compose ps
```
You should see:
*   `forward_bot_app` (Up)
*   `forward_bot_postgres` (Up)
*   `forward_bot_redis` (Up)

To monitor logs in real-time:
```bash
docker compose logs -f bot
```

---

## 3. Database Administration & Backups

PostgreSQL data is persisted outside of the containers in a named Docker volume (`anti-forwardtgbot_pgdata`). This ensures that database entries are safe during container rebuilds and updates.

### Direct SQL Inspection
To access the database shell and inspect tables:
```bash
docker compose exec postgres psql -U fwbot_admin -d forward_bot_db
```
Useful commands inside the `psql` shell:
*   **Show registered channels:** `SELECT * FROM channels;`
*   **Show message log events:** `SELECT * FROM event_logs LIMIT 10;`
*   **Exit shell:** `\q`

### Database Backups (pg_dump)
To perform a manual hot backup of your PostgreSQL database:
```bash
docker compose exec postgres pg_dump -U fwbot_admin forward_bot_db > ~/db_backup_$(date +%F).sql
```

---

## 4. Updates & Maintenance

Whenever you push new updates to GitHub and want to sync them onto your production server:
1.  SSH into your VPS.
2.  Navigate to `/var/www/anti-forward-bot`.
3.  Run the deployment script:
    ```bash
    ./deploy.sh
    ```
The script will stash local overrides, pull the latest code, rebuild the container layers, execute any new migrations, and restart the bot cleanly.

---

## 5. Rollback & Recovery (Emergency)

If a new update breaks or causes unexpected exceptions in production, you can roll back to a previous stable state:

1.  View the recent commit history on the VPS to find the stable commit hash:
    ```bash
    git log --oneline -n 10
    ```
2.  Checkout that specific stable commit hash:
    ```bash
    git checkout <stable-commit-hash>
    ```
3.  Rebuild and restart the container services:
    ```bash
    ./deploy.sh
    ```
4.  Once the issue is resolved and fixed in your development environment, push it to git, switch back to the `main` branch on the VPS (`git checkout main`), and run `./deploy.sh` to restore current updates.
