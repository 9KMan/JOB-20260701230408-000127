-- =====================================================================
-- 001_initial.sql — initial schema for the multi-agent orchestration
--                    platform (Job-127).
--
-- Idempotent: every CREATE uses IF NOT EXISTS so re-running the
-- migration against a partially-populated database is safe.
--
-- Requires PostgreSQL 14+ with the pgcrypto extension (for
-- gen_random_uuid()) and pgvector (for the VECTOR type).
-- =====================================================================

CREATE EXTENSION IF NOT EXISTS pgcrypto;
CREATE EXTENSION IF NOT EXISTS vector;

-- ---------------------------------------------------------------------
-- agents — registered AI agents (rows mirror Agent ORM model).
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS agents (
    id              UUID         PRIMARY KEY DEFAULT gen_random_uuid(),
    name            VARCHAR(128) NOT NULL UNIQUE,
    role            VARCHAR(32)  NOT NULL DEFAULT 'custom',
    config          JSONB        NOT NULL DEFAULT '{}'::jsonb,
    system_prompt   TEXT         NOT NULL DEFAULT '',
    tools           JSONB        NOT NULL DEFAULT '[]'::jsonb,
    created_at      TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS ix_agents_role_created_at
    ON agents (role, created_at);

-- ---------------------------------------------------------------------
-- source_documents — RAG source documents with pgvector embeddings.
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS source_documents (
    id                UUID             PRIMARY KEY DEFAULT gen_random_uuid(),
    source_type       VARCHAR(64)     NOT NULL,
    external_id       VARCHAR(256)    NOT NULL,
    title             VARCHAR(512)    NOT NULL,
    content_text      TEXT            NOT NULL DEFAULT '',
    content_embedding vector(1536),
    metadata          JSONB           NOT NULL DEFAULT '{}'::jsonb,
    fetched_at        TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    created_at        TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    updated_at        TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_source_documents_source_type_external_id
        UNIQUE (source_type, external_id)
);

CREATE INDEX IF NOT EXISTS ix_source_documents_source_type
    ON source_documents (source_type);

-- HNSW index on content_embedding for cosine-distance similarity
-- search. m=16 / ef_construction=64 are reasonable production
-- defaults for 10K–1M docs; tune at scale.
CREATE INDEX IF NOT EXISTS ix_source_documents_content_embedding_hnsw
    ON source_documents
    USING hnsw (content_embedding vector_cosine_ops)
    WITH (m = 16, ef_construction = 64);

-- ---------------------------------------------------------------------
-- tasks — units of orchestrated work.
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS tasks (
    id                  UUID          PRIMARY KEY DEFAULT gen_random_uuid(),
    state               VARCHAR(32)   NOT NULL DEFAULT 'pending',
    input_payload       JSONB         NOT NULL DEFAULT '{}'::jsonb,
    output_payload      JSONB         NOT NULL DEFAULT '{}'::jsonb,
    assigned_agent_id   UUID          REFERENCES agents(id) ON DELETE SET NULL,
    lease_until         TIMESTAMPTZ,
    source_doc_id       UUID          REFERENCES source_documents(id) ON DELETE SET NULL,
    error_message       TEXT,
    retry_count         INTEGER       NOT NULL DEFAULT 0,
    max_retries         INTEGER       NOT NULL DEFAULT 3,
    created_at          TIMESTAMPTZ   NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMPTZ   NOT NULL DEFAULT NOW(),
    CONSTRAINT ck_tasks_state CHECK (
        state IN ('pending', 'running', 'awaiting_review',
                  'completed', 'failed', 'cancelled')
    )
);

-- Composite index used by TaskQueue.claim() and recover_stale_tasks().
CREATE INDEX IF NOT EXISTS ix_tasks_state_lease_until
    ON tasks (state, lease_until);

CREATE INDEX IF NOT EXISTS ix_tasks_assigned_agent_id
    ON tasks (assigned_agent_id);

CREATE INDEX IF NOT EXISTS ix_tasks_source_doc_id
    ON tasks (source_doc_id);

CREATE INDEX IF NOT EXISTS ix_tasks_created_at
    ON tasks (created_at);

-- ---------------------------------------------------------------------
-- runs — per-attempt execution log (audit / observability).
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS runs (
    id              UUID          PRIMARY KEY DEFAULT gen_random_uuid(),
    agent_id        UUID          NOT NULL REFERENCES agents(id) ON DELETE CASCADE,
    task_id         UUID          NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
    started_at      TIMESTAMPTZ   NOT NULL,
    finished_at     TIMESTAMPTZ,
    status          VARCHAR(32)   NOT NULL DEFAULT 'failed',
    tokens_in       INTEGER       NOT NULL DEFAULT 0,
    tokens_out      INTEGER       NOT NULL DEFAULT 0,
    cost_usd        DOUBLE PRECISION NOT NULL DEFAULT 0,
    error_message   TEXT,
    log             JSONB         NOT NULL DEFAULT '{}'::jsonb,
    created_at      TIMESTAMPTZ   NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ   NOT NULL DEFAULT NOW(),
    CONSTRAINT ck_runs_status CHECK (
        status IN ('success', 'partial', 'failed')
    )
);

CREATE INDEX IF NOT EXISTS ix_runs_status_started_at
    ON runs (status, started_at);

CREATE INDEX IF NOT EXISTS ix_runs_agent_started_at
    ON runs (agent_id, started_at);

CREATE INDEX IF NOT EXISTS ix_runs_task_id
    ON runs (task_id);

-- ---------------------------------------------------------------------
-- review_queue — human-in-the-loop approval queue.
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS review_queue (
    id              UUID          PRIMARY KEY DEFAULT gen_random_uuid(),
    task_id         UUID          NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
    action          JSONB         NOT NULL DEFAULT '{}'::jsonb,
    reason          VARCHAR(512)  NOT NULL DEFAULT '',
    status          VARCHAR(32)   NOT NULL DEFAULT 'pending',
    resolved_at     TIMESTAMPTZ,
    resolved_by     VARCHAR(128),
    note            TEXT,
    created_at      TIMESTAMPTZ   NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ   NOT NULL DEFAULT NOW(),
    CONSTRAINT ck_review_queue_status CHECK (
        status IN ('pending', 'approved', 'rejected')
    )
);

CREATE INDEX IF NOT EXISTS ix_review_queue_status_created_at
    ON review_queue (status, created_at);

CREATE INDEX IF NOT EXISTS ix_review_queue_task_id
    ON review_queue (task_id);

-- ---------------------------------------------------------------------
-- updated_at triggers — keep the column fresh on every UPDATE.
-- ---------------------------------------------------------------------
CREATE OR REPLACE FUNCTION set_updated_at() RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_trigger WHERE tgname = 'trg_agents_updated_at') THEN
        CREATE TRIGGER trg_agents_updated_at BEFORE UPDATE ON agents
            FOR EACH ROW EXECUTE FUNCTION set_updated_at();
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_trigger WHERE tgname = 'trg_tasks_updated_at') THEN
        CREATE TRIGGER trg_tasks_updated_at BEFORE UPDATE ON tasks
            FOR EACH ROW EXECUTE FUNCTION set_updated_at();
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_trigger WHERE tgname = 'trg_runs_updated_at') THEN
        CREATE TRIGGER trg_runs_updated_at BEFORE UPDATE ON runs
            FOR EACH ROW EXECUTE FUNCTION set_updated_at();
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_trigger WHERE tgname = 'trg_source_documents_updated_at') THEN
        CREATE TRIGGER trg_source_documents_updated_at BEFORE UPDATE ON source_documents
            FOR EACH ROW EXECUTE FUNCTION set_updated_at();
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_trigger WHERE tgname = 'trg_review_queue_updated_at') THEN
        CREATE TRIGGER trg_review_queue_updated_at BEFORE UPDATE ON review_queue
            FOR EACH ROW EXECUTE FUNCTION set_updated_at();
    END IF;
END$$;