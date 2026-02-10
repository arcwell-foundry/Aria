# Enrollment Tracker

Generate enrollment status and velocity analysis for active clinical trials in **{therapeutic_area}**.

## Data Retrieval

1. Search ClinicalTrials.gov for actively recruiting trials:
   - `GET https://clinicaltrials.gov/api/v2/studies?query.cond={therapeutic_area}&filter.overallStatus=RECRUITING,ENROLLING_BY_INVITATION&pageSize=100&fields=NCTId,BriefTitle,Phase,OverallStatus,EnrollmentCount,EnrollmentType,StartDate,PrimaryCompletionDate,StudyFirstPostDate,LeadSponsorName,InterventionName&format=json`
2. For trials with enrollment data, calculate enrollment metrics.
3. Fetch full details for trials showing enrollment risk signals:
   - `GET https://clinicaltrials.gov/api/v2/studies/{nctId}?format=json`

## Enrollment Metrics

For each recruiting trial, calculate:
- **Target Enrollment**: From EnrollmentCount field
- **Time Elapsed**: Months since StudyFirstPostDate or StartDate
- **Time Remaining**: Months until PrimaryCompletionDate
- **Expected Progress**: (Time elapsed / Total study duration) as percentage
- **Enrollment Velocity Classification**:
  - **On Track**: Expected progress aligns with typical enrollment curves
  - **At Risk**: Trial has been recruiting >50% of planned duration with >12 months remaining
  - **Behind Schedule**: Primary completion date has passed or is within 3 months with recruiting status
  - **Unknown**: Insufficient data to assess

## Enrollment Risk Signals

Flag trials with:
- Primary completion date already passed but still "Recruiting"
- Study duration >5 years (potential enrollment difficulty)
- Enrollment target >1000 (large trials with higher execution risk)
- Phase 3 trials that have been recruiting for >3 years

## Phase-Level Enrollment Summary

Aggregate enrollment data by phase:
- Total target enrollment per phase
- Average enrollment target per trial per phase
- Median time-to-completion per phase
- Percentage of trials at risk per phase

## Chart Output

Produce a **bar chart** showing enrollment targets by phase with at-risk highlighting.

- xKey: `"phase"`
- yKeys:
  - `on_track_enrollment` (success color) — total target enrollment from on-track trials
  - `at_risk_enrollment` (warning color) — total target enrollment from at-risk trials
  - `behind_schedule_enrollment` (danger color) — total target enrollment from behind-schedule trials
- Stack bars with stackId: `"enrollment_status"`
- Include subtitle with overall at-risk percentage

Populate `trial_context.key_trials` with trials flagged as at-risk or behind-schedule (up to 15). Include `enrollment_summary` with totals. In `metadata.summary`, highlight the enrollment health of the therapeutic area (e.g., "34% of recruiting NASH trials show enrollment risk signals, concentrated in Phase 3 where 5 of 12 trials are behind schedule").
