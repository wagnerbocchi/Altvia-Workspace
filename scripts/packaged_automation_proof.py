"""Actual packaged assignment/recovery proof with synthetic, disjoint scopes."""

import json
import time
from uuid import uuid4

import httpx
from packaged_ticket_work_proof import _activity, _detail

TEAM_GRANT = """
import json,sys
from uuid import UUID
from sqlalchemy.orm import Session
from altvia.config import DatabaseSettings
from altvia.database import make_engine
from altvia.management import set_team_role
p=json.load(sys.stdin)
s=DatabaseSettings()
e=make_engine(s)
assert e.url.database=='altvia_test'
with Session(e) as db,db.begin():
    set_team_role(db,p['email'],UUID(p['team_id']),'operations_manager',True)
"""

PUBLISH = """
import json
from datetime import UTC,datetime
from sqlalchemy import select
from sqlalchemy.orm import Session
from altvia.config import WorkerSettings
from altvia.database import make_engine
from altvia.models import AutomationExecution
from altvia.worker import build_worker,dispatch_assignment_once
s=WorkerSettings();e=make_engine(s,worker_timeouts=True)
assert e.url.database=='altvia_test' and e.url.username=='altvia_worker'
b,w,_=build_worker(e,s,accounts={})
sent=dispatch_assignment_once(e,b,datetime.now(UTC))
with Session(e) as db:
    rows=[{'id':str(r.id),'attempts':r.attempts,'state':r.state}
          for r in db.scalars(select(AutomationExecution))]
print(json.dumps({'sent':sent,'queued':b.do_qsize('automation'),'rows':rows}))
b.close();e.dispose()
"""

BROKER_EMPTY = """
from altvia.config import WorkerSettings
from altvia.database import make_engine
from altvia.worker import build_worker
s=WorkerSettings();e=make_engine(s,worker_timeouts=True)
b,w,_=build_worker(e,s,accounts={})
assert b.do_qsize('automation')==0
b.close();e.dispose()
"""

COUNTS = """
import json,sys
from uuid import UUID
from sqlalchemy import select,func
from sqlalchemy.orm import Session
from altvia.config import DatabaseSettings
from altvia.database import make_engine
from altvia.models import (AutomationExecution,AutomationEffect,OutboxEvent,
                          ActivityEvent,WorkItem,TicketWorkItem)
p=json.load(sys.stdin);client=UUID(p['client_id']);rule=UUID(p['rule_id'])
e=make_engine(DatabaseSettings());assert e.url.database=='altvia_test'
with Session(e) as db:
    executions=[{'id':str(r.id),'ticket_id':str(r.ticket_id),'state':r.state,
                 'attempts':r.attempts} for r in db.scalars(
                     select(AutomationExecution).where(AutomationExecution.rule_id==rule))]
    events=list(db.scalars(select(OutboxEvent).where(
        OutboxEvent.schema_version==2,
        OutboxEvent.payload['execution_id'].astext.in_([r['id'] for r in executions]))))
    projected={str(r.event_id):db.scalar(select(func.count()).select_from(ActivityEvent)
               .where(ActivityEvent.event_id==r.event_id)) for r in events}
    print(json.dumps({'executions':executions,
        'effect_count':db.scalar(select(func.count()).select_from(AutomationEffect)
                                .where(AutomationEffect.rule_id==rule)),
        'work_count':db.scalar(select(func.count()).select_from(WorkItem)
                              .where(WorkItem.project_id==UUID(p['project_id']))),
        'link_count':db.scalar(select(func.count()).select_from(TicketWorkItem)
                              .where(TicketWorkItem.client_id==client)),
        'schema2_types':sorted(r.event_type for r in events),
        'projected_count_by_event':projected}))
"""


def _login(client, body):
    response = client.post("/api/v1/auth/sessions", json=body)
    assert response.status_code == 201
    client.headers["X-CSRF-Token"] = response.json()["csrf_token"]


def _intent(version):
    return {"If-Match": f'"{version}"', "Idempotency-Key": uuid4().hex}


