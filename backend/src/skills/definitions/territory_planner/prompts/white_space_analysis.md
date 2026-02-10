# White Space Analysis

Identify uncovered life sciences markets and expansion opportunities for user {user_id}.

## Data Source

Query `lead_memories` table filtered by `user_id = '{user_id}'`. Extract all geographic locations where the user has active leads or accounts.

## Known Life Sciences Hubs

Compare current territory coverage against these major life sciences markets:
- **Tier 1** (must-have presence): Boston/Cambridge MA, San Francisco Bay Area CA, San Diego CA, Research Triangle NC, New Jersey (NJ Pharma Corridor)
- **Tier 2** (strong markets): Philadelphia PA, Minneapolis MN, Indianapolis IN, Chicago IL, Los Angeles CA, Seattle WA, Washington DC / Maryland
- **Tier 3** (emerging hubs): Houston TX, Denver CO, Austin TX, Nashville TN, Salt Lake City UT, Pittsburgh PA

## Analysis

For each known hub:
1. Check if the user has leads in or near this market
2. If uncovered, estimate the market opportunity based on known biopharma density
3. If partially covered, note the coverage gap (e.g. "2 leads but 50+ potential accounts")

## Territory Data Format

For covered territories, use the standard format with status "balanced" or "overloaded".
For uncovered hubs, use:
- `name`: Hub name
- `lead_count`: 0
- `pipeline_value`: 0
- `status`: "uncovered"
- `avg_health_score`: 0

## Recommendations

Provide expansion recommendations prioritized by:
1. Market size and biopharma density
2. Adjacency to existing strong territories
3. Competitive landscape signals (if available)
4. Travel efficiency from the user's base

## Context Data

{lead_data}
