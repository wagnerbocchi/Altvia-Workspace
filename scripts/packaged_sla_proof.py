"""Real installed-image SLA proof in an independent disposable customer/queue."""

import json
import time

from packaged_automation_proof import TEAM_GRANT, _client, _intent, _login, _post, _run_python
from packaged_smtp_proof import prepare_packaged_smtp
from packaged_ticket_work_proof import _detail

COUNTS = """
import json,sys
from uuid import UUID
from sqlalchemy import select,func
from sqlalchemy.orm import Session
from altvia.config import DatabaseSettings
from altvia.database import make_engine
from altvia.models import TicketSlaEvent,TicketSlaAcceptance,ActivityEvent,TicketQueue
p=json.load(sys.stdin);e=make_engine(DatabaseSettings())
assert e.url.database=='altvia_test'
ids=[UUID(i) for i in p['ticket_ids']]
with Session(e) as db:
    queue=db.get(TicketQueue,UUID(p['queue_id']))
    assert queue is not None and queue.name=='SLA packaged proof queue'
    events=list(db.scalars(select(TicketSlaEvent).where(TicketSlaEvent.ticket_id.in_(ids))))
    rows=[{'id':str(r.event_id),'ticket_id':str(r.ticket_id),'cycle':r.cycle_number,
           'goal':r.goal,'kind':r.kind,'outcome':r.outcome,
           'occurred_at':r.occurred_at.isoformat()} for r in events]
    projected={str(r.event_id):db.scalar(select(func.count()).select_from(ActivityEvent)
               .where(ActivityEvent.event_id==r.event_id)) for r in events}
    accepted=db.scalar(select(func.count()).select_from(TicketSlaAcceptance)
                       .where(TicketSlaAcceptance.ticket_id.in_(ids)))
    print(json.dumps({'events':sorted(rows,key=lambda r:r['id']),
                      'projected':projected,'accepted_count':accepted}))
e.dispose()
"""

RECONCILE = """
import json,sys
from datetime import datetime
from uuid import UUID
from sqlalchemy.orm import Session
from altvia.config import DatabaseSettings
from altvia.database import make_engine
from altvia.models import OutboundMessage,TicketQueue
from altvia.mail_delivery import reconcile
p=json.load(sys.stdin);e=make_engine(DatabaseSettings())
assert e.url.database=='altvia_test'
with Session(e) as db,db.begin():
    queue=db.get(TicketQueue,UUID(p['queue_id']))
    assert queue is not None and queue.name=='SLA packaged proof queue'
    row=db.get(OutboundMessage,UUID(p['delivery_id']))
    assert row is not None and str(row.ticket_id)==p['ticket_id']
    reconcile(db,row.id,row.version,'accepted','synthetic-packaged-sla-evidence',
              workers_drained=True,accepted_at=datetime.fromisoformat(p['accepted_at']))
e.dispose()
"""


def _change(client, path, target):
    response = client.post(
        path + "/transitions",
        json={"target_status": target, "reason": "Synthetic packaged SLA lifecycle"},
        headers=_intent(_detail(client, path)["version"]),
    )
    assert response.status_code == 200, (target, response.status_code)


def _wait(client, path, predicate, label, seconds=40):
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        value = _detail(client, path + "/sla")
        if predicate(value):
            return value
        time.sleep(0.5)
    raise RuntimeError("Packaged SLA did not reach " + label)


def _configure(client, queue_path, collection, body):
    result = client.post(
        queue_path + collection,
        json=body,
        headers=_intent(_detail(client, queue_path)["version"]),
    )
    assert result.status_code == 201, (collection, result.status_code)
    return result.json()


def _policy_patch(client, path, body):
    row = _detail(client, path)
    response = client.patch(
        path,
        json=body,
        headers={**_intent(row["version"]), "If-Match-Queue": f'"{row["queue_version"]}"'},
    )
    assert response.status_code == 200
    return _detail(client, path)


