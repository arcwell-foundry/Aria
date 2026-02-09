-- Create predictions table for tracking ARIA's predictions
CREATE TABLE predictions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,

    -- Prediction content
    prediction_type TEXT NOT NULL CHECK (
        prediction_type IN ('user_action', 'external_event', 'deal_outcome', 'timing', 'market_signal', 'lead_response', 'meeting_outcome')
    ),
    prediction_text TEXT NOT NULL,
    predicted_outcome TEXT,
    confidence FLOAT NOT NULL CHECK (confidence >= 0 AND confidence <= 1),

    -- Context
    context JSONB,
    source_conversation_id UUID,
    source_message_id UUID,
    validation_criteria TEXT,

    -- Timeline
    expected_resolution_date DATE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    -- Outcome
    status TEXT NOT NULL DEFAULT 'pending' CHECK (
        status IN ('pending', 'validated_correct', 'validated_incorrect', 'expired', 'cancelled')
    ),
    validated_at TIMESTAMPTZ,
    validation_notes TEXT
);

-- Create calibration tracking table
CREATE TABLE prediction_calibration (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    prediction_type TEXT NOT NULL,
    confidence_bucket FLOAT NOT NULL CHECK (confidence_bucket >= 0.1 AND confidence_bucket <= 1.0),
    total_predictions INTEGER NOT NULL DEFAULT 0,
    correct_predictions INTEGER NOT NULL DEFAULT 0,
    last_updated TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE(user_id, prediction_type, confidence_bucket)
);

-- Indexes for predictions
CREATE INDEX idx_predictions_user_status ON predictions(user_id, status);
CREATE INDEX idx_predictions_resolution ON predictions(expected_resolution_date) WHERE status = 'pending';
CREATE INDEX idx_predictions_type ON predictions(user_id, prediction_type);
CREATE INDEX idx_predictions_created ON predictions(user_id, created_at DESC);

-- Indexes for calibration
CREATE INDEX idx_calibration_user ON prediction_calibration(user_id);
CREATE INDEX idx_calibration_user_type ON prediction_calibration(user_id, prediction_type);

-- Enable RLS
ALTER TABLE predictions ENABLE ROW LEVEL SECURITY;
ALTER TABLE prediction_calibration ENABLE ROW LEVEL SECURITY;

-- RLS policies for predictions
CREATE POLICY "Users can read own predictions" ON predictions
    FOR SELECT USING (auth.uid() = user_id);

CREATE POLICY "Users can insert own predictions" ON predictions
    FOR INSERT WITH CHECK (auth.uid() = user_id);

CREATE POLICY "Users can update own predictions" ON predictions
    FOR UPDATE USING (auth.uid() = user_id);

CREATE POLICY "Users can delete own predictions" ON predictions
    FOR DELETE USING (auth.uid() = user_id);

-- RLS policies for calibration
CREATE POLICY "Users can read own calibration" ON prediction_calibration
    FOR SELECT USING (auth.uid() = user_id);

CREATE POLICY "Users can insert own calibration" ON prediction_calibration
    FOR INSERT WITH CHECK (auth.uid() = user_id);

CREATE POLICY "Users can update own calibration" ON prediction_calibration
    FOR UPDATE USING (auth.uid() = user_id);

-- Function for atomic calibration upsert
CREATE OR REPLACE FUNCTION upsert_calibration(
    p_user_id UUID,
    p_prediction_type TEXT,
    p_confidence_bucket FLOAT,
    p_is_correct BOOLEAN
) RETURNS VOID AS $$
BEGIN
    INSERT INTO prediction_calibration (
        user_id, prediction_type, confidence_bucket,
        total_predictions, correct_predictions
    ) VALUES (
        p_user_id, p_prediction_type, p_confidence_bucket,
        1, CASE WHEN p_is_correct THEN 1 ELSE 0 END
    )
    ON CONFLICT (user_id, prediction_type, confidence_bucket)
    DO UPDATE SET
        total_predictions = prediction_calibration.total_predictions + 1,
        correct_predictions = prediction_calibration.correct_predictions +
            CASE WHEN p_is_correct THEN 1 ELSE 0 END,
        last_updated = NOW();
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

-- Comments
COMMENT ON TABLE predictions IS 'Stores predictions made by ARIA for learning and calibration';
COMMENT ON COLUMN predictions.confidence IS '0.0-1.0 confidence level in the prediction';
COMMENT ON COLUMN predictions.prediction_type IS 'Category of prediction for calibration tracking';
COMMENT ON TABLE prediction_calibration IS 'Tracks prediction accuracy by confidence bucket for calibration';
COMMENT ON COLUMN prediction_calibration.confidence_bucket IS 'Rounded confidence value (0.1, 0.2, ..., 1.0)';
COMMENT ON FUNCTION upsert_calibration IS 'Atomically updates calibration stats when a prediction is validated';
