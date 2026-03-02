-- Add workspace registry and metering tables

-- Workspace registry (tenant lifecycle)
CREATE TABLE IF NOT EXISTS workspaces (
    id SERIAL PRIMARY KEY,
    workspace_id VARCHAR(255) UNIQUE NOT NULL,
    display_name VARCHAR(255),
    status VARCHAR(16) NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'disabled')),
    metadata JSONB DEFAULT '{}'::JSONB,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    disabled_at TIMESTAMP WITH TIME ZONE
);

CREATE INDEX IF NOT EXISTS idx_workspaces_workspace_id ON workspaces(workspace_id);
CREATE INDEX IF NOT EXISTS idx_workspaces_status ON workspaces(status);

DROP TRIGGER IF EXISTS trigger_update_workspaces_timestamp ON workspaces;
CREATE TRIGGER trigger_update_workspaces_timestamp
    BEFORE UPDATE ON workspaces
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

GRANT ALL PRIVILEGES ON TABLE workspaces TO ai_user;
GRANT ALL PRIVILEGES ON SEQUENCE workspaces_id_seq TO ai_user;

-- Workspace/user-scoped metering events
CREATE TABLE IF NOT EXISTS workspace_metering_events (
    id SERIAL PRIMARY KEY,
    event_id VARCHAR(255) UNIQUE NOT NULL,
    workspace_id VARCHAR(255) NOT NULL,
    user_id VARCHAR(255),
    meter_key VARCHAR(128) NOT NULL,
    quantity DOUBLE PRECISION NOT NULL DEFAULT 1,
    request_id VARCHAR(255),
    metadata JSONB DEFAULT '{}'::JSONB,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_metering_workspace_id ON workspace_metering_events(workspace_id);
CREATE INDEX IF NOT EXISTS idx_metering_user_id ON workspace_metering_events(user_id);
CREATE INDEX IF NOT EXISTS idx_metering_meter_key ON workspace_metering_events(meter_key);
CREATE INDEX IF NOT EXISTS idx_metering_created_at ON workspace_metering_events(created_at);
CREATE INDEX IF NOT EXISTS idx_metering_workspace_meter_key
    ON workspace_metering_events(workspace_id, meter_key);
CREATE INDEX IF NOT EXISTS idx_metering_workspace_user_meter_key
    ON workspace_metering_events(workspace_id, user_id, meter_key);

GRANT ALL PRIVILEGES ON TABLE workspace_metering_events TO ai_user;
GRANT ALL PRIVILEGES ON SEQUENCE workspace_metering_events_id_seq TO ai_user;
