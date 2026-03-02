-- Bootstrap migration system
-- Creates the schema_migrations table to track applied migrations

CREATE TABLE IF NOT EXISTS schema_migrations (
    version INTEGER PRIMARY KEY,
    applied_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP NOT NULL,
    checksum TEXT NOT NULL
);

-- Grant permissions to ai_user
GRANT ALL PRIVILEGES ON TABLE schema_migrations TO ai_user;
