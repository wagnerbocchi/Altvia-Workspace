Private files are development scope under ADR-0037. Migration00025 and the API/
worker now implement private ticket public/note and work assets, binary uploads,
metadata/download, protected failed-scan retry and durable fenced scanning.
Task3 adds immutable content links and explicitly reviewed outbound MIME files.
Task4 adds native browser upload, scoped selection/download and protected recovery;
all five hosted gates passed at2da7788, recorded in
docs/phase-3i-private-file-browser-evidence.md. There is no manual clean override.
Production rollout, real data import, deletion/retention policy and final target
CPU qualification remain separate gates.

Use `infra/compose.yaml` plus `infra/compose.files.yaml`. The overlay adds the
private storage/scanner services and scoped API/worker mounts without starting
them in existing five-service development projects. Full scanner acceptance needs
adequately provisioned Docker with at least 6 GiB available engine memory. Do not
resize or restart the existing 2048 MiB local Podman machine for this proof.

Supply all secrets in the existing restricted `ALTVIA_SECRET_DIR`. Each storage
JSON file (`storage_owner`, `storage_api`, `storage_scanner`) contains exactly:

```json
{
  "endpoint": "https://storage:8443",
  "ca_file": "/run/secrets/storage_ca",
  "access_key": "REPLACE_WITH_INDEPENDENT_RANDOM_ACCESS_KEY",
  "secret_key": "REPLACE_WITH_INDEPENDENT_RANDOM_SECRET"
}
```

`storage_root_access` and `storage_root_secret` contain the owner's matching
values. Provide `storage_cert`, `storage_key` and `storage_ca` as the verified
private TLS material for DNS name `storage`. Credentials belong only in secret
files, never command arguments, source control or a shared environment file.
Make the private parent directory accessible only to its operator and permit the
non-root service UID 10001 to read the mounted files. The owner configuration is
mounted only for the finite bootstrap; API and worker receive independent ordinary
non-owner accounts. The scanner mount has no write grant.

```sh
docker compose -f infra/compose.yaml -f infra/compose.files.yaml build storage clamd migrate
docker compose -f infra/compose.yaml -f infra/compose.files.yaml up -d --wait storage
docker compose -f infra/compose.yaml -f infra/compose.files.yaml run --rm storage-bootstrap
docker compose -f infra/compose.yaml -f infra/compose.files.yaml run --rm freshclam --stdout
docker compose -f infra/compose.yaml -f infra/compose.files.yaml up -d --wait clamd
```

Bootstrap inspects existing identity, bucket ownership and exact policy. A changed
credential, broadened policy, existing runtime-owned bucket or partially created
bucket without its expected policy is refused. Investigate and reconcile under
owner review; do not reset credentials, remove a bucket or delete objects to make
initialization pass. Native global ListBuckets returns HTTP 200 with an empty
list for the non-owner runtime users; this is recorded as emptiness, never a 403.
Actual object enumeration, cross-bucket requests, admin actions and destructive
operations remain denied. Native conditional copy/multipart completion can create
a new same-scope object, but cannot replace an existing destination. The runtime
adapter exposes only bounded single PUT/GET.

The storage process runs pinned VersityGW with `--fsync`, native conditional policy
and `flock`, over the durable `private_objects` named volume. Do not replace it
with an emulated S3 server, a public bucket, a permissive admin key or an adapter
that invents signing. Keep objects and IAM state together. Any future matching
database/object restore must retain exact keys and bytes; no cleanup schedule is
implied by this task.

Only freshclam has definition-download egress. It verifies signed complete vendor
definitions, tests and atomically replaces them in `clam_definitions`. Clamd mounts
that volume read-only, requires complete signed main/daily/bytecode files and
uses `OfficialDatabaseOnly`, signed bytecode, bounded encrypted/limit alerts and
non-concurrent reload. SelfCheck reloads updates without exposing a control socket
to the updater. Only the worker receives the private UID-restricted Unix socket;
no scanner or storage port is published. Neither service may silently downgrade
TLS, signatures, freshness, limits or fail-closed behavior.

