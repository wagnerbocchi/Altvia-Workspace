"""New synthetic incoming set in the existing signed file/restore proof owner.

All returned context is private. Only the explicit safe summary is exported by
packaged_file_proof; original roots, wires and session invalidations stay intact.
"""

import json
from email.message import EmailMessage
from email.policy import SMTP
from uuid import uuid4

from packaged_file_proof import (
    OWNER_FILES,
    SNAPSHOT,
    digest,
    owner,
    privacy_checkpoint,
    require_opt_in,
    run_file_browser,
    select_current_file_author,
    snapshot_file_markers,
)

CASE_CONTEXT = """
import json,sys
from uuid import UUID
from sqlalchemy.orm import Session
from altvia.config import DatabaseSettings
from altvia.database import make_engine
from altvia.models import Ticket,ClientContact
p=json.load(sys.stdin)
with Session(make_engine(DatabaseSettings())) as db:
    ticket=db.get(Ticket,UUID(p['ticket_id']))
    assert ticket.subject=='Packaged independent synthetic file context'
    contact=db.get(ClientContact,ticket.requester_id)
    assert contact.active and contact.client_id==ticket.client_id
    print(json.dumps({'queue_id':str(ticket.queue_id),'contact_id':str(contact.id),
                      'contact_version':contact.version,'email':contact.email_normalized}))
"""

PRIVATE_IMAP_RESULT = """
# The existing owner keeps its actual synthetic IMAPS credentials in this
# private child environment. Return them only to the parent's canary owner.
output=io.StringIO()
with redirect_stdout(output):
    packaged_classified_imap_proof(imap_server)
result=json.loads(output.getvalue())
result['private_credentials']=[os.environ['ALTVIA_IMAP_USERNAME'],
                               os.environ['ALTVIA_IMAP_PASSWORD']]
print(json.dumps(result))
"""


def incoming_message(context, nonce, files):
    message = EmailMessage(policy=SMTP)
    message["From"] = context["email"]
    message["Message-ID"] = "<incoming-files-" + nonce + "@example.test>"
    message["Subject"] = "Packaged independent incoming files"
    message.set_content("incoming-file-text-" + nonce)
    for file in files:
        message.add_attachment(
            file["body"].encode(), maintype="text", subtype="plain", filename=file["filename"]
        )
    return message.as_bytes().decode("ascii")


def assert_incoming_access(client, incoming):
    case = client.get("/api/v1/mail-cases/" + incoming["case_id"])
    assert case.status_code == 200
    block = case.json()["files"]
    assert block["extraction_version"] == 1 and block["status"] == "complete"
    assert [row["id"] for row in block["items"]] == incoming["ids"]
    path = "/api/v1/tickets/" + incoming["ticket_id"]
    message = client.get(path + "/incoming-messages/" + incoming["incoming_id"])
    assert message.status_code == 200 and message.json()["case_id"] == incoming["case_id"]
    assert message.json()["files"] == block
    assert client.get(path + "/delivery-choices").json()["participant"] is None
    for row, expected in zip(block["items"], incoming["files"], strict=True):
        assert row["filename"] == expected["filename"]
        assert row["bytes"] == len(expected["body"].encode())
        assert row["owner_type"] == "mail_case" and row["owner_id"] == incoming["case_id"]
        assert row["purpose"] == "incoming" and row["state"] == expected["state"]
        content = client.get("/api/v1/attachments/" + row["id"] + "/content")
        if expected["state"] == "ready":
            assert row["can_download"] and content.status_code == 200
            assert content.content == expected["body"].encode()
        else:
            assert not row["can_download"] and content.status_code == 409


