"""Real paired persistence and current-ACL proof; returned data has no content/secrets."""

import time
from typing import Any
from uuid import uuid4

import httpx

LINK_EVENTS = {
    "ticket.work_linked",
    "ticket.work_unlinked",
    "work_item.ticket_linked",
    "work_item.ticket_unlinked",
}

# Existing owner-only migrate command consumes IDs on stdin. No runtime grants.
PROJECTION_COUNTS = """
import json,sys
from uuid import UUID
from sqlalchemy import select,func
from sqlalchemy.orm import Session
from altvia.config import DatabaseSettings
from altvia.database import make_engine
from altvia.models import OutboxEvent,ActivityEvent,TicketWorkItem
p=json.load(sys.stdin)
ids=[UUID(value) for value in p['link_event_ids']]
with Session(make_engine(DatabaseSettings())) as db:
    events=list(db.scalars(select(OutboxEvent.event_id).where(OutboxEvent.event_id.in_(ids))))
    assert set(events)==set(ids)
    counts={str(identifier):db.scalar(select(func.count()).select_from(ActivityEvent)
            .where(ActivityEvent.event_id==identifier)) for identifier in ids}
    pairs=[[str(t),str(w)] for t,w in db.execute(select(
        TicketWorkItem.ticket_id,TicketWorkItem.work_item_id).where(
        TicketWorkItem.ticket_id==UUID(p['ticket_id']),
        TicketWorkItem.work_item_id==UUID(p['work_item_id'])))]
    print(json.dumps({'projected_count_by_event':counts,'retained_link_pairs':pairs}))
"""


def _detail(client, path):
    response = client.get(path)
    assert response.status_code == 200
    return response.json()


def _paths(proof):
    return (
        "/api/v1/tickets/" + proof["ticket_id"],
        "/api/v1/work-items/" + proof["work_item_id"],
    )


def _headers(ticket, work, key=None):
    return {
        "If-Match": f'"{ticket}"',
        "If-Match-Work-Item": f'"{work}"',
        "Idempotency-Key": key or uuid4().hex,
    }


def _pair(client, proof, *, present=True):
    ticket_path, work_path = _paths(proof)
    ticket = _detail(client, ticket_path + "/work-items")
    work = _detail(client, work_path + "/tickets")
    assert ticket["next_cursor"] is None and work["next_cursor"] is None
    assert [row["work_item_id"] for row in ticket["items"]] == (
        [proof["work_item_id"]] if present else []
    )
    assert [row["ticket_id"] for row in work["items"]] == ([proof["ticket_id"]] if present else [])
    return [[proof["ticket_id"], proof["work_item_id"]]] if present else []


def _activity(client, path):
    # A one-row page exercises filtering before cursor construction. Reject
    # empty intermediate pages, repeated cursors and unbounded traversal.
    rows, cursors = [], set()
    cursor = None
    for _ in range(20):
        params = {"limit": 1}
        if cursor is not None:
            params["cursor"] = cursor
        response = client.get(path + "/activity", params=params)
        assert response.status_code == 200
        page = response.json()
        assert len(page["items"]) <= 1
        if cursor is not None:
            assert page["items"]
        rows.extend(page["items"])
        cursor = page["next_cursor"]
        if cursor is None:
            assert len({row["event_id"] for row in rows}) == len(rows)
            return rows
        assert page["items"] and cursor not in cursors
        cursors.add(cursor)
    raise RuntimeError("Packaged ticket/work activity exceeded bounded pagination")


def _projected(client, paths, expected):
    for _ in range(60):
        pages = [_activity(client, path) for path in paths]
        if all(len(rows) == count for rows, count in zip(pages, expected, strict=True)):
            return pages
        time.sleep(0.5)
    raise RuntimeError("Packaged ticket/work activity did not project")


def _link_ids(pages):
    return sorted(
        row["event_id"] for rows in pages for row in rows if row["event_type"] in LINK_EVENTS
    )


def _unified(client, proof, statuses, *, linked=True, ticket_visible=True):
    page = _detail(client, "/api/v1/my-work/unified?limit=100")
    assert page["next_cursor"] is None
    expected = {("work_item", proof["work_item_id"])}
    if ticket_visible and not linked:
        expected.add(("ticket", proof["ticket_id"]))
    keys = [(row["kind"], row["id"]) for row in page["items"]]
    assert len(keys) == len(expected) and set(keys) == expected
    work = next(row for row in page["items"] if row["kind"] == "work_item")
    assert work["status"] == statuses[1]
    badges = work["linked_tickets"]
    assert [row["id"] for row in badges] == (
        [proof["ticket_id"]] if linked and ticket_visible else []
    )
    assert work["has_more_linked_tickets"] is False
    if ticket_visible:
        ticket = (
            badges[0] if linked else next(row for row in page["items"] if row["kind"] == "ticket")
        )
        assert ticket["status"] == statuses[0]
    else:
        assert proof["ticket_id"] not in str(page)
    # Only keys/states leave the private proof, never titles, subjects or tokens.
    return {
        "row_keys": sorted(keys),
        "work_status": work["status"],
        "ticket_status": statuses[0] if ticket_visible else None,
        "badge_ticket_ids": [row["id"] for row in badges],
        "has_more_linked_tickets": work["has_more_linked_tickets"],
    }


