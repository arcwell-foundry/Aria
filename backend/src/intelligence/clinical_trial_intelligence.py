"""
Clinical Trial Pipeline Predictor for Life Sciences.
Maps clinical trial phase advancements to future bioprocessing equipment procurement needs.
"""

import logging
from typing import Optional

logger = logging.getLogger(__name__)

# Drug modality detection keywords
MODALITY_PATTERNS = {
    'mAb': ['monoclonal antibody', 'mab', 'antibody', 'IgG', 'bispecific', 'biologics'],
    'ADC': ['antibody-drug conjugate', 'ADC', 'conjugate', 'payload'],
    'cell_therapy': ['cell therapy', 'CAR-T', 'CAR T', 'T-cell', 'cell-based', 'autologous', 'allogeneic'],
    'gene_therapy': ['gene therapy', 'AAV', 'viral vector', 'lentiviral', 'adenoviral', 'gene transfer'],
    'vaccine': ['vaccine', 'immunization', 'mRNA vaccine', 'adjuvant', 'antigen'],
    'biosimilar': ['biosimilar', 'interchangeable', 'reference product'],
}

# Phase detection
PHASE_PATTERNS = {
    'Phase 1': ['phase 1', 'phase I', 'first-in-human', 'FIH'],
    'Phase 2': ['phase 2', 'phase II', 'proof of concept', 'POC trial'],
    'Phase 3': ['phase 3', 'phase III', 'pivotal', 'registrational', 'pivotal trial'],
    'BLA/NDA': ['BLA', 'NDA', 'regulatory submission', 'filing'],
}

# Equipment needs by modality + phase (from drug_equipment_mapping table, kept in code for speed)
EQUIPMENT_NEEDS = {
    ('mAb', 'Phase 3'): {
        'upstream': ['2000L+ bioreactors', 'perfusion systems', 'ATF systems'],
        'downstream': ['TFF/UF systems', 'chromatography columns', 'viral filtration'],
        'procurement_lead_months': 12,
        'note': 'Manufacturing scale-up begins 6-12 months into Phase 3'
    },
    ('mAb', 'Phase 2'): {
        'upstream': ['500-2000L bioreactors', 'fed-batch or perfusion'],
        'downstream': ['TFF systems', 'chromatography'],
        'procurement_lead_months': 18,
        'note': 'Process development and tech transfer procurement starts in Phase 2'
    },
    ('cell_therapy', 'Phase 2'): {
        'upstream': ['cell expansion systems', 'wash/concentrate', 'cryopreservation'],
        'downstream': ['cleanroom equipment', 'isolators'],
        'procurement_lead_months': 15,
        'note': 'Autologous cell therapy requires decentralized manufacturing'
    },
    ('gene_therapy', 'Phase 2'): {
        'upstream': ['suspension bioreactors', 'transfection systems'],
        'downstream': ['AAV purification', 'TFF systems'],
        'procurement_lead_months': 18,
        'note': 'Viral vector production is capacity-constrained'
    },
    ('vaccine', 'Phase 3'): {
        'upstream': ['10000L+ bioreactors', 'continuous centrifugation'],
        'downstream': ['sterile filtration', 'fill-finish equipment'],
        'procurement_lead_months': 12,
        'note': 'Vaccine scale requires massive upstream capacity'
    },
    ('ADC', 'Phase 3'): {
        'upstream': ['conjugation reactors'],
        'downstream': ['HIC chromatography', 'TFF systems', 'viral filtration'],
        'procurement_lead_months': 12,
        'note': 'ADC purification is more complex than standard mAb'
    },
    ('biosimilar', 'Phase 3'): {
        'upstream': ['stainless steel bioreactors'],
        'downstream': ['chromatography skids', 'UF/DF systems'],
        'procurement_lead_months': 12,
        'note': 'Biosimilar manufacturing mirrors innovator process'
    },
}


def detect_clinical_trial_signal(event_text: str, signal_type: str = '') -> Optional[dict]:
    """Detect if a signal relates to clinical trial advancement and predict equipment needs."""
    text_lower = event_text.lower()

    # Quick check
    if signal_type not in ('clinical_trial', 'fda_approval', '') and \
       not any(kw in text_lower for kw in ['trial', 'phase', 'clinical', 'enrollment', 'pivotal', 'BLA']):
        return None

    # Detect phase
    detected_phase = None
    for phase, keywords in PHASE_PATTERNS.items():
        if any(kw.lower() in text_lower for kw in keywords):
            detected_phase = phase
            break

    if not detected_phase:
        return None

    # Detect modality
    detected_modality = None
    for modality, keywords in MODALITY_PATTERNS.items():
        if any(kw.lower() in text_lower for kw in keywords):
            detected_modality = modality
            break

    if not detected_modality:
        detected_modality = 'mAb'  # Default assumption for bioprocessing

    # Look up equipment needs
    equipment = EQUIPMENT_NEEDS.get((detected_modality, detected_phase))
    if not equipment:
        # Try just the phase with mAb as default
        equipment = EQUIPMENT_NEEDS.get(('mAb', detected_phase))

    if not equipment:
        return None

    return {
        'clinical_phase': detected_phase,
        'drug_modality': detected_modality,
        'equipment_needs': equipment,
        'procurement_lead_months': equipment.get('procurement_lead_months', 12),
    }


def format_clinical_trial_context(trial_info: dict, company_name: str = '') -> str:
    """Format clinical trial intelligence context for LLM prompts."""
    equipment = trial_info['equipment_needs']
    parts = [
        f"\n🧬 CLINICAL TRIAL INTELLIGENCE DETECTED",
        f"Phase: {trial_info['clinical_phase']} | Modality: {trial_info['drug_modality']}",
        f"Procurement window: Equipment needed in ~{trial_info['procurement_lead_months']} months",
        f"Note: {equipment.get('note', '')}",
        f"\nEQUIPMENT PROCUREMENT PREDICTION:",
        f"Upstream needs: {', '.join(equipment.get('upstream', []))}",
        f"Downstream needs: {', '.join(equipment.get('downstream', []))}",
    ]

    if company_name:
        parts.append(f"\nANALYZE: {company_name} will need this equipment within {trial_info['procurement_lead_months']} months. Identify which of our products map to these needs. Recommend specific outreach timing and positioning.")

    return '\n'.join(parts)
