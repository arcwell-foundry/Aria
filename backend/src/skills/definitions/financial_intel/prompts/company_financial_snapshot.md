# Company Financial Snapshot

Generate a comprehensive financial overview from the most recent SEC EDGAR filings for **{company_name}**.

## Data Retrieval

1. Search EDGAR for the most recent 10-K (annual) and 10-Q (quarterly) filings:
   - `GET https://efts.sec.gov/LATEST/search-index?q="{company_name}"&forms=10-K,10-Q&dateRange=custom&startdt={start_date}&enddt={end_date}`
2. Parse the filing documents to extract key financial sections.

## Required Extractions

From the most recent annual filing (10-K):
- **Revenue**: Total revenue and segment breakdown (if available)
- **Gross Margin**: Gross profit / total revenue
- **R&D Spend**: Research and development expenses (absolute and as % of revenue)
- **SG&A**: Selling, general & administrative expenses
- **Operating Income**: GAAP operating income/loss
- **Net Income**: GAAP net income/loss
- **Cash Position**: Cash, cash equivalents, and short-term investments
- **Debt**: Total long-term debt and current maturities
- **Guidance**: Any forward-looking revenue or earnings guidance

From the most recent quarterly filing (10-Q), extract the same metrics for the latest quarter.

## Pipeline Intelligence

Scan Item 1 (Business) and MD&A for:
- Named products and their revenue contributions
- Pipeline programs with phase and indication
- Regulatory milestones mentioned (NDA/BLA submissions, PDUFA dates, approvals)
- Commercial launch timelines

## Risk Factor Highlights

From Item 1A, extract the top 5 risk factors by relevance to commercial strategy:
- Categorize each as: market, regulatory, competitive, operational, or financial
- Flag any risk factors that are NEW compared to the prior filing

## Chart Output

Produce a **bar chart** comparing key financial metrics (revenue, R&D, SG&A, operating income) across the most recent 2 annual periods plus the latest quarter (annualized).

- xKey: `"period"` (e.g., "FY2024", "FY2025", "Q3 2025 Ann.")
- yKeys: `revenue`, `rd_spend`, `sga`, `operating_income`
- Use success color for revenue, primary for R&D, accent1 for SG&A, and info for operating income

Include the full `financial_context` with filings_analyzed, pipeline_mentions, and risk_factors populated.
