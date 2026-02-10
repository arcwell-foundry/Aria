# Pipeline Funnel Visualization

Generate a funnel chart showing pipeline stage distribution for user {user_id}.

## Data Source

Query `lead_memories` table filtered by `user_id = '{user_id}'` where `lifecycle_stage` is active (not CHURNED or ARCHIVED).

Group leads by `lifecycle_stage` and count the number of leads in each stage. Also sum `deal_value` per stage.

## Expected Stages (funnel order)

1. PROSPECT
2. QUALIFIED
3. ENGAGED
4. PROPOSAL
5. NEGOTIATION
6. CLOSED_WON

Omit stages with zero leads. Include CLOSED_LOST as a separate annotation in metadata.summary but not in the funnel data.

## Data Format

Each data point should have:
- `stage`: Human-readable stage name (e.g. "Prospect", "Qualified")
- `count`: Number of leads in this stage
- `value`: Total deal value in this stage (numeric, USD)

## Config

- chart_type: "funnel"
- xKey: "stage"
- yKeys: one series for "count" (primary color) and one for "value" (accent1 color)
- title: "Pipeline Distribution"
- subtitle: Include total pipeline value and lead count

## Context Data

{lead_data}
