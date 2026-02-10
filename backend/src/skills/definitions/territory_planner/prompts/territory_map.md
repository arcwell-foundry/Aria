# Territory Map

Generate a geographic heatmap of lead distribution with pipeline value sizing for user {user_id}.

## Data Source

Query `lead_memories` table filtered by `user_id = '{user_id}'`. Extract location fields (state, region, city, or headquarters location) and aggregate by geography.

## Aggregation

Group leads by their primary geographic region. For each region calculate:
- Lead count
- Total pipeline value (sum of deal values across all stages)
- Average health score
- Average deal size
- Top 3 accounts by pipeline value

## Territory Data Format

Each territory entry should have:
- `name`: Geographic region name (e.g. "Greater Boston", "San Francisco Bay Area", "Research Triangle")
- `lead_count`: Number of leads in territory
- `pipeline_value`: Total pipeline value (numeric USD)
- `avg_health_score`: Average health score (0–100)
- `avg_deal_size`: Average deal size (numeric USD)
- `top_accounts`: Array of top account names
- `status`: "overloaded" if >2x median lead count, "underserved" if <0.5x median, otherwise "balanced"

Sort by `pipeline_value` descending. Limit to top 50 territories.

## Visualization

Generate an insight-visualizer compatible treemap specification:
- chart_type: "treemap"
- data: Array of objects with `name`, `size` (pipeline_value), `count` (lead_count), `health` (avg_health_score)
- config:
  - title: "Territory Coverage"
  - subtitle: Include total territory count and aggregate pipeline value
  - xKey: "name"
  - yKeys: one series for "size" with label "Pipeline Value" and color "#6366F1"

## Recommendations

Provide 2–5 recommendations based on observed patterns:
- Flag overloaded territories that may need splitting
- Flag underserved territories with high-value accounts
- Identify concentration risk (too much pipeline in one region)

## Context Data

{lead_data}
