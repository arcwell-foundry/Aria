# Redaction Report

Redact all PHI/PII from the provided text and produce a manifest of changes.

## Pre-Scan Results

The following patterns were detected by automated regex scanning:

{pre_scan_findings}

## Text to Redact

{text_content}

## Redaction Rules

Apply the following redaction rules in order of priority:

### Must Redact (replace with [REDACTED])
1. **SSN**: Any XXX-XX-XXXX or 9-digit number pattern → `[REDACTED-SSN]`
2. **MRN**: Medical Record Numbers → `[REDACTED-MRN]`
3. **Patient ID**: Patient identifier numbers → `[REDACTED-PATIENT-ID]`
4. **DOB**: Date of birth patterns near identifiers → `[REDACTED-DOB]`

### Should Redact (replace with type-specific tokens)
5. **Names near medical context**: Person names within 50 words of medical terms → `[REDACTED-NAME]`
6. **Drug + name co-occurrence**: Drug names adjacent to patient names → redact the name, keep the drug name
7. **Email addresses**: → `[REDACTED-EMAIL]`
8. **Phone numbers**: → `[REDACTED-PHONE]`
9. **Full addresses with names**: → `[REDACTED-ADDRESS]`

### Preserve (do not redact)
- Company names and business addresses
- Drug names, device names (unless adjacent to patient identifiers)
- General medical terminology without identifying context
- Aggregate statistics and anonymized data
- HCP names in professional context (these may need Sunshine Act review, not redaction)

## Output Format

1. **redacted_text**: The full text with all sensitive items replaced by `[REDACTED-TYPE]` tokens
2. **findings**: Array documenting each redaction with:
   - category: Type of data redacted
   - description: What was redacted and why (without revealing the data)
   - confidence: Detection confidence
   - location: Where in the text
   - action_required: "redact"
3. **risk_level**: Based on what was found
4. **metadata**: Include count of redactions performed
