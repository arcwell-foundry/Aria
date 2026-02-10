# R&D Investment Tracker

Generate an R&D spending analysis with pipeline investment context from SEC EDGAR filings for **{company_name}**.

## Data Retrieval

1. Search EDGAR for 3-5 years of 10-K filings:
   - `GET https://efts.sec.gov/LATEST/search-index?q="{company_name}"&forms=10-K&dateRange=custom&startdt={trend_start_date}&enddt={end_date}`
2. Additionally pull the latest 10-Q for current-year trajectory.

## Required Extractions

For each filing period:
- **R&D Expense**: Total research and development costs
- **R&D as % of Revenue**: R&D expense / total revenue
- **R&D Headcount**: If disclosed in 10-K Item 1 (number of R&D employees)
- **Capitalized R&D**: Any capitalized development costs (if applicable)
- **Total R&D Investment**: Expensed + capitalized R&D
- **Revenue**: For ratio calculations

## Pipeline Correlation

From each 10-K, extract pipeline program mentions and correlate R&D spend changes with:
- **New program initiations**: Phase 1 starts that may drive R&D increases
- **Late-stage investment**: Phase 3 trials that significantly increase spend
- **Program terminations**: Discontinued programs that may reduce spend
- **Regulatory submissions**: NDA/BLA preparations that shift spend from R&D to commercial

## Efficiency Metrics

Calculate:
- **R&D Intensity Trend**: How R&D-to-revenue ratio is changing over time
- **Implied R&D per Program**: Total R&D / number of active pipeline programs
- **R&D Growth vs Revenue Growth**: Are they investing proportionally to growth?
- **Industry Benchmark Context**: Note whether R&D intensity is typical for the company's sub-sector (biotech: 30-60%, large pharma: 15-25%, medtech: 6-12%)

## Chart Output

Produce a **bar chart** with R&D spend (bars) and R&D-to-revenue ratio (overlaid as a second yKey series).

- xKey: `"period"` (e.g., "FY2021", "FY2022", "FY2023", "FY2024", "FY2025")
- yKeys: `rd_spend` (bar, primary color), `rd_revenue_ratio` (bar, accent1 color), `revenue` (bar, success color with lower opacity via muted)
- Include a subtitle with the R&D intensity trend direction

Populate `financial_context.pipeline_mentions` with all programs found. Include `metadata.summary` highlighting the R&D trajectory (e.g., "R&D intensity rising from 18% to 24% of revenue, driven by 3 new Phase 2 program initiations").
