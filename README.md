# 📅 Daily Planner Telegram Bot

A production-ready Telegram Bot to track daily plans, task priorities, and send reminders.
Designed for deployment on **Render** using persistent disk storage and SQLite.

## 🚀 Deployment Instructions for Render

1. **Push Code to GitHub:**
   - Commit all files to a private or public repository on GitHub.

2. **Create Web Service / Worker on Render:**
   - Log into [Render.com](https://render.com).
   - Click **New +** -> **Blueprint**.
   - Connect your GitHub repository.
   - Render automatically detects `render.yaml`.

3. **Configure Secrets:**
   - Under Environment Variables on Render, set:
     - `BOT_TOKEN`: The token provided by Telegram's `@BotFather`.

4. **Persistent Disk Setup (Handled by Blueprint):**
   - The included `render.yaml` automatically mounts a 1 GB persistent disk at `/var/data` to ensure your SQLite database survives service restarts.

## 💻 Local Running

```bash
python3 -m venv env
source env/bin/activate
pip install -r requirements.txt
cp .env.example .env
# Edit .env with your BOT_TOKEN
python main.py