def prepare_ticket_work(
    client: httpx.Client, ticket_body: dict[str, Any], work_body: dict[str, Any]
) -> dict[str, Any]:
    ticket = client.post(
        "/api/v1/tickets", json=ticket_body, headers={"Idempotency-Key": uuid4().hex}
    )
    work = client.post(
        "/api/v1/work-items", json=work_body, headers={"Idempotency-Key": uuid4().hex}
    )
    assert ticket.status_code == 201 and work.status_code == 201
    proof = {
        "ticket_id": ticket.json()["ticket_id"],
        "work_item_id": work.json()["work_item_id"],
        "queue_id": ticket_body["queue_id"],
        "actor_id": _detail(client, "/api/v1/auth/me")["id"],
    }
    paths = _paths(proof)
    before = [_detail(client, path) for path in paths]
    proof["original_link"] = {
        "operation": "link",
        "key": uuid4().hex,
        "ticket_version": before[0]["version"],
        "work_version": before[1]["version"],
    }
    intent = proof["original_link"]
    response = client.post(
        paths[0] + "/work-items",
        json={"work_item_id": proof["work_item_id"]},
        headers=_headers(intent["ticket_version"], intent["work_version"], intent["key"]),
    )
    assert response.status_code == 201
    assert response.json() == {key: proof[key] for key in ("ticket_id", "work_item_id")}
    proof["before_recreation_link_pairs"] = _pair(client, proof)
    after = [_detail(client, path) for path in paths]
    assert [row["version"] for row in after] == [row["version"] + 1 for row in before]
    assert [row["status"] for row in after] == [row["status"] for row in before]
    proof["versions"] = [row["version"] for row in after]
    proof["statuses"] = [row["status"] for row in after]
    proof["before_recreation_unified"] = _unified(client, proof, proof["statuses"])
    # Assigned ticket creation emits assigned AND created at version one.
    # Wait for all three ticket rows, not the transient two-row prefix.
    initial = _projected(client, paths, [3, 2])
    assert {row["event_type"] for row in initial[0]} == {
        "ticket.created",
        "ticket.assigned",
        "ticket.work_linked",
    }
    assert {row["event_type"] for row in initial[1]} == {
        "work_item.created",
        "work_item.ticket_linked",
    }
    proof["initial_activity_counts"] = [len(rows) for rows in initial]
    proof["initial_link_event_ids"] = _link_ids(initial)
    assert len(proof["initial_link_event_ids"]) == 2
    return proof


