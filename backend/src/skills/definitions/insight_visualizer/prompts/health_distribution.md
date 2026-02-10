# Health Distribution

Generate a bar chart showing health score distribution across the portfolio for user {user_id}.

## Data Source

Query `health_score_history` table joined with `lead_memories` filtered by `user_id = '{user_id}'`. Use the most recent health score per lead.

## Aggregation

Bucket leads by health score ranges:
- 0–20: "Critical" (danger color)
- 21–40: "At Risk" (warning color)
- 41–60: "Needs Attention" (info color)
- 61–80: "Healthy" (success color)
- 81–100: "Thriving" (primary color)

For each bucket calculate:
- Lead count
- Total pipeline value
- Average deal value

## Data Format

Each data point should have:
- `bucket`: Bucket label (e.g. "Critical", "At Risk")
- `count`: Number of leads in this bucket
- `pipeline_value`: Total pipeline value (numeric)
- `avg_deal_value`: Average deal value (numeric)

Order buckets from Critical to Thriving (ascending health).

## Config

- chart_type: "bar"
- xKey: "bucket"
- yKeys:
  - "count" (primary color, label: "Lead Count")
  - "pipeline_value" (accent1 color, label: "Pipeline Value")
- title: "Portfolio Health Distribution"
- subtitle: Include total leads, average health score, and leads needing attention (score < 41)

## Context Data

{health_data}
