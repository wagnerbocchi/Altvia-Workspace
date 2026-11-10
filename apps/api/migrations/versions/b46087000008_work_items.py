"""Expand durable project work; preserve history and serialize hierarchy writes."""

from alembic import op

revision = "b46087000008"
down_revision = "b46087000007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """CREATE TABLE work_items (
    id UUID NOT NULL,
    project_id UUID NOT NULL,
    parent_id UUID,
    owner_id UUID,
    title VARCHAR(300) NOT NULL,
    description TEXT NOT NULL,
    status VARCHAR(20) NOT NULL,
    work_type VARCHAR(20) NOT NULL,
    priority VARCHAR(20) NOT NULL,
    blocked_reason VARCHAR(2000),
    due_at TIMESTAMP WITH TIME ZONE,
    due_precision VARCHAR(10),
    due_date_local DATE,
    due_timezone VARCHAR(100),
    started_at TIMESTAMP WITH TIME ZONE,
    completed_at TIMESTAMP WITH TIME ZONE,
    estimated_minutes INTEGER,
    version INTEGER NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
    PRIMARY KEY (id),
    CONSTRAINT uq_work_project UNIQUE (id, project_id),
    CONSTRAINT fk_work_parent_project
            FOREIGN KEY(parent_id, project_id) REFERENCES work_items
            (id, project_id),
    CONSTRAINT ck_work_parent CHECK (parent_id IS NULL
            OR parent_id <> id),
    CONSTRAINT ck_work_title CHECK (char_length(btrim(title)) BETWEEN 1
            AND 300),
    CONSTRAINT ck_work_description CHECK (char_length(description) <= 20000),
    CONSTRAINT ck_work_status CHECK (
        status IN ('todo','in_progress','blocked','done','cancelled')),
    CONSTRAINT ck_work_type CHECK (work_type IN ('one_off','ongoing')),
    CONSTRAINT ck_work_priority CHECK (priority IN ('low','medium','high','critical')),
    CONSTRAINT ck_work_version CHECK (version > 0),
    CONSTRAINT ck_work_estimate CHECK (estimated_minutes IS NULL
            OR estimated_minutes >= 0),
    CONSTRAINT ck_work_block CHECK ((status='blocked'
            AND blocked_reason IS NOT NULL
            AND char_length(btrim(blocked_reason)) BETWEEN 1
            AND 2000)
            OR (status<>'blocked'
            AND blocked_reason IS NULL)),
    CONSTRAINT ck_work_completion CHECK ((status='done'
            AND completed_at IS NOT NULL)
            OR (status<>'done'
            AND completed_at IS NULL)),
    CONSTRAINT ck_work_due CHECK ((due_at IS NULL
            AND due_precision IS NULL
            AND due_date_local IS NULL
            AND due_timezone IS NULL)
            OR (due_at IS NOT NULL
            AND due_precision IS NOT NULL AND due_precision='date'
            AND due_date_local IS NOT NULL
            AND due_timezone IS NOT NULL)
            OR (due_at IS NOT NULL
            AND due_precision IS NOT NULL AND due_precision='instant'
            AND due_date_local IS NULL
            AND due_timezone IS NULL)),

            FOREIGN KEY(project_id) REFERENCES projects (id),

            FOREIGN KEY(owner_id) REFERENCES users (id)
)"""
    )
    op.execute("CREATE INDEX ix_work_items_owner_id ON work_items (owner_id)")
    op.execute("CREATE INDEX ix_work_project_id ON work_items (project_id, id)")
    op.execute(
        """CREATE TABLE work_item_assignees (
    work_item_id UUID NOT NULL,
    user_id UUID NOT NULL,
    PRIMARY KEY (work_item_id, user_id),

            FOREIGN KEY(work_item_id) REFERENCES work_items (id),

            FOREIGN KEY(user_id) REFERENCES users (id)
)"""
    )
    op.execute("CREATE INDEX ix_work_item_assignees_user_id ON work_item_assignees (user_id)")
    op.execute(
        """CREATE TABLE work_item_comments (
    id UUID NOT NULL,
    work_item_id UUID NOT NULL,
    author_id UUID NOT NULL,
    body TEXT NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
    PRIMARY KEY (id),
    CONSTRAINT ck_work_comment_body CHECK (char_length(btrim(body)) BETWEEN 1
            AND 10000),

            FOREIGN KEY(work_item_id) REFERENCES work_items (id),

            FOREIGN KEY(author_id) REFERENCES users (id)
)"""
    )
    op.execute(
        "CREATE INDEX ix_work_comment_page ON work_item_comments (work_item_id, created_at, id)"
    )
    op.execute(
        """CREATE TABLE work_item_status_history (
    id UUID NOT NULL,
    work_item_id UUID NOT NULL,
    actor_id UUID NOT NULL,
    from_status VARCHAR(20),
    to_status VARCHAR(20) NOT NULL,
    reason VARCHAR(2000),
    version INTEGER NOT NULL,
    occurred_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
    PRIMARY KEY (id),
    CONSTRAINT uq_work_status_version UNIQUE (work_item_id, version),

            FOREIGN KEY(work_item_id) REFERENCES work_items (id),

            FOREIGN KEY(actor_id) REFERENCES users (id)
)"""
    )

    # PostgreSQL is the single owner of business-date boundaries. In a repeated
    # midnight, AT TIME ZONE alone selects the later occurrence. In a midnight
    # gap, find the actual first instant rather than normalizing the clock time.
    op.execute("""CREATE FUNCTION altvia_work_day_start(day date, zone text)
    RETURNS timestamptz LANGUAGE plpgsql STABLE STRICT AS $$
    DECLARE anchor timestamptz; exact_start timestamptz;
            lower_bound timestamptz; upper_bound timestamptz; middle timestamptz;
    BEGIN
        anchor := day::timestamp AT TIME ZONE zone;
        WITH offsets AS (
            SELECT DISTINCT (point AT TIME ZONE zone) - (point AT TIME ZONE 'UTC') AS delta
            FROM generate_series(anchor - interval '2 days', anchor + interval '2 days',
                                 interval '1 hour') AS point
        ), candidates AS (
            SELECT (day::timestamp - delta) AT TIME ZONE 'UTC' AS instant FROM offsets
        )
        SELECT min(instant) FILTER (WHERE (instant AT TIME ZONE zone) = day::timestamp),
               min(instant), max(instant)
        INTO exact_start, lower_bound, upper_bound FROM candidates;
        IF exact_start IS NOT NULL THEN RETURN exact_start; END IF;
        -- Candidate offsets bracket a forward gap. Timestamp resolution is one
        -- microsecond; this also returns the next valid date after a skipped day.
        WHILE upper_bound - lower_bound > interval '1 microsecond' LOOP
            middle := lower_bound + (upper_bound - lower_bound) / 2;
            IF (middle AT TIME ZONE zone)::date >= day THEN upper_bound := middle;
            ELSE lower_bound := middle; END IF;
        END LOOP;
        RETURN upper_bound;
    END $$""")
    op.execute("""CREATE FUNCTION altvia_guard_work() RETURNS trigger
    LANGUAGE plpgsql AS $$ BEGIN
        IF TG_OP='UPDATE'
            AND NEW.project_id<>OLD.project_id THEN
            RAISE EXCEPTION 'Work project is immutable' USING ERRCODE='23514';
        END IF;
        PERFORM pg_advisory_xact_lock(hashtextextended(
            'altvia:work-graph:'||NEW.project_id::text,0));
        IF NEW.parent_id IS NOT NULL
            AND EXISTS(
            WITH RECURSIVE ancestors AS (
                SELECT id,parent_id FROM work_items WHERE id=NEW.parent_id
                UNION SELECT w.id,w.parent_id FROM work_items w JOIN ancestors a ON w.id=a.parent_id
            ) SELECT 1 FROM ancestors WHERE id=NEW.id
        ) THEN RAISE EXCEPTION 'Work parent cycle' USING ERRCODE='23514'; END IF;
        IF NEW.due_precision='date' THEN
            IF NOT EXISTS(SELECT 1 FROM pg_timezone_names WHERE name=NEW.due_timezone) THEN
                RAISE EXCEPTION 'Invalid due timezone' USING ERRCODE='23514';
            END IF;
            IF NEW.due_at IS DISTINCT FROM
                altvia_work_day_start(NEW.due_date_local+1, NEW.due_timezone)

            OR (altvia_work_day_start(NEW.due_date_local, NEW.due_timezone)
                AT TIME ZONE NEW.due_timezone)::date
                IS DISTINCT FROM NEW.due_date_local THEN
                RAISE EXCEPTION 'Invalid due boundary' USING ERRCODE='23514';
            END IF;
        END IF;
        RETURN NEW;
    END $$""")
    op.execute(
        "CREATE TRIGGER work_guard BEFORE INSERT OR UPDATE ON work_items "
        "FOR EACH ROW EXECUTE FUNCTION altvia_guard_work()"
    )
    for table in ["work_item_comments", "work_item_status_history"]:
        op.execute(
            f"CREATE TRIGGER {table}_immutable BEFORE UPDATE OR DELETE ON {table} "
            "FOR EACH ROW EXECUTE FUNCTION altvia_reject_audit_mutation()"
        )
    op.drop_constraint("ck_activity_resource", "activity_events", type_="check")
    op.create_check_constraint(
        "ck_activity_resource",
        "activity_events",
        "resource_type IN ('identity','team','client','project','operational_area','work_item')",
    )


def downgrade() -> None:
    op.execute("""DO $$ BEGIN
        IF EXISTS(SELECT 1 FROM work_items)
            OR EXISTS(SELECT 1 FROM work_item_comments)

            OR EXISTS(SELECT 1 FROM work_item_status_history)

            OR EXISTS(SELECT 1 FROM activity_events WHERE resource_type='work_item')
        THEN RAISE EXCEPTION 'Cannot downgrade while durable work data exists'; END IF;
    END $$""")
    op.drop_constraint("ck_activity_resource", "activity_events", type_="check")
    op.create_check_constraint(
        "ck_activity_resource",
        "activity_events",
        "resource_type IN ('identity','team','client','project','operational_area')",
    )
    for table in [
        "work_item_status_history",
        "work_item_comments",
        "work_item_assignees",
        "work_items",
    ]:
        op.drop_table(table)
    op.execute("DROP FUNCTION altvia_guard_work()")
    op.execute("DROP FUNCTION altvia_work_day_start(date,text)")
