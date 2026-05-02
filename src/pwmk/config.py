from __future__ import annotations

import os
from dataclasses import dataclass, field
from decimal import Decimal
from pathlib import Path


def db_path_from_env() -> Path:
    return Path(os.getenv("PWMK_DB_PATH", "data/pwmk.sqlite")).expanduser()


def _bool_env(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _int_env(name: str, default: int) -> int:
    return int(os.getenv(name, str(default)))


def _float_env(name: str, default: float) -> float:
    return float(os.getenv(name, str(default)))


def _decimal_env(name: str, default: str) -> Decimal:
    return Decimal(os.getenv(name, default))


@dataclass(frozen=True)
class AppSettings:
    db_path: Path = field(default_factory=db_path_from_env)
    api_token: str | None = field(default_factory=lambda: os.getenv("PWMK_API_TOKEN"))
    enable_scheduler: bool = field(
        default_factory=lambda: _bool_env("PWMK_ENABLE_SCHEDULER", False)
    )
    poll_limit: int = field(default_factory=lambda: _int_env("PWMK_POLL_LIMIT", 200))
    poll_interval_seconds: int = field(
        default_factory=lambda: _int_env("PWMK_POLL_INTERVAL_SECONDS", 60)
    )
    live_events: int = field(default_factory=lambda: _int_env("PWMK_LIVE_EVENTS", 25))
    enable_stream: bool = field(default_factory=lambda: _bool_env("PWMK_ENABLE_STREAM", False))
    stream_asset_limit: int = field(
        default_factory=lambda: _int_env("PWMK_STREAM_ASSET_LIMIT", 100)
    )
    stream_window_seconds: int = field(
        default_factory=lambda: _int_env("PWMK_STREAM_WINDOW_SECONDS", 300)
    )
    stream_restart_delay_seconds: int = field(
        default_factory=lambda: _int_env("PWMK_STREAM_RESTART_DELAY_SECONDS", 5)
    )
    alert_webhook_url: str | None = field(
        default_factory=lambda: os.getenv("PWMK_ALERT_WEBHOOK_URL")
    )
    volume_spike_min_delta: float = field(
        default_factory=lambda: _float_env("PWMK_VOLUME_SPIKE_MIN_DELTA", 100000)
    )
    volume_spike_multiplier: float = field(
        default_factory=lambda: _float_env("PWMK_VOLUME_SPIKE_MULTIPLIER", 2.0)
    )
    stale_ingestion_minutes: int = field(
        default_factory=lambda: _int_env("PWMK_STALE_INGESTION_MINUTES", 10)
    )


@dataclass(frozen=True)
class WeatherSettings:
    gamma_base_url: str = field(
        default_factory=lambda: os.getenv(
            "PWMK_GAMMA_BASE_URL", "https://gamma-api.polymarket.com"
        )
    )
    clob_base_url: str = field(
        default_factory=lambda: os.getenv("PWMK_CLOB_BASE_URL", "https://clob.polymarket.com")
    )
    open_meteo_ensemble_url: str = field(
        default_factory=lambda: os.getenv(
            "PWMK_OPEN_METEO_ENSEMBLE_URL", "https://ensemble-api.open-meteo.com/v1/ensemble"
        )
    )
    open_meteo_model: str = field(
        default_factory=lambda: os.getenv("PWMK_OPEN_METEO_MODEL", "gfs_seamless")
    )
    bankroll_usd: Decimal = field(
        default_factory=lambda: _decimal_env("PWMK_BANKROLL_USD", "1000")
    )
    min_edge: Decimal = field(default_factory=lambda: _decimal_env("PWMK_MIN_EDGE", "0.08"))
    max_spread: Decimal = field(
        default_factory=lambda: _decimal_env("PWMK_MAX_SPREAD", "0.08")
    )
    max_trade_usd: Decimal = field(
        default_factory=lambda: _decimal_env("PWMK_MAX_TRADE_USD", "25")
    )
    max_market_usd: Decimal = field(
        default_factory=lambda: _decimal_env("PWMK_MAX_MARKET_USD", "50")
    )


def weather_settings_from_env() -> WeatherSettings:
    return WeatherSettings()


def app_settings_from_env() -> AppSettings:
    return AppSettings()
