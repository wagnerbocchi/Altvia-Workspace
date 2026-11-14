"""Immutable scoped business calendar and disabled SLA policy configuration."""

from alembic import op

revision = "b46087000031"
down_revision = "b46087000030"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""CREATE FUNCTION public.valid_business_calendar_windows(candidate jsonb)
    RETURNS boolean LANGUAGE plpgsql IMMUTABLE STRICT SECURITY INVOKER
    SET search_path=pg_catalog AS $$
    DECLARE entry jsonb; day_number integer; opening_minute integer;
      closing_minute integer; previous_day integer := -1; previous_end integer := -1;
    BEGIN
      IF jsonb_typeof(candidate)<>'array'
        OR jsonb_array_length(candidate) NOT BETWEEN 1 AND 28 THEN RETURN false; END IF;
      FOR entry IN SELECT value FROM jsonb_array_elements(candidate) LOOP
        IF jsonb_typeof(entry)<>'object'
          OR NOT entry ?& ARRAY['weekday','start_minute','end_minute']
          OR entry-'weekday'-'start_minute'-'end_minute'<>'{}'::jsonb
          OR jsonb_typeof(entry->'weekday')<>'number'
          OR jsonb_typeof(entry->'start_minute')<>'number'
          OR jsonb_typeof(entry->'end_minute')<>'number'
          OR (entry->>'weekday') !~ '^[0-9]{1,4}$'
          OR (entry->>'start_minute') !~ '^[0-9]{1,4}$'
          OR (entry->>'end_minute') !~ '^[0-9]{1,4}$' THEN RETURN false; END IF;
        day_number := (entry->>'weekday')::integer;
        opening_minute := (entry->>'start_minute')::integer;
        closing_minute := (entry->>'end_minute')::integer;
        IF day_number NOT BETWEEN 0 AND 6 OR opening_minute<0
          OR closing_minute>1440 OR opening_minute>=closing_minute
          OR day_number<previous_day
          OR (day_number=previous_day AND opening_minute<=previous_end)
          THEN RETURN false; END IF;
        previous_day := day_number; previous_end := closing_minute;
      END LOOP;
      RETURN true;
    EXCEPTION WHEN data_exception THEN RETURN false;
    END $$""")
    op.execute("""CREATE FUNCTION public.valid_business_calendar_holidays(candidate jsonb)
    RETURNS boolean LANGUAGE plpgsql IMMUTABLE STRICT SECURITY INVOKER
    SET search_path=pg_catalog AS $$
    DECLARE entry jsonb; local_day date; previous_day date; label_text text;
    BEGIN
      IF jsonb_typeof(candidate)<>'array' OR jsonb_array_length(candidate)>1000
        THEN RETURN false; END IF;
      FOR entry IN SELECT value FROM jsonb_array_elements(candidate) LOOP
        IF jsonb_typeof(entry)<>'object' OR NOT entry ? 'date'
          OR entry-'date'-'label'<>'{}'::jsonb
          OR jsonb_typeof(entry->'date')<>'string'
          OR (entry->>'date') !~ '^[0-9]{4}-[0-9]{2}-[0-9]{2}$'
          THEN RETURN false; END IF;
        local_day := (entry->>'date')::date;
        IF to_char(local_day,'YYYY-MM-DD')<>entry->>'date'
          OR (previous_day IS NOT NULL AND local_day<=previous_day)
          THEN RETURN false; END IF;
        IF entry ? 'label' AND jsonb_typeof(entry->'label')<>'null' THEN
          IF jsonb_typeof(entry->'label')<>'string' THEN RETURN false; END IF;
          label_text := entry->>'label';
          IF char_length(label_text) NOT BETWEEN 1 AND 160
            OR label_text !~ '[^[:space:]]' THEN RETURN false; END IF;
        END IF;
        previous_day := local_day;
      END LOOP;
      RETURN true;
    EXCEPTION WHEN data_exception THEN RETURN false;
    END $$""")
    op.execute("REVOKE ALL ON FUNCTION public.valid_business_calendar_windows(jsonb) FROM PUBLIC")
    op.execute("REVOKE ALL ON FUNCTION public.valid_business_calendar_holidays(jsonb) FROM PUBLIC")
    # Frozen native DDL; no runtime dependency on later model definitions.
    op.execute("""CREATE TABLE business_calendars (
    id UUID NOT NULL,
    client_id UUID NOT NULL,
    queue_id UUID NOT NULL,
    version INTEGER DEFAULT '1' NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
    PRIMARY KEY (id),
    CONSTRAINT uq_business_calendar_context UNIQUE (id, client_id, queue_id),
    CONSTRAINT ck_business_calendar_version CHECK (version BETWEEN 1 AND 2147483647),
    FOREIGN KEY(client_id) REFERENCES clients (id) ON DELETE RESTRICT ON UPDATE RESTRICT,
    FOREIGN KEY(queue_id) REFERENCES ticket_queues (id) ON DELETE RESTRICT ON UPDATE
    RESTRICT
    )""")
    op.execute(
        "CREATE INDEX ix_business_calendar_scope ON business_calendars (queue_id, client_id, id)"
    )
    op.execute("""CREATE TABLE business_calendar_revisions (
    calendar_id UUID NOT NULL,
    version INTEGER NOT NULL,
    client_id UUID NOT NULL,
    queue_id UUID NOT NULL,
    active BOOLEAN NOT NULL,
    name VARCHAR(160) NOT NULL,
    timezone VARCHAR(100) NOT NULL,
    windows JSONB NOT NULL,
    holidays JSONB NOT NULL,
    tzif BYTEA NOT NULL,
    tzif_sha256 VARCHAR(64) NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
    PRIMARY KEY (calendar_id, version),
    CONSTRAINT fk_business_calendar_revision_context FOREIGN KEY(calendar_id, client_id,
    queue_id) REFERENCES business_calendars (id, client_id, queue_id) ON DELETE RESTRICT ON
    UPDATE RESTRICT,
    CONSTRAINT uq_business_calendar_revision_context UNIQUE (calendar_id, version,
    client_id, queue_id),
    CONSTRAINT ck_calendar_revision_version CHECK (version BETWEEN 1 AND 2147483647),
    CONSTRAINT ck_calendar_revision_name CHECK (name ~ '[^[:space:]]' AND char_length(name)
    BETWEEN 1 AND 160 AND position(chr(10) in name)=0 AND position(chr(13) in name)=0),
    CONSTRAINT ck_calendar_revision_timezone CHECK (timezone ~ '^[A-Za-z0-9_+/-]{1,100}$'
    AND timezone !~ '(^/|//|/$)'),
    CONSTRAINT ck_calendar_revision_windows CHECK
    (public.valid_business_calendar_windows(windows)),
    CONSTRAINT ck_calendar_revision_holidays CHECK
    (public.valid_business_calendar_holidays(holidays)),
    CONSTRAINT ck_calendar_revision_artifact CHECK (octet_length(tzif) BETWEEN 44 AND 262144
    AND substring(tzif from 1 for 4)=decode('545a6966','hex') AND tzif_sha256 ~
    '^[0-9a-f]{64}$' AND tzif_sha256=encode(sha256(tzif),'hex'))
    )""")
    op.execute("""CREATE TABLE sla_policies (
    id UUID NOT NULL,
    client_id UUID NOT NULL,
    queue_id UUID NOT NULL,
    category_id UUID,
    priority VARCHAR(20),
    version INTEGER DEFAULT '1' NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
    PRIMARY KEY (id),
    CONSTRAINT uq_sla_policy_context UNIQUE (id, client_id, queue_id),
    CONSTRAINT uq_sla_policy_selector UNIQUE NULLS NOT DISTINCT (queue_id, client_id,
    category_id, priority),
    CONSTRAINT fk_sla_policy_category FOREIGN KEY(category_id, queue_id) REFERENCES
    ticket_categories (id, queue_id) ON DELETE RESTRICT ON UPDATE RESTRICT,
    CONSTRAINT ck_sla_policy_version CHECK (version BETWEEN 1 AND 2147483647),
    CONSTRAINT ck_sla_policy_priority CHECK (priority IS NULL OR priority IN
    ('low','medium','high','critical')),
    FOREIGN KEY(client_id) REFERENCES clients (id) ON DELETE RESTRICT ON UPDATE RESTRICT,
    FOREIGN KEY(queue_id) REFERENCES ticket_queues (id) ON DELETE RESTRICT ON UPDATE
    RESTRICT
    )""")
    op.execute("""CREATE INDEX ix_sla_policy_scope ON sla_policies (queue_id, client_id, id)""")
    op.execute("""CREATE TABLE sla_policy_revisions (
    policy_id UUID NOT NULL,
    version INTEGER NOT NULL,
    client_id UUID NOT NULL,
    queue_id UUID NOT NULL,
    enabled BOOLEAN DEFAULT 'false' NOT NULL,
    name VARCHAR(160) NOT NULL,
    calendar_id UUID NOT NULL,
    calendar_version INTEGER NOT NULL,
    first_response_minutes INTEGER NOT NULL,
    resolution_minutes INTEGER NOT NULL,
    approach_minutes INTEGER NOT NULL,
    pause_states VARCHAR(20)[] NOT NULL,
    authorizer_id UUID NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
    PRIMARY KEY (policy_id, version),
    CONSTRAINT fk_sla_policy_revision_context FOREIGN KEY(policy_id, client_id, queue_id)
    REFERENCES sla_policies (id, client_id, queue_id) ON DELETE RESTRICT ON UPDATE RESTRICT,
    CONSTRAINT uq_sla_policy_revision_context UNIQUE (policy_id, version, client_id,
    queue_id),
    CONSTRAINT fk_sla_policy_calendar FOREIGN KEY(calendar_id, calendar_version, client_id,
    queue_id) REFERENCES business_calendar_revisions (calendar_id, version, client_id,
    queue_id) ON DELETE RESTRICT ON UPDATE RESTRICT,
    CONSTRAINT ck_sla_policy_revision_version CHECK (version BETWEEN 1 AND 2147483647 AND
    calendar_version BETWEEN 1 AND 2147483647),
    CONSTRAINT ck_sla_policy_revision_name CHECK (name ~ '[^[:space:]]' AND
    char_length(name) BETWEEN 1 AND 160 AND position(chr(10) in name)=0 AND position(chr(13)
    in name)=0),
    CONSTRAINT ck_sla_policy_targets CHECK (first_response_minutes BETWEEN 1 AND 525600 AND
    resolution_minutes BETWEEN 1 AND 525600 AND approach_minutes BETWEEN 0 AND 525600),
    CONSTRAINT ck_sla_policy_pause_states CHECK (coalesce(array_ndims(pause_states),1)=1 AND
    coalesce(array_lower(pause_states,1),1)=1 AND cardinality(pause_states) BETWEEN 0 AND 2
    AND pause_states <@ ARRAY['pending_customer','pending_third_party']::varchar[] AND
    (cardinality(pause_states)<2 OR pause_states[1]<>pause_states[2])),
    FOREIGN KEY(authorizer_id) REFERENCES users (id) ON DELETE RESTRICT ON UPDATE RESTRICT
    )""")


def downgrade() -> None:
    op.execute(
        "LOCK TABLE business_calendars,business_calendar_revisions,sla_policies,"
        "sla_policy_revisions,outbox_events,audit_logs,activity_events,idempotency_records "
        "IN ACCESS EXCLUSIVE MODE"
    )
    op.execute("""DO $$ BEGIN
      IF EXISTS(SELECT 1 FROM business_calendars)
      OR EXISTS(SELECT 1 FROM business_calendar_revisions)
      OR EXISTS(SELECT 1 FROM sla_policies)
      OR EXISTS(SELECT 1 FROM sla_policy_revisions)
      OR EXISTS(SELECT 1 FROM outbox_events WHERE event_type LIKE 'business_calendar.%'
        OR event_type LIKE 'sla_policy.%')
      OR EXISTS(SELECT 1 FROM audit_logs WHERE action LIKE 'business_calendar.%'
        OR action LIKE 'sla_policy.%')
      OR EXISTS(SELECT 1 FROM activity_events WHERE event_type LIKE 'business_calendar.%'
        OR event_type LIKE 'sla_policy.%')
      OR EXISTS(SELECT 1 FROM idempotency_records WHERE route LIKE 'sla-calendar-%'
        OR route LIKE 'sla-policy-%') THEN
        RAISE EXCEPTION 'Cannot contract SLA configuration/history';
      END IF; END $$""")
    op.drop_table("sla_policy_revisions")
    op.drop_table("sla_policies")
    op.drop_table("business_calendar_revisions")
    op.drop_table("business_calendars")
    op.execute("DROP FUNCTION public.valid_business_calendar_windows(jsonb)")
    op.execute("DROP FUNCTION public.valid_business_calendar_holidays(jsonb)")
