# Bot Kira OT (Telegram Bot) — Render Deployment

## How to deploy
1. Upload all files to GitHub.
2. Create Render Web Service.
3. Build command:
   pip install -r requirements.txt
4. Start command:
   gunicorn main:app
5. Add env variable:
   BOT_TOKEN=<your telegram token>
6. Set webhook:
   https://api.telegram.org/bot<BOT_TOKEN>/setWebhook?url=https://<RENDER-URL>/webhook
