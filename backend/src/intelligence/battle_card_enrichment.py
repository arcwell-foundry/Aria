"""Battle Card Product Enrichment via Exa.

Discovers competitor product names and creates product-vs-product matchups
by searching competitor websites and product pages.
"""

from __future__ import annotations

import json
import logging
import re
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger(__name__)


class BattleCardEnricher:
    """Enriches battle cards with competitor product data discovered via Exa."""

    def __init__(self, supabase_client: Any, exa_client: Any | None = None) -> None:
        self._db = supabase_client
        self._exa = exa_client

    async def enrich_competitor_products(self, battle_card_id: str) -> dict[str, Any]:
        """For a given competitor, use Exa to discover their product lineup
        and create product-vs-product matchups against user's products.

        Args:
            battle_card_id: UUID of the battle card to enrich.

        Returns:
            Summary dict with competitor name, products discovered, matchups created.
        """
        # 1. Get the battle card
        card = (
            self._db.table("battle_cards")
            .select("*")
            .eq("id", battle_card_id)
            .limit(1)
            .execute()
        )
        if not card.data:
            return {"error": "Battle card not found"}

        competitor = card.data[0]
        competitor_name = competitor["competitor_name"]
        competitor_domain = competitor.get("competitor_domain", "")

        # 2. Gather user's product references from differentiation across all cards
        company_id = competitor.get("company_id")
        all_cards_query = self._db.table("battle_cards").select("differentiation")
        if company_id:
            all_cards_query = all_cards_query.eq("company_id", company_id)
        all_cards = all_cards_query.execute()

        user_products: set[str] = set()
        for c in all_cards.data or []:
            for d in c.get("differentiation") or []:
                if isinstance(d, str) and len(d) > 2:
                    user_products.add(d)

        if not self._exa:
            return {"error": "Exa client not available"}

        # 3. Search Exa for competitor products
        search_queries = [
            f"{competitor_name} bioprocessing products portfolio",
            f"{competitor_name} filtration chromatography product lineup",
        ]
        if competitor_domain:
            search_queries.append(f"site:{competitor_domain} products")
        else:
            search_queries.append(f"{competitor_name} product catalog bioprocess")

        discovered_products: list[str] = []
        for query in search_queries:
            try:
                results = await self._exa.search_fast(query, num_results=5)
                for r in results or []:
                    text = (r.title or "") + " " + (r.text or "")
                    products = self._extract_product_names(text, competitor_name)
                    discovered_products.extend(products)
            except Exception as e:
                logger.warning("[BattleCardEnricher] Exa search failed: %s", e)

        # Deduplicate
        discovered_products = list(set(discovered_products))

        # 4. Use LLM to create product matchups
        matchups: list[dict[str, str]] = []
        if discovered_products:
            matchups = await self._generate_product_matchups(
                competitor_name, discovered_products, list(user_products)
            )

        # 5. Update battle card
        try:
            self._db.table("battle_cards").update(
                {
                    "competitor_products": discovered_products[:20],
                    "product_matchups": matchups[:10],
                    "last_enriched_at": datetime.now(timezone.utc).isoformat(),
                    "enrichment_source": "exa",
                }
            ).eq("id", battle_card_id).execute()
        except Exception as e:
            logger.warning("[BattleCardEnricher] Failed to update battle card: %s", e)

        return {
            "competitor": competitor_name,
            "products_discovered": len(discovered_products),
            "matchups_created": len(matchups),
        }

    def _extract_product_names(self, text: str, competitor: str) -> list[str]:
        """Extract product names from text using bioprocess product patterns."""
        # Common bioprocessing product name patterns (generic, not company-specific)
        patterns = [
            r"(?:the\s+)?([A-Z][a-zA-Z]+(?:\s+[A-Z][a-zA-Z]*)*)\s+(?:system|platform|bioreactor|column|membrane|filter|sensor|analyzer|controller)",
            r"(?:the\s+)?([A-Z][a-zA-Z]+(?:\s*[A-Z0-9]+)*)\s+(?:series|line|range|family)",
            r"([A-Z][a-zA-Z]*(?:\s*[A-Z0-9]+)+)\s+(?:for\s+bioprocess|for\s+chromatography|for\s+filtration)",
        ]

        products: set[str] = set()
        for pattern in patterns:
            matches = re.findall(pattern, text)
            for m in matches:
                product = m.strip()
                skip_words = {"the", "our", "new", "for", "this", "that", "with"}
                if (
                    len(product) > 2
                    and product.lower() != competitor.lower()
                    and product.lower() not in skip_words
                ):
                    products.add(product)

        return list(products)

    async def _generate_product_matchups(
        self,
        competitor: str,
        their_products: list[str],
        our_products: list[str],
    ) -> list[dict[str, str]]:
        """Use LLM to create product-vs-product competitive matchups."""
        try:
            from src.core.llm import LLMClient
            from src.core.task_types import TaskType

            prompt = (
                f"Given these products from {competitor}: {', '.join(their_products[:10])}\n"
                f"And these differentiation points (which reference our products): "
                f"{', '.join(str(p)[:100] for p in our_products[:5])}\n\n"
                "Create product-vs-product competitive matchups. For each matchup, identify:\n"
                "1. Which of their products competes with which of our capabilities\n"
                "2. One-line positioning statement\n\n"
                'Respond in JSON array format:\n'
                '[{"their_product": "...", "our_advantage": "...", "positioning": "one line"}]\n\n'
                "Only include clear, direct competitive matchups. Max 5."
            )

            llm = LLMClient()
            response = await llm.generate_response(
                task_type=TaskType.ANALYST_RESEARCH,
                messages=[{"role": "user", "content": prompt}],
                system_prompt="You are a competitive intelligence analyst for life sciences. Return only valid JSON.",
            )

            text = response.text if hasattr(response, "text") else str(response)
            json_start = text.find("[")
            json_end = text.rfind("]") + 1
            if json_start >= 0 and json_end > json_start:
                return json.loads(text[json_start:json_end])
        except Exception as e:
            logger.warning("[BattleCardEnricher] LLM matchup generation failed: %s", e)

        return []

    async def enrich_all_battle_cards(self) -> int:
        """Enrich all battle cards with product data.

        Returns:
            Number of cards successfully enriched.
        """
        cards = self._db.table("battle_cards").select("id, competitor_name").execute()
        count = 0
        for card in cards.data or []:
            try:
                result = await self.enrich_competitor_products(card["id"])
                if result.get("products_discovered", 0) > 0:
                    count += 1
            except Exception as e:
                logger.warning(
                    "[BattleCardEnricher] Failed to enrich card %s: %s",
                    card.get("competitor_name", card["id"]),
                    e,
                )
        return count
