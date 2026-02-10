# Publication Tracker

Generate a publication volume trend analysis for **{therapeutic_area}** to identify research momentum shifts and emerging sub-topics.

## Data Retrieval

1. Search PubMed for publications over the last 5 years, grouped by year:
   - For each year: `GET https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi?db=pubmed&term={mesh_terms}+AND+("{year}"[PDat])&retmode=json&rettype=count`
2. For the most recent 2 years, fetch full details for up to 100 publications per year:
   - `GET https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi?db=pubmed&term={mesh_terms}+AND+("last 2 years"[PDat])&retmax=200&sort=date&retmode=json`
   - `GET https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esummary.fcgi?db=pubmed&id={pmid_list}&retmode=json`

## Trend Analysis

Calculate for each year in the 5-year window:
- **Total publication count** in the therapeutic area
- **YoY growth rate** in publication volume
- **Sub-topic breakdown**: Categorize publications into 4-6 major sub-topics based on MeSH qualifiers and keywords (e.g., for oncology: immunotherapy, targeted therapy, biomarkers, combination therapy, real-world evidence, health economics)

## Emerging Topics Detection

From the most recent 2 years of detailed publications:
- Identify MeSH terms and keywords that appear with significantly higher frequency vs. prior years
- Flag sub-topics with >50% YoY growth as "emerging"
- Flag sub-topics with negative YoY growth as "declining"
- Note any new MeSH terms introduced in the latest year

## Research Momentum

Assess overall therapeutic area momentum:
- **Accelerating**: Publication volume growing >10% YoY for 2+ consecutive years
- **Stable**: Publication volume growth between -5% and +10%
- **Decelerating**: Publication volume declining or growth slowing for 2+ years

## Chart Output

Produce a **line chart** showing publication volume over time with sub-topic breakdown.

- xKey: `"year"` (e.g., "2021", "2022", "2023", "2024", "2025")
- yKeys: `total_publications` (primary color, solid line) plus 3-4 sub-topic series with stackId for area comparison (success, accent1, accent2, info colors)
- Include subtitle with overall momentum assessment (e.g., "Accelerating — 18% CAGR over 5 years")

Populate `kol_context` with `therapeutic_area`, `mesh_terms`, `search_query`, `time_range`, and `total_publications_scanned`. In `metadata.summary`, highlight the key trend and any emerging sub-topics (e.g., "Publication volume in NASH grew 22% YoY, driven by surge in biomarker and combination therapy research").