```sh
ALTVIA_ALLOW_FILE_INFRA_TEST=1 uv run python scripts/private_file_infra_proof.py
uv run python scripts/scan_service_images.py --output-dir /restricted/evidence/image-scan
```

The first command uses a random isolated project, synthetic credentials and test
certificates. It requires actual complete/current signed definitions, clean/EICAR,
encrypted/expanded-limit controls, fresh-version checks, vendor replacement and
actual daemon reload, refusal, storage restart/integrity and Docker cgroup/network
proof. Failure is a failed gate; tiny unsigned fixtures or mocked clean results
cannot replace it. The hosted Container checks workflow runs this full profile.
For a constrained local storage-only proof use `--engine podman --storage-only`;
that result does not qualify AV capacity or effective target resource controls.

The image-security workflow scans all seven real images against one vulnerability
database, preserving lower severity findings and failing HIGH/CRITICAL. Storage
must have a nonempty Go dependency inventory, and ClamAV a nonempty exact vendor
engine/native package inventory. GOAMD64=v1 and a package inventory are build
constraints, not actual target CPU acceptance.

The storage archive remains the exact ADR-0037 commit/hash. Its build copies
`infra/versitygw.go.mod` and `.sum` over upstream's module manifests to select the
verified compatible `golang.org/x/crypto` fix
`v0.58.1-0.20261009181718-2f1f834330b2`. GO-2026-5932 applies to the retired
OpenPGP subtree, absent from the actual command's imported packages. The narrow
pin also removes the module inventory finding; no advisory suppression is used.

Proof artifacts live under `.superpowers/file-infra/`. Manifests and named
`inventory-*.txt` and numbered stdout/stderr outputs are selected for hosted
upload. Exact secret-free command outputs retain their hashes. If a command
unexpectedly echoes a synthetic private credential, only its sanitized output is
uploaded; the manifest records the original hash and the raw file stays under
the excluded private directory. Keep secret directories
and unrestricted command logs private; do not archive secret mounts or environment
inspections. Proof cleanup stops only its random project and preserves its named
volumes. No `down -v`, retention deletion, production rollout or per-slice target
homologation is authorized here.

The Task2 hosted API gate adds a separate bounded S3-only fixture using the same
storage Dockerfile, native bootstrap and TLS certificate tool. It runs the
existing full API suite once with file tests required, from the Linux runner to a
private bridge address in the synthetic certificate SAN. No storage port or AV
definitions are published or loaded. Missing required file configuration and a
skipped attachment suite fail that gate. Local developers without this external
fixture may receive explicit skips; those do not qualify file behavior. Fixture
cleanup stops only the random task container and preserves its object volume and
hash-bound command evidence.

For the hosted Linux API fixture, the existing job runs:

```sh
uv run python scripts/ci_file_storage.py start
uv run pytest -q --junitxml=.superpowers/api-tests.xml
uv run python scripts/ci_file_storage.py verify
uv run python scripts/ci_file_storage.py stop
```

The start/stop commands are bounded to the random path recorded through GITHUB_ENV;
they are not a general local deployment utility. The mandatory job sets
ALTVIA_REQUIRE_FILE_TESTS=1. Its manifest and numbered raw streams are retained
without secret mounts; the JUnit verifier rejects skipped/missing/failed attachment
suites. API settings use ALTVIA_STORAGE_FILE and the worker uses
ALTVIA_SCANNER_STORAGE_FILE; the Compose overlay selects the existing mounted JSON
files. Existing five-service stacks may leave these unset, which fails file
transfer closed and does not fabricate a clean result. Quarantine/retry backlog
remains durable. Historical ready policy1 decisions remain valid through scanner
outages, subject to current authorization and verified stored bytes.

Drain the file-aware API and worker before any contraction. Migration00025 refuses
contraction while any asset, attempt or file audit/outbox history exists. Retain
the file-aware application pair, S3 objects and matching database backup on rollback;
do not delete data to make a downgrade pass. Failed final upload writes and matching
concurrent uploads may leave opaque unreferenced private objects. No orphan removal,
retention, ready-file expiry or production scanning policy is implied.
