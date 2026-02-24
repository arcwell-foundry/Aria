# Territory Heatmap

Generate a Recharts-compatible **treemap** specification showing geographic lead distribution for user `{user_id}`.

## Data

The following real territory data was fetched from the database:

```json
{visualization_data}
```

## Instructions

1. Use a treemap where each cell represents a geographic region.
2. Cell size reflects lead count; color reflects average health score (green for healthy, red for at-risk).
3. Each data point: `name` (location string), `size` (lead_count), `color` (health-mapped hex).
4. Set `chart_type` to `"treemap"`.
5. Set `config.xKey` to `"name"` and one yKey with key `"size"`, label `"Leads"`, color `"#6366F1"`.
6. Limit to top 50 regions by lead count.
7. Populate `metadata.record_count` with total leads across all regions.
8. Set `metadata.confidence_level` based on data completeness.
9. Write a one-line `metadata.summary` noting the top region and any coverage gaps.
