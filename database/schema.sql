CREATE EXTENSION IF NOT EXISTS pgcrypto;

CREATE TABLE IF NOT EXISTS capabilities (
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

CREATE TABLE IF NOT EXISTS model_capabilities (
    capability_id UUID PRIMARY KEY REFERENCES capabilities(id) ON DELETE CASCADE,
    model_name TEXT NOT NULL,
    model_version TEXT NOT NULL,
    confidence_threshold DOUBLE PRECISION NOT NULL DEFAULT 0.0
);

CREATE TABLE IF NOT EXISTS classic_algorithm_capabilities (
    capability_id UUID PRIMARY KEY REFERENCES capabilities(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS solutions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name TEXT NOT NULL UNIQUE,
    description TEXT NOT NULL DEFAULT '',
    user_params JSONB NOT NULL DEFAULT '{}'::jsonb,
    internal_config JSONB NOT NULL DEFAULT '{}'::jsonb,
    version INTEGER NOT NULL DEFAULT 1,
    sha TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_solutions_sha ON solutions (sha);

CREATE TABLE IF NOT EXISTS solution_steps (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    solution_id UUID NOT NULL REFERENCES solutions(id) ON DELETE CASCADE,
    step_id TEXT NOT NULL,
    step_type TEXT NOT NULL CHECK (step_type IN ('inference', 'async_inference', 'postprocess', 'local_capability')),
    capability_id UUID NULL REFERENCES capabilities(id) ON DELETE RESTRICT,
    position INTEGER NOT NULL,
    depends_on TEXT[] NOT NULL DEFAULT ARRAY[]::TEXT[],
    user_params JSONB NOT NULL DEFAULT '{}'::jsonb,
    internal_config JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CHECK (
        step_type NOT IN ('inference', 'async_inference') OR capability_id IS NOT NULL
    ),
    UNIQUE (solution_id, step_id),
    UNIQUE (solution_id, position)
);

CREATE INDEX IF NOT EXISTS idx_solution_steps_solution_id ON solution_steps (solution_id, position);
CREATE INDEX IF NOT EXISTS idx_solution_steps_capability_id ON solution_steps (capability_id);

CREATE TABLE IF NOT EXISTS sensor_assignments (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    sensor_id TEXT NOT NULL,
    solution_id UUID NOT NULL REFERENCES solutions(id) ON DELETE RESTRICT,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    config_overrides JSONB NOT NULL DEFAULT '{}'::jsonb,
    solution_sha TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_sensor_assignments_sensor_id ON sensor_assignments (sensor_id);
CREATE UNIQUE INDEX IF NOT EXISTS idx_sensor_assignments_sensor_solution
    ON sensor_assignments (sensor_id, solution_id);
