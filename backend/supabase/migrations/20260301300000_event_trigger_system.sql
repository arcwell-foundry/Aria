-- Event Trigger System: Central event log for real-time event processing
-- Tracks all events (Composio webhooks, internal signals, reconciliation catches)
-- through their full lifecycle: received → classified → processing → handled → delivered

CREATE TABLE IF NOT EXISTS event_log (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES auth.users(id),
    event_type TEXT NOT NULL,
    event_source TEXT NOT NULL,
    source_id TEXT,
    payload JSONB NOT NULL DEFAULT '{}',
    classification JSONB,
    handler_result JSONB,
    pulse_signal_id UUID,
    status TEXT NOT NULL DEFAULT 'received',
    error_message TEXT,
    latency_ms INTEGER,
    is_reconciliation BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    processed_at TIMESTAMPTZ,
    delivered_at TIMESTAMPTZ
);

CREATE INDEX idx_event_log_user_status ON event_log(user_id, status);
CREATE INDEX idx_event_log_type ON event_log(event_type);
CREATE INDEX idx_event_log_source_id ON event_log(source_id);
CREATE INDEX idx_event_log_created ON event_log(created_at DESC);

ALTER TABLE event_log ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Users see own events"
    ON event_log FOR SELECT
    USING (auth.uid() = user_id);

CREATE POLICY "Service can insert events"
    ON event_log FOR INSERT
    WITH CHECK (true);

CREATE POLICY "Service can update events"
    ON event_log FOR UPDATE
    USING (true);
