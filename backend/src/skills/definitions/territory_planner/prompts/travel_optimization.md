# Travel Optimization

Cluster leads by geographic proximity and suggest efficient visit routes for user {user_id}.

## Data Source

Query `lead_memories` table filtered by `user_id = '{user_id}'`. Extract location data (city, state, coordinates if available) for all active leads.

## Clustering

Group leads into geographic clusters based on:
- City/metro area proximity (leads in the same metro area form a natural cluster)
- Driving/travel distance between clusters
- Aim for clusters of 3–8 accounts that can be visited in a 1–2 day trip

## Route Optimization Per Cluster

For each cluster:
- Suggest a visit sequence that minimizes backtracking
- Estimate the number of days needed for a full cluster visit (assuming 3–4 meetings/day)
- Prioritize high-value and low-health accounts for earlier visits
- Note accounts that are overdue for an in-person visit

## Territory Data Format

Use the standard territory format where each "territory" represents a travel cluster:
- `name`: Cluster label (e.g. "Boston Metro — 5 accounts")
- `lead_count`: Accounts in cluster
- `pipeline_value`: Total cluster pipeline
- `top_accounts`: Ordered by visit priority

## Recommendations

Provide travel-specific recommendations:
- Optimal trip schedule for the next 30 days
- Accounts to combine for multi-stop trips
- Accounts where virtual meetings may suffice (high health, low complexity)
- Cost-efficiency notes (clustering saves X trips vs visiting individually)

## Context Data

### Lead Data
{lead_data}

### Visit History
{visit_history}
