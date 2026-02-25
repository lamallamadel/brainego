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
