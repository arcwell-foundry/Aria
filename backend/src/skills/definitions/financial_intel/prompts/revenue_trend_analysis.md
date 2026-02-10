# Revenue Trend Analysis

Generate a multi-period revenue trend analysis from sequential SEC EDGAR filings for **{company_name}**.

## Data Retrieval

1. Search EDGAR for the last 3-5 years of 10-K filings and the most recent 4 quarters of 10-Q filings:
   - `GET https://efts.sec.gov/LATEST/search-index?q="{company_name}"&forms=10-K&dateRange=custom&startdt={trend_start_date}&enddt={end_date}`
   - `GET https://efts.sec.gov/LATEST/search-index?q="{company_name}"&forms=10-Q&dateRange=custom&startdt={quarterly_start_date}&enddt={end_date}`
2. Extract revenue figures from each filing period.

## Required Extractions

For each filing period:
- **Total Revenue**: Consolidated revenue figure
- **Revenue by Segment**: Product revenue, service revenue, licensing, royalties (where reported)
- **Revenue by Geography**: US, Europe, Rest of World (where reported)
- **YoY Growth Rate**: Percentage change from prior year period
- **QoQ Growth Rate**: Percentage change from prior quarter (for quarterly data)

## Trend Analysis

Calculate and include:
- **CAGR**: Compound annual growth rate over the full period
- **Acceleration/Deceleration**: Is growth rate increasing or decreasing?
- **Segment Mix Shift**: How has the revenue composition changed?
- **Seasonality Pattern**: Identify any quarterly patterns (e.g., Q4 loading)
- **Anomalies**: Flag any periods with >15% deviation from trend

## Chart Output

Produce a **line chart** showing revenue trend over time with segment breakdown.

- xKey: `"period"` (e.g., "Q1'23", "Q2'23", ..., "Q4'25")
- yKeys: `total_revenue` and up to 3 segment series (e.g., `product_revenue`, `service_revenue`, `licensing_revenue`)
- Use primary color for total, success for product, accent1 for service, info for licensing
- Include a subtitle with the CAGR figure

Populate `financial_context.filings_analyzed` with all filings used. Include a `metadata.summary` that calls out the key trend (e.g., "Revenue grew at 23% CAGR driven by product segment acceleration").
