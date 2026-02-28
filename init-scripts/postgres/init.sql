-- PostgreSQL initialization script for feedback collection system
-- Database: ai_platform

-- Create feedback table
CREATE TABLE IF NOT EXISTS feedback (
    id SERIAL PRIMARY KEY,
    feedback_id VARCHAR(255) UNIQUE NOT NULL,
    query TEXT NOT NULL,
    response TEXT NOT NULL,
    model VARCHAR(255) NOT NULL,
    memory_used INTEGER DEFAULT 0,
    tools_called TEXT[] DEFAULT ARRAY[]::TEXT[],
    rating INTEGER NOT NULL CHECK (rating IN (-1, 1)),
    reason TEXT,
    timestamp TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    user_id VARCHAR(255),
    session_id VARCHAR(255),
    intent VARCHAR(100),
    project VARCHAR(255),
    metadata JSONB DEFAULT '{}'::JSONB,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Create indexes for efficient querying
CREATE INDEX IF NOT EXISTS idx_feedback_timestamp ON feedback(timestamp);
CREATE INDEX IF NOT EXISTS idx_feedback_model ON feedback(model);
CREATE INDEX IF NOT EXISTS idx_feedback_rating ON feedback(rating);
CREATE INDEX IF NOT EXISTS idx_feedback_intent ON feedback(intent);
CREATE INDEX IF NOT EXISTS idx_feedback_project ON feedback(project);
CREATE INDEX IF NOT EXISTS idx_feedback_user_id ON feedback(user_id);
CREATE INDEX IF NOT EXISTS idx_feedback_session_id ON feedback(session_id);

-- Create accuracy tracking materialized view
CREATE MATERIALIZED VIEW IF NOT EXISTS model_accuracy_by_intent AS
SELECT 
    model,
    intent,
    project,
    COUNT(*) as total_feedback,
    COUNT(*) FILTER (WHERE rating = 1) as positive_feedback,
    COUNT(*) FILTER (WHERE rating = -1) as negative_feedback,
    ROUND(
        COUNT(*) FILTER (WHERE rating = 1)::NUMERIC / NULLIF(COUNT(*), 0) * 100, 
        2
    ) as accuracy_percentage,
    MAX(timestamp) as last_updated
FROM feedback
WHERE intent IS NOT NULL
GROUP BY model, intent, project;

-- Create index on materialized view
CREATE UNIQUE INDEX IF NOT EXISTS idx_model_accuracy_unique 
    ON model_accuracy_by_intent(model, intent, COALESCE(project, ''));

-- Create function to refresh materialized view
CREATE OR REPLACE FUNCTION refresh_model_accuracy()
RETURNS TRIGGER AS $$
BEGIN
    REFRESH MATERIALIZED VIEW CONCURRENTLY model_accuracy_by_intent;
    RETURN NULL;
END;
$$ LANGUAGE plpgsql;

-- Create trigger to auto-refresh materialized view
DROP TRIGGER IF EXISTS trigger_refresh_accuracy ON feedback;
CREATE TRIGGER trigger_refresh_accuracy
    AFTER INSERT OR UPDATE OR DELETE ON feedback
    FOR EACH STATEMENT
    EXECUTE FUNCTION refresh_model_accuracy();

-- Create function for weekly export of fine-tuning dataset
CREATE OR REPLACE FUNCTION get_weekly_finetuning_dataset(
    start_date TIMESTAMP WITH TIME ZONE DEFAULT NOW() - INTERVAL '7 days',
    end_date TIMESTAMP WITH TIME ZONE DEFAULT NOW()
)
RETURNS TABLE (
    query TEXT,
    response TEXT,
    model VARCHAR,
    rating INTEGER,
    reason TEXT,
    weight NUMERIC,
    timestamp TIMESTAMP WITH TIME ZONE,
    intent VARCHAR,
    project VARCHAR
) AS $$
BEGIN
    RETURN QUERY
    SELECT 
        f.query,
        f.response,
        f.model,
        f.rating,
        f.reason,
        CASE 
            WHEN f.rating = 1 THEN 2.0
            WHEN f.rating = -1 THEN 0.5
            ELSE 1.0
        END as weight,
        f.timestamp,
        f.intent,
        f.project
    FROM feedback f
    WHERE f.timestamp >= start_date 
      AND f.timestamp <= end_date
    ORDER BY f.timestamp DESC;
END;
$$ LANGUAGE plpgsql;

-- Create function to update updated_at timestamp
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Create trigger for updated_at
DROP TRIGGER IF EXISTS trigger_update_feedback_timestamp ON feedback;
CREATE TRIGGER trigger_update_feedback_timestamp
    BEFORE UPDATE ON feedback
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

-- Grant permissions to ai_user
GRANT ALL PRIVILEGES ON TABLE feedback TO ai_user;
GRANT ALL PRIVILEGES ON SEQUENCE feedback_id_seq TO ai_user;
GRANT SELECT ON model_accuracy_by_intent TO ai_user;
GRANT EXECUTE ON FUNCTION get_weekly_finetuning_dataset TO ai_user;
GRANT EXECUTE ON FUNCTION refresh_model_accuracy TO ai_user;

-- Drift monitoring tables
-- Create drift_metrics table for tracking drift detection results
CREATE TABLE IF NOT EXISTS drift_metrics (
    id SERIAL PRIMARY KEY,
    kl_divergence FLOAT NOT NULL,
    psi FLOAT NOT NULL,
    baseline_accuracy FLOAT NOT NULL,
    current_accuracy FLOAT NOT NULL,
    drift_detected BOOLEAN NOT NULL,
    severity VARCHAR(20),
    timestamp TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Create indexes for drift_metrics
CREATE INDEX IF NOT EXISTS idx_drift_metrics_timestamp ON drift_metrics(timestamp);
CREATE INDEX IF NOT EXISTS idx_drift_metrics_drift_detected ON drift_metrics(drift_detected);
CREATE INDEX IF NOT EXISTS idx_drift_metrics_severity ON drift_metrics(severity);

-- Create finetuning_triggers table for tracking automatic fine-tuning triggers
CREATE TABLE IF NOT EXISTS finetuning_triggers (
    id SERIAL PRIMARY KEY,
    job_id VARCHAR(255),
    drift_metrics JSONB,
    trigger_timestamp TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Create indexes for finetuning_triggers
CREATE INDEX IF NOT EXISTS idx_finetuning_triggers_timestamp ON finetuning_triggers(trigger_timestamp);
CREATE INDEX IF NOT EXISTS idx_finetuning_triggers_job_id ON finetuning_triggers(job_id);

-- Grant permissions to ai_user for drift monitoring tables
GRANT ALL PRIVILEGES ON TABLE drift_metrics TO ai_user;
GRANT ALL PRIVILEGES ON SEQUENCE drift_metrics_id_seq TO ai_user;
GRANT ALL PRIVILEGES ON TABLE finetuning_triggers TO ai_user;
GRANT ALL PRIVILEGES ON SEQUENCE finetuning_triggers_id_seq TO ai_user;

-- LoRA adapter version tracking
CREATE TABLE IF NOT EXISTS lora_adapters (
    id SERIAL PRIMARY KEY,
    version VARCHAR(50) UNIQUE NOT NULL,
    training_job_id VARCHAR(255),
    base_model VARCHAR(255) NOT NULL,
    rank INTEGER NOT NULL,
    alpha INTEGER NOT NULL,
    dropout FLOAT NOT NULL,
    num_epochs INTEGER,
    learning_rate FLOAT,
    batch_size INTEGER,
    num_samples INTEGER,
    training_loss FLOAT,
    validation_loss FLOAT,
    training_time_seconds INTEGER,
    minio_path TEXT,
    metadata JSONB DEFAULT '{}'::JSONB,
    is_active BOOLEAN DEFAULT false,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    deployed_at TIMESTAMP WITH TIME ZONE,
    deactivated_at TIMESTAMP WITH TIME ZONE
);

-- Create indexes for lora_adapters
CREATE INDEX IF NOT EXISTS idx_lora_adapters_version ON lora_adapters(version);
CREATE INDEX IF NOT EXISTS idx_lora_adapters_is_active ON lora_adapters(is_active);
CREATE INDEX IF NOT EXISTS idx_lora_adapters_created_at ON lora_adapters(created_at);
CREATE INDEX IF NOT EXISTS idx_lora_adapters_training_job_id ON lora_adapters(training_job_id);

-- LoRA adapter performance metrics
CREATE TABLE IF NOT EXISTS lora_performance (
    id SERIAL PRIMARY KEY,
    adapter_version VARCHAR(50) NOT NULL,
    metric_name VARCHAR(100) NOT NULL,
    metric_value FLOAT NOT NULL,
    sample_count INTEGER,
    timestamp TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    metadata JSONB DEFAULT '{}'::JSONB,
    FOREIGN KEY (adapter_version) REFERENCES lora_adapters(version) ON DELETE CASCADE
);

-- Create indexes for lora_performance
CREATE INDEX IF NOT EXISTS idx_lora_performance_adapter_version ON lora_performance(adapter_version);
CREATE INDEX IF NOT EXISTS idx_lora_performance_metric_name ON lora_performance(metric_name);
CREATE INDEX IF NOT EXISTS idx_lora_performance_timestamp ON lora_performance(timestamp);

-- Grant permissions for LoRA tracking tables
GRANT ALL PRIVILEGES ON TABLE lora_adapters TO ai_user;
GRANT ALL PRIVILEGES ON SEQUENCE lora_adapters_id_seq TO ai_user;
GRANT ALL PRIVILEGES ON TABLE lora_performance TO ai_user;
GRANT ALL PRIVILEGES ON SEQUENCE lora_performance_id_seq TO ai_user;
