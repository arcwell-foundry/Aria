# Win/Loss Trend

Generate a Recharts-compatible **line chart** specification showing win/loss rates over time for user `{user_id}`.

## Data

The following real outcome data was fetched from the database:

```json
{visualization_data}
```

## Instructions

1. Create a line chart with months on the x-axis and outcome counts on the y-axis.
2. Include separate lines for wins and losses (and optionally active/in-progress).
3. Each data point: `month` (YYYY-MM), `wins` (count), `losses` (count).
4. Set `chart_type` to `"line"`.
5. Set `config.xKey` to `"month"` and add yKeys: wins (#10B981 success), losses (#EF4444 danger).
6. If a win rate can be calculated, include it as a derived percentage series.
7. Populate `metadata.record_count` from summary.total_records.
8. Set `metadata.confidence_level` based on the number of months with data.
9. Write a one-line `metadata.summary` noting the trend direction and overall win rate.
