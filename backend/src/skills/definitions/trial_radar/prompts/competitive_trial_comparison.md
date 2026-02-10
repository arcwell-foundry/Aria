# Competitive Trial Comparison

Generate a head-to-head comparison of competing clinical trials in **{therapeutic_area}** organized by sponsor strategy.

## Data Retrieval

1. Search ClinicalTrials.gov for active trials, prioritizing Phase 2 and Phase 3:
   - `GET https://clinicaltrials.gov/api/v2/studies?query.cond={therapeutic_area}&filter.overallStatus=RECRUITING,ACTIVE_NOT_RECRUITING,ENROLLING_BY_INVITATION&filter.phase=PHASE2,PHASE3&pageSize=100&fields=NCTId,BriefTitle,Phase,OverallStatus,EnrollmentCount,StartDate,PrimaryCompletionDate,Condition,InterventionName,InterventionType,LeadSponsorName,PrimaryOutcomeMeasure,SecondaryOutcomeMeasure&format=json`
2. Fetch full study details for Phase 3 trials:
   - `GET https://clinicaltrials.gov/api/v2/studies/{nctId}?format=json`
3. Group trials by mechanism of action or drug class.

## Competitive Clustering

Group competing trials into clusters by:
- **Mechanism of action** (e.g., PD-1 inhibitors, CDK4/6 inhibitors, GLP-1 agonists)
- **Drug class** (e.g., monoclonal antibodies, small molecules, cell therapies, ADCs)
- **Combination strategy** (monotherapy vs. combination, and combination partners)

For each cluster, identify:
- Number of competing trials
- Sponsors involved
- Phase distribution within the cluster
- Most advanced trial (closest to completion)

## Endpoint Design Comparison

For each competitive cluster, compare endpoint strategies:
- **Primary endpoints**: Categorize as efficacy, safety, biomarker, PRO, or composite
- **Endpoint convergence**: Are competitors using similar endpoints (industry consensus)?
- **Endpoint innovation**: Any novel endpoints (biomarker-based, digital, composite)?
- **Regulatory implications**: Note if endpoints align with known FDA/EMA preferences

## Timeline & Positioning

For each sponsor within a competitive cluster:
- **Estimated data readout**: Based on primary completion date
- **First-mover advantage**: Which trial will likely report first?
- **Enrollment advantage**: Which trial has the largest enrollment (statistical power)?
- **Differentiation strategy**: Unique indication, population, combination, or endpoint

## Chart Output

Produce a **bar chart** comparing competitive clusters by trial count and phase maturity.

- xKey: `"cluster"` (mechanism of action or drug class name)
- yKeys:
  - `phase_2_trials` (info color) — count of Phase 2 trials in cluster
  - `phase_3_trials` (primary color) — count of Phase 3 trials in cluster
  - `total_enrollment` (success color, secondary axis conceptually) — sum of enrollment targets
- Stack phase counts with stackId: `"phase"`
- Include subtitle identifying the most crowded cluster

Populate `trial_context.competitive_clusters` with full detail for each cluster. Populate `trial_context.key_trials` with the most advanced trial from each cluster (the "leader"). Include `metadata.summary` with competitive landscape insight (e.g., "PD-1/PD-L1 combinations remain the most crowded space with 23 active trials across 8 sponsors; ADC-based approaches emerging as differentiated with 6 trials and less endpoint convergence").
