# Pipeline Funnel Visualization

Generate a Recharts-compatible **funnel chart** specification showing the lead pipeline distribution for user `{user_id}`.

## Data

The following real pipeline data was fetched from the database:

```json
{visualization_data}
```

## Instructions

1. Map each pipeline stage to a funnel step, ordered from earliest to latest stage (e.g. Prospecting > Qualified > Proposal > Negotiation > Won).
2. Each data point must have `stage` (string label) and `value` (numeric count).
3. Use ARIA palette colors progressing from primary (#6366F1) at the top to success (#10B981) at the bottom.
4. If the data includes `avg_health_score`, include it as a secondary metric in the tooltip config.
5. Set `chart_type` to `"funnel"`.
6. Set `config.xKey` to `"stage"` and include one yKey with key `"value"`, label `"Leads"`, color `"#6366F1"`.
7. Populate `metadata.record_count` with the total number of leads.
8. Set `metadata.confidence_level` based on total_leads: high if >20, moderate if 5-20, low if <5.
9. Write a one-line `metadata.summary` describing the pipeline shape.
