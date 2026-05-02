from __future__ import annotations

import argparse
import asyncio
import json
import os
from datetime import date
from decimal import Decimal
from pathlib import Path

from pwmk.collectors.open_meteo import OpenMeteoClient
from pwmk.collectors.polymarket import PolymarketClient
from pwmk.config import db_path_from_env, weather_settings_from_env
from pwmk.db.repository import Repository, init_db
from pwmk.ingestion.pipeline import poll_loop, poll_once, stream_trades
from pwmk.models.domain import PaperOrder, RawMarket
from pwmk.parsing.normalize import normalize_market, utc_now_iso
from pwmk.parsing.weather_market_parser import WeatherMarketParser
from pwmk.trading.risk import RiskLimits
from pwmk.trading.settlement import infer_market_settlement
from pwmk.trading.signals import build_signal, paper_order_quantity


def _db_path(args: argparse.Namespace) -> Path:
    return Path(args.db).expanduser() if getattr(args, "db", None) else db_path_from_env()


def _print_json(payload: object) -> None:
    print(json.dumps(payload, indent=2, sort_keys=True))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="pwmk")
    parser.add_argument(
        "--db", help="SQLite database path. Defaults to PWMK_DB_PATH or data/pwmk.sqlite"
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("init-db", help="Create or migrate the SQLite database")

    serve = subparsers.add_parser("serve", help="Run the FastAPI dashboard")
    serve.add_argument("--host", default="127.0.0.1")
    serve.add_argument("--port", type=int, default=8000)
    serve.add_argument("--reload", action="store_true")

    export = subparsers.add_parser("export-markets", help="Print normalized markets as JSON")
    export.add_argument("--limit", type=int, default=1000)

    ingest = subparsers.add_parser("ingest", help="Run ingestion tasks")
    ingest_subparsers = ingest.add_subparsers(dest="ingest_command", required=True)

    poll = ingest_subparsers.add_parser("poll", help="Fetch one market snapshot batch")
    poll.add_argument("--limit", type=int, default=100)
    poll.add_argument("--page-size", type=int, default=250)
    poll.add_argument("--live-events", type=int, default=25)
    poll.add_argument("--skip-live-volume", action="store_true")

    loop = ingest_subparsers.add_parser("loop", help="Continuously fetch market snapshots")
    loop.add_argument("--limit", type=int, default=100)
    loop.add_argument("--interval", type=int, default=60)
    loop.add_argument("--live-events", type=int, default=25)

    stream = ingest_subparsers.add_parser("stream", help="Record public CLOB trade prints")
    stream.add_argument("--asset-limit", type=int, default=50)
    stream.add_argument("--duration", type=int)
    stream.add_argument("--bootstrap-limit", type=int, default=100)

    weather = subparsers.add_parser("weather", help="Run weather-market research workflows")
    weather_subparsers = weather.add_subparsers(dest="weather_command", required=True)

    parse_title = weather_subparsers.add_parser("parse-title", help="Parse a weather market title")
    parse_title.add_argument("title")

    audit = weather_subparsers.add_parser(
        "audit-titles", help="Audit weather title parser coverage"
    )
    audit.add_argument("--limit", type=int, default=200)
    audit.add_argument("--offset", type=int, default=0)
    audit.add_argument("--source", choices=["keyword", "weather-tag", "both"], default="both")
    audit.add_argument("--examples", type=int, default=50)
    audit.add_argument("--include-parsed", action="store_true")

    scan = weather_subparsers.add_parser("scan", help="Generate paper weather signals")
    scan.add_argument("--limit", type=int, default=200)
    scan.add_argument("--offset", type=int, default=0)
    scan.add_argument("--source", choices=["keyword", "weather-tag", "both"], default="keyword")
    scan.add_argument("--min-confidence", type=Decimal, default=Decimal("0.70"))
    scan.add_argument("--min-edge", type=Decimal)
    scan.add_argument("--max-spread", type=Decimal)
    scan.add_argument("--no-paper", action="store_true")

    signals = weather_subparsers.add_parser("signals", help="Show recent paper signals")
    signals.add_argument("--limit", type=int, default=20)

    settlements = weather_subparsers.add_parser("settlements", help="Show recent settlements")
    settlements.add_argument("--limit", type=int, default=20)

    sync_settlements = weather_subparsers.add_parser(
        "sync-settlements", help="Fetch resolved outcomes for paper-traded markets"
    )
    sync_settlements.add_argument("--limit", type=int, default=100)
    sync_settlements.add_argument(
        "--recent-closed",
        action="store_true",
        help="Scan recent closed markets instead of only unsettled paper orders",
    )

    weather_subparsers.add_parser("calibration", help="Report settled paper-trade calibration")

    return parser


async def _weather_scan(args: argparse.Namespace, db_path: Path) -> dict[str, object]:
    init_db(db_path)
    repo = Repository(db_path)
    settings = weather_settings_from_env()
    min_edge = args.min_edge if args.min_edge is not None else settings.min_edge
    max_spread = args.max_spread if args.max_spread is not None else settings.max_spread
    risk_limits = RiskLimits(
        bankroll_usd=settings.bankroll_usd,
        max_trade_usd=settings.max_trade_usd,
        max_market_usd=settings.max_market_usd,
    )

    poly = PolymarketClient(settings.gamma_base_url, settings.clob_base_url)
    weather = OpenMeteoClient(settings.open_meteo_ensemble_url, model=settings.open_meteo_model)
    parser = WeatherMarketParser()
    observed_at = utc_now_iso()
    markets = await _fetch_weather_source_markets(poly, args.source, args.limit, args.offset)

    parsed = 0
    forecasted = 0
    signals = 0
    paper_orders = 0
    skipped: dict[str, int] = {}

    for market in markets:
        condition_id = market.condition_id
        if not condition_id:
            _bump(skipped, "missing_condition_id")
            continue
        try:
            repo.save_market_bundle([normalize_market(market.raw, observed_at=observed_at)])
        except ValueError:
            _bump(skipped, "normalize_failed")

        attempt = parser.parse_with_reason(market.title)
        if attempt.spec is None:
            _bump(skipped, attempt.reason)
            continue
        spec = attempt.spec
        if spec.location is None:
            _bump(skipped, "unknown_location")
            continue
        if spec.confidence < args.min_confidence:
            _bump(skipped, "low_confidence")
            continue
        repo.save_weather_market_spec(condition_id, spec)
        parsed += 1
        if spec.event_date < date.today():
            _bump(skipped, "stale_event_date")
            continue

        yes_token = market.token_for_outcome("Yes")
        no_token = market.token_for_outcome("No")
        if not market.enable_order_book or not yes_token:
            _bump(skipped, "no_order_book")
            continue

        try:
            forecast = await weather.fetch_forecast(spec, market_id=condition_id)
        except Exception:
            _bump(skipped, "forecast_fetch_failed")
            continue
        repo.save_weather_forecast(condition_id, forecast)

        try:
            yes_book = await poly.fetch_order_book(yes_token, outcome="Yes")
            no_book = await poly.fetch_order_book(no_token, outcome="No") if no_token else None
        except Exception:
            _bump(skipped, "order_book_fetch_failed")
            continue

        repo.save_weather_order_book(condition_id, yes_book)
        if no_book:
            repo.save_weather_order_book(condition_id, no_book)
        forecasted += 1

        signal = build_signal(
            market,
            spec,
            forecast,
            yes_book,
            no_book,
            min_edge=min_edge,
            max_spread=max_spread,
            risk_limits=risk_limits,
        )
        if signal is None:
            _bump(skipped, "no_signal")
            continue

        signal_id = repo.save_weather_signal(signal)
        signals += 1
        if not args.no_paper:
            order = PaperOrder(
                signal_id=signal_id,
                market_id=signal.market_id,
                title=signal.title,
                side=signal.side,
                price=signal.price,
                quantity=paper_order_quantity(signal.suggested_stake_usd, signal.price),
                stake_usd=signal.suggested_stake_usd,
            )
            repo.save_weather_paper_order(order)
            paper_orders += 1

    return {
        "markets_seen": len(markets),
        "parsed": parsed,
        "forecasted": forecasted,
        "signals": signals,
        "paper_orders": paper_orders,
        "skipped": skipped,
    }


async def _weather_audit_titles(args: argparse.Namespace, db_path: Path) -> dict[str, object]:
    init_db(db_path)
    repo = Repository(db_path)
    settings = weather_settings_from_env()
    poly = PolymarketClient(settings.gamma_base_url, settings.clob_base_url)
    parser = WeatherMarketParser()
    observed_at = utc_now_iso()
    markets = await _fetch_weather_source_markets(poly, args.source, args.limit, args.offset)

    parsed = 0
    reasons: dict[str, int] = {}
    examples: list[dict[str, object]] = []
    for market in markets:
        if market.raw:
            try:
                repo.save_market_bundle([normalize_market(market.raw, observed_at=observed_at)])
            except ValueError:
                pass

        attempt = parser.parse_with_reason(market.title)
        _bump(reasons, attempt.reason)
        if attempt.parsed:
            parsed += 1
        if len(examples) >= args.examples:
            continue
        if attempt.parsed and not args.include_parsed:
            continue

        item: dict[str, object] = {
            "condition_id": market.condition_id,
            "title": market.title,
            "parsed": attempt.parsed,
            "reason": attempt.reason,
        }
        if attempt.spec:
            item.update(
                {
                    "city": attempt.spec.city,
                    "event_date": attempt.spec.event_date.isoformat(),
                    "metric": attempt.spec.metric.value,
                    "comparator": attempt.spec.comparator.value,
                    "threshold": str(attempt.spec.threshold),
                    "unit": attempt.spec.unit,
                    "confidence": str(attempt.spec.confidence),
                    "notes": attempt.spec.notes,
                }
            )
        examples.append(item)

    return {
        "source": args.source,
        "markets_seen": len(markets),
        "parsed": parsed,
        "unparsed": len(markets) - parsed,
        "reasons": reasons,
        "examples": examples,
    }


async def _weather_sync_settlements(args: argparse.Namespace, db_path: Path) -> dict[str, object]:
    init_db(db_path)
    repo = Repository(db_path)
    settings = weather_settings_from_env()
    poly = PolymarketClient(settings.gamma_base_url, settings.clob_base_url)
    observed_at = utc_now_iso()

    if args.recent_closed:
        markets = await poly.fetch_closed_markets(limit=args.limit)
    else:
        condition_ids = repo.unsettled_weather_condition_ids(limit=args.limit)
        markets = []
        for condition_id in condition_ids:
            market = await poly.fetch_closed_market_by_condition(condition_id)
            if market:
                markets.append(market)

    saved = 0
    ambiguous = 0
    for market in markets:
        try:
            repo.save_market_bundle([normalize_market(market.raw, observed_at=observed_at)])
        except ValueError:
            pass
        settlement = infer_market_settlement(market.raw)
        if settlement is None:
            ambiguous += 1
            continue
        repo.save_market_settlement(settlement)
        saved += 1

    return {
        "markets_checked": len(markets),
        "settlements_saved": saved,
        "ambiguous_or_unresolved": ambiguous,
    }


async def _fetch_weather_source_markets(
    poly: PolymarketClient, source: str, limit: int, offset: int = 0
) -> list[RawMarket]:
    markets = []
    if source in {"keyword", "both"}:
        markets.extend(await poly.fetch_weather_markets(limit=limit, offset=offset))
    if source in {"weather-tag", "both"}:
        markets.extend(await poly.fetch_weather_tagged_markets(limit=limit))
    return _dedupe_markets(markets)


def _dedupe_markets(markets: list[RawMarket]) -> list[RawMarket]:
    seen: set[str] = set()
    deduped = []
    for market in markets:
        key = market.condition_id or market.market_id
        if key in seen:
            continue
        seen.add(key)
        deduped.append(market)
    return deduped


def _bump(counts: dict[str, int], key: str) -> None:
    counts[key] = counts.get(key, 0) + 1


def main(argv: list[str] | None = None) -> None:
    parser = build_parser()
    args = parser.parse_args(argv)
    db_path = _db_path(args)

    if args.command == "init-db":
        init_db(db_path)
        _print_json({"status": "ok", "db_path": str(db_path)})
        return

    if args.command == "export-markets":
        init_db(db_path)
        print(Repository(db_path).export_markets_json(limit=args.limit))
        return

    if args.command == "serve":
        os.environ["PWMK_DB_PATH"] = str(db_path)
        init_db(db_path)
        import uvicorn

        uvicorn.run(
            "pwmk.api.app:create_app",
            factory=True,
            host=args.host,
            port=args.port,
            reload=args.reload,
        )
        return

    if args.command == "ingest":
        if args.ingest_command == "poll":
            result = asyncio.run(
                poll_once(
                    db_path,
                    limit=args.limit,
                    page_size=args.page_size,
                    live_events=args.live_events,
                    include_live_volume=not args.skip_live_volume,
                )
            )
            _print_json(result.as_dict())
            return

        if args.ingest_command == "loop":
            asyncio.run(
                poll_loop(
                    db_path,
                    limit=args.limit,
                    interval=args.interval,
                    live_events=args.live_events,
                )
            )
            return

        if args.ingest_command == "stream":
            result = asyncio.run(
                stream_trades(
                    db_path,
                    asset_limit=args.asset_limit,
                    duration=args.duration,
                    bootstrap_limit=args.bootstrap_limit,
                )
            )
            _print_json(result.as_dict())
            return

    if args.command == "weather":
        if args.weather_command == "parse-title":
            spec = WeatherMarketParser().parse(args.title)
            if spec is None:
                _print_json({"status": "error", "error": "could_not_parse"})
                raise SystemExit(1)
            _print_json(json.loads(spec.model_dump_json()))
            return

        if args.weather_command == "scan":
            _print_json(asyncio.run(_weather_scan(args, db_path)))
            return

        if args.weather_command == "audit-titles":
            _print_json(asyncio.run(_weather_audit_titles(args, db_path)))
            return

        if args.weather_command == "signals":
            init_db(db_path)
            _print_json(Repository(db_path).recent_weather_signals(limit=args.limit))
            return

        if args.weather_command == "settlements":
            init_db(db_path)
            _print_json(Repository(db_path).recent_settlements(limit=args.limit))
            return

        if args.weather_command == "sync-settlements":
            _print_json(asyncio.run(_weather_sync_settlements(args, db_path)))
            return

        if args.weather_command == "calibration":
            init_db(db_path)
            _print_json(Repository(db_path).weather_calibration_report())
            return

    parser.error("Unhandled command")


if __name__ == "__main__":
    main()
