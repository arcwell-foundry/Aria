# Win/Loss Trend

Generate a line chart showing win/loss rates over time from lead status changes for user {user_id}.

## Data Source

Query `lead_memories` table filtered by `user_id = '{user_id}'` where `lifecycle_stage` is CLOSED_WON or CLOSED_LOST. Use the `updated_at` timestamp to determine when the status changed.

## Aggregation

Group by month (format: "Jan 2026", "Feb 2026", etc.). For each month calculate:
- Win count (CLOSED_WON)
- Loss count (CLOSED_LOST)
- Win rate percentage: wins / (wins + losses) * 100
- Total closed value (sum of deal_value for won deals)

Include up to 12 most recent months. Omit months with zero closings.

## Data Format

Each data point should have:
- `month`: Month label (e.g. "Jan 2026")
- `wins`: Number of wins
- `losses`: Number of losses
- `win_rate`: Win rate as percentage (0–100)
- `closed_value`: Total won deal value

## Config

- chart_type: "line"
- xKey: "month"
- yKeys:
  - "win_rate" (success color, label: "Win Rate %")
  - "wins" (primary color, label: "Wins")
  - "losses" (danger color, label: "Losses")
- title: "Win/Loss Trend"
- subtitle: Include overall win rate and total closed value for the period

## Context Data

{lead_data}
