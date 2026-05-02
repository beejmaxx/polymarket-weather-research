from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException, Query, Request, Response
from fastapi.responses import FileResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles

from pwmk.config import AppSettings, app_settings_from_env, db_path_from_env
from pwmk.db.repository import Repository, init_db
from pwmk.ingestion.pipeline import backfill_markets, poll_once, run_maintenance
from pwmk.ingestion.scheduler import IngestionScheduler

STATIC_DIR = Path(__file__).with_name("static")


def _repo() -> Repository:
    return Repository(db_path_from_env())


def _api_token_from_request(request: Request) -> str | None:
    api_key = request.headers.get("x-api-key")
    if api_key:
        return api_key
    authorization = request.headers.get("authorization", "")
    prefix = "Bearer "
    if authorization.startswith(prefix):
        return authorization[len(prefix) :].strip()
    return None


def require_api_token(request: Request) -> None:
    settings: AppSettings = request.app.state.settings
    if not settings.api_token:
        return
    if _api_token_from_request(request) != settings.api_token:
        raise HTTPException(status_code=401, detail="Missing or invalid API token")


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = app_settings_from_env()
    app.state.settings = settings
    init_db(settings.db_path)
    scheduler = IngestionScheduler(settings)
    app.state.scheduler = scheduler
    scheduler.start()
    try:
        yield
    finally:
        await scheduler.stop()


def create_app() -> FastAPI:
    app = FastAPI(title="Prediction Market Volume Layer", version="0.2.0", lifespan=lifespan)
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

    @app.get("/", include_in_schema=False)
    def dashboard() -> FileResponse:
        return FileResponse(STATIC_DIR / "index.html")

    @app.get("/api/health")
    def health() -> dict[str, str]:
        return {"status": "ok", "db_path": str(db_path_from_env())}

    @app.get("/api/summary")
    def summary(_: None = Depends(require_api_token)) -> dict:
        return _repo().summary()

    @app.get("/api/scheduler")
    def scheduler_status(request: Request, _: None = Depends(require_api_token)) -> dict:
        scheduler: IngestionScheduler = request.app.state.scheduler
        return scheduler.status().as_dict()

    @app.get("/api/markets")
    def markets(
        limit: int = Query(50, ge=1, le=500),
        search: str | None = Query(None),
        active: bool | None = Query(True),
        sort: str = Query("volume24h", pattern="^(volume24h|volumeTotal|liquidity|updated)$"),
        _: None = Depends(require_api_token),
    ) -> list[dict]:
        return _repo().list_markets(limit=limit, search=search, active=active, sort=sort)

    @app.get("/api/events")
    def events(
        limit: int = Query(50, ge=1, le=500),
        _: None = Depends(require_api_token),
    ) -> list[dict]:
        return _repo().list_events(limit=limit)

    @app.get("/api/markets/{condition_id}")
    def market(condition_id: str, _: None = Depends(require_api_token)) -> dict:
        data = _repo().get_market(condition_id)
        if data is None:
            raise HTTPException(status_code=404, detail="Market not found")
        return data

    @app.get("/api/markets/{condition_id}/volume")
    def volume_series(
        condition_id: str,
        hours: int = Query(24, ge=1, le=24 * 365),
        _: None = Depends(require_api_token),
    ) -> list[dict]:
        return _repo().volume_series(condition_id, hours=hours)

    @app.get("/api/markets/{condition_id}/aggregates")
    def aggregate_series(
        condition_id: str,
        bucket_size: str = Query("hour", pattern="^(hour|day)$"),
        hours: int = Query(24 * 7, ge=1, le=24 * 365),
        _: None = Depends(require_api_token),
    ) -> list[dict]:
        return _repo().aggregate_series(condition_id, bucket_size=bucket_size, hours=hours)

    @app.get("/api/momentum")
    def momentum(
        limit: int = Query(25, ge=1, le=200),
        _: None = Depends(require_api_token),
    ) -> list[dict]:
        return _repo().volume_momentum(limit=limit)

    @app.get("/api/trades")
    def trades(
        limit: int = Query(50, ge=1, le=500),
        _: None = Depends(require_api_token),
    ) -> list[dict]:
        return _repo().recent_trades(limit=limit)

    @app.get("/api/alerts")
    def alerts(
        limit: int = Query(50, ge=1, le=500),
        status: str | None = Query(None, pattern="^(pending|delivered|resolved)$"),
        _: None = Depends(require_api_token),
    ) -> list[dict]:
        return _repo().recent_alerts(limit=limit, status=status)

    @app.get("/api/data-quality")
    def data_quality(
        limit: int = Query(50, ge=1, le=500),
        _: None = Depends(require_api_token),
    ) -> list[dict]:
        return _repo().recent_data_quality_issues(limit=limit)

    @app.get("/api/weather/signals")
    def weather_signals(
        limit: int = Query(50, ge=1, le=500),
        _: None = Depends(require_api_token),
    ) -> list[dict]:
        return _repo().recent_weather_signals(limit=limit)

    @app.get("/api/weather/settlements")
    def weather_settlements(
        limit: int = Query(50, ge=1, le=500),
        _: None = Depends(require_api_token),
    ) -> list[dict]:
        return _repo().recent_settlements(limit=limit)

    @app.get("/api/weather/calibration")
    def weather_calibration(_: None = Depends(require_api_token)) -> dict:
        return _repo().weather_calibration_report()

    @app.get("/api/export/markets.csv")
    def export_markets_csv(
        limit: int = Query(1000, ge=1, le=10000),
        _: None = Depends(require_api_token),
    ) -> Response:
        return Response(
            _repo().export_markets_csv(limit=limit),
            media_type="text/csv",
            headers={"Content-Disposition": "attachment; filename=markets.csv"},
        )

    @app.get("/api/export/trades.csv")
    def export_trades_csv(
        limit: int = Query(1000, ge=1, le=10000),
        _: None = Depends(require_api_token),
    ) -> Response:
        return Response(
            _repo().export_trades_csv(limit=limit),
            media_type="text/csv",
            headers={"Content-Disposition": "attachment; filename=trades.csv"},
        )

    @app.get("/api/export/markets.json")
    def export_markets_json(
        limit: int = Query(1000, ge=1, le=10000),
        _: None = Depends(require_api_token),
    ) -> PlainTextResponse:
        return PlainTextResponse(
            _repo().export_markets_json(limit=limit),
            media_type="application/json",
        )

    @app.post("/api/ingest/poll")
    async def trigger_poll(
        limit: int = Query(100, ge=1, le=1000),
        _: None = Depends(require_api_token),
    ) -> dict:
        result = await poll_once(db_path_from_env(), limit=limit)
        return result.as_dict()

    @app.post("/api/ingest/backfill")
    async def trigger_backfill(
        active_limit: int = Query(1000, ge=0, le=10000),
        closed_limit: int = Query(1000, ge=0, le=10000),
        _: None = Depends(require_api_token),
    ) -> dict:
        return await backfill_markets(
            db_path_from_env(),
            active_limit=active_limit,
            closed_limit=closed_limit,
        )

    @app.post("/api/maintenance")
    async def trigger_maintenance(_: None = Depends(require_api_token)) -> dict:
        return await run_maintenance(db_path_from_env())

    return app


app = create_app()
