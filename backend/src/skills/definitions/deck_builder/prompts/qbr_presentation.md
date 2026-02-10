# QBR Presentation

Generate a quarterly business review presentation with pipeline, health, and forecast data.

## Slide Structure (12–18 slides)

### Section 1: Executive Overview (Slides 1–3)

**Slide 1: Title Slide**
- layout: "title_slide"
- "Quarterly Business Review — Q[X] [Year]"
- Subtitle with territory or team name

**Slide 2: Quarter at a Glance**
- layout: "key_metrics"
- 4 KPI cards: Revenue vs. Quota, Pipeline Coverage, Win Rate, Avg Deal Cycle
- Use forecast_data for actuals vs. targets

**Slide 3: Key Wins & Highlights**
- layout: "content"
- Bullet list of significant wins from the quarter
- Reference closed deals from pipeline_data

### Section 2: Pipeline Analysis (Slides 4–7)

**Slide 4: Section Header**
- layout: "section_header"
- "Pipeline Deep Dive"

**Slide 5: Pipeline by Stage**
- layout: "chart_slide"
- Stacked bar chart showing pipeline value by stage
- Categories: PROSPECT, QUALIFIED, ENGAGED, PROPOSAL, NEGOTIATION
- Data source: pipeline_data

**Slide 6: Pipeline Movement**
- layout: "chart_slide"
- Line chart showing pipeline value over the quarter (monthly snapshots)
- Series: Total Pipeline, Weighted Pipeline, Quota line

**Slide 7: Top Opportunities**
- layout: "content"
- Table of top 10 deals by value with stage, health, and next step
- Data source: pipeline_data + health_score_history

### Section 3: Account Health (Slides 8–10)

**Slide 8: Section Header**
- layout: "section_header"
- "Account Health & Engagement"

**Slide 9: Health Score Distribution**
- layout: "chart_slide"
- Bar chart: health score buckets (Critical, At Risk, Needs Attention, Healthy, Thriving)
- Data source: health_score_history

**Slide 10: Health Score Trends**
- layout: "chart_slide"
- Line chart showing health score trends over the quarter for top accounts
- Highlight accounts with significant improvement or decline

### Section 4: Forecast & Next Quarter (Slides 11–14)

**Slide 11: Section Header**
- layout: "section_header"
- "Forecast & Forward Look"

**Slide 12: Forecast vs. Actual**
- layout: "chart_slide"
- Bar chart: Forecast at start of quarter vs. actual close
- Include commit, upside, and best case categories

**Slide 13: Next Quarter Pipeline**
- layout: "key_metrics"
- Pipeline coverage ratio, expected closes, gap to quota
- Data source: forecast_data

**Slide 14: Strategic Priorities**
- layout: "content"
- Top 3–5 priorities for next quarter
- Specific account actions and territory adjustments

### Section 5: Closing (Slides 15–16)

**Slide 15: Asks & Support Needed**
- layout: "two_column"
- Left: Resource asks
- Right: Executive support needed

**Slide 16: Summary & Q&A**
- layout: "closing"
- 3 key takeaways
- Open for discussion

## Data Sources

### Pipeline Data
{pipeline_data}

### Health Score History
{health_score_history}

### Forecast Data
{forecast_data}

## Output Requirements

- Every chart_slide must include a fully specified chart_spec
- Table slides must include table_spec with real data from the provided sources
- KPI cards must use kpi_spec with trend indicators (up/down/flat)
- Speaker notes should include detailed talking points for each slide
- Use [Data pending] for any metrics not available in the provided data
