"""
Regulatory Event Chain Intelligence for Life Sciences.
Detects FDA events in signals and enriches context with regulatory-specific implications.
"""

import logging
from typing import Optional

logger = logging.getLogger(__name__)

# Keywords from fda_event_types table — kept in code for fast matching
FDA_EVENT_PATTERNS = {
    'bla_approval': {
        'keywords': ['BLA approved', 'FDA approves', 'biologics license', 'NDA approved', 'approval'],
        'urgency': 'high',
        'impact_template': 'Competitor product entering market. Manufacturing scale-up demand increases. Monitor for displacement risk at accounts using alternatives.'
    },
    'bla_rejection': {
        'keywords': ['complete response letter', 'CRL', 'FDA rejects', 'BLA rejected', 'refused to file'],
        'urgency': 'very_high',
        'impact_template': 'Competitor delayed 12-18 months. Their customers need alternatives NOW. Displacement window opens immediately.'
    },
    'warning_letter': {
        'keywords': ['warning letter', 'FDA warning', 'cGMP violation', '483 observation', 'form 483'],
        'urgency': 'very_high',
        'impact_template': 'Manufacturing facility compliance issue. Supply chain disruption likely. Customers may face delays — displacement opportunity.'
    },
    'product_recall': {
        'keywords': ['recall', 'market withdrawal', 'safety alert', 'product recall', 'voluntary recall'],
        'urgency': 'very_high',
        'impact_template': 'URGENT: Product supply disrupted. Customers need replacement products immediately. First-mover advantage critical.'
    },
    'guidance_change': {
        'keywords': ['FDA guidance', 'draft guidance', 'final guidance', 'regulatory guidance', 'new guidance'],
        'urgency': 'medium',
        'impact_template': 'Regulatory landscape changing. May affect procurement requirements or manufacturing standards industry-wide.'
    },
    'breakthrough_designation': {
        'keywords': ['breakthrough therapy', 'breakthrough designation', 'fast track', 'accelerated approval'],
        'urgency': 'medium',
        'impact_template': 'Accelerated development timeline. Manufacturing needs will arrive earlier than standard timeline.'
    },
    'pdufa_date': {
        'keywords': ['PDUFA', 'action date', 'target date', 'PDUFA date'],
        'urgency': 'high',
        'impact_template': 'Decision date approaching. Prepare for either approval (scale-up) or rejection (displacement window).'
    },
}


def detect_fda_event(event_text: str, signal_type: str = '') -> Optional[dict]:
    """Detect if a signal is an FDA/regulatory event and classify it."""
    text_lower = event_text.lower()

    # Quick check: is this regulatory at all?
    if signal_type not in ('fda_approval', 'regulatory', '') and \
       not any(kw in text_lower for kw in ['fda', 'regulatory', 'approval', 'recall', 'warning letter', 'guidance']):
        return None

    # Match against patterns
    for event_type, config in FDA_EVENT_PATTERNS.items():
        for keyword in config['keywords']:
            if keyword.lower() in text_lower:
                return {
                    'fda_event_type': event_type,
                    'urgency': config['urgency'],
                    'impact_template': config['impact_template'],
                    'matched_keyword': keyword,
                }

    return None


def format_regulatory_context(fda_event: dict, battle_card: dict = None, company_name: str = '') -> str:
    """Format regulatory intelligence context for LLM prompts."""
    parts = [
        f"\n🏛️ REGULATORY EVENT DETECTED: {fda_event['fda_event_type'].upper().replace('_', ' ')}",
        f"Urgency: {fda_event['urgency'].upper()}",
        f"Standard Impact: {fda_event['impact_template']}",
    ]

    if battle_card and company_name:
        parts.append(f"\nCOMPETITIVE CONTEXT FOR {company_name.upper()}:")
        weaknesses = battle_card.get('weaknesses', [])
        if weaknesses:
            parts.append(f"Known weaknesses: {', '.join(str(w) for w in weaknesses[:3])}")
        differentiation = battle_card.get('differentiation', [])
        if differentiation:
            parts.append(f"Your advantages: {', '.join(str(d) for d in differentiation[:3])}")
        pricing = battle_card.get('pricing', {})
        if isinstance(pricing, dict) and pricing.get('strategy'):
            parts.append(f"Their pricing strategy: {pricing['strategy']}")

    parts.append("\nANALYZE: Trace the chain from this regulatory event through the competitive landscape to specific commercial actions. Who is affected? What products are disrupted? Where are the displacement opportunities?")

    return '\n'.join(parts)
