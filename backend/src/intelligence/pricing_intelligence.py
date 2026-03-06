"""
Competitive Pricing Intelligence for Life Sciences.
Detects pricing signals and cross-references with battle card pricing data.
"""
import logging
from typing import Optional

logger = logging.getLogger(__name__)

PRICING_PATTERNS = {
    'pricing_pressure': {
        'keywords': ['pricing pressure', 'margin pressure', 'price erosion', 'pricing headwinds',
                     'average selling price decline', 'ASP decline', 'price competition'],
        'impact': 'Competitor facing pricing pressure. May discount aggressively to maintain share.'
    },
    'discounting': {
        'keywords': ['discount', 'promotional pricing', 'price reduction', 'price cut',
                     'competitive pricing', 'aggressive pricing', 'below market'],
        'impact': 'Active discounting detected. Expect competitive pricing plays in your territory.'
    },
    'price_increase': {
        'keywords': ['price increase', 'pricing power', 'premium pricing', 'raised prices',
                     'higher ASP', 'pricing discipline'],
        'impact': 'Competitor raising prices. Window to position as value alternative.'
    },
    'revenue_miss': {
        'keywords': ['revenue miss', 'below expectations', 'revenue decline', 'revenue shortfall',
                     'missed estimates', 'lower guidance', 'reduced outlook'],
        'impact': 'Revenue underperformance likely triggers aggressive sales tactics and deeper discounting.'
    },
    'contract_terms': {
        'keywords': ['multi-year agreement', 'enterprise contract', 'volume commitment',
                     'long-term supply', 'framework agreement', 'master agreement'],
        'impact': 'Contract structure intelligence. Understand their lock-in strategy.'
    },
}


def detect_pricing_signal(event_text: str, signal_type: str = '') -> Optional[dict]:
    """Detect pricing-related signals in market events."""
    text_lower = event_text.lower()

    if signal_type not in ('earnings', 'product', 'funding', '') and \
       not any(kw in text_lower for kw in ['price', 'pric', 'revenue', 'margin', 'discount', 'contract']):
        return None

    detected = []
    for pattern_type, config in PRICING_PATTERNS.items():
        for keyword in config['keywords']:
            if keyword.lower() in text_lower:
                detected.append({
                    'type': pattern_type,
                    'impact': config['impact'],
                    'keyword': keyword,
                })
                break

    if not detected:
        return None

    return {
        'pricing_signals': detected,
        'primary_type': detected[0]['type'],
        'count': len(detected),
    }


def format_pricing_context(pricing_info: dict, battle_card: dict = None, company_name: str = '') -> str:
    """Format pricing intelligence context for LLM prompts."""
    parts = [
        "\n\U0001f4b0 PRICING INTELLIGENCE DETECTED",
    ]

    for signal in pricing_info['pricing_signals']:
        parts.append(f"- {signal['type'].replace('_', ' ').title()}: {signal['impact']}")

    if battle_card and company_name:
        pricing = battle_card.get('pricing', {})
        if isinstance(pricing, dict):
            parts.append(f"\nEXISTING PRICING INTEL FOR {company_name.upper()} (from battle card):")
            if pricing.get('model'):
                parts.append(f"  Pricing model: {pricing['model']}")
            if pricing.get('range'):
                parts.append(f"  Price range: {pricing['range']}")
            if pricing.get('strategy'):
                parts.append(f"  Strategy: {pricing['strategy']}")
            if pricing.get('notes'):
                parts.append(f"  Notes: {pricing['notes']}")
            parts.append("ANALYZE: How does this new pricing signal UPDATE or CONFIRM the existing pricing intelligence? What tactical pricing response should the sales team prepare?")

    return '\n'.join(parts)