def assert_ticket_work(
    client: httpx.Client,
    proof: dict[str, Any],
    *,
    configuration_client: httpx.Client,
    login_body: dict[str, str],
) -> dict[str, Any]:
    paths = _paths(proof)
    assert _detail(client, "/api/v1/auth/me")["id"] == proof["actor_id"]
    current = [_detail(client, path) for path in paths]
    assert [row["version"] for row in current] == proof["versions"]
    assert [row["status"] for row in current] == proof["statuses"]
    pairs = _pair(client, proof)
    assert pairs == proof["before_recreation_link_pairs"]
    restored_unified = _unified(client, proof, proof["statuses"])
    assert restored_unified == proof["before_recreation_unified"]
    assert (
        _link_ids(_projected(client, paths, proof["initial_activity_counts"]))
        == proof["initial_link_event_ids"]
    )
    intent = proof["original_link"]
    replay = client.post(
        paths[0] + "/work-items",
        json={"work_item_id": proof["work_item_id"]},
        headers=_headers(intent["ticket_version"], intent["work_version"], intent["key"]),
    )
    assert replay.status_code == 200
    assert replay.json() == {key: proof[key] for key in ("ticket_id", "work_item_id")}
    assert [_detail(client, path) for path in paths] == current

    unlink_headers = _headers(*proof["versions"])
    unlink_path = paths[0] + "/work-items/" + proof["work_item_id"]
    removed = client.delete(unlink_path, headers=unlink_headers)
    assert removed.status_code == 204 and removed.content == b""
    _pair(client, proof, present=False)
    absent = [_detail(client, path) for path in paths]
    _unified(client, proof, proof["statuses"], linked=False)
    assert [row["version"] for row in absent] == [v + 1 for v in proof["versions"]]
    unlinked = _projected(client, paths, [4, 3])
    for rows, prefix in zip(unlinked, ("ticket.work_", "work_item.ticket_"), strict=True):
        assert {row["event_type"] for row in rows if row["event_type"] in LINK_EVENTS} == {
            prefix + "linked",
            prefix + "unlinked",
        }
    noop = client.delete(unlink_path, headers=_headers(*(row["version"] for row in absent)))
    assert noop.status_code == 204 and noop.content == b""
    assert [_detail(client, path) for path in paths] == absent
    assert [_activity(client, path) for path in paths] == unlinked
    # A historical link receipt cannot recreate an absent link.
    replay = client.post(
        paths[0] + "/work-items",
        json={"work_item_id": proof["work_item_id"]},
        headers=_headers(intent["ticket_version"], intent["work_version"], intent["key"]),
    )
    assert replay.status_code == 200
    _pair(client, proof, present=False)
    assert [_detail(client, path) for path in paths] == absent
    relink = client.post(
        paths[0] + "/work-items",
        json={"work_item_id": proof["work_item_id"]},
        headers=_headers(*(row["version"] for row in absent)),
    )
    assert relink.status_code == 201
    relinked = [_detail(client, path) for path in paths]
    assert [row["version"] for row in relinked] == [row["version"] + 1 for row in absent]
    delayed = client.delete(unlink_path, headers=unlink_headers)
    assert delayed.status_code == 204 and delayed.content == b""
    assert [_detail(client, path) for path in paths] == relinked
    _pair(client, proof)

    # Native lifecycle commands mutate only their own aggregate.
    for index, target in ((1, "in_progress"), (0, "open")):
        before = [_detail(client, path) for path in paths]
        changed = client.post(
            paths[index] + "/transitions",
            json={"target_status": target},
            headers={"If-Match": f'"{before[index]["version"]}"', "Idempotency-Key": uuid4().hex},
        )
        assert changed.status_code == 200
        assert _detail(client, paths[index])["status"] == target
        assert _detail(client, paths[1 - index]) == before[1 - index]
    final = [_detail(client, path) for path in paths]
    _unified(client, proof, [row["status"] for row in final])
    pages = _projected(client, paths, [6, 5])
    event_ids = _link_ids(pages)
    assert len(event_ids) == 6 and len(set(event_ids)) == 6
    hidden_ids = {row["event_id"] for row in pages[1] if row["event_type"] in LINK_EVENTS}
    ordinary_ids = {row["event_id"] for row in pages[1] if row["event_type"] not in LINK_EVENTS}
    assert len(hidden_ids) == 3 and len(ordinary_ids) == 2

    queue_path = "/api/v1/ticket-queues/" + proof["queue_id"]
    queue = configuration_client.get(queue_path)
    assert queue.status_code == 200
    revoked = configuration_client.delete(
        queue_path + "/members/" + proof["actor_id"],
        headers={"If-Match": queue.headers["etag"]},
    )
    assert revoked.status_code == 204
    assert client.get(paths[1]).status_code == 401
    assert client.get("/api/v1/my-work/unified").status_code == 401
    login = client.post("/api/v1/auth/sessions", json=login_body)
    assert login.status_code == 201
    client.headers["X-CSRF-Token"] = login.json()["csrf_token"]
    assert _detail(client, "/api/v1/auth/me")["id"] == proof["actor_id"]
    assert client.get(paths[0]).status_code == 404
    assert _detail(client, paths[1]) == final[1]
    private_unified = _unified(
        client, proof, [row["status"] for row in final], ticket_visible=False
    )
    links = _detail(client, paths[1] + "/tickets")
    assert links["items"] == [] and links["next_cursor"] is None
    visible = _activity(client, paths[1])
    visible_ids = {row["event_id"] for row in visible}
    assert hidden_ids.isdisjoint(visible_ids) and visible_ids == ordinary_ids
    complete_page = client.get(paths[1] + "/activity", params={"limit": len(ordinary_ids)})
    assert complete_page.status_code == 200
    assert {row["event_id"] for row in complete_page.json()["items"]} == ordinary_ids
    assert complete_page.json()["next_cursor"] is None
    return {
        **proof,
        "after_recreation_link_pairs": pairs,
        "after_recreation_unified": restored_unified,
        "after_queue_revocation_unified": private_unified,
        "final_versions": [row["version"] for row in final],
        "final_statuses": [row["status"] for row in final],
        "link_event_ids": event_ids,
        "final_activity_counts": [len(rows) for rows in pages],
        "readable_unlink_history": True,
        "original_link_and_unlink_receipts": True,
        "absent_delete_noop": True,
        "independent_lifecycle": True,
        "old_session_status": 401,
        "same_actor_fresh_login": True,
        "fresh_ticket_status": 404,
        "fresh_work_status": 200,
        "hidden_counterpart_event_ids": sorted(hidden_ids),
        "returned_activity_event_ids": sorted(visible_ids),
        "ordinary_activity_count": len(visible),
    }
