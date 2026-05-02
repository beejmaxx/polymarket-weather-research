from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import httpx

from pwmk.db.repository import Repository
from pwmk.parsing.normalize import compact_json, utc_now_iso


def _parse_iso(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(UTC)


def _hour_bucket(value: str) -> str:
    dt = _parse_iso(value).replace(minute=0, second=0, microsecond=0)
    return dt.isoformat(timespec="seconds").replace("+00:00", "Z")


def create_volume_spike_alerts(
    repo: Repository,
    *,
    min_delta: float,
    multiplier: float,
    limit: int = 100,
) -> int:
    created = 0
    for row in repo.volume_momentum(limit=limit):
        previous = float(row["previous_volume_24h"] or 0)
        current = float(row["volume_24h"] or 0)
        change = current - previous
        if previous <= 0 or change < min_delta or current < previous * multiplier:
            continue

        condition_id = row["condition_id"]
        alert = {
            "source": "polymarket",
            "alert_type": "volume_spike",
            "severity": "high",
            "condition_id": condition_id,
            "event_id": None,
            "title": row["question"],
            "message": (
                f"24h volume jumped from {previous:,.0f} to {current:,.0f} "
                f"on {row['question']}"
            ),
            "metric_value": current,
            "threshold_value": previous * multiplier,
            "status": "pending",
            "dedupe_key": f"volume_spike:{condition_id}:{_hour_bucket(row['observed_at'])}",
            "created_at": utc_now_iso(),
            "delivered_at": None,
            "raw_json": compact_json(row),
        }
        created += int(repo.save_alert(alert))
    return created


def create_stale_ingestion_alert(repo: Repository, *, stale_minutes: int) -> int:
    summary = repo.summary()
    latest_snapshot_at = summary.get("latest_snapshot_at")
    if not latest_snapshot_at:
        return int(
            repo.save_alert(
                {
                    "source": "polymarket",
                    "alert_type": "stale_ingestion",
                    "severity": "critical",
                    "condition_id": None,
                    "event_id": None,
                    "title": "No snapshots",
                    "message": "No market snapshots have been ingested yet.",
                    "metric_value": None,
                    "threshold_value": stale_minutes,
                    "status": "pending",
                    "dedupe_key": f"stale_ingestion:none:{utc_now_iso()[:13]}",
                    "created_at": utc_now_iso(),
                    "delivered_at": None,
                    "raw_json": compact_json(summary),
                }
            )
        )

    age_seconds = (datetime.now(UTC) - _parse_iso(str(latest_snapshot_at))).total_seconds()
    stale_seconds = stale_minutes * 60
    if age_seconds <= stale_seconds:
        repo.resolve_alerts("stale_ingestion")
        return 0

    return int(
        repo.save_alert(
            {
                "source": "polymarket",
                "alert_type": "stale_ingestion",
                "severity": "critical",
                "condition_id": None,
                "event_id": None,
                "title": "Stale ingestion",
                "message": (
                    f"Latest market snapshot is {age_seconds / 60:.1f} minutes old, "
                    f"above the {stale_minutes} minute threshold."
                ),
                "metric_value": age_seconds / 60,
                "threshold_value": stale_minutes,
                "status": "pending",
                "dedupe_key": f"stale_ingestion:{_hour_bucket(str(latest_snapshot_at))}",
                "created_at": utc_now_iso(),
                "delivered_at": None,
                "raw_json": compact_json(summary),
            }
        )
    )


def run_alert_checks(
    repo: Repository,
    *,
    min_delta: float,
    multiplier: float,
    stale_minutes: int,
) -> dict[str, int]:
    return {
        "volume_spike_alerts": create_volume_spike_alerts(
            repo, min_delta=min_delta, multiplier=multiplier
        ),
        "stale_ingestion_alerts": create_stale_ingestion_alert(
            repo, stale_minutes=stale_minutes
        ),
    }


async def deliver_pending_alerts(
    repo: Repository,
    *,
    webhook_url: str | None,
    limit: int = 10,
) -> int:
    if not webhook_url:
        return 0

    delivered = 0
    alerts = repo.recent_alerts(limit=limit, status="pending")
    async with httpx.AsyncClient(timeout=10) as client:
        for alert in alerts:
            payload: dict[str, Any] = {
                "text": alert["message"],
                "alert": alert,
            }
            response = await client.post(webhook_url, json=payload)
            response.raise_for_status()
            repo.mark_alert_delivered(int(alert["id"]))
            delivered += 1
    return delivered
