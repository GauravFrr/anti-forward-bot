#!/bin/bash
# Exit immediately if a command exits with a non-zero status
set -e

echo "========================================================="
echo "🚀 Starting Anti-Forward Telegram Bot VPS Deployment"
echo "========================================================="

# 1. Pull latest code changes if inside Git repository
if [ -d .git ]; then
    echo "📦 Stashing any local environment overrides..."
    git stash || true
    echo "📥 Pulling latest code changes from Git main branch..."
    git pull origin main
else
    echo "⚠️  Warning: Not a Git repository. Skipping git pull."
fi

# 2. Build and restart Docker Compose containers
echo "🛠️  Building and starting Docker Compose services..."
docker compose down
docker compose up -d --build

# 3. Verify running services status
echo "🔍 Checking running container states..."
docker compose ps

echo "========================================================="
echo "✅ Deployment Completed Successfully!"
echo "💡 To monitor live logs, run: docker compose logs -f bot"
echo "========================================================="
