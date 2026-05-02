from __future__ import annotations

import os
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path


def db_path_from_env() -> Path:
    return Path(os.getenv("PWMK_DB_PATH", "data/pwmk.sqlite")).expanduser()


def _decimal_env(name: str, default: str) -> Decimal:
    return Decimal(os.getenv(name, default))


@dataclass(frozen=True)
class WeatherSettings:
    gamma_base_url: str = os.getenv("PWMK_GAMMA_BASE_URL", "https://gamma-api.polymarket.com")
    clob_base_url: str = os.getenv("PWMK_CLOB_BASE_URL", "https://clob.polymarket.com")
    open_meteo_ensemble_url: str = os.getenv(
        "PWMK_OPEN_METEO_ENSEMBLE_URL", "https://ensemble-api.open-meteo.com/v1/ensemble"
    )
    open_meteo_model: str = os.getenv("PWMK_OPEN_METEO_MODEL", "gfs_seamless")
    bankroll_usd: Decimal = _decimal_env("PWMK_BANKROLL_USD", "1000")
    min_edge: Decimal = _decimal_env("PWMK_MIN_EDGE", "0.08")
    max_spread: Decimal = _decimal_env("PWMK_MAX_SPREAD", "0.08")
    max_trade_usd: Decimal = _decimal_env("PWMK_MAX_TRADE_USD", "25")
    max_market_usd: Decimal = _decimal_env("PWMK_MAX_MARKET_USD", "50")


def weather_settings_from_env() -> WeatherSettings:
    return WeatherSettings()
