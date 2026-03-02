-- PostgreSQL Cross-Region Replication Setup using pglogical
-- This script configures logical replication for multi-region deployments

-- Enable pglogical extension
CREATE EXTENSION IF NOT EXISTS pglogical;

-- Create replication user with appropriate privileges
DO $$
BEGIN
  IF NOT EXISTS (SELECT FROM pg_user WHERE usename = 'replication_user') THEN
    CREATE USER replication_user WITH REPLICATION PASSWORD 'replication_password';
    RAISE NOTICE 'Created replication user';
  ELSE
    RAISE NOTICE 'Replication user already exists';
  END IF;
END
$$;

-- Grant necessary privileges
GRANT ALL PRIVILEGES ON DATABASE ai_platform TO replication_user;
GRANT USAGE ON SCHEMA public TO replication_user;
GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA public TO replication_user;
GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public TO replication_user;
GRANT ALL PRIVILEGES ON ALL FUNCTIONS IN SCHEMA public TO replication_user;

-- Grant default privileges for future objects
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON TABLES TO replication_user;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON SEQUENCES TO replication_user;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON FUNCTIONS TO replication_user;

-- Create monitoring function for replication lag
CREATE OR REPLACE FUNCTION get_replication_lag()
RETURNS TABLE (
    subscription_name TEXT,
    remote_lsn pg_lsn,
    local_lsn pg_lsn,
    lag_bytes BIGINT,
    lag_seconds NUMERIC
) AS $$
BEGIN
    RETURN QUERY
    SELECT 
        sub.sub_name::TEXT AS subscription_name,
        sub.sub_remote_lsn AS remote_lsn,
        sub.sub_local_lsn AS local_lsn,
        pg_wal_lsn_diff(sub.sub_remote_lsn, sub.sub_local_lsn) AS lag_bytes,
        EXTRACT(EPOCH FROM (now() - sub.sub_last_sync_at)) AS lag_seconds
    FROM pglogical.subscription sub;
END;
$$ LANGUAGE plpgsql;

-- Create view for easy monitoring
CREATE OR REPLACE VIEW replication_status AS
SELECT * FROM get_replication_lag();

-- Create table for replication metrics (for Prometheus exporter)
CREATE TABLE IF NOT EXISTS replication_metrics (
    id SERIAL PRIMARY KEY,
    region VARCHAR(50) NOT NULL,
    metric_name VARCHAR(100) NOT NULL,
    metric_value NUMERIC NOT NULL,
    timestamp TIMESTAMP DEFAULT NOW(),
    INDEX idx_replication_metrics_timestamp (timestamp)
);

-- Function to update replication metrics
CREATE OR REPLACE FUNCTION update_replication_metrics()
RETURNS VOID AS $$
BEGIN
    -- Clear old metrics (keep last 24 hours)
    DELETE FROM replication_metrics WHERE timestamp < NOW() - INTERVAL '24 hours';
    
    -- Insert current replication lag metrics
    INSERT INTO replication_metrics (region, metric_name, metric_value)
    SELECT 
        split_part(subscription_name, '_', 1) AS region,
        'replication_lag_seconds',
        COALESCE(lag_seconds, 0)
    FROM replication_status;
    
    -- Insert current replication lag in bytes
    INSERT INTO replication_metrics (region, metric_name, metric_value)
    SELECT 
        split_part(subscription_name, '_', 1) AS region,
        'replication_lag_bytes',
        COALESCE(lag_bytes, 0)
    FROM replication_status;
END;
$$ LANGUAGE plpgsql;

-- Create function to setup replication node (run on each region)
CREATE OR REPLACE FUNCTION setup_replication_node(
    node_name_param TEXT,
    node_dsn_param TEXT
)
RETURNS TEXT AS $$
DECLARE
    node_exists BOOLEAN;
BEGIN
    -- Check if node already exists
    SELECT EXISTS (
        SELECT 1 FROM pglogical.node WHERE node_name = node_name_param
    ) INTO node_exists;
    
    IF node_exists THEN
        RETURN 'Node ' || node_name_param || ' already exists';
    END IF;
    
    -- Create the node
    PERFORM pglogical.create_node(
        node_name := node_name_param,
        dsn := node_dsn_param
    );
    
    RETURN 'Created node ' || node_name_param;
END;
$$ LANGUAGE plpgsql;

-- Create function to setup replication set
CREATE OR REPLACE FUNCTION setup_replication_set(
    set_name_param TEXT DEFAULT 'ai_platform_set'
)
RETURNS TEXT AS $$
DECLARE
    set_exists BOOLEAN;
