# Lavalink Setup (Exact Steps)

This project currently uses `yt-dlp` + `FFmpeg` for battle music playback.

If you want to move toward Lavalink, start by running a Lavalink node and adding env config to the bot. This document gives copy/paste setup so your server side is ready.

## 1) Start Lavalink with Docker Compose

Create/run:

```bash
docker compose -f docker-compose.lavalink.yml up -d
```

Verify:

```bash
docker compose -f docker-compose.lavalink.yml logs -f lavalink
```

You should see Lavalink boot messages and no fatal errors.

## 2) Add these exact lines to `.env`

```env
LAVALINK_ENABLED=true
LAVALINK_HOST=127.0.0.1
LAVALINK_PORT=2333
LAVALINK_PASSWORD=change-me-super-secret
LAVALINK_SSL=false
```

If Lavalink runs on another machine, replace `127.0.0.1` with that host/IP.

## 3) Match password in Lavalink config

`docker/lavalink/application.yml` contains:

```yaml
lavalink:
  server:
    password: "change-me-super-secret"
```

Make sure `LAVALINK_PASSWORD` in your `.env` is identical.

## 4) Networking/Firewall

Open TCP port `2333` between bot host and Lavalink host (if separate machines).

## 5) Restart bot after env change

```bash
python pokebot.py
```

---

## Important note

This repo now includes Lavalink deployment/config assets and environment wiring guidance.
The in-bot playback path is still `discord.py` voice + `yt-dlp` unless/ until a Wavelink/Lavalink player backend is fully wired in code.
