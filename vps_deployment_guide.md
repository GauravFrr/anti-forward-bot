# Production Deployment Guide: Hosting on Webdock VPS

This guide provides step-by-step instructions for deploying and maintaining the **Anti-Forward-Tag Telegram Bot** on a Webdock (or any Ubuntu-based) VPS using Docker Compose.

---

## 1. Host Machine Setup
Before deploying, ensure Docker and Docker Compose are installed on your Linux VPS.

### Install Docker Engine (Ubuntu)
Run the following commands on your VPS terminal:
```bash
# Update package index
sudo apt-get update

# Install prerequisites
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

---

## 2. Deploying the Application

### Step 1: Clone the Repository
Clone your project repository onto the VPS directory (we recommend cloning directly into your home directory `~/` to avoid permission errors):
```bash
git clone https://github.com/GauravFrr/anti-forward-bot.git ~/anti-forward-bot
cd ~/anti-forward-bot
```

### Step 2: Configure Environment Variables
Create the production environment file:
```bash
cp .env.example .env
nano .env
```
Fill in the configuration details:
```ini
# Telegram Bot Token from @BotFather
BOT_TOKEN=8366861081:AAHwALxXHoXvI_IQKAc_6DPUMKmMlAj6VBk

# Your Telegram account ID (Owner of the bot)
OWNER_ID=6447766151

# Logger verbosity level
LOG_LEVEL=INFO
```

> [!CAUTION]
> **Git Safety Warning:** Never commit your live production `.env` containing the real `BOT_TOKEN` or active database passwords to Git. The project contains a `.gitignore` that excludes `.env` automatically. Ensure this is maintained.

*(Note: Keep the default Postgres and Redis connection strings inside `docker-compose.yml` to automatically route communication through internal secure Docker network names).*

### Step 3: Run the Startup Script
Make the deployment script executable and launch the containers:
```bash
chmod +x deploy.sh
./deploy.sh
```

### Step 4: Monitor Log Outputs
Verify that migrations have completed and the polling loop is active:
```bash
docker compose logs -f bot
```

---

## 3. Database Administration & Backups

All database assets are persisted on the VPS host inside a named Docker Volume (`anti-forwardtgbot_pgdata`) defined in `docker-compose.yml`. This ensures that your data remains safe and is never wiped during container rebuilds, code updates, or running `deploy.sh --build`.

### Inspect Live Database Tables
To execute query commands directly against the production Postgres instance:
```bash
docker compose exec postgres psql -U fwbot_admin -d forward_bot_db
```
Useful SQL queries:
- **List Channels:** `SELECT * FROM channels;`
- **View Log Events:** `SELECT * FROM event_logs LIMIT 10;`

### Backup PostgreSQL Data (pg_dump)
Run this command to create a timestamped SQL backup on the host machine:
```bash
docker compose exec postgres pg_dump -U fwbot_admin forward_bot_db > ~/db_backup_$(date +%F).sql
```

---

## 4. Updates & Maintenance
Whenever you update code or make edits on your local machine and push them to Git:
1. SSH into the Webdock VPS.
2. Run `./deploy.sh`.
This will pull the latest version, rebuild the container, run any new migrations, and restart the services gracefully without manual downtime configuration.

---

## 5. Rollback & Recovery Instructions

If a code deployment introduces a bug or breaks production:
1. Check the git commit history to find the last known stable commit hash:
   ```bash
   git log --oneline -n 10
   ```
2. Checkout the stable commit hash:
   ```bash
   git checkout <stable-commit-hash>
   ```
3. Rebuild and restart the containers to load the previous stable version:
   ```bash
   ./deploy.sh
   ```
4. Once you isolate and fix the bug in your development environment, push the fix to git, switch back to the main branch on the VPS (`git checkout main`), and run `./deploy.sh` to update.
