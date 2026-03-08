-- Stale threads detection function for follow-up tracking
-- Finds sent drafts where the recipient hasn't replied within the threshold

CREATE OR REPLACE FUNCTION get_stale_threads(p_user_id UUID)
RETURNS TABLE (
    draft_id UUID,
    recipient_name TEXT,
    recipient_email TEXT,
    subject TEXT,
    sent_at TIMESTAMPTZ,
    days_since_sent INTEGER,
    urgency TEXT,
    thread_id TEXT
) AS $$
BEGIN
    RETURN QUERY
    SELECT
        d.id AS draft_id,
        d.recipient_name,
        d.recipient_email,
        d.subject,
        d.sent_at,
        EXTRACT(DAY FROM NOW() - d.sent_at)::INTEGER AS days_since_sent,
        COALESCE(e.urgency, 'NORMAL')::TEXT AS urgency,
        d.thread_id
    FROM email_drafts d
    LEFT JOIN email_scan_log e
        ON e.email_id = d.original_email_id
        AND e.user_id = d.user_id
    WHERE d.user_id = p_user_id
      AND d.status IN ('sent', 'saved_to_client', 'approved')
      AND d.sent_at < NOW() - INTERVAL '3 days'
      AND (
          d.thread_id IS NULL
          OR NOT EXISTS (
              SELECT 1 FROM email_scan_log s
              WHERE s.user_id = p_user_id
                AND s.thread_id = d.thread_id
                AND s.sender_email = d.recipient_email
                AND s.scanned_at > d.sent_at
                AND s.category != 'SKIP'
          )
      )
    ORDER BY days_since_sent DESC;
END;
$$ LANGUAGE plpgsql STABLE;

COMMENT ON FUNCTION get_stale_threads IS 'Finds sent drafts where the recipient has not replied. Used for follow-up tracking.';
