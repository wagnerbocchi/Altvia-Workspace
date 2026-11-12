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
from redis.backoff import NoBackoff
from redis.exceptions import RedisError
from redis.retry import Retry
from sqlalchemy import Engine, func, or_, select, text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from altvia import attachment_scan, mail_delivery
from altvia.activity import CONSUMER, claim_events, consume_event, publication_failed, replay_event
from altvia.config import WorkerSettings
from altvia.database import make_engine
from altvia.file_scan_transport import ClamClient
from altvia.file_settings import ScannerSettings
from altvia.file_storage import S3Store
from altvia.file_storage_owner import load_storage
from altvia.mail_settings import SMTPAccount, load_accounts
from altvia.models import Attachment, OutboundMessage, OutboxEvent
from altvia.observability import configure_logging
from altvia.smtp_transport import ActiveTransports, deliver_once

LOGGER = logging.getLogger("altvia.worker")


def build_worker(
    engine: Engine,
    settings: WorkerSettings,
    *,
    accounts: dict[UUID, SMTPAccount] | None = None,
    active: ActiveTransports | None = None,
    file_storage: S3Store | None = None,
    file_scanner: ClamClient | None = None,
    stop: Event | None = None,
) -> tuple[RedisBroker, Worker, Actor[[str], None]]:
    accounts = (
        accounts
        if accounts is not None
        else (load_accounts(settings.smtp_accounts_file) if settings.smtp_accounts_file else {})
    )
    active = active or ActiveTransports()
    # Dramatiq's typed distribution leaves this constructor unannotated.
    broker = RedisBroker(  # type: ignore[no-untyped-call]
        url=settings.redis_url.get_secret_value(),
        namespace="altvia",
        middleware=[Retries(max_retries=0)],
        socket_connect_timeout=1,
        socket_timeout=2,
        retry=Retry(NoBackoff(), 0),
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
    queues = {"identity"}
    if accounts:

        def send_mail(delivery_id: str) -> None:
            try:
                identifier = UUID(delivery_id)
            except (TypeError, ValueError, AttributeError):
                LOGGER.warning("", extra={"event_code": "invalid_message"})
                return
            try:
                deliver_once(engine, identifier, accounts, active=active)
            except SQLAlchemyError:
                # Persisted stage/expiry owns restart recovery; no broker retry.
                LOGGER.error("", extra={"event_code": "mail_database_unavailable"})

        actor(broker=broker, actor_name="mail_delivery", queue_name="mail", max_retries=0)(
            send_mail
        )
        queues.add("mail")
    if file_storage is not None and file_scanner is not None:
        file_stop = stop if stop is not None else Event()

        def scan_file(file_id: str) -> None:
            try:
                identifier = UUID(file_id)
            except (TypeError, ValueError, AttributeError):
                LOGGER.warning("", extra={"event_code": "invalid_message"})
                return
            try:
                attachment_scan.scan_once(engine, identifier, file_storage, file_scanner, file_stop)
            except SQLAlchemyError:
                LOGGER.error("", extra={"event_code": "file_database_unavailable"})

        actor(broker=broker, actor_name="file_scan", queue_name="files", max_retries=0)(scan_file)
        queues.add("files")
    return broker, Worker(broker, queues=queues, worker_threads=2), registered


def dispatch_mail_once(
    engine: Engine,
    broker: RedisBroker,
    accounts: dict[UUID, SMTPAccount],
    stop: Event | None = None,
) -> int:
    if stop is not None and stop.is_set():
        return 0
    mail_delivery.recover(engine)
    if not accounts:
        return 0
    # One short global publication window and a finite broker backlog. The
    # broker's own queue-size command includes outstanding acknowledgements.
    if not broker.client.set("altvia:mail:publisher", "1", nx=True, ex=10):
        return 0
    size = int(broker.do_qsize("mail"))
    capacity = max(0, min(2, 8 - size))
    if not capacity:
        return 0
    with Session(engine) as db:
        identifiers = list(
            db.scalars(
                select(OutboundMessage.id)
                .where(
                    OutboundMessage.state == "queued",
                    OutboundMessage.attempts < 8,
                    or_(
                        *(
                            (OutboundMessage.source_id == identifier)
                            & (OutboundMessage.namespace_hash == account.namespace_hash)
                            for identifier, account in accounts.items()
                        )
                    ),
                    OutboundMessage.next_attempt_at <= func.clock_timestamp(),
                )
                .order_by(OutboundMessage.next_attempt_at, OutboundMessage.id)
                .limit(capacity)
            )
        )
    registered = broker.get_actor("mail_delivery")
    sent = 0
    for identifier in identifiers:
        if stop is not None and stop.is_set():
            break
        registered.send(str(identifier))
        sent += 1
    return sent


def dispatch_file_once(engine: Engine, broker: RedisBroker, stop: Event | None = None) -> int:
    if stop is not None and stop.is_set():
        return 0
    attachment_scan.recover(engine)
    if "file_scan" not in broker.actors:
        return 0
    if not broker.client.set("altvia:file:publisher", "1", nx=True, ex=10):
        return 0
    capacity = max(0, min(2, 8 - int(broker.do_qsize("files"))))
    if not capacity:
        return 0
    with Session(engine) as db:
        identifiers = list(
            db.scalars(
                select(Attachment.id)
                .where(
                    Attachment.state == "quarantine",
                    Attachment.attempts < 8,
                    Attachment.next_attempt_at <= func.clock_timestamp(),
                )
                .order_by(Attachment.next_attempt_at, Attachment.id)
                .limit(capacity)
            )
        )
    registered = broker.get_actor("file_scan")
    count = 0
    for identifier in identifiers:
        if stop is not None and stop.is_set():
            break
        registered.send(str(identifier))
        count += 1
    return count


def dispatch_once(
    engine: Engine, registered: Actor[[str], None], now: datetime, stop: Event | None = None
) -> int:
    sent = 0
    if stop is not None and stop.is_set():
        return sent
    for event_id, lease in claim_events(engine, now):
        if stop is not None and stop.is_set():
            # Unsubmitted claims retain their leases and are recovered after expiry.
            break
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
    active = ActiveTransports()
    stop = Event()
    file_storage = None
    try:
        settings = WorkerSettings()
        accounts = load_accounts(settings.smtp_accounts_file) if settings.smtp_accounts_file else {}
        engine = make_engine(settings, worker_timeouts=True)
        file_storage = (
            S3Store(load_storage(settings.scanner_storage_file))
            if settings.scanner_storage_file is not None
            else None
        )
        file_scanner = ClamClient(ScannerSettings(socket_path=settings.scanner_socket))
        broker, worker, registered = build_worker(
            engine,
            settings,
            accounts=accounts,
            active=active,
            file_storage=file_storage,
            file_scanner=file_scanner,
            stop=stop,
        )
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
        settings.worker_state_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
        for name in (signal.SIGTERM, signal.SIGINT):
            signal.signal(name, lambda _signum, _frame: stop.set())
        worker.start()
        LOGGER.info("", extra={"event_code": "worker_started"})
        while not stop.is_set():
            try:
                count = dispatch_once(engine, registered, datetime.now(UTC), stop)
                count += dispatch_mail_once(engine, broker, accounts, stop)
                count += dispatch_file_once(engine, broker, stop)
                if stop.is_set():
                    break
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
        # Dramatiq applies this budget separately to worker and consumer joins.
        # Leave room within Compose's 30s grace for bounded broker I/O as well.
        active.cancel()
        worker.stop(timeout=5000)
        worker = None
        LOGGER.info("", extra={"event_code": "worker_stopped"})
        return 0
    except (RedisError, SQLAlchemyError, ValidationError, ValueError, OSError):
        LOGGER.error("", extra={"event_code": "worker_configuration_or_dependency_failure"})
        return 1
    finally:
        stop.set()
        active.cancel()
        if worker is not None and worker.workers:
            worker.stop(timeout=5000)
        if file_storage is not None:
            file_storage.close()
        if broker is not None:
            broker.client.close()
        if engine is not None:
            engine.dispose()


if __name__ == "__main__":
    raise SystemExit(main())
