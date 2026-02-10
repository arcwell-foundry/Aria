"""Document Forge skill definition for ARIA.

A Category B LLM skill that generates professional documents from ARIA's
context using structured prompt chains. Supports multiple document templates:

- ``account_plan`` — Comprehensive account plan for a target company
- ``meeting_one_pager`` — Pre-meeting briefing document
- ``qbr_deck`` — Quarterly business review deck
- ``battle_card`` — Competitive battle card
- ``territory_map`` — Territory analysis document

Usage::

    from src.core.llm import LLMClient

    llm = LLMClient()
    forge = DocumentForgeSkill(llm)

    result = await forge.run_template("account_plan", {
        "lead_data": "...",
        "stakeholders": "...",
        "recent_signals": "...",
    })
"""

from src.skills.definitions.document_forge.skill import DocumentForgeSkill

__all__ = ["DocumentForgeSkill"]
