# Territory Heatmap

Generate a treemap visualization of geographic coverage from lead locations for user {user_id}.

## Data Source

Query `lead_memories` table filtered by `user_id = '{user_id}'`. Extract location fields (state, region, or city) and aggregate by geography.

## Aggregation

Group leads by their primary geographic attribute (state or region). For each geography calculate:
- Lead count
- Total pipeline value
- Average health score

## Data Format

Each data point should have:
- `name`: Geographic region name (e.g. "Northeast", "California")
- `size`: Total pipeline value in that region (numeric, drives treemap cell size)
- `count`: Number of leads
- `health`: Average health score (0–100)

Sort by `size` descending. Limit to top 50 regions.

## Config

- chart_type: "treemap"
- xKey: "name"
- yKeys: one series for "size" (primary color)
- title: "Territory Coverage"
- subtitle: Include total territory count and aggregate pipeline value

## Context Data

{lead_data}
