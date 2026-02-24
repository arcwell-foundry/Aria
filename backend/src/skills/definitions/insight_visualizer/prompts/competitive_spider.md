# Competitive Spider Chart

Generate a Recharts-compatible **radar chart** specification comparing competitors for user `{user_id}`.

## Data

The following real battle card data was fetched from the database:

```json
{visualization_data}
```

## Instructions

1. Create a radar chart with one series per competitor (max 6 competitors).
2. Each axis represents a competitive dimension (e.g. Product, Pricing, Support, Market Share, Innovation, Clinical Evidence).
3. Values should be normalized to 0-100 scale.
4. Set `chart_type` to `"radar"`.
5. Set `config.xKey` to `"dimension"` and add one yKey per competitor with distinct ARIA palette colors.
6. If no dimension_scores exist in the data, derive reasonable axes from available battle card fields.
7. Populate `metadata.record_count` with the number of competitors analyzed.
8. Set `metadata.confidence_level` based on data completeness.
9. Write a one-line `metadata.summary` highlighting the strongest/weakest competitor.
