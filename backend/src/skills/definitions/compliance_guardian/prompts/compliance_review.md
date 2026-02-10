# Compliance Review

Perform a comprehensive compliance scan of the provided text for PHI/PII and Sunshine Act reporting triggers.

## Pre-Scan Results

The following patterns were detected by automated regex scanning. Use these as a starting point — your contextual analysis should go deeper.

{pre_scan_findings}

## Text to Analyze

{text_content}

## Analysis Instructions

### Step 1: PHI/PII Detection

Scan for the following categories:

**Direct Identifiers (confidence 0.95)**
- Social Security Numbers (XXX-XX-XXXX or 9-digit sequences)
- Medical Record Numbers (MRN patterns)
- Patient ID numbers
- Insurance member IDs

**Quasi-Identifiers (confidence 0.80)**
- Date of birth near other identifiers
- ZIP code + age + gender combinations that could identify individuals
- Rare disease + location combinations

**Contextual PHI (confidence 0.85)**
- Person names appearing within 50 words of medical terms (drug names, diagnoses, procedures, conditions)
- Drug names co-occurring with patient identifiers
- Treatment plans or clinical notes with identifying information

**Standard PII (confidence 0.90)**
- Email addresses, phone numbers
- Full mailing addresses with names

### Step 2: Sunshine Act Analysis

Check for any transfers of value between commercial teams and Healthcare Professionals (HCPs):
- Meals, beverages, or entertainment
- Speaker fees or honoraria
- Consulting arrangements
- Travel and lodging
- Research funding
- Educational grants
- Gifts or samples

For each transfer of value found, note:
- The HCP referenced (by role, not by reproducing their name in your output)
- The type of transfer
- The estimated value if determinable
- Whether it exceeds de minimis thresholds ($10 individual / $100 annual aggregate)

### Step 3: Risk Assessment

Assign overall risk_level:
- **critical**: PHI direct identifiers found (SSN, MRN) — immediate redaction needed
- **high**: Contextual PHI or multiple PII elements — redaction recommended
- **medium**: Sunshine Act triggers found — reporting review needed
- **low**: Minor PII or no findings

## Output

Return findings array with each detection, risk_level, and sunshine_act_summary. Do NOT reproduce any actual sensitive data in your response — describe by type and location only.
