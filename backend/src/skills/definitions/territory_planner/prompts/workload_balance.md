# Workload Balance

Analyze rep workload distribution across territories and flag imbalances for user {user_id}.

## Data Source

Query `lead_memories` table filtered by `user_id = '{user_id}'`. Group by territory/region and calculate workload metrics.

## Workload Metrics Per Territory

For each territory calculate:
- **Lead count**: Total active leads
- **Pipeline value**: Total deal value across all stages
- **Active deal count**: Leads in stages QUALIFIED through NEGOTIATION
- **Avg health score**: Portfolio health indicator
- **Meeting density**: Approximate meetings per week based on active deals
- **Admin burden score**: Estimated administrative overhead (higher for complex, multi-stakeholder deals)

## Balance Assessment

Calculate the median lead count and median pipeline value across all territories:
- **Overloaded**: Lead count > 2× median OR pipeline value > 3× median
- **Balanced**: Within 0.5×–2× median on both metrics
- **Underserved**: Lead count < 0.5× median AND pipeline value < 0.5× median

## Territory Data Format

Each territory entry includes all standard fields plus:
- `status`: "overloaded", "balanced", or "underserved"
- Recommendations should address specific rebalancing actions

## Recommendations

Provide actionable rebalancing recommendations:
- Which territories should be split (if overloaded)
- Which territories can be merged (if too small)
- Which accounts could be reassigned for better balance
- Impact estimate for each change (e.g. "Splitting Northeast reduces avg load by 35%")

Priority: high for territories with health score < 50 AND overloaded status.

## Context Data

{lead_data}
