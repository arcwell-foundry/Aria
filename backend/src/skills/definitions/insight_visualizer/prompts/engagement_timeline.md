# Engagement Timeline

Generate a Recharts-compatible **bar chart** specification showing communication frequency per lead for user `{user_id}`.

## Data

The following real engagement data was fetched from the database:

```json
{visualization_data}
```

## Instructions

1. Create a stacked bar chart with leads on the x-axis and event counts on the y-axis.
2. Stack by event type (email_sent, email_received, meeting, call, etc.) using distinct ARIA palette colors.
3. Limit to top 15 most-engaged leads for readability.
4. Set `chart_type` to `"bar"`.
5. Set `config.xKey` to `"lead"` and add one yKey per event type, each with `stackId: "engagement"`.
6. Color mapping: email_sent (#6366F1), email_received (#3B82F6), meeting (#10B981), call (#F59E0B).
7. Populate `metadata.record_count` from total_events.
8. Set `metadata.confidence_level` based on total_events: high if >50, moderate if 10-50, low if <10.
9. Write a one-line `metadata.summary` noting which leads are most/least engaged.