def _post(client, path, body):
    response = client.post(path, json=body, headers={"Idempotency-Key": uuid4().hex})
    assert response.status_code == 201, (path, response.status_code)
    return response.json()


def _rule_patch(client, path, **body):
    current = _detail(client, path)
    response = client.patch(
        path,
        json=body,
        headers={
            **_intent(current["version"]),
            "If-Match-Queue": f'"{current["queue_version"]}"',
        },
    )
    assert response.status_code == 200
    return _detail(client, path)


def _run_python(run, compose, service, code, payload=None):
    return run(
        [*compose, "run", "--rm", "--no-deps", "-T", service, "python", "-c", code],
        data=json.dumps(payload) if payload is not None else None,
    )


def _client(origin, secret_dir):
    return httpx.Client(
        base_url=origin,
        verify=str(secret_dir / "tls_cert"),
        headers={"Origin": origin},
        timeout=15,
        trust_env=False,
    )


def prepare_automation(run, compose, origin, secret_dir, password, team_id, area_id):
    """Use real APIs; only explicit synthetic team metadata uses the owner tool."""
    login = {"email": "automation-packaged@example.test", "password": password}
    with _client(origin, secret_dir) as admin:
        _login(admin, {"email": "admin@example.test", "password": password})
        actor = _post(admin, "/api/v1/users", {**login, "display_name": "Automation proof"})
        customer = _post(
            admin,
            "/api/v1/clients",
            {"name": "Automation proof customer", "manager_user_id": actor["id"]},
        )["client_id"]
        project = _post(
            admin,
            "/api/v1/projects",
            {
                "name": "Automation proof project",
                "scope_kind": "client",
                "client_id": customer,
                "team_id": team_id,
                "operational_area_id": area_id,
                "manager_user_id": actor["id"],
            },
        )["project_id"]
        queue = _post(
            admin, "/api/v1/ticket-queues", {"name": "Automation proof queue", "team_id": team_id}
        )["queue_id"]
        queue_path = "/api/v1/ticket-queues/" + queue
        granted = admin.post(
            queue_path + "/members",
            json={"email": login["email"], "role_name": "operations_manager"},
            headers=_intent(_detail(admin, queue_path)["version"]),
        )
        assert granted.status_code == 201
    _run_python(run, compose, "migrate", TEAM_GRANT, {"email": login["email"], "team_id": team_id})
    run([*compose, "stop", "-t", "30", "worker"])
    with _client(origin, secret_dir) as client:
        _login(client, login)
        customer_path = "/api/v1/clients/" + customer
        response = client.patch(
            customer_path,
            json={"default_project_id": project},
            headers=_intent(_detail(client, customer_path)["version"]),
        )
        assert response.status_code == 200
        contact = _post(
            client,
            customer_path + "/contacts",
            {"display_name": "Automation requester", "email": "automation-proof@example.test"},
        )["contact_id"]
        body = {
            "queue_id": queue,
            "client_id": customer,
            "requester_id": contact,
            "subject": "Synthetic private source, never copied",
            "description": "Synthetic private ticket content",
            "priority": "high",
            "assignee_id": actor["id"],
        }
        no_rule = _post(client, "/api/v1/tickets", body)["ticket_id"]
        collection = queue_path + "/automation-rules"
        response = client.post(
            collection,
            json={
                "client_id": customer,
                "title": "Synthetic configured task",
                "priority": "medium",
                "ticket_statuses": ["new", "open"],
            },
            headers=_intent(_detail(client, queue_path)["version"]),
        )
        assert response.status_code == 201
        rule_id = response.json()["rule_id"]
        rule_path = collection + "/" + rule_id
        assert _detail(client, rule_path)["enabled"] is False
        disabled = _post(client, "/api/v1/tickets", body)["ticket_id"]
        for identifier in (no_rule, disabled):
            assert _detail(client, f"/api/v1/tickets/{identifier}/automation-executions") == {
                "items": [],
                "next_cursor": None,
            }
        _rule_patch(client, rule_path, enabled=True)
        fenced = _post(client, "/api/v1/tickets", body)["ticket_id"]
        first = json.loads(_run_python(run, compose, "worker", PUBLISH))
        assert first["sent"] == 1 and first["queued"] == 1
        assert len(first["rows"]) == 1
        assert first["rows"][0]["state"] == "processing" and first["rows"][0]["attempts"] == 1
        floor = _rule_patch(client, rule_path, enabled=False)["cancelled_through_version"]
        assert _rule_patch(client, rule_path, enabled=True)["cancelled_through_version"] == floor
        headers = {"Idempotency-Key": uuid4().hex}
        response = client.post("/api/v1/tickets", json=body, headers=headers)
        assert response.status_code == 201
        ticket = response.json()["ticket_id"]
        second = json.loads(_run_python(run, compose, "worker", PUBLISH))
        assert second["sent"] == 1 and second["queued"] == 2
        assert len(second["rows"]) == 2
        assert all(r["state"] == "processing" and r["attempts"] == 1 for r in second["rows"])
    # Redis has no durable volume. Recreating it loses actual published messages;
    # the database leases, rather than artificial due-time updates, own recovery.
    run([*compose, "up", "-d", "--no-deps", "--no-build", "--force-recreate", "redis"])
    _run_python(run, compose, "worker", BROKER_EMPTY)
    return {
        "login": login,
        "actor_id": actor["id"],
        "client_id": customer,
        "project_id": project,
        "queue_id": queue,
        "rule_id": rule_id,
        "ticket_id": ticket,
        "fenced_ticket_id": fenced,
        "disabled_ticket_ids": [no_rule, disabled],
        "rule_path": rule_path,
        "create_body": body,
        "create_headers": headers,
        "published_before_loss": second,
    }


