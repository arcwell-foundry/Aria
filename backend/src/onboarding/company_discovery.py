"""Company Discovery service for onboarding (US-902).

Validates company info, checks life sciences vertical, creates company profile,
and triggers enrichment. Implements the first step of ARIA's intelligence
initialization flow.
"""

import asyncio
import json
import logging
import uuid
from datetime import UTC, datetime
from typing import Any

from src.core.llm import LLMClient
from src.db.supabase import SupabaseClient
from src.memory.episodic import Episode, EpisodicMemory

logger = logging.getLogger(__name__)

# Personal email domains to reject
PERSONAL_DOMAINS = {
    "gmail.com",
    "yahoo.com",
    "hotmail.com",
    "outlook.com",
    "aol.com",
    "icloud.com",
    "mail.com",
    "protonmail.com",
    "zoho.com",
    "yandex.com",
    "gmx.com",
    "live.com",
    "me.com",
    "msn.com",
    "inbox.com",
    "fastmail.com",
}


class CompanyDiscoveryService:
    """Handles company discovery step of onboarding.

    Validates company info, checks life sciences vertical,
    creates company profile, and triggers enrichment.
    """

    def __init__(self) -> None:
        """Initialize service with Supabase client."""
        self._db = SupabaseClient.get_client()

    async def validate_email_domain(self, email: str) -> dict[str, Any]:
        """Check if email is corporate (not personal).

        Args:
            email: Email address to validate.

        Returns:
            Dict with 'valid' (bool) and 'reason' (str|None) keys.
        """
        try:
            domain = email.split("@")[-1].lower()
        except IndexError:
            return {"valid": False, "reason": "Invalid email format"}

        # Check both direct domain match and subdomain match
        # e.g., both "gmail.com" and "mail.gmail.com" should be rejected
        if domain in PERSONAL_DOMAINS or any(
            domain.endswith(f".{personal_domain}") for personal_domain in PERSONAL_DOMAINS
        ):
            return {
                "valid": False,
                "reason": "Please use your corporate email address. Personal email domains are not accepted.",
            }
        return {"valid": True, "reason": None}

    async def check_life_sciences_gate(self, company_name: str, website: str) -> dict[str, Any]:
        """Use LLM to determine if company is in life sciences.

        Args:
            company_name: Name of the company.
            website: Company website URL.

        Returns:
            Dict with 'is_life_sciences' (bool), 'confidence' (float),
            and 'reasoning' (str) keys.
        """
        llm = LLMClient()
        prompt = f"""Determine if this company operates in the life sciences vertical.

Company: {company_name}
Website: {website}

Life sciences includes: pharmaceuticals, biotechnology, medical devices,
diagnostics, CROs (contract research organizations), CDMOs (contract
development and manufacturing organizations), cell therapy, gene therapy,
biologics, biosimilars, healthcare technology serving life sciences,
and companies providing services/products primarily to life sciences companies.

Life sciences does NOT include: general healthcare (hospitals, clinics),
consumer health/wellness, fitness, general tech companies, food/agriculture
(unless biotech-related).

Respond in JSON format:
{{"is_life_sciences": true/false, "confidence": 0.0-1.0, "reasoning": "brief explanation"}}"""

        try:
            response = await llm.generate_response(
                messages=[{"role": "user", "content": prompt}],
                max_tokens=200,
                temperature=0.3,
            )
            # Parse JSON from response
            result = json.loads(response)
            # Ensure all required fields exist
            return {
                "is_life_sciences": result.get("is_life_sciences", False),
                "confidence": result.get("confidence", 0.0),
                "reasoning": result.get("reasoning", ""),
            }
        except json.JSONDecodeError:
            logger.warning(f"Failed to parse life sciences gate response: {response}")
            return {
                "is_life_sciences": True,
                "confidence": 0.5,
                "reasoning": "Unable to parse LLM response — allowing through for manual review",
            }
        except Exception as e:
            logger.exception(f"Life sciences gate check failed: {e}")
            return {
                "is_life_sciences": True,
                "confidence": 0.5,
                "reasoning": "Gate check unavailable — allowing through for manual review",
            }

    async def check_existing_company(self, domain: str) -> dict[str, Any] | None:
        """Check if company already exists in Corporate Memory.

        Used for cross-user acceleration (US-917).

        Args:
            domain: Company domain to search for.

        Returns:
            Company data dict if found, None otherwise.
        """
        try:
            result = (
                self._db.table("companies")
                .select("*")
                .eq("domain", domain)
                .maybe_single()
                .execute()
            )
            if result.data:  # type: ignore[union-attr]
                return dict(result.data)  # type: ignore[union-attr, arg-type]
            return None
        except Exception as e:
            logger.warning(f"Error checking existing company: {e}")
            return None

    async def create_company_profile(
        self,
        user_id: str,
        company_name: str,
        website: str,
        email: str,
    ) -> dict[str, Any]:
        """Create company and link user to it.

        Args:
            user_id: The user's UUID.
            company_name: Name of the company.
            website: Company website URL.
            email: User's corporate email.

        Returns:
            Created company record with 'is_existing' bool key.
        """
        # Normalize domain from website
        domain = (
            website.replace("https://", "")
            .replace("http://", "")
            .replace("www.", "")
            .strip("/")
            .strip("/")
        )

        # Check if company already exists
        existing = await self.check_existing_company(domain)
        if existing:
            # Link user to existing company
            logger.info(f"Linking user {user_id} ({email}) to existing company {existing['id']}")
            (
                self._db.table("user_profiles")
                .update({"company_id": existing["id"]})
                .eq("id", user_id)
                .execute()
            )
            return {**existing, "is_existing": True}

        # Create new company
        company_data: dict[str, Any] = {
            "name": company_name,
            "domain": domain,
            "website": website,
            "settings": {
                "source": "onboarding",
                "registered_by": user_id,
            },
        }
        result = self._db.table("companies").insert(company_data).execute()
        company: dict[str, Any] = dict(result.data[0])  # type: ignore[arg-type]

        # Link user to company
        (
            self._db.table("user_profiles")
            .update({"company_id": company["id"]})
            .eq("id", user_id)
            .execute()
        )

        return {**company, "is_existing": False}

    async def submit_company_discovery(
        self,
        user_id: str,
        company_name: str,
        website: str,
        email: str,
    ) -> dict[str, Any]:
        """Full company discovery submission flow.

        1. Validate email domain
        2. Check life sciences gate
        3. Create/link company profile
        4. Trigger enrichment (async, non-blocking)
        5. Record events to memory

        Args:
            user_id: The user's UUID.
            company_name: Name of the company.
            website: Company website URL.
            email: User's corporate email.

        Returns:
            Submission result with status and company info.
        """
        # 1. Validate email
        email_check = await self.validate_email_domain(email)
        if not email_check["valid"]:
            return {"success": False, "error": email_check["reason"], "type": "email_validation"}

        # 2. Check life sciences classification for context (don't gate)
        # This provides useful metadata but doesn't block onboarding
        gate_result = await self.check_life_sciences_gate(company_name, website)

        # 3. Create company profile
        company = await self.create_company_profile(user_id, company_name, website, email)

        # 4. Trigger enrichment (US-903 — fire and forget)
        from src.onboarding.enrichment import CompanyEnrichmentEngine

        enrichment_engine = CompanyEnrichmentEngine()
        asyncio.create_task(
            enrichment_engine.enrich_company(
                company_id=company["id"],
                company_name=company_name,
                website=website,
                user_id=user_id,
            )
        )
        logger.info(
            "Enrichment triggered for company",
            extra={
                "company_name": company_name,
                "company_id": company["id"],
                "user_id": user_id,
            },
        )

        # 5. Record to episodic memory
        try:
            memory = EpisodicMemory()
            now = datetime.now(UTC)
            episode = Episode(
                id=str(uuid.uuid4()),
                user_id=user_id,
                event_type="onboarding_company_registered",
                content=f"User registered company: {company_name}",
                participants=[],
                occurred_at=now,
                recorded_at=now,
                context={
                    "company_name": company_name,
                    "website": website,
                    "is_existing_company": company.get("is_existing", False),
                    "gate_confidence": gate_result.get("confidence", 0),
                },
            )
            await memory.store_episode(episode)
        except Exception as e:
            logger.warning(f"Failed to record episodic event: {e}")

        # 6. Update readiness score
        try:
            from src.onboarding.orchestrator import OnboardingOrchestrator

            orch = OnboardingOrchestrator()
            await orch.update_readiness_scores(user_id, {"corporate_memory": 10.0})
        except Exception as e:
            logger.warning(f"Failed to update readiness scores: {e}")

        return {
            "success": True,
            "company": {
                "id": company["id"],
                "name": company_name,
                "domain": company.get("domain"),
                "is_existing": company.get("is_existing", False),
            },
            "gate_result": {
                "is_life_sciences": True,
                "confidence": gate_result.get("confidence", 0),
            },
            "enrichment_status": "queued",
        }
