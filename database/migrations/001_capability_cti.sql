-- Migrate capabilities to Class Table Inheritance (CTI).
--
-- All existing rows are 'model' kind. Steps:
--   1. Rename old table, drop FK + CHECK from solution_steps
--   2. Create new capabilities base table + child tables
--   3. Backfill from old table
--   4. Restore FK, update CHECK on solution_steps
--   5. Drop old table

BEGIN;

ALTER TABLE capabilities RENAME TO capabilities_v1;

ALTER TABLE solution_steps
    DROP CONSTRAINT IF EXISTS solution_steps_capability_id_fkey,
    DROP CONSTRAINT IF EXISTS solution_steps_check;

CREATE TABLE capabilities (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    capability_type TEXT NOT NULL,
    algorithm TEXT NOT NULL,
    kind TEXT NOT NULL CHECK (kind IN ('model', 'classic_algorithm')),
    user_params JSONB NOT NULL DEFAULT '{}'::jsonb,
    internal_config JSONB NOT NULL DEFAULT '{}'::jsonb,
    sha TEXT NOT NULL UNIQUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE model_capabilities (
    capability_id UUID PRIMARY KEY REFERENCES capabilities(id) ON DELETE CASCADE,
    model_name TEXT NOT NULL,
    model_version TEXT NOT NULL,
    confidence_threshold DOUBLE PRECISION NOT NULL DEFAULT 0.0
);

CREATE TABLE classic_algorithm_capabilities (
    capability_id UUID PRIMARY KEY REFERENCES capabilities(id) ON DELETE CASCADE
);

INSERT INTO capabilities (id, capability_type, algorithm, kind, user_params, internal_config, sha, created_at, updated_at)
SELECT id, capability_type, algorithm, 'model', user_params, internal_config, sha, created_at, updated_at
FROM capabilities_v1;

INSERT INTO model_capabilities (capability_id, model_name, model_version, confidence_threshold)
SELECT id, model_name, model_version, confidence_threshold
FROM capabilities_v1;

ALTER TABLE solution_steps
    ADD CONSTRAINT solution_steps_capability_id_fkey
        FOREIGN KEY (capability_id) REFERENCES capabilities(id) ON DELETE RESTRICT,
    ADD CONSTRAINT solution_steps_inference_requires_capability CHECK (
        step_type NOT IN ('inference', 'async_inference') OR capability_id IS NOT NULL
    );

DROP TABLE capabilities_v1;

COMMIT;
