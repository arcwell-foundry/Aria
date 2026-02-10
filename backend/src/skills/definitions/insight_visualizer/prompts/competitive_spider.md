# Competitive Spider Chart

Generate a radar/spider chart comparing competitors across multiple axes for {competitor_names}.

## Data Source

Query `battle_cards` table for competitors matching the provided names. Extract scores or qualitative assessments across standard competitive dimensions.

## Comparison Axes

Evaluate each competitor on these dimensions (scale 0–100):
1. **Product Strength** — feature completeness, clinical evidence, regulatory status
2. **Market Presence** — installed base, market share, brand recognition
3. **Pricing** — competitiveness (100 = most competitive / lowest relative price)
4. **Service & Support** — implementation, training, customer success
5. **Innovation** — R&D pipeline, recent launches, technology differentiation
6. **Relationships** — KOL network, advisory boards, existing account penetration

## Data Format

Each data point should have:
- `axis`: Dimension name (e.g. "Product Strength")
- One key per competitor with their score (e.g. `competitor_a: 85`)

## Config

- chart_type: "radar"
- xKey: "axis"
- yKeys: one series per competitor, each with a distinct color from the palette
- title: "Competitive Landscape"
- subtitle: List competitor names

## Context Data

{battle_card_data}