def finish_automation(run, compose, origin, secret_dir, proof, work):
    """Called after API/PostgreSQL recreation, before unrelated owner mutations."""
    run([*compose, "up", "-d", "--no-deps", "--no-build", "--force-recreate", "worker"])
    ticket_path = "/api/v1/tickets/" + proof["ticket_id"]
    with _client(origin, secret_dir) as client:
        _login(client, proof["login"])
        for _ in range(120):
            rows = _detail(client, ticket_path + "/automation-executions")["items"]
            fenced = _detail(
                client, "/api/v1/tickets/" + proof["fenced_ticket_id"] + "/automation-executions"
            )["items"]
            if (
                len(rows) == len(fenced) == 1
                and rows[0]["state"] == "succeeded"
                and fenced[0]["state"] == "cancelled"
            ):
                break
            time.sleep(0.5)
        else:
            raise RuntimeError("Packaged assignment did not recover persisted leases")
        assert rows[0]["attempts"] == fenced[0]["attempts"] == 2
        assert fenced[0]["error_code"] == "rule_disabled" and fenced[0]["effect"] is None
        effect = rows[0]["effect"]
        assert effect["mode"] == "created" and effect["project_id"] == proof["project_id"]
        for identifier in proof["disabled_ticket_ids"]:
            assert (
                _detail(client, f"/api/v1/tickets/{identifier}/automation-executions")["items"]
                == []
            )
        work_path = "/api/v1/work-items/" + effect["work_item_id"]
        task = _detail(client, work_path)
        assert task["title"] == "Synthetic configured task" and task["description"] == ""
        assert task["owner_id"] == proof["actor_id"] and task["priority"] == "medium"
        assert task["status"] == "todo" and task["due_at"] is None
        assert _detail(client, ticket_path)["priority"] == "high"
        replay = client.post(
            "/api/v1/tickets", json=proof["create_body"], headers=proof["create_headers"]
        )
        assert replay.status_code == 200 and replay.json()["ticket_id"] == proof["ticket_id"]
        for _ in range(60):
            counts = json.loads(_run_python(run, compose, "migrate", COUNTS, proof))
            if len(counts["projected_count_by_event"]) == 3 and set(
                counts["projected_count_by_event"].values()
            ) == {1}:
                break
            time.sleep(0.5)
        else:
            raise RuntimeError("Packaged schema2 activity did not project exactly once")
        assert counts["effect_count"] == counts["work_count"] == counts["link_count"] == 1
        assert counts["schema2_types"] == [
            "ticket.work_linked",
            "work_item.created",
            "work_item.ticket_linked",
        ]
        before_events = counts["projected_count_by_event"]
        source = _detail(client, ticket_path)
        removed = client.delete(
            ticket_path + "/work-items/" + effect["work_item_id"],
            headers={**_intent(source["version"]), "If-Match-Work-Item": f'"{task["version"]}"'},
        )
        assert removed.status_code == 204
        task_after_unlink = _detail(client, work_path)
        _rule_patch(client, proof["rule_path"], title="Later configured title", priority="critical")
        customer_path = "/api/v1/clients/" + proof["client_id"]
        cleared = client.patch(
            customer_path,
            json={"default_project_id": None},
            headers=_intent(_detail(client, customer_path)["version"]),
        )
        assert cleared.status_code == 200
        for assignee in (None, proof["actor_id"]):
            changed = client.patch(
                ticket_path,
                json={"assignee_id": assignee},
                headers=_intent(_detail(client, ticket_path)["version"]),
            )
            assert changed.status_code == 200
        for _ in range(80):
            later = _detail(client, ticket_path + "/automation-executions")["items"]
            if len(later) == 2 and all(row["state"] == "succeeded" for row in later):
                break
            time.sleep(0.5)
        else:
            raise RuntimeError("Packaged retained effect was not reused")
        assert all(row["effect"] == effect for row in later)
        assert _detail(client, work_path) == task_after_unlink
        assert _detail(client, ticket_path + "/work-items")["items"] == []
        replay = client.post(
            "/api/v1/tickets", json=proof["create_body"], headers=proof["create_headers"]
        )
        assert replay.status_code == 200
        assert _detail(client, ticket_path + "/work-items")["items"] == []
        # The same account remains a project/client manager but loses ticket scope.
        # Queue/team configuration authority must not disclose customer content.
        with _client(origin, secret_dir) as admin:
            _login(admin, {"email": "admin@example.test", "password": proof["login"]["password"]})
            queue_path = "/api/v1/ticket-queues/" + proof["queue_id"]
            revoked = admin.delete(
                queue_path + "/members/" + proof["actor_id"],
                headers=_intent(_detail(admin, queue_path)["version"]),
            )
            assert revoked.status_code == 204
        assert client.get(work_path).status_code == 401
        _login(client, proof["login"])
        assert client.get(ticket_path).status_code == 404
        assert client.get(ticket_path + "/automation-executions").status_code == 404
        assert _detail(client, work_path) == task_after_unlink
        visible = _activity(client, work_path)
        assert len(visible) == 1 and visible[0]["event_type"] == "work_item.created"
        assert visible[0]["actor_kind"] == "automation" and visible[0]["actor_id"] is None
        hidden = [
            proof["ticket_id"],
            *(row["id"] for row in later),
            *(row["source_event_id"] for row in later),
        ]
        assert all(identifier not in json.dumps(visible) for identifier in hidden)
        complete = _detail(client, work_path + "/activity?limit=1")
        assert complete["items"] == visible and complete["next_cursor"] is None
        assert _detail(client, work_path + "/tickets") == {"items": [], "next_cursor": None}
    final = json.loads(_run_python(run, compose, "migrate", COUNTS, proof))
    assert final["effect_count"] == final["work_count"] == 1 and final["link_count"] == 0
    assert final["projected_count_by_event"] == before_events
    (work / "assignment-automation-proof.json").write_text(
        json.dumps(
            {
                "synthetic_only": True,
                "redis_messages_lost": 2,
                "actual_lease_recovery": True,
                "disabled_no_scan": True,
                "off_on_floor": True,
                "create_replay": True,
                "unlink_rule_edit_default_clear_reassignment": True,
                "old_session_status": 401,
                "fresh_ticket_status": 404,
                "work_only_truthful_activity": True,
                **final,
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
