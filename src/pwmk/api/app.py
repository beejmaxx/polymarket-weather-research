from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from pwmk.config import db_path_from_env
from pwmk.db.repository import Repository, init_db
from pwmk.ingestion.pipeline import poll_once

STATIC_DIR = Path(__file__).with_name("static")


def _repo() -> Repository:
    return Repository(db_path_from_env())


def create_app() -> FastAPI:
    app = FastAPI(title="Prediction Market Volume Layer", version="0.1.0")
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

    @app.on_event("startup")
    def startup() -> None:
        init_db(db_path_from_env())

    @app.get("/", include_in_schema=False)
    def dashboard() -> FileResponse:
        return FileResponse(STATIC_DIR / "index.html")

    @app.get("/api/health")
    def health() -> dict[str, str]:
        return {"status": "ok", "db_path": str(db_path_from_env())}

    @app.get("/api/summary")
    def summary() -> dict:
        return _repo().summary()

    @app.get("/api/markets")
    def markets(
        limit: int = Query(50, ge=1, le=500),
        search: str | None = Query(None),
        active: bool | None = Query(True),
        sort: str = Query("volume24h", pattern="^(volume24h|volumeTotal|liquidity|updated)$"),
    ) -> list[dict]:
        return _repo().list_markets(limit=limit, search=search, active=active, sort=sort)

    @app.get("/api/markets/{condition_id}")
    def market(condition_id: str) -> dict:
        data = _repo().get_market(condition_id)
        if data is None:
            raise HTTPException(status_code=404, detail="Market not found")
        return data

    @app.get("/api/markets/{condition_id}/volume")
    def volume_series(
        condition_id: str,
        hours: int = Query(24, ge=1, le=24 * 365),
    ) -> list[dict]:
        return _repo().volume_series(condition_id, hours=hours)

    @app.get("/api/trades")
    def trades(limit: int = Query(50, ge=1, le=500)) -> list[dict]:
        return _repo().recent_trades(limit=limit)

    @app.get("/api/weather/signals")
    def weather_signals(limit: int = Query(50, ge=1, le=500)) -> list[dict]:
        return _repo().recent_weather_signals(limit=limit)

    @app.get("/api/weather/settlements")
    def weather_settlements(limit: int = Query(50, ge=1, le=500)) -> list[dict]:
        return _repo().recent_settlements(limit=limit)

    @app.get("/api/weather/calibration")
    def weather_calibration() -> dict:
        return _repo().weather_calibration_report()

    @app.post("/api/ingest/poll")
    async def trigger_poll(limit: int = Query(100, ge=1, le=1000)) -> dict:
        result = await poll_once(db_path_from_env(), limit=limit)
        return result.as_dict()

    return app


app = create_app()
