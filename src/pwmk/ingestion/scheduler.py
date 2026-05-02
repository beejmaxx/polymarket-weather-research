from __future__ import annotations

import asyncio
from dataclasses import asdict, dataclass

from pwmk.config import AppSettings
from pwmk.ingestion.pipeline import poll_loop, stream_loop
from pwmk.parsing.normalize import utc_now_iso


@dataclass(frozen=True)
class SchedulerStatus:
    enabled: bool
    stream_enabled: bool
    started_at: str | None
    tasks: list[str]
    poll_interval_seconds: int
    poll_limit: int
    stream_asset_limit: int

    def as_dict(self) -> dict[str, object]:
        return asdict(self)


class IngestionScheduler:
    def __init__(self, settings: AppSettings):
        self.settings = settings
        self.started_at: str | None = None
        self._tasks: list[asyncio.Task[None]] = []

    def start(self) -> None:
        if self._tasks or not self.settings.enable_scheduler:
            return

        self.started_at = utc_now_iso()
        self._tasks.append(
            asyncio.create_task(
                poll_loop(
                    self.settings.db_path,
                    limit=self.settings.poll_limit,
                    interval=self.settings.poll_interval_seconds,
                    live_events=self.settings.live_events,
                ),
                name="poll-loop",
            )
        )
        if self.settings.enable_stream:
            self._tasks.append(
                asyncio.create_task(
                    stream_loop(
                        self.settings.db_path,
                        asset_limit=self.settings.stream_asset_limit,
                        window_seconds=self.settings.stream_window_seconds,
                        restart_delay_seconds=self.settings.stream_restart_delay_seconds,
                        bootstrap_limit=self.settings.poll_limit,
                    ),
                    name="stream-loop",
                )
            )

    async def stop(self) -> None:
        for task in self._tasks:
            task.cancel()
        if self._tasks:
            await asyncio.gather(*self._tasks, return_exceptions=True)
        self._tasks = []

    def status(self) -> SchedulerStatus:
        return SchedulerStatus(
            enabled=self.settings.enable_scheduler,
            stream_enabled=self.settings.enable_stream,
            started_at=self.started_at,
            tasks=[task.get_name() for task in self._tasks if not task.done()],
            poll_interval_seconds=self.settings.poll_interval_seconds,
            poll_limit=self.settings.poll_limit,
            stream_asset_limit=self.settings.stream_asset_limit,
        )
