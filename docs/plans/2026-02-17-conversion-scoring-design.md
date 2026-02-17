# Conversion Scoring Service Design

**Date:** 2026-02-17
**Status:** Approved
**Type:** Feature

## Overview

A `ConversionScoringService` that calculates conversion probability for each lead using a weighted logistic regression on nine normalized features extracted from existing lead memory data.

## Architecture

### Data Models

```python
class ConversionScore(BaseModel):
    lead_memory_id: UUID
    conversion_probability: float  # 0-100%
    confidence: float  # 0-1.0, data completeness
    feature_values: dict[str, float]  # Normalized 0-1
    feature_importance: dict[str, float]  # Weighted contribution
    calculated_at: datetime

class ScoreExplanation(BaseModel):
    lead_memory_id: UUID
    summary: str  # Natural language summary
    key_drivers: list[dict]  # Top 3 positive factors
    key_risks: list[dict]  # Top 2 negative factors
    recommendation: str  # Suggested action
```

### Storage

- Cached in `lead_memories.metadata["conversion_score"]` as JSON
- Prediction record in `predictions` table with `prediction_type: "deal_outcome"`
- Staleness threshold: 24 hours

### Service Methods

1. `calculate_conversion_score(lead_memory_id)` → `ConversionScore`
2. `explain_score(lead_memory_id)` → `ScoreExplanation`
3. `batch_score_all_leads(user_id)` → `BatchScoreResult`

## Feature Definitions

| Feature | Weight | Source | Normalization |
|---------|--------|--------|---------------|
| engagement_frequency | 0.18 | `lead_memory_events` count (30 days) | `min(count/20, 1.0)` |
| stakeholder_depth | 0.12 | Weighted stakeholder count | `sum(influence) / (count × 10)` |
| avg_response_time | 0.10 | Email response latency | `1.0 - min(hours/72, 1.0)` |
| sentiment_trend | 0.12 | Sentiment change over 30 days | `(delta + 1) / 2` |
| stage_velocity | 0.10 | Days in stage vs expected | `1.0 - min(days/expected, 1.5)/1.5` |
| health_score_trend | 0.08 | Health score slope | `0.5 + (slope × 0.05)` |
| meeting_frequency | 0.12 | Debriefs count (60 days) | `min(count/4, 1.0)` |
| commitment_fulfillment_theirs | 0.12 | Their commitments fulfilled | `fulfilled / total` |
| commitment_fulfillment_ours | 0.06 | Our commitments fulfilled | `fulfilled / total` |

## Score Calculation

```python
raw_score = sum(feature_value × weight for each feature)
conversion_probability = 100 / (1 + exp(-10 × (raw_score - 0.5)))
confidence = sum(has_data[feature] × weight for each feature)
```

## Edge Cases

- New lead (<7 days): `confidence *= 0.5`
- No events: `engagement_frequency = 0`, exclude response_time from confidence
- Missing stakeholders: `stakeholder_depth = 0`, `sentiment_trend = 0.5`
- No commitments: Both fulfillment features = `0.5`
- Won/lost leads: Skip scoring, return cached or None

## Decisions

1. **Commitment tracking:** Both theirs (0.7 weight) and ours (0.3 weight) within the 0.17 combined weight
2. **Score refresh:** Real-time with 24-hour staleness check; batch for overnight refresh
3. **Weight storage:** Hardcoded in code for v1; migrate to database if tuning needed
