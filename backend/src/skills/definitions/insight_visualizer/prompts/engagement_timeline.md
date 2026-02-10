# Engagement Timeline

Generate a timeline chart showing communication frequency per lead from events for user {user_id}.

## Data Source

Query `lead_memory_events` table joined with `lead_memories` filtered by `user_id = '{user_id}'`. Extract event timestamps and types (email, call, meeting, note).

## Aggregation

Group by week over the most recent 12 weeks. For each week calculate:
- Total events across all leads
- Events by type (email, call, meeting, note)
- Number of unique leads contacted

## Data Format

Each data point should have:
- `week`: Week label (e.g. "Week of Jan 6")
- `emails`: Email event count
- `calls`: Call event count
- `meetings`: Meeting event count
- `notes`: Note event count
- `unique_leads`: Number of distinct leads engaged

## Config

- chart_type: "bar"
- xKey: "week"
- yKeys (stacked):
  - "emails" (info color, label: "Emails", stackId: "engagement")
  - "calls" (success color, label: "Calls", stackId: "engagement")
  - "meetings" (accent1 color, label: "Meetings", stackId: "engagement")
  - "notes" (muted color, label: "Notes", stackId: "engagement")
- title: "Engagement Activity"
- subtitle: Include total events and average weekly unique leads

## Context Data

{event_data}
