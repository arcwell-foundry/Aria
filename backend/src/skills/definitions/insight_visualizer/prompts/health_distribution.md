# Health Score Distribution

Generate a Recharts-compatible **bar chart** specification showing health score distribution across the portfolio for user `{user_id}`.

## Data

The following real health score data was fetched from the database:

```json
{visualization_data}
```

## Instructions

1. Create a histogram-style bar chart with score ranges on the x-axis and lead counts on the y-axis.
2. Use color gradient: red (#EF4444) for 0-29, warning (#F59E0B) for 30-59, success (#10B981) for 60-100.
3. Each data point: `range` (e.g. "0-9", "10-19"), `count` (number of leads in that range).
4. Set `chart_type` to `"bar"`.
5. Set `config.xKey` to `"range"` and one yKey with key `"count"`, label `"Leads"`.
6. Assign colors per bar based on the health range (danger/warning/success).
7. Populate `metadata.record_count` from statistics.count.
8. Set `metadata.confidence_level` based on the number of leads with scores.
9. Write a one-line `metadata.summary` noting the mean score and distribution shape (skewed healthy, bimodal, etc.).