BEGIN
    -- Check if replication set already exists
    SELECT EXISTS (
        SELECT 1 FROM pglogical.replication_set WHERE set_name = set_name_param
    ) INTO set_exists;
    
    IF set_exists THEN
        RETURN 'Replication set ' || set_name_param || ' already exists';
    END IF;
    
    -- Create the replication set
    PERFORM pglogical.create_replication_set(
        set_name := set_name_param,
        replicate_insert := true,
        replicate_update := true,
        replicate_delete := true,
        replicate_truncate := true
    );
    
    -- Add all tables to the replication set
    PERFORM pglogical.replication_set_add_all_tables(
        set_name := set_name_param,
        schema_names := ARRAY['public']
    );
    
    -- Add all sequences to the replication set
    PERFORM pglogical.replication_set_add_all_sequences(
        set_name := set_name_param,
        schema_names := ARRAY['public']
    );
    
    RETURN 'Created replication set ' || set_name_param || ' and added all tables/sequences';
END;
$$ LANGUAGE plpgsql;

-- Create function to setup subscription (run on replica regions)
CREATE OR REPLACE FUNCTION setup_replication_subscription(
    subscription_name_param TEXT,
    provider_dsn_param TEXT,
    replication_sets_param TEXT[] DEFAULT ARRAY['ai_platform_set', 'default']
)
RETURNS TEXT AS $$
DECLARE
    sub_exists BOOLEAN;
BEGIN
    -- Check if subscription already exists
    SELECT EXISTS (
        SELECT 1 FROM pglogical.subscription WHERE sub_name = subscription_name_param
    ) INTO sub_exists;
    
    IF sub_exists THEN
        RETURN 'Subscription ' || subscription_name_param || ' already exists';
    END IF;
    
    -- Create the subscription
    PERFORM pglogical.create_subscription(
        subscription_name := subscription_name_param,
        provider_dsn := provider_dsn_param,
        replication_sets := replication_sets_param,
        synchronize_structure := false,
        synchronize_data := true
    );
    
    RETURN 'Created subscription ' || subscription_name_param;
END;
$$ LANGUAGE plpgsql;

-- Create function to check replication health
CREATE OR REPLACE FUNCTION check_replication_health()
RETURNS TABLE (
    subscription_name TEXT,
    status TEXT,
    lag_seconds NUMERIC,
    health_status TEXT
) AS $$
BEGIN
    RETURN QUERY
    SELECT 
        sub.sub_name::TEXT AS subscription_name,
        sub.sub_status::TEXT AS status,
        EXTRACT(EPOCH FROM (now() - sub.sub_last_sync_at)) AS lag_seconds,
        CASE 
            WHEN sub.sub_status = 'ready' AND EXTRACT(EPOCH FROM (now() - sub.sub_last_sync_at)) < 30 THEN 'healthy'
            WHEN sub.sub_status = 'ready' AND EXTRACT(EPOCH FROM (now() - sub.sub_last_sync_at)) < 60 THEN 'warning'
            ELSE 'critical'
        END AS health_status
    FROM pglogical.subscription sub;
END;
$$ LANGUAGE plpgsql;

-- Create materialized view for replication dashboard
CREATE MATERIALIZED VIEW IF NOT EXISTS replication_dashboard AS
SELECT 
    rs.subscription_name,
    rs.lag_bytes,
    rs.lag_seconds,
    rh.status,
    rh.health_status
FROM replication_status rs
LEFT JOIN check_replication_health() rh ON rs.subscription_name = rh.subscription_name;

-- Create index on materialized view
CREATE INDEX IF NOT EXISTS idx_replication_dashboard_subscription 
ON replication_dashboard(subscription_name);

-- Function to refresh replication dashboard
CREATE OR REPLACE FUNCTION refresh_replication_dashboard()
RETURNS VOID AS $$
BEGIN
    REFRESH MATERIALIZED VIEW CONCURRENTLY replication_dashboard;
END;
$$ LANGUAGE plpgsql;

-- Configuration for pg_stat_replication monitoring
CREATE OR REPLACE VIEW pg_stat_replication_extended AS
SELECT 
    pid,
    usename,
    application_name,
    client_addr,
    client_hostname,
    client_port,
    backend_start,
    backend_xmin,
    state,
    sent_lsn,
    write_lsn,
    flush_lsn,
    replay_lsn,
    write_lag,
    flush_lag,
    replay_lag,
    sync_priority,
    sync_state,
    pg_wal_lsn_diff(sent_lsn, replay_lsn) AS lag_bytes,
    EXTRACT(EPOCH FROM replay_lag) AS replay_lag_seconds
