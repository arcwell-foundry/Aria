-- Action undo buffer table for ARIA execution modes.
-- Tracks recently executed actions within a 5-minute undo window.
-- Referenced by ActionExecutionService for EXECUTE_AND_NOTIFY mode.

CREATE TABLE IF NOT EXISTS action_undo_buffer (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  action_id UUID NOT NULL REFERENCES aria_action_queue(id),
  user_id UUID NOT NULL REFERENCES auth.users(id),
  action_category TEXT NOT NULL,
  executed_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  undo_deadline TIMESTAMPTZ NOT NULL,  -- executed_at + interval '5 minutes'
  undo_requested BOOLEAN NOT NULL DEFAULT false,
  undo_completed BOOLEAN NOT NULL DEFAULT false,
  reversal_details JSONB,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_undo_buffer_user_deadline ON action_undo_buffer(user_id, undo_deadline);
CREATE INDEX idx_undo_buffer_action ON action_undo_buffer(action_id);

ALTER TABLE action_undo_buffer ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Users can view own undo buffer"
  ON action_undo_buffer FOR SELECT
  USING (auth.uid() = user_id);

CREATE POLICY "Service can insert undo buffer"
  ON action_undo_buffer FOR INSERT
  WITH CHECK (auth.uid() = user_id);

CREATE POLICY "Users can update own undo buffer"
  ON action_undo_buffer FOR UPDATE
  USING (auth.uid() = user_id);
