# Deployment

## Docker Compose

```bash
cp .env.example .env
docker compose up --build -d
```

Open `http://localhost:8000`.

Recommended production `.env`:

```dotenv
PWMK_API_TOKEN=replace-me
PWMK_ENABLE_SCHEDULER=true
PWMK_POLL_LIMIT=500
PWMK_POLL_INTERVAL_SECONDS=60
PWMK_ENABLE_STREAM=true
PWMK_STREAM_ASSET_LIMIT=200
PWMK_ALERT_WEBHOOK_URL=
```

## Systemd

Install the repo at `/opt/polymarket-weather-research`, create a virtualenv, install the package, copy `deploy/pwmk.service` into `/etc/systemd/system/`, then run:

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now pwmk
sudo journalctl -u pwmk -f
```

## Operational Notes

- SQLite is suitable for demos and moderate internal use.
- For heavy historical ingestion, migrate the repository layer to Postgres/TimescaleDB.
- Keep `PWMK_API_TOKEN` set for any public-facing deployment.
- Use `/api/scheduler`, `/api/summary`, `/api/alerts`, and `/api/data-quality` for health checks.