FROM pg_stat_replication;

-- Grants for monitoring views
GRANT SELECT ON replication_status TO replication_user;
GRANT SELECT ON replication_dashboard TO replication_user;
GRANT SELECT ON replication_metrics TO replication_user;
GRANT SELECT ON pg_stat_replication_extended TO replication_user;

-- Example usage comments for operators:
COMMENT ON FUNCTION setup_replication_node IS 
'Setup replication node on each region. Example:
SELECT setup_replication_node(
    ''us-west-1'', 
    ''host=postgres.us-west-1.ai-platform.svc.cluster.local port=5432 dbname=ai_platform user=replication_user password=replication_password''
);';

COMMENT ON FUNCTION setup_replication_set IS
'Setup replication set with all tables. Example:
SELECT setup_replication_set(''ai_platform_set'');';

COMMENT ON FUNCTION setup_replication_subscription IS
'Setup subscription to replicate from primary region. Example (run on replica):
SELECT setup_replication_subscription(
    ''sub_from_us_west_1'',
    ''host=postgres.us-west-1.ai-platform.svc.cluster.local port=5432 dbname=ai_platform user=replication_user password=replication_password'',
    ARRAY[''ai_platform_set'', ''default'']
);';

-- Create alert thresholds table
CREATE TABLE IF NOT EXISTS replication_alert_thresholds (
    id SERIAL PRIMARY KEY,
    metric_name VARCHAR(100) NOT NULL UNIQUE,
    warning_threshold NUMERIC NOT NULL,
    critical_threshold NUMERIC NOT NULL,
    description TEXT
);

-- Insert default thresholds
INSERT INTO replication_alert_thresholds (metric_name, warning_threshold, critical_threshold, description)
VALUES 
    ('replication_lag_seconds', 30, 60, 'Replication lag in seconds'),
    ('replication_lag_bytes', 10485760, 52428800, 'Replication lag in bytes (10MB warning, 50MB critical)')
ON CONFLICT (metric_name) DO NOTHING;

-- Function to check alerts
CREATE OR REPLACE FUNCTION check_replication_alerts()
RETURNS TABLE (
    subscription_name TEXT,
    metric_name TEXT,
    current_value NUMERIC,
    threshold_exceeded TEXT,
    severity TEXT
) AS $$
BEGIN
    RETURN QUERY
    WITH current_metrics AS (
        SELECT 
            rs.subscription_name,
            'replication_lag_seconds' AS metric_name,
            rs.lag_seconds AS current_value
        FROM replication_status rs
        UNION ALL
        SELECT 
            rs.subscription_name,
            'replication_lag_bytes' AS metric_name,
            rs.lag_bytes AS current_value
        FROM replication_status rs
    )
    SELECT 
        cm.subscription_name,
        cm.metric_name,
        cm.current_value,
        CASE 
            WHEN cm.current_value >= rat.critical_threshold THEN 'Critical threshold'
            WHEN cm.current_value >= rat.warning_threshold THEN 'Warning threshold'
            ELSE 'OK'
        END AS threshold_exceeded,
        CASE 
            WHEN cm.current_value >= rat.critical_threshold THEN 'critical'
            WHEN cm.current_value >= rat.warning_threshold THEN 'warning'
            ELSE 'ok'
        END AS severity
    FROM current_metrics cm
    JOIN replication_alert_thresholds rat ON cm.metric_name = rat.metric_name
    WHERE cm.current_value >= rat.warning_threshold;
END;
$$ LANGUAGE plpgsql;

-- Grant execute permissions
GRANT EXECUTE ON FUNCTION setup_replication_node TO replication_user;
GRANT EXECUTE ON FUNCTION setup_replication_set TO replication_user;
GRANT EXECUTE ON FUNCTION setup_replication_subscription TO replication_user;
GRANT EXECUTE ON FUNCTION check_replication_health TO replication_user;
GRANT EXECUTE ON FUNCTION check_replication_alerts TO replication_user;
GRANT EXECUTE ON FUNCTION update_replication_metrics TO replication_user;

-- Success message
DO $$
BEGIN
    RAISE NOTICE 'PostgreSQL cross-region replication setup complete';
    RAISE NOTICE 'Run setup_replication_node() on each region to initialize nodes';
    RAISE NOTICE 'Run setup_replication_set() on primary region to create replication set';
    RAISE NOTICE 'Run setup_replication_subscription() on replica regions to start replication';
END
$$;
