import json
import logging
import uuid
from datetime import UTC, datetime
from typing import Any, cast

import httpx

from src.core.config import settings
from src.core.llm import LLMClient
from src.db.supabase import SupabaseClient

logger = logging.getLogger(__name__)


class LinkedInResearchService:
    def __init__(self) -> None:
        self._db = SupabaseClient.get_client()
        self._llm = LLMClient()

    async def research_profile(
        self,
        user_id: str,
        linkedin_url: str,
        full_name: str,
        job_title: str,
        company_name: str,
    ) -> dict[str, Any]:
        try:
            raw_results = await self._search_person(
                full_name, job_title, company_name, linkedin_url
            )

            profile = await self._extract_profile(full_name, job_title, company_name, raw_results)

            await self._store_in_digital_twin(user_id, profile)
            await self._store_semantic_facts(user_id, profile)
            await self._record_episodic_event(user_id, profile)

            # Record activity for feed
            try:
                from src.services.activity_service import ActivityService

                await ActivityService().record(
                    user_id=user_id,
                    agent="analyst",
                    activity_type="linkedin_research_complete",
                    title="Researched professional background",
                    description=f"ARIA researched {full_name}'s professional background",
                    confidence=0.8,
                )
            except Exception as e:
                logger.warning("Failed to record LinkedIn research activity: %s", e)

            summary = await self._generate_summary(full_name, profile)
            await self._store_summary_for_frontend(user_id, summary)

            return {"profile": profile, "summary": summary}

        except Exception as e:
            logger.warning("LinkedIn research failed for user %s: %s", user_id, e)
            return {}

    async def _search_person(
        self,
        full_name: str,
        job_title: str,
        company_name: str,
        _linkedin_url: str,
    ) -> list[dict[str, Any]]:
        if not settings.EXA_API_KEY:
            logger.info("Exa API key not configured, skipping LinkedIn research")
            return []

        all_results: list[dict[str, Any]] = []

        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    "https://api.exa.ai/search",
                    headers={"x-api-key": settings.EXA_API_KEY},
                    json={
                        "query": f'"{full_name}" "{company_name}" site:linkedin.com',
                        "numResults": 3,
                        "type": "auto",
                        "contents": {"text": {"maxCharacters": 2000}},
                    },
                    timeout=30.0,
                )
                if response.status_code == 200:
                    data = response.json()
                    for item in data.get("results", []):
                        all_results.append(
                            {
                                "source": "linkedin_search",
                                "url": item.get("url", ""),
                                "title": item.get("title", ""),
                                "content": item.get("text", ""),
                            }
                        )
        except Exception as e:
            logger.warning("LinkedIn search query 1 failed: %s", e)

        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    "https://api.exa.ai/search",
                    headers={"x-api-key": settings.EXA_API_KEY},
                    json={
                        "query": f'"{full_name}" "{job_title}" life sciences',
                        "numResults": 5,
                        "type": "neural",
                        "contents": {"text": {"maxCharacters": 2000}},
                    },
                    timeout=30.0,
                )
                if response.status_code == 200:
                    data = response.json()
                    for item in data.get("results", []):
                        all_results.append(
                            {
                                "source": "web_search",
                                "url": item.get("url", ""),
                                "title": item.get("title", ""),
                                "content": item.get("text", ""),
                            }
                        )
        except Exception as e:
            logger.warning("LinkedIn search query 2 failed: %s", e)

        logger.info("LinkedIn research found %d results for %s", len(all_results), full_name)
        return all_results

    async def _extract_profile(
        self,
        full_name: str,
        job_title: str,
        company_name: str,
        raw_results: list[dict[str, Any]],
    ) -> dict[str, Any]:
        if not raw_results:
            return {
                "career_history": [],
                "education": [],
                "industry_tenure_years": 0,
                "expertise_areas": [],
                "publications_or_presentations": [],
                "professional_summary": "",
            }

        research_text = ""
        for item in raw_results[:8]:
            content = str(item.get("content", ""))[:1500]
            research_text += f"\n[{item.get('source', '')}] {item.get('title', '')}: {content}\n"

        prompt = f"""Extract a professional profile for {full_name}, {job_title} at {company_name}.

Research data:
{research_text}

Return a JSON object:
{{
    "career_history": [{{"company": "", "title": "", "years": ""}}],
    "education": [{{"institution": "", "degree": "", "field": ""}}],
    "industry_tenure_years": 0,
    "expertise_areas": ["area1", "area2"],
    "publications_or_presentations": ["title1", "title2"],
    "professional_summary": "2-3 sentence summary"
}}

Only include information supported by the research data. If data is insufficient for a field, use empty list or 0.
Respond ONLY with the JSON object, no additional text."""

        response = await self._llm.generate_response(
            messages=[{"role": "user", "content": prompt}],
            max_tokens=1024,
            temperature=0.2,
        )

        try:
            return cast(dict[str, Any], json.loads(response))
        except (json.JSONDecodeError, Exception) as e:
            logger.warning("Profile extraction parse failed: %s", e)
            return {
                "career_history": [],
                "education": [],
                "industry_tenure_years": 0,
                "expertise_areas": [],
                "publications_or_presentations": [],
                "professional_summary": "",
            }

    async def _store_in_digital_twin(self, user_id: str, profile: dict[str, Any]) -> None:
        try:
            result = (
                self._db.table("user_settings")
                .select("preferences")
                .eq("user_id", user_id)
                .maybe_single()
                .execute()
            )

            current_prefs: dict[str, Any] = {}
            if result and result.data:
                row = cast(dict[str, Any], result.data)
                current_prefs = row.get("preferences", {}) or {}

            digital_twin = current_prefs.get("digital_twin", {})
            digital_twin["professional_profile"] = profile
            digital_twin["professional_profile_updated_at"] = datetime.now(UTC).isoformat()
            current_prefs["digital_twin"] = digital_twin

            (
                self._db.table("user_settings")
                .update({"preferences": current_prefs})
                .eq("user_id", user_id)
                .execute()
            )
        except Exception as e:
            logger.warning("Failed to store LinkedIn profile in digital twin: %s", e)

    async def _store_semantic_facts(self, user_id: str, profile: dict[str, Any]) -> None:
        facts_to_store: list[dict[str, str]] = []

        if profile.get("professional_summary"):
            facts_to_store.append(
                {
                    "fact": profile["professional_summary"],
                    "category": "professional_summary",
                }
            )

        tenure = profile.get("industry_tenure_years", 0)
        if tenure and tenure > 0:
            facts_to_store.append(
                {
                    "fact": f"Has {tenure} years of experience in the life sciences industry",
                    "category": "experience",
                }
            )

        for area in profile.get("expertise_areas", []):
            facts_to_store.append(
                {
                    "fact": f"Has expertise in {area}",
                    "category": "expertise",
                }
            )

        for item in facts_to_store:
            try:
                self._db.table("memory_semantic").insert(
                    {
                        "user_id": user_id,
                        "fact": item["fact"],
                        "confidence": 0.80,
                        "source": "linkedin_research",
                        "metadata": {"category": item["category"]},
                    }
                ).execute()
            except Exception as e:
                logger.warning("Failed to store semantic fact: %s", e)

    async def _record_episodic_event(self, user_id: str, profile: dict[str, Any]) -> None:
        try:
            from src.memory.episodic import Episode, EpisodicMemory

            memory = EpisodicMemory()
            now = datetime.now(UTC)
            episode = Episode(
                id=str(uuid.uuid4()),
                user_id=user_id,
                event_type="linkedin_research_complete",
                content=(
                    f"LinkedIn research completed — found {len(profile.get('career_history', []))} "
                    f"career entries, {len(profile.get('expertise_areas', []))} expertise areas"
                ),
                participants=[],
                occurred_at=now,
                recorded_at=now,
                context={
                    "expertise_areas": profile.get("expertise_areas", []),
                    "industry_tenure_years": profile.get("industry_tenure_years", 0),
                    "career_entries": len(profile.get("career_history", [])),
                },
            )
            await memory.store_episode(episode)
        except Exception as e:
            logger.warning("Failed to record LinkedIn research episodic event: %s", e)

    async def _generate_summary(self, full_name: str, profile: dict[str, Any]) -> str:
        first_name = full_name.split()[0] if full_name else "there"
        tenure = profile.get("industry_tenure_years", 0)
        expertise = profile.get("expertise_areas", [])
        career = profile.get("career_history", [])

        parts = [f"I found your profile, {first_name}"]

        if tenure and tenure > 0:
            parts[0] += f" \u2014 you've been in life sciences for {tenure} years"

        if expertise:
            top = expertise[:3]
            parts.append(f"with deep expertise in {', '.join(top)}")

        if career:
            latest = career[0]
            parts.append(
                f"currently serving as {latest.get('title', 'a leader')} "
                f"at {latest.get('company', 'your organization')}"
            )

        summary = ", ".join(parts) + "."
        return summary

    async def _store_summary_for_frontend(self, user_id: str, summary: str) -> None:
        try:
            state_result = (
                self._db.table("onboarding_state")
                .select("step_data")
                .eq("user_id", user_id)
                .maybe_single()
                .execute()
            )

            if state_result.data:
                step_data = state_result.data.get("step_data", {}) or {}
                step_data["linkedin_summary"] = summary
                (
                    self._db.table("onboarding_state")
                    .update({"step_data": step_data})
                    .eq("user_id", user_id)
                    .execute()
                )
        except Exception as e:
            logger.warning("Failed to store LinkedIn summary for frontend: %s", e)
