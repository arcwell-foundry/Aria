"""
Supply Chain Vulnerability Detection for Life Sciences.
Detects manufacturing disruptions, quality issues, and capacity constraints at competitors.
"""

import logging
from typing import Optional

logger = logging.getLogger(__name__)

SUPPLY_CHAIN_PATTERNS = {
    'manufacturing_disruption': {
        'keywords': ['manufacturing issue', 'production delay', 'facility closure', 'plant shutdown',
                     'manufacturing capacity', 'production capacity', 'manufacturing problem'],
        'urgency': 'very_high',
        'impact': 'Direct supply disruption. Customers need alternatives immediately.'
    },
    'quality_issue': {
        'keywords': ['warning letter', 'FDA warning', '483 observation', 'cGMP violation',
                     'quality issue', 'quality problem', 'deviation', 'out of spec'],
        'urgency': 'very_high',
        'impact': 'Quality concerns may halt shipments. Customers at risk of supply interruption.'
    },
    'product_recall': {
        'keywords': ['recall', 'voluntary recall', 'market withdrawal', 'product withdrawal',
                     'safety concern', 'adverse event'],
        'urgency': 'very_high',
        'impact': 'IMMEDIATE supply gap. Customers must find replacement products NOW.'
    },
    'capacity_constraint': {
        'keywords': ['capacity constraint', 'backlog', 'lead time increase', 'delivery delay',
                     'supply shortage', 'allocation', 'supply constraint', 'long lead time'],
        'urgency': 'high',
        'impact': 'Extended delivery timelines. Customers may seek alternative suppliers.'
    },
    'workforce_disruption': {
        'keywords': ['workforce reduction', 'layoff', 'restructuring', 'headcount reduction',
                     'workforce cut', 'job cuts', 'downsizing'],
        'urgency': 'high',
        'impact': 'Reduced operational capacity and customer support. Service quality at risk.'
    },
    'raw_material_shortage': {
        'keywords': ['raw material shortage', 'resin shortage', 'media shortage',
                     'supply chain disruption', 'material supply', 'single source'],
        'urgency': 'high',
        'impact': 'Upstream supply issue cascades to all products using affected materials.'
    },
}


def detect_supply_chain_signal(event_text: str, signal_type: str = '') -> Optional[dict]:
    """Detect supply chain vulnerability signals."""
    text_lower = event_text.lower()

    for vuln_type, config in SUPPLY_CHAIN_PATTERNS.items():
        for keyword in config['keywords']:
            if keyword.lower() in text_lower:
                return {
                    'vulnerability_type': vuln_type,
                    'urgency': config['urgency'],
                    'impact': config['impact'],
                    'matched_keyword': keyword,
                }

    return None


def format_supply_chain_context(vuln_info: dict, battle_card: dict = None, company_name: str = '') -> str:
    """Format supply chain intelligence context for LLM prompts."""
    parts = [
        f"\n⚠️ SUPPLY CHAIN VULNERABILITY DETECTED: {vuln_info['vulnerability_type'].upper().replace('_', ' ')}",
        f"Urgency: {vuln_info['urgency'].upper()}",
        f"Impact: {vuln_info['impact']}",
    ]

    if battle_card and company_name:
        parts.append(f"\nDISPLACEMENT PLAYBOOK FOR {company_name.upper()}:")
        differentiation = battle_card.get('differentiation', [])
        if differentiation:
            parts.append(f"Your advantages over them: {', '.join(str(d) for d in differentiation[:3])}")

        # Include objection handlers relevant to switching
        objection_handlers = battle_card.get('objection_handlers', [])
        if objection_handlers and isinstance(objection_handlers, list):
            parts.append("RELEVANT OBJECTION HANDLERS FOR DISPLACEMENT:")
            for oh in objection_handlers[:2]:
                if isinstance(oh, dict):
                    parts.append(f"  Objection: \"{oh.get('objection', '')}\"")
                    parts.append(f"  Response: \"{oh.get('response', '')[:200]}\"")

        pricing = battle_card.get('pricing', {})
        if isinstance(pricing, dict) and pricing.get('notes'):
            parts.append(f"Pricing intel: {pricing['notes']}")

    parts.append("\nANALYZE: Which of their customers are most affected? What products from our portfolio are direct replacements? What's the urgency window for outreach? Generate a specific displacement action plan.")

    return '\n'.join(parts)
