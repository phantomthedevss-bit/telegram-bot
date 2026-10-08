# NEXUS Telegram bot

One-file Python bot. Same command set as the NEXUS console. Hosted as a Render web service via webhook.

## What you need

1. A Telegram bot token from [@BotFather](https://t.me/BotFather) (`/newbot`)
2. A Render account
3. These files in a Git repo: `bot.py`, `requirements.txt`, `render.yaml`

## Render

1. New Web Service from the repo
2. Build: `pip install -r requirements.txt`
3. Start: `python bot.py`
4. Environment:

```
TELEGRAM_BOT_TOKEN=123456:ABC...
WEBHOOK_URL=https://YOUR-SERVICE.onrender.com
XAI_API_KEY=optional
```

`WEBHOOK_URL` must be the public https origin with no trailing slash. The bot registers `/telegram` as the webhook path and serves `GET /` as a health check.

## Local polling (optional)

```
export TELEGRAM_BOT_TOKEN=123456:ABC
python bot.py
```

If `WEBHOOK_URL` is unset, the bot uses long polling.

## Rules baked in

- No port scans, exploits, flooders, or malware helpers
- No YouTube/TikTok file ripping (metadata via oEmbed only)
- Public DNS/RDAP/CT/headers only, with private-IP blocks
- `/ask` `/summarize` `/explain` need `XAI_API_KEY`

Open Telegram and send `/start`.