def prepare_sla(run, compose, origin, secret_dir, password, team_id, root):
    """Only explicit synthetic configuration; reuse the real verified TLS relay."""
    login = {"email": "sla-packaged@example.test", "password": password}
    with _client(origin, secret_dir) as admin:
        _login(admin, {"email": "admin@example.test", "password": password})
        actor = _post(admin, "/api/v1/users", {**login, "display_name": "SLA proof"})
        customer = _post(
            admin,
            "/api/v1/clients",
            {"name": "SLA packaged proof customer", "manager_user_id": actor["id"]},
        )["client_id"]
        queue = _post(
            admin,
            "/api/v1/ticket-queues",
            {"name": "SLA packaged proof queue", "team_id": team_id},
        )["queue_id"]
        queue_path = "/api/v1/ticket-queues/" + queue
        response = admin.patch(
            queue_path,
            json={"allow_reopen": True},
            headers=_intent(_detail(admin, queue_path)["version"]),
        )
        assert response.status_code == 200
        granted = admin.post(
            queue_path + "/members",
            json={
                "email": login["email"],
                "role_name": "operations_manager",
                "note_access": "write",
            },
            headers=_intent(_detail(admin, queue_path)["version"]),
        )
        assert granted.status_code == 201
    _run_python(run, compose, "migrate", TEAM_GRANT, {"email": login["email"], "team_id": team_id})
    with _client(origin, secret_dir) as client:
        _login(client, login)
        contact = _post(
            client,
            "/api/v1/clients/" + customer + "/contacts",
            {"display_name": "Synthetic SLA requester", "email": "sla-proof@example.test"},
        )["contact_id"]
        calendar_id = _configure(
            client,
            queue_path,
            "/business-calendars",
            {
                "client_id": customer,
                "name": "Synthetic packaged UTC calendar",
                "timezone": "UTC",
                "windows": [
                    {"weekday": day, "start_minute": 0, "end_minute": 1440} for day in range(7)
                ],
                "holidays": [],
                "active": True,
            },
        )["calendar_id"]
        calendar_path = queue_path + "/business-calendars/" + calendar_id
        policy_id = _configure(
            client,
            queue_path,
            "/sla-policies",
            {
                "client_id": customer,
                "name": "Synthetic packaged SLA",
                "calendar_id": calendar_id,
                "calendar_version": 1,
                "first_response_minutes": 2,
                "resolution_minutes": 240,
                "approach_minutes": 0,
                "pause_states": ["pending_customer"],
            },
        )["policy_id"]
        policy_path = queue_path + "/sla-policies/" + policy_id
        assert _detail(client, policy_path)["enabled"] is False
        _policy_patch(client, policy_path, {"enabled": True})
        ticket_body = {
            "queue_id": queue,
            "client_id": customer,
            "requester_id": contact,
            "priority": "critical",
        }
        mail = prepare_packaged_smtp(
            client, ticket_body, run, compose, root, secret_dir, source_key="packaged-sla"
        )
        accepted, lost, held = mail["records"]
        accepted_path = "/api/v1/tickets/" + accepted["ticket_id"]
        _wait(
            client,
            accepted_path,
            lambda r: r["current"]["first_response"]["status"] == "fulfilled",
            "real accepted response",
        )
        lost_path = "/api/v1/tickets/" + lost["ticket_id"]
        held_path = "/api/v1/tickets/" + held["ticket_id"]
        evidence_at = _detail(client, lost_path + "/sla")["observed_at"]
        for path in (lost_path, held_path):
            goal = _detail(client, path + "/sla")["current"]["first_response"]
            assert goal["fulfilled_at"] is None and goal["status"] != "fulfilled"

        # Actual status history and DB time, with no test backdating or fake clock.
        _change(client, accepted_path, "open")
        _change(client, accepted_path, "pending_customer")
        paused = _wait(
            client,
            accepted_path,
            lambda r: r["current"]["resolution"]["status"] == "paused",
            "native pause",
        )["current"]["resolution"]["elapsed_business_seconds"]
        time.sleep(2)
        assert (
            _detail(client, accepted_path + "/sla")["current"]["resolution"][
                "elapsed_business_seconds"
            ]
            == paused
        )
        _change(client, accepted_path, "open")
        _change(client, accepted_path, "resolved")
        _wait(
            client,
            accepted_path,
            lambda r: r["current"]["resolution"]["status"] == "fulfilled",
            "native resolution",
        )

        breached = _wait(
            client,
            lost_path,
            lambda r: r["current"]["first_response"]["status"] == "breached",
            "actual two-minute response breach",
            seconds=160,
        )["current"]["first_response"]["breached_at"]
        assert breached is not None
        _change(client, lost_path, "open")
        _change(client, lost_path, "resolved")
        old = _detail(client, calendar_path)
        response = client.patch(
            calendar_path,
            json={"name": "Synthetic later calendar"},
            headers={**_intent(old["version"]), "If-Match-Queue": f'"{old["queue_version"]}"'},
        )
        assert response.status_code == 200
        latest = _policy_patch(
            client,
            policy_path,
            {"calendar_id": calendar_id, "calendar_version": 2, "first_response_minutes": 60},
        )
        _change(client, lost_path, "open")
        reopened = _detail(client, lost_path + "/sla")
        assert reopened["current"]["number"] == 2
        assert reopened["current"]["policy_version"] == latest["version"]
        assert reopened["current"]["calendar_version"] == 2
        assert reopened["history"][0]["calendar_version"] == 1
    # Drain actual main before the existing owner-only historical evidence command.
    run([*compose, "stop", "-t", "30", "worker"])
    _run_python(
        run,
        compose,
        "migrate",
        RECONCILE,
        {
            "queue_id": queue,
            "ticket_id": lost["ticket_id"],
            "delivery_id": lost["delivery_id"],
            "accepted_at": evidence_at,
        },
    )
    return {
        "login": login,
        "queue_id": queue,
        "ticket_ids": [r["ticket_id"] for r in mail["records"]],
        "accepted_ticket_id": accepted["ticket_id"],
        "corrected_ticket_id": lost["ticket_id"],
        "breached_at": breached,
        "reopened_policy_version": latest["version"],
        "smtp_scenarios": mail["proofs"],
    }


