"""JSON-only identity worker, durable dispatcher and restricted recovery commands."""

import argparse
import logging
import signal
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from threading import Event
from uuid import UUID

from dramatiq import Actor, actor
from dramatiq.brokers.redis import RedisBroker
from dramatiq.middleware import Retries
from dramatiq.worker import Worker
from pydantic import ValidationError
from redis.exceptions import RedisError
from sqlalchemy import Engine, func, select, text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from altvia.activity import CONSUMER, claim_events, consume_event, publication_failed, replay_event
from altvia.config import WorkerSettings
from altvia.database import make_engine
from altvia.models import OutboxEvent
from altvia.observability import configure_logging

LOGGER = logging.getLogger("altvia.worker")


def build_worker(
    engine: Engine, settings: WorkerSettings
) -> tuple[RedisBroker, Worker, Actor[[str], None]]:
    # Dramatiq's typed distribution leaves this constructor unannotated.
    broker = RedisBroker(  # type: ignore[no-untyped-call]
        url=settings.redis_url.get_secret_value(),
        namespace="altvia",
        middleware=[Retries(max_retries=0)],
        socket_connect_timeout=3,
        socket_timeout=5,
    )

    def project_identity(event_id: str) -> None:
        try:
            identifier = UUID(event_id)
        except (TypeError, ValueError, AttributeError):
            LOGGER.warning("", extra={"event_code": "invalid_message"})
            return
        try:
            changed = consume_event(engine, identifier, datetime.now(UTC))
            LOGGER.info(
                "",
                extra={
                    "event_code": "activity_projected" if changed else "delivery_reconciled",
                    "event_id": str(identifier),
                },
            )
        except SQLAlchemyError:
            # No broker-side retry can replace an uncommitted database effect.
            # The outstanding durable lease expires and is republished.
            LOGGER.error(
                "",
                extra={
                    "event_code": "projection_database_unavailable",
                    "event_id": str(identifier),
                },
            )

    registered = actor(broker=broker, actor_name=CONSUMER, queue_name="identity", max_retries=0)(
        project_identity
    )
    return broker, Worker(broker, queues={"identity"}, worker_threads=2), registered


def dispatch_once(engine: Engine, registered: Actor[[str], None], now: datetime) -> int:
    sent = 0
    for event_id, lease in claim_events(engine, now):
        try:
            registered.send(str(event_id))
            sent += 1
        except RedisError:
            publication_failed(engine, event_id, lease, now, "broker_unavailable")
            LOGGER.warning(
                "", extra={"event_code": "broker_unavailable", "event_id": str(event_id)}
            )
    return sent


def healthy(engine: Engine, broker: RedisBroker, heartbeat: Path) -> bool:
    if not heartbeat.is_file() or not 0 <= time.time() - heartbeat.stat().st_mtime < 30:
        return False
    with engine.connect() as connection:
        connection.execute(text("SELECT 1"))
    return bool(broker.client.ping())


def main() -> int:
    parser = argparse.ArgumentParser(description="Identity activity worker and restricted recovery")
    parser.add_argument(
        "command", choices=("run", "health", "status", "replay"), nargs="?", default="run"
    )
    parser.add_argument("--event-id", type=UUID)
    args = parser.parse_args()
    configure_logging()
    engine = None
    broker = None
    worker = None
    try:
        settings = WorkerSettings()
        engine = make_engine(settings)
        broker, worker, registered = build_worker(engine, settings)
        heartbeat = settings.worker_state_dir / "heartbeat"
        if args.command == "health":
            return 0 if healthy(engine, broker, heartbeat) else 1
        if args.command == "status":
            with Session(engine) as db:
                counts = {
                    row[0]: row[1]
                    for row in db.execute(
                        select(OutboxEvent.status, func.count()).group_by(OutboxEvent.status)
                    ).all()
                }
            for status, count in counts.items():
                LOGGER.info("", extra={"event_code": "outbox_" + status, "count": count})
            return 0
        if args.command == "replay":
            if args.event_id is None or not sys.stdin.isatty() or not sys.stdout.isatty():
                LOGGER.error("", extra={"event_code": "interactive_uuid_confirmation_required"})
                return 1
            if input(f"Type {args.event_id} to replay this dead event: ") != str(args.event_id):
                return 1
            return 0 if replay_event(engine, args.event_id, datetime.now(UTC)) else 1
        stop = Event()
        settings.worker_state_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
        for name in (signal.SIGTERM, signal.SIGINT):
            signal.signal(name, lambda _signum, _frame: stop.set())
        worker.start()
        LOGGER.info("", extra={"event_code": "worker_started"})
        while not stop.is_set():
            try:
                count = dispatch_once(engine, registered, datetime.now(UTC))
                if (
                    broker.client.ping()
                    and all(t.is_alive() for t in worker.workers)
                    and all(t.is_alive() for t in worker.consumers.values())
                ):
                    heartbeat.touch()
                if count:
                    LOGGER.info("", extra={"event_code": "events_dispatched", "count": count})
            except (RedisError, SQLAlchemyError):
                LOGGER.error("", extra={"event_code": "worker_dependency_unavailable"})
            stop.wait(1)
        worker.stop(timeout=20000)
        worker = None
        LOGGER.info("", extra={"event_code": "worker_stopped"})
        return 0
    except (RedisError, SQLAlchemyError, ValidationError, ValueError, OSError):
        LOGGER.error("", extra={"event_code": "worker_configuration_or_dependency_failure"})
        return 1
    finally:
        if worker is not None and worker.workers:
            worker.stop(timeout=20000)
        if broker is not None:
            broker.client.close()
        if engine is not None:
            engine.dispose()


if __name__ == "__main__":
    raise SystemExit(main())