def prepare_packaged_incoming_files(client, run, compose, root, secret_dir, work, proof):
    require_opt_in()
    # The baseline has intentionally invalidated the original session. Reuse the
    # already-captured fresh actor and prove old401; never salvage stale cookies.
    select_current_file_author(client, proof)
    before = owner(run, compose, SNAPSHOT)
    context = owner(run, compose, CASE_CONTEXT, {"ticket_id": proof["context"]["ticket_id"]})
    nonce = uuid4().hex
    files = [
        {
            "filename": "incoming-caf\u00e9-" + nonce + ".txt",
            "body": "incoming-original-bytes-" + uuid4().hex + "\n",
            "state": "ready",
        },
        {
            "filename": "incoming-eicar-" + nonce + ".txt",
            "body": "X5O!P%@AP[4\\PZX54(P^)7CC)7}$EICAR-STANDARD-ANTIVIRUS-TEST-FILE!$H+H*",
            "state": "rejected",
        },
    ]
    raw = incoming_message(context, nonce, files)
    code = (root / "apps/api/tests/imap_fixture.py").read_text(encoding="utf-8")
    code += "\n" + (root / "scripts/packaged_imap_proof.py").read_text(encoding="utf-8")
    code += "\n" + PRIVATE_IMAP_RESULT
    captured = json.loads(
        run(
            [
                *compose,
                "run",
                "--rm",
                "--no-deps",
                "-T",
                "-e",
                "ALTVIA_ALLOW_CONTAINER_TEST=1",
                "--entrypoint",
                "python",
                "mail-cases-owner",
                "-c",
                code,
            ],
            data=json.dumps(
                {
                    **context,
                    "raw": raw,
                    "source_key": "incoming-files-" + nonce,
                    "cert": (secret_dir / "imap_cert").read_text(),
                    "key": (secret_dir / "imap_key").read_text(),
                }
            ),
        )
    )
    assert captured["verified_imaps"] and captured["poll_and_attestation_replay"]
    credentials = captured.pop("private_credentials")
    assert len(credentials) == 2 and all(isinstance(value, str) and value for value in credentials)
    browser = run_file_browser(
        run,
        work,
        {
            "origin": str(client.base_url).rstrip("/"),
            "session": proof["current_session"],
            "incoming": {"case_id": captured["case_id"], "files": files},
        },
    )
    incoming = {**captured, **browser, "files": files}
    assert_incoming_access(client, incoming)
    snapshot = owner(
        run, compose, OWNER_FILES, {"ids": incoming["ids"], "ticket_id": incoming["ticket_id"]}
    )
    attempts = snapshot["attempts"]
    assert len(attempts) == 2 and {r["reason"] for r in attempts} == {"clean", "infected"}
    assert all(
        r["engine"] == "1.4.6" and r["database_version"] and r["database_date"] for r in attempts
    )
    markers = [
        *credentials,
        context["email"],
        "incoming-file-text-" + nonce,
        "<incoming-files-" + nonce + "@example.test>",
        digest(raw.encode()),
    ]
    for file in files:
        markers.extend([file["filename"], file["body"].strip(), digest(file["body"].encode())])
    markers.extend(snapshot_file_markers(snapshot))
    # Check both decoded UTF8 and its JSON ASCII representation in actual SQL,
    # Redis and service diagnostics. Credentials remain in the shared context.
    markers += [json.dumps(value, ensure_ascii=True)[1:-1] for value in markers]
    proof["context"]["ids"] = [*proof["context"]["ids"], *incoming["ids"]]
    proof["context"]["extra_aggregate_ids"] = [
        captured["case_id"],
        captured["source_id"],
        captured["variant_id"],
        incoming["ticket_id"],
    ]
    proof["context"]["markers"].extend(markers)
    proof["scan_evidence"].extend({k: v for k, v in row.items() if k != "id"} for row in attempts)
    after = owner(run, compose, SNAPSHOT)
    assert after["wires"] == before["wires"] and after["links"] == before["links"]
    for field in ("files", "case_headers", "incoming"):
        assert all(row in after[field] for row in before[field])
    proof["checkpoints"].append(
        privacy_checkpoint(
            run, compose, root, proof["context"], "after-incoming-files-delivered-and-processed"
        )
    )
    incoming["safe"] = {
        "verified_imaps_and_owner_replay": True,
        "native_triage_promotion_conversation": True,
        "same_immutable_set_and_exact_download": True,
        "signed_current_clean_and_eicar": True,
        "old_contexts_and_wires_unchanged": True,
        "no_implicit_smtp_participant_or_copy": True,
        "files": len(files),
        "raw_sha256": captured["raw_sha256"],
    }
    proof["incoming"] = incoming
