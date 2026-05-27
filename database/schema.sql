CREATE EXTENSION IF NOT EXISTS pgcrypto;

CREATE TABLE IF NOT EXISTS tool_actions (
    id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name             TEXT NOT NULL UNIQUE,
    display_name     TEXT NOT NULL DEFAULT '',
    category         TEXT NOT NULL DEFAULT '',
    status           TEXT NOT NULL DEFAULT 'draft'
                       CHECK (status IN ('draft', 'active', 'deprecated')),
    sensor_type      TEXT NOT NULL DEFAULT 'camera',
    supported_modes  TEXT[] NOT NULL DEFAULT '{}',
    setup            JSONB NOT NULL DEFAULT '{}',
    output_schema_ref TEXT NOT NULL DEFAULT '',
    use_cases        TEXT NOT NULL DEFAULT '',
    technical_overview TEXT NOT NULL DEFAULT '',
    limitations      TEXT NOT NULL DEFAULT '',
    version          INT NOT NULL DEFAULT 1,
    sha              TEXT NOT NULL UNIQUE,
    user_params      JSONB NOT NULL DEFAULT '{}',
    internal_config  JSONB NOT NULL DEFAULT '{}',
    created_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at       TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_tool_actions_name ON tool_actions (name);
CREATE INDEX IF NOT EXISTS idx_tool_actions_status ON tool_actions (status);
CREATE INDEX IF NOT EXISTS idx_tool_actions_sensor_type ON tool_actions (sensor_type);
CREATE INDEX IF NOT EXISTS idx_tool_actions_category ON tool_actions (category);

CREATE TABLE IF NOT EXISTS tool_action_slas (
    tool_action_id UUID NOT NULL REFERENCES tool_actions(id) ON DELETE CASCADE,
    delivery_mode  TEXT NOT NULL,
    sla_seconds    INT NOT NULL,
    notes          TEXT NOT NULL DEFAULT '',
    PRIMARY KEY (tool_action_id, delivery_mode)
);

CREATE TABLE IF NOT EXISTS action_steps (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tool_action_id  UUID NOT NULL REFERENCES tool_actions(id) ON DELETE CASCADE,
    step_id         TEXT NOT NULL,
    step_type       TEXT NOT NULL CHECK (step_type IN ('model', 'classic_algorithm', 'service')),
    capability_id   UUID,
    capability_sha  TEXT NOT NULL DEFAULT '',
    position        INT NOT NULL DEFAULT 0,
    depends_on      TEXT[] NOT NULL DEFAULT '{}',
    user_params     JSONB NOT NULL DEFAULT '{}',
    internal_config JSONB NOT NULL DEFAULT '{}',
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (tool_action_id, step_id)
);

CREATE INDEX IF NOT EXISTS idx_action_steps_tool_action_id ON action_steps (tool_action_id);
CREATE INDEX IF NOT EXISTS idx_action_steps_capability_id ON action_steps (capability_id);

CREATE TABLE IF NOT EXISTS sensor_assignments (
    id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    sensor_id        TEXT NOT NULL,
    tool_action_id   UUID NOT NULL REFERENCES tool_actions(id) ON DELETE CASCADE,
    is_active        BOOL NOT NULL DEFAULT true,
    config_overrides JSONB NOT NULL DEFAULT '{}',
    tool_action_sha  TEXT NOT NULL DEFAULT '',
    created_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (sensor_id, tool_action_id)
);

CREATE INDEX IF NOT EXISTS idx_sensor_assignments_sensor_id ON sensor_assignments (sensor_id);
CREATE INDEX IF NOT EXISTS idx_sensor_assignments_tool_action_id ON sensor_assignments (tool_action_id);
