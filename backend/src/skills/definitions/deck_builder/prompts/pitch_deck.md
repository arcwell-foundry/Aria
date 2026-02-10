# Pitch Deck

Generate a prospect pitch deck for a life sciences commercial engagement.

## Target Audience

{audience}

## Slide Structure (8–12 slides)

### Slide 1: Title Slide
- layout: "title_slide"
- Company logo placeholder, prospect name, date
- Subtitle with the meeting purpose

### Slide 2: Executive Summary
- layout: "content"
- 3–4 bullet points summarizing the value proposition
- Tailor to the prospect's specific challenges from lead data

### Slide 3: The Challenge
- layout: "two_column"
- Left: Industry pain points relevant to this prospect
- Right: Quantified impact (e.g. "72% of rep time on admin")
- Reference specific challenges from lead intelligence

### Slide 4: Our Solution
- layout: "content"
- Key capabilities mapped to the prospect's needs
- Use data from battle_card_data to position against competitors

### Slide 5: Competitive Differentiation
- layout: "comparison"
- Table comparing our solution vs. competitors mentioned in battle cards
- Highlight areas where we lead
- Data source: battle_card_data

### Slide 6: Customer Success / Social Proof
- layout: "content"
- Reference similar customers from lead_memories (same therapeutic area or company size)
- Include KPI improvements where available

### Slide 7: ROI / Value Metrics
- layout: "key_metrics"
- 3–4 KPI cards showing expected value delivery
- Connect to the prospect's pipeline data if available

### Slide 8: Implementation / Timeline
- layout: "content"
- Phased approach with milestones
- Address common concerns from battle cards

### Slide 9: Proposed Next Steps
- layout: "closing"
- Clear call to action
- Contact information

### Additional slides (if data supports):
- Technical architecture overview
- Security and compliance slide
- Pricing overview

## Data Sources

### Lead Intelligence
{lead_data}

### Battle Card Data
{battle_card_data}

## Output Requirements

Every slide must include:
- `speaker_notes`: Talking points for the presenter
- `elements`: Complete element specifications with exact positioning
- Element positions should not overlap and should respect slide margins (0.5" on all sides)

For the competitive comparison table, use `table_spec` with headers and rows extracted from battle_card_data. For ROI metrics, use `kpi_spec` elements.
