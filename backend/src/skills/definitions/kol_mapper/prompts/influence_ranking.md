# Influence Ranking

Generate a multi-axis influence comparison of top KOLs in **{therapeutic_area}** using a radar chart.

## Data Retrieval

1. Search PubMed for the therapeutic area across the last 5 years:
   - `GET https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi?db=pubmed&term={mesh_terms}+AND+("last 5 years"[PDat])&retmax=200&sort=date&retmode=json`
2. Fetch publication details:
   - `GET https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esummary.fcgi?db=pubmed&id={pmid_list}&retmode=json`
3. For the top 6 candidate KOLs (by initial publication count), run targeted author searches to build complete profiles.

## Influence Axes (6 dimensions)

For each of the top 6 KOLs, score these axes on a 0-100 scale:

1. **Publication Volume**: Total publications in therapeutic area, normalized within cohort
   - 100 = highest publisher, others scaled proportionally

2. **Citation Impact**: Estimated from PubMed Central cross-references and citation indicators
   - Weight highly-cited publications more heavily

3. **Recency**: Activity concentration in last 2 years
   - 100 = all publications in last 2 years, scale by recency distribution

4. **Journal Quality**: Percentage of publications in top-tier journals
   - Top-tier: NEJM, Lancet, JAMA, Nature Medicine, JCO, Blood, Cell, Science
   - 100 = all publications in top-tier journals

5. **Leadership Roles**: First/last authorship ratio (indicates PI-level involvement)
   - 100 = 100% first/last author publications

6. **Breadth**: Number of distinct sub-specialties or MeSH sub-categories covered
   - 100 = broadest topical coverage within the therapeutic area

## KOL Profile Archetypes

Based on the radar shape, classify each KOL:
- **The Prolific Leader**: High volume + high leadership + moderate everything else
- **The High-Impact Specialist**: Lower volume but very high citation + journal quality
- **The Rising Star**: High recency + moderate volume, lower on established metrics
- **The Broad Authority**: High breadth + moderate-to-high across all axes
- **The Clinical Pioneer**: High leadership + journal quality (clinical trial focused)

## Chart Output

Produce a **radar chart** comparing the top 6 KOLs across all 6 influence axes.

- xKey: `"axis"` (the 6 influence dimensions)
- Each KOL is a separate yKey series with their name as label
- Use 6 distinct colors from ARIA's palette: primary, success, warning, info, accent1, accent2
- Data format: array of 6 objects (one per axis), each with a score per KOL

Example data structure:
```json
[
  {"axis": "Publication Volume", "Dr. Smith": 85, "Dr. Jones": 62, ...},
  {"axis": "Citation Impact", "Dr. Smith": 70, "Dr. Jones": 92, ...},
  ...
]
```

Populate `kol_context.kol_profiles` for all 6 KOLs with full detail. Include `metadata.summary` identifying the top-ranked KOL and their archetype (e.g., "Dr. Sarah Chen ranks #1 as a Broad Authority in immuno-oncology with consistent high scores across all influence dimensions").
