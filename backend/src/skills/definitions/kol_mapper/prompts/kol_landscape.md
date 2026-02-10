# KOL Landscape

Generate a comprehensive Key Opinion Leader map for **{therapeutic_area}**.

## Data Retrieval

1. Construct a PubMed search query combining MeSH terms and keywords for the therapeutic area:
   - `GET https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi?db=pubmed&term={mesh_terms}+AND+("last 5 years"[PDat])&retmax=200&sort=date&retmode=json`
2. Fetch publication details for returned PMIDs:
   - `GET https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esummary.fcgi?db=pubmed&id={pmid_list}&retmode=json`
3. For top authors, run targeted searches to get their full publication counts:
   - `GET https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi?db=pubmed&term={author_name}[Author]+AND+{mesh_terms}&retmode=json`

## Author Aggregation

From the initial 200 publications:
- Extract all authors, tracking first-author and last-author positions
- Aggregate by author name (normalize name variants)
- Count total appearances, first-author count, last-author count
- Record institutional affiliations from the most recent publication

## Influence Scoring (Top 15)

For the top 15 authors by publication count, calculate composite influence score (0-100):

| Factor | Weight | Scoring |
|--------|--------|---------|
| Publication volume | 25% | Normalize to 0-100 within the cohort |
| Citation impact | 25% | Estimate from PubMed Central links, normalize |
| Recency & activity | 20% | Publications in last 2 years (3x weight) vs. 2-5 years (1.5x) |
| First/last authorship | 15% | Ratio of PI-position publications to total |
| Journal quality | 15% | Top-tier journal percentage (NEJM, Lancet, JAMA, Nature Medicine, etc.) |

## KOL Tier Classification

- **Tier 1 - Global**: Influence score >= 80, publications in top-tier journals, international collaborations
- **Tier 2 - National**: Influence score 60-79, strong domestic publication record
- **Tier 3 - Regional**: Influence score 40-59, focused expertise in sub-specialty
- **Rising Star**: Influence score 30-50 BUT recency score >= 70 (recent surge in output)

## Chart Output

Produce a **bar chart** ranking the top 15 KOLs by influence score.

- xKey: `"name"` (author last name, first initial)
- yKeys: `influence_score` (primary color)
- Sort descending by influence score
- Include subtitle with therapeutic area and publication count scanned

Populate `kol_context.kol_profiles` with full detail for each of the 15 KOLs including institution, subspecialties, tier, and advisory board candidate flag. Set `advisory_board_candidate: true` for any KOL with influence_score >= 70 AND clinical_trial_pi = true.