def finish_sla(run, compose, origin, secret_dir, proof, work):
    """Check retained obligations after the actual API/PG/Redis/worker recreation."""
    with _client(origin, secret_dir) as client:
        _login(client, proof["login"])
        path = "/api/v1/tickets/" + proof["corrected_ticket_id"]
        result = _wait(
            client,
            path,
            lambda r: (
                bool(r["history"] and r["history"][0]["first_response"]["corrected"])
                and r["current"]["state"] == "ready"
            ),
            "retained historical correction",
        )
        current, previous = result["current"], result["history"][0]
        assert current["number"] == 2 and current["first_response"]["fulfilled_at"] is None
        assert current["policy_version"] == proof["reopened_policy_version"]
        assert current["calendar_version"] == 2 and previous["calendar_version"] == 1
        assert previous["first_response"]["breached_at"] == proof["breached_at"]
        assert previous["first_response"]["fulfilled_at"] is not None
        accepted = _detail(client, "/api/v1/tickets/" + proof["accepted_ticket_id"] + "/sla")
        assert accepted["current"]["first_response"]["status"] == "fulfilled"
        assert accepted["current"]["resolution"]["status"] == "fulfilled"
    scope = {"queue_id": proof["queue_id"], "ticket_ids": proof["ticket_ids"]}
    for _ in range(60):
        counts = json.loads(_run_python(run, compose, "migrate", COUNTS, scope))
        if counts["events"] and set(counts["projected"].values()) == {1}:
            break
        time.sleep(0.5)
    else:
        raise RuntimeError("Packaged SLA observations were not projected once")
    assert counts["accepted_count"] == 2
    corrected = [r for r in counts["events"] if r["ticket_id"] == proof["corrected_ticket_id"]]
    assert sum(r["cycle"] == 1 and r["kind"] == "corrected" for r in corrected) == 1
    assert (
        sum(
            r["cycle"] == 1 and r["kind"] == "breached" and r["goal"] == "first_response"
            for r in corrected
        )
        == 1
    )
    run(
        [
            *compose,
            "up",
            "-d",
            "--no-deps",
            "--no-build",
            "--force-recreate",
            "--wait",
            "--wait-timeout",
            "90",
            "worker",
        ]
    )
    time.sleep(3)
    repeated = json.loads(_run_python(run, compose, "migrate", COUNTS, scope))
    assert repeated == counts
    (work / "ticket-sla-proof.json").write_text(
        json.dumps(
            {
                "synthetic_only": True,
                "native_time_and_history": True,
                "actual_pause_resolution_reopen": True,
                "api_postgres_redis_worker_recreation": True,
                "late_owner_correction_retains_breach": True,
                "old_response_never_fulfills_reopen": True,
                "recreated_worker_no_duplicate_observation": True,
                "smtp_scenarios": proof["smtp_scenarios"],
                **counts,
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
