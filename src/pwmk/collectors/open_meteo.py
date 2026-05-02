from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Any

import httpx

from pwmk.models.domain import ForecastSnapshot, MarketSpec, WeatherMetric


class OpenMeteoClient:
    def __init__(
        self, ensemble_url: str, model: str = "gfs_seamless", timeout: float = 20.0
    ) -> None:
        self.ensemble_url = ensemble_url
        self.model = model
        self.timeout = timeout

    async def fetch_forecast(
        self, spec: MarketSpec, market_id: str | None = None
    ) -> ForecastSnapshot:
        if spec.location is None:
            raise ValueError(f"No coordinates available for {spec.city}")

        daily_var = daily_variable(spec.metric)
        params = {
            "latitude": spec.location.latitude,
            "longitude": spec.location.longitude,
            "models": self.model,
            "daily": daily_var,
            "start_date": spec.event_date.isoformat(),
            "end_date": spec.event_date.isoformat(),
            "timezone": spec.location.timezone,
        }
        if spec.metric in {WeatherMetric.HIGH_TEMP, WeatherMetric.LOW_TEMP}:
            params["temperature_unit"] = "fahrenheit" if spec.unit == "F" else "celsius"
        if spec.metric is WeatherMetric.PRECIP_SUM:
            params["precipitation_unit"] = "inch" if spec.unit == "inch" else "mm"

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.get(self.ensemble_url, params=params)
            response.raise_for_status()
            payload = response.json()

        values = extract_daily_member_values(payload, daily_var, spec.event_date)
        return ForecastSnapshot(
            market_id=market_id,
            model=self.model,
            spec=spec,
            values=values,
            raw=payload,
        )


def daily_variable(metric: WeatherMetric) -> str:
    if metric is WeatherMetric.HIGH_TEMP:
        return "temperature_2m_max"
    if metric is WeatherMetric.LOW_TEMP:
        return "temperature_2m_min"
    if metric is WeatherMetric.PRECIP_SUM:
        return "precipitation_sum"
    raise ValueError(f"Unsupported weather metric: {metric}")


def extract_daily_member_values(
    payload: dict[str, Any], daily_var: str, event_date: date
) -> list[Decimal]:
    daily = payload.get("daily") or {}
    times = daily.get("time") or []
    target = event_date.isoformat()
    if target not in times:
        raise ValueError(f"Forecast response did not include {target}")
    idx = times.index(target)

    values: list[Decimal] = []
    if daily_var in daily and len(daily[daily_var]) > idx and daily[daily_var][idx] is not None:
        values.append(Decimal(str(daily[daily_var][idx])))

    for member_idx in range(1, 100):
        key = f"{daily_var}_member{member_idx:02d}"
        if key not in daily:
            continue
        member_values = daily[key]
        if len(member_values) > idx and member_values[idx] is not None:
            values.append(Decimal(str(member_values[idx])))

    if not values:
        raise ValueError(f"Forecast response had no values for {daily_var} on {target}")
    return values
