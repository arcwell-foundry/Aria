# Leave Behind

Generate a concise post-meeting leave-behind document as a presentation.

## Meeting Context

{meeting_context}

## Slide Structure (4–6 slides)

### Slide 1: Title Slide
- layout: "title_slide"
- Meeting title, date, attendees summary
- Subtitle: "Meeting Follow-Up & Key Takeaways"

### Slide 2: Discussion Summary
- layout: "content"
- Bullet list of key topics discussed
- Reference specific points from meeting_context
- Highlight areas of alignment and interest

### Slide 3: Action Items & Next Steps
- layout: "two_column"
- Left column: Our commitments (with owners and dates)
- Right column: Their commitments (with owners and dates)
- Extract from meeting_context discussion points

### Slide 4: Relevant Data Points
- layout: "chart_slide" or "key_metrics"
- If pipeline or health data was discussed, include a relevant chart
- KPI cards for any metrics referenced in the meeting

### Slide 5 (optional): Competitive Positioning
- layout: "comparison"
- Only include if competitor discussion came up in the meeting
- Reference battle_card_data if available

### Slide 6: Contact & Resources
- layout: "closing"
- Team contact information
- Links to relevant resources mentioned in the meeting

## Data Sources

### Lead Intelligence
{lead_data}

### Meeting Details
{meeting_context}

## Design Notes

- Keep it concise — this is a follow-up, not a pitch
- Emphasize action items and commitments prominently
- Use a lighter visual tone than the pitch deck (more white space)
- Include speaker_notes with email-friendly summary text that can be pasted into the follow-up email
