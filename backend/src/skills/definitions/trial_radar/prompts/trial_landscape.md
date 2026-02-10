# Trial Landscape

Generate a comprehensive clinical trial landscape for **{therapeutic_area}**.

## Data Retrieval

1. Search ClinicalTrials.gov for all active and recently completed trials:
   - `GET https://clinicaltrials.gov/api/v2/studies?query.cond={therapeutic_area}&filter.overallStatus=RECRUITING,ACTIVE_NOT_RECRUITING,ENROLLING_BY_INVITATION,COMPLETED&pageSize=100&fields=NCTId,BriefTitle,Phase,OverallStatus,EnrollmentCount,StartDate,PrimaryCompletionDate,Condition,InterventionName,InterventionType,LeadSponsorName,LeadSponsorClass&format=json`
2. If results exceed 100, paginate to capture the full landscape (up to 500 trials).
3. For key trials (Phase 3 and pivotal Phase 2), fetch full study detail:
   - `GET https://clinicaltrials.gov/api/v2/studies/{nctId}?format=json`

## Phase Distribution Analysis

Aggregate trials by phase and produce counts:
- Early Phase 1
- Phase 1
- Phase 1/Phase 2
- Phase 2
- Phase 2/Phase 3
- Phase 3
- Phase 4
- Not Applicable

Calculate the "pipeline maturity index": weighted sum where Phase 3 = 3 points, Phase 2 = 2, Phase 1 = 1. Higher index = more mature pipeline in the therapeutic area.

## Sponsor Landscape

Group trials by lead sponsor and classify:
- **Industry**: Pharmaceutical and biotech companies
- **Academic**: Universities and medical centers
- **Government**: NIH, BARDA, etc.
- **Consortium**: Multi-site collaborative groups

Identify the top 10 sponsors by active trial count.

## Geographic & Site Distribution

From study location data (where available):
- Count trials by country
- Identify multi-national vs. single-country trials
- Note any concentration in specific regions

## Competitive Density

Calculate competitive metrics:
- **Total active trials** in the therapeutic area
- **Trial density trend**: Is the number of new trial starts increasing or decreasing?
- **Crowded indications**: Sub-indications with >10 active trials
- **White space indications**: Related sub-indications with <3 active trials

## Chart Output

Produce a **bar chart** showing phase distribution across the therapeutic area.

- xKey: `"phase"` (using ClinicalTrials.gov phase labels)
- yKeys: `industry_trials` (primary color), `academic_trials` (success color), `government_trials` (info color)
- Stack bars by sponsor class to show both total count and composition
- Use stackId: `"sponsor"` for all three yKeys
- Include subtitle with total trial count and top sponsor

Populate `trial_context` with full `search_scope`, `phase_distribution`, `enrollment_summary`, `key_trials` (top 10 Phase 3 trials), and `competitive_clusters`. Include `metadata.summary` with the key landscape insight (e.g., "142 active trials in NSCLC dominated by immunotherapy combinations, with Merck and Roche leading Phase 3 activity").
