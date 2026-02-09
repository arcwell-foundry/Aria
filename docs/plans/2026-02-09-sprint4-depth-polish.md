# Sprint 4: Depth & Polish — Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Implement 6 fixes covering LinkedIn research, goal decomposition, role dropdown, role-influenced behavior, goal lifecycle, and activity feed during onboarding.

**Architecture:** Each fix is a self-contained vertical slice (migration → backend service → wiring → frontend where applicable). All follow existing patterns: Exa API calls via httpx, Supabase insert/update, asyncio.create_task() for background work, ActivityService.record() for feed entries.

**Tech Stack:** Python 3.11 / FastAPI / Supabase / Exa API / Anthropic Claude LLM / React 18 / TypeScript / Tailwind CSS

---

## Task 1: Database Migration — Role Column + Goal Milestones Agent Type

**Files:**
- Create: `backend/supabase/migrations/20260209100000_sprint4_depth_polish.sql`

**Step 1: Write the migration**

```sql
-- Sprint 4: Depth & Polish
-- Adds role column to user_profiles for Fix 3
-- Adds agent_type and success_criteria columns to goal_milestones for Fix 2

-- Fix 3: Role dropdown in User Profile
ALTER TABLE user_profiles ADD COLUMN IF NOT EXISTS role TEXT;

-- Fix 2: Goal decomposition — extend goal_milestones with agent_type and success_criteria
ALTER TABLE goal_milestones ADD COLUMN IF NOT EXISTS agent_type TEXT;
ALTER TABLE goal_milestones ADD COLUMN IF NOT EXISTS success_criteria TEXT;

-- Fix 6: Activity feed table already exists (aria_activity, created by US-940)
-- No new table needed — ActivityService.record() writes to aria_activity
```

**Step 2: Commit**

```bash
git add backend/supabase/migrations/20260209100000_sprint4_depth_polish.sql
git commit -m "feat(db): Sprint 4 migration — role column, goal milestone extensions"
```

---

## Task 2: Fix 1 — LinkedIn Background Research Service

**Files:**
- Create: `backend/src/onboarding/linkedin_research.py`

**Step 1: Create LinkedInResearchService**

Follow the Exa API pattern from `enrichment.py:368-458` (httpx POST to `https://api.exa.ai/search`, graceful degradation when EXA_API_KEY missing).

```python
"""LinkedIn Background Research service for onboarding (US-905 Gap #7).

Researches a user's professional background via Exa API triangulation.
Stores results in Digital Twin and Semantic Memory. Generates a trust-building
summary for the frontend to display.
"""

import json
import logging
from datetime import UTC, datetime
from typing import Any

import httpx

from src.core.config import settings
from src.core.llm import LLMClient
from src.db.supabase import SupabaseClient

logger = logging.getLogger(__name__)


class LinkedInResearchService:
    """Researches a user's professional background using web search.

    Uses Exa API to triangulate:
    1. LinkedIn profile search: "{name}" "{company}" site:linkedin.com
    2. Professional context search: "{name}" "{title}" life sciences

    From results, LLM extracts:
    - Career history (past companies, roles, tenure)
    - Education (degrees, institutions)
    - Industry tenure (years in life sciences)
    - Expertise areas (therapeutic areas, modalities, functions)
    - Publications/conference appearances
    - Professional summary
    """

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
        """Research a user's professional background.

        Main entry point — called as asyncio.create_task() after profile save.

        Args:
            user_id: The user's UUID.
            linkedin_url: LinkedIn profile URL.
            full_name: User's full name.
            job_title: Current job title.
            company_name: Current company name.

        Returns:
            Dict with professional_profile and summary.
        """
        logger.info(
            "Starting LinkedIn background research",
            extra={"user_id": user_id, "full_name": full_name},
        )

        # 1. Search via Exa API
        raw_results = await self._search_person(
            full_name=full_name,
            job_title=job_title,
            company_name=company_name,
            linkedin_url=linkedin_url,
        )

        if not raw_results:
            logger.info(
                "No research results found",
                extra={"user_id": user_id},
            )
            return {"status": "no_results"}

        # 2. Extract structured profile via LLM
        profile = await self._extract_profile(
            full_name=full_name,
            job_title=job_title,
            company_name=company_name,
            raw_results=raw_results,
        )

        # 3. Store in Digital Twin (user_settings.preferences.digital_twin.professional_profile)
        await self._store_in_digital_twin(user_id, profile)

        # 4. Store key facts in semantic memory
        await self._store_semantic_facts(user_id, profile)

        # 5. Record episodic memory
        await self._record_episodic_event(user_id, profile)

        # 6. Generate trust-building summary
        summary = await self._generate_summary(full_name, profile)

        # 7. Store summary in onboarding_state.step_data for frontend
        await self._store_summary_for_frontend(user_id, summary)

        logger.info(
            "LinkedIn research complete",
            extra={
                "user_id": user_id,
                "expertise_count": len(profile.get("expertise_areas", [])),
                "career_entries": len(profile.get("career_history", [])),
            },
        )

        return {
            "status": "complete",
            "professional_profile": profile,
            "summary": summary,
        }

    async def _search_person(
        self,
        full_name: str,
        job_title: str,
        company_name: str,
        linkedin_url: str,
    ) -> list[dict[str, Any]]:
        """Triangulate person via Exa API searches.

        Args:
            full_name: User's full name.
            job_title: Current job title.
            company_name: Current company name.
            linkedin_url: LinkedIn profile URL.

        Returns:
            List of search result dicts with source, url, title, content.
        """
        results: list[dict[str, Any]] = []

        if not settings.EXA_API_KEY:
            logger.info("Exa API key not configured, skipping LinkedIn research")
            return results

        queries = [
            {
                "query": f'"{full_name}" "{company_name}" site:linkedin.com',
                "numResults": 3,
                "type": "auto",
            },
            {
                "query": f'"{full_name}" "{job_title}" life sciences',
                "numResults": 5,
                "type": "neural",
            },
        ]

        async with httpx.AsyncClient() as client:
            for query_config in queries:
                try:
                    response = await client.post(
                        "https://api.exa.ai/search",
                        headers={"x-api-key": settings.EXA_API_KEY},
                        json={
                            **query_config,
                            "contents": {"text": {"maxCharacters": 2000}},
                        },
                        timeout=30.0,
                    )
                    if response.status_code == 200:
                        data = response.json()
                        for item in data.get("results", []):
                            results.append({
                                "source": "linkedin_research",
                                "url": item.get("url", ""),
                                "title": item.get("title", ""),
                                "content": item.get("text", ""),
                            })
                except Exception as e:
                    logger.warning(f"LinkedIn search query failed: {e}")

        logger.info(f"LinkedIn research found {len(results)} results")
        return results

    async def _extract_profile(
        self,
        full_name: str,
        job_title: str,
        company_name: str,
        raw_results: list[dict[str, Any]],
    ) -> dict[str, Any]:
        """Extract structured professional profile from search results via LLM.

        Args:
            full_name: User's full name.
            job_title: Current job title.
            company_name: Current company name.
            raw_results: Raw search results from Exa.

        Returns:
            Structured professional profile dict.
        """
        results_text = "\n\n".join(
            f"Source: {r['url']}\nTitle: {r['title']}\nContent: {r['content'][:1500]}"
            for r in raw_results[:8]
        )

        prompt = (
            f"Extract a professional profile for {full_name}, "
            f"currently {job_title} at {company_name}.\n\n"
            f"SEARCH RESULTS:\n{results_text}\n\n"
            "Respond with ONLY a JSON object:\n"
            "{\n"
            '  "career_history": [{"company": "...", "role": "...", "approximate_tenure": "..."}],\n'
            '  "education": [{"institution": "...", "degree": "..."}],\n'
            '  "industry_tenure_years": 0,\n'
            '  "expertise_areas": ["therapeutic area or function"],\n'
            '  "publications_or_presentations": ["title or description"],\n'
            '  "professional_summary": "2-3 sentence summary"\n'
            "}\n\n"
            "Only include information clearly supported by the search results. "
            "If information is not found, use empty arrays or null."
        )

        try:
            raw = await self._llm.generate_response(
                messages=[{"role": "user", "content": prompt}],
                max_tokens=1024,
                temperature=0.2,
            )
            return json.loads(raw)
        except (json.JSONDecodeError, Exception) as e:
            logger.warning(f"Profile extraction failed: {e}")
            return {
                "career_history": [],
                "education": [],
                "industry_tenure_years": None,
                "expertise_areas": [],
                "publications_or_presentations": [],
                "professional_summary": None,
            }

    async def _store_in_digital_twin(self, user_id: str, profile: dict[str, Any]) -> None:
        """Store professional profile in Digital Twin.

        Args:
            user_id: The user's UUID.
            profile: Structured professional profile.
        """
        try:
            # Get current settings
            result = (
                self._db.table("user_settings")
                .select("preferences")
                .eq("user_id", user_id)
                .maybe_single()
                .execute()
            )

            preferences = {}
            if result.data:
                preferences = result.data.get("preferences", {})

            digital_twin = preferences.get("digital_twin", {})
            digital_twin["professional_profile"] = profile

            preferences["digital_twin"] = digital_twin

            self._db.table("user_settings").upsert(
                {"user_id": user_id, "preferences": preferences},
                on_conflict="user_id",
            ).execute()

            logger.info("Professional profile stored in Digital Twin", extra={"user_id": user_id})
        except Exception as e:
            logger.warning(f"Failed to store in Digital Twin: {e}")

    async def _store_semantic_facts(self, user_id: str, profile: dict[str, Any]) -> None:
        """Store key professional facts in semantic memory.

        Args:
            user_id: The user's UUID.
            profile: Structured professional profile.
        """
        facts: list[str] = []

        tenure = profile.get("industry_tenure_years")
        if tenure:
            facts.append(f"User has approximately {tenure} years of experience in life sciences")

        for area in profile.get("expertise_areas", [])[:5]:
            facts.append(f"User has expertise in {area}")

        summary = profile.get("professional_summary")
        if summary:
            facts.append(f"Professional background: {summary}")

        for career in profile.get("career_history", [])[:3]:
            company = career.get("company", "")
            role = career.get("role", "")
            if company and role:
                facts.append(f"Previously worked as {role} at {company}")

        for fact_text in facts:
            try:
                self._db.table("memory_semantic").insert({
                    "user_id": user_id,
                    "fact": fact_text,
                    "confidence": 0.80,
                    "source": "linkedin_research",
                    "metadata": {"category": "professional_background"},
                }).execute()
            except Exception as e:
                logger.warning(f"Failed to store semantic fact: {e}")

    async def _record_episodic_event(self, user_id: str, profile: dict[str, Any]) -> None:
        """Record LinkedIn research in episodic memory.

        Args:
            user_id: The user's UUID.
            profile: Structured professional profile.
        """
        try:
            from src.memory.episodic import Episode, EpisodicMemory

            tenure = profile.get("industry_tenure_years", "unknown")
            areas = ", ".join(profile.get("expertise_areas", [])[:3]) or "various areas"

            memory = EpisodicMemory()
            now = datetime.now(UTC)
            import uuid

            episode = Episode(
                id=str(uuid.uuid4()),
                user_id=user_id,
                event_type="linkedin_research_complete",
                content=(
                    f"Researched user's professional background — "
                    f"{tenure} years in life sciences, expertise in {areas}"
                ),
                participants=[],
                occurred_at=now,
                recorded_at=now,
                context={"source": "linkedin_research", "profile_data": profile},
            )
            await memory.store_episode(episode)
        except Exception as e:
            logger.warning(f"Failed to record episodic event: {e}")

    async def _generate_summary(self, full_name: str, profile: dict[str, Any]) -> str:
        """Generate trust-building summary for the user.

        Args:
            full_name: User's full name.
            profile: Structured professional profile.

        Returns:
            Human-readable summary string.
        """
        first_name = full_name.split()[0] if full_name else "there"
        tenure = profile.get("industry_tenure_years")
        areas = profile.get("expertise_areas", [])
        career = profile.get("career_history", [])

        parts: list[str] = [f"I found your professional profile, {first_name}"]

        if tenure:
            parts.append(f"you've been in life sciences for about {tenure} years")

        if areas:
            area_text = ", ".join(areas[:3])
            parts.append(f"with expertise in {area_text}")

        if career:
            latest = career[0]
            parts.append(
                f"most recently as {latest.get('role', '')} at {latest.get('company', '')}"
            )

        summary = " — ".join(parts) + ". Is this right?"
        return summary

    async def _store_summary_for_frontend(self, user_id: str, summary: str) -> None:
        """Store research summary in onboarding_state for frontend to display.

        Args:
            user_id: The user's UUID.
            summary: Trust-building summary text.
        """
        try:
            result = (
                self._db.table("onboarding_state")
                .select("step_data")
                .eq("user_id", user_id)
                .maybe_single()
                .execute()
            )

            step_data = {}
            if result.data:
                step_data = result.data.get("step_data", {}) or {}

            step_data["linkedin_summary"] = summary

            self._db.table("onboarding_state").update(
                {"step_data": step_data}
            ).eq("user_id", user_id).execute()

        except Exception as e:
            logger.warning(f"Failed to store LinkedIn summary: {e}")
```

**Step 2: Commit**

```bash
git add backend/src/onboarding/linkedin_research.py
git commit -m "feat: Fix 1 — LinkedInResearchService with Exa API triangulation"
```

---

## Task 3: Wire LinkedIn Research into Profile Save

**Files:**
- Modify: `backend/src/services/profile_service.py:19-31` (add "role" to ALLOWED_USER_FIELDS)
- Modify: `backend/src/services/profile_service.py:200-203` (fire LinkedIn research after profile save)

**Step 1: Add "role" to ALLOWED_USER_FIELDS (serves Fix 3 too)**

In `backend/src/services/profile_service.py`, update the ALLOWED_USER_FIELDS frozenset at line 19-31:

```python
ALLOWED_USER_FIELDS = frozenset(
    {
        "full_name",
        "title",
        "department",
        "linkedin_url",
        "avatar_url",
        "communication_preferences",
        "privacy_exclusions",
        "default_tone",
        "tracked_competitors",
        "role",
    }
)
```

**Step 2: Wire LinkedIn research trigger after profile save**

In `backend/src/services/profile_service.py`, after line 203 (the `asyncio.create_task(ProfileMergeService()...)` line), add:

```python
            # Fire LinkedIn research if URL was provided (US-905 Gap #7)
            linkedin_url = update_data.get("linkedin_url")
            if linkedin_url:
                try:
                    from src.onboarding.linkedin_research import LinkedInResearchService

                    # Gather context for triangulation
                    full_name = update_data.get("full_name") or old_data.get("full_name", "")
                    job_title = update_data.get("title") or old_data.get("title", "")

                    # Get company name from user's company
                    company_name = ""
                    try:
                        company_result = (
                            self.db.table("companies")
                            .select("name")
                            .eq("id", response.data[0].get("company_id", ""))
                            .maybe_single()
                            .execute()
                        )
                        if company_result.data:
                            company_name = company_result.data.get("name", "")
                    except Exception:
                        pass

                    if full_name:
                        asyncio.create_task(
                            LinkedInResearchService().research_profile(
                                user_id=user_id,
                                linkedin_url=linkedin_url,
                                full_name=full_name,
                                job_title=job_title,
                                company_name=company_name,
                            )
                        )
                except Exception as e:
                    logger.warning(
                        "Failed to trigger LinkedIn research",
                        extra={"user_id": user_id, "error": str(e)},
                    )
```

**Step 3: Commit**

```bash
git add backend/src/services/profile_service.py
git commit -m "feat: wire LinkedIn research into profile save, add role to allowed fields"
```

---

## Task 4: Fix 2 — Goal Decomposition

**Files:**
- Modify: `backend/src/onboarding/first_goal.py:731-763` (replace `_create_goal_milestones`)

**Step 1: Replace _create_goal_milestones with LLM decomposition**

In `backend/src/onboarding/first_goal.py`, replace the `_create_goal_milestones` method (lines 731-763) with:

```python
    async def _create_goal_milestones(
        self, user_id: str, goal_id: str, title: str, description: str | None
    ) -> None:
        """Decompose goal into 3-5 milestones via LLM and store them.

        Uses LLM to break the goal into concrete sub-tasks with agent
        assignments, then creates milestone records plus a check-in
        prospective memory entry.

        Args:
            user_id: The user's UUID.
            goal_id: The created goal's UUID.
            title: Goal title.
            description: Goal description.
        """
        # 1. Decompose via LLM
        milestones = await self._decompose_goal(title, description)

        # 2. Create milestone records
        for i, milestone in enumerate(milestones):
            try:
                due_offset = timedelta(days=milestone.get("estimated_days", (i + 1) * 3))
                due_date = datetime.now(UTC) + due_offset

                insert_data: dict[str, Any] = {
                    "goal_id": goal_id,
                    "title": milestone["title"],
                    "description": milestone.get("description", ""),
                    "agent_type": milestone.get("agent_type"),
                    "success_criteria": milestone.get("success_criteria"),
                    "status": "pending",
                    "sort_order": i + 1,
                    "due_date": due_date.isoformat(),
                }

                self._db.table("goal_milestones").insert(insert_data).execute()
                logger.info(f"Created milestone {i + 1} for goal {goal_id}")
            except Exception as e:
                logger.warning(f"Failed to create milestone: {e}")

        # 3. Create prospective memory check-in
        try:
            tomorrow = datetime.now(UTC) + timedelta(days=1)
            self._db.table("prospective_memories").insert({
                "user_id": user_id,
                "task": f"Review progress on goal: {title}",
                "due_date": tomorrow.isoformat(),
                "status": "pending",
                "metadata": {
                    "type": "goal_check_in",
                    "goal_id": goal_id,
                    "priority": "low",
                },
            }).execute()
        except Exception as e:
            logger.warning(f"Failed to create check-in: {e}")

    async def _decompose_goal(
        self, title: str, description: str | None
    ) -> list[dict[str, Any]]:
        """Use LLM to decompose a goal into 3-5 concrete milestones.

        Args:
            title: Goal title.
            description: Optional goal description.

        Returns:
            List of milestone dicts with title, description, agent_type,
            estimated_days, and success_criteria.
        """
        desc_text = description or title

        prompt = (
            f"Break this goal into 3-5 concrete, actionable milestones.\n\n"
            f"Goal: {title}\n"
            f"Description: {desc_text}\n\n"
            "For each milestone, assign the most appropriate ARIA agent:\n"
            "- hunter: finding and qualifying prospects\n"
            "- analyst: research, data analysis, account insights\n"
            "- scout: competitive intelligence, market monitoring\n"
            "- scribe: drafting communications, emails, follow-ups\n"
            "- operator: CRM updates, pipeline management, data quality\n"
            "- strategist: strategic planning, territory analysis\n\n"
            "Respond with ONLY a JSON array:\n"
            "[\n"
            "  {\n"
            '    "title": "Milestone title",\n'
            '    "description": "What needs to be done",\n'
            '    "agent_type": "hunter|analyst|scout|scribe|operator|strategist",\n'
            '    "estimated_days": 3,\n'
            '    "success_criteria": "How to know this is done"\n'
            "  }\n"
            "]\n\n"
            "Make milestones progressive — each builds on the previous. "
            "Keep estimated_days realistic (1-14 range)."
        )

        try:
            raw = await self._llm.generate_response(
                messages=[{"role": "user", "content": prompt}],
                max_tokens=1024,
                temperature=0.3,
            )
            milestones = json.loads(raw)
            if isinstance(milestones, list) and len(milestones) >= 2:
                return milestones[:5]
        except (json.JSONDecodeError, Exception) as e:
            logger.warning(f"Goal decomposition failed: {e}")

        # Fallback: single generic milestone
        return [
            {
                "title": f"Initial research for: {title}",
                "description": "Gather information and develop an initial approach",
                "agent_type": "analyst",
                "estimated_days": 3,
                "success_criteria": "Research brief delivered with key findings",
            },
            {
                "title": f"Execute primary action for: {title}",
                "description": "Take the main action toward achieving the goal",
                "agent_type": "analyst",
                "estimated_days": 7,
                "success_criteria": "Primary deliverable completed",
            },
            {
                "title": f"Review and refine: {title}",
                "description": "Assess results and make adjustments",
                "agent_type": "strategist",
                "estimated_days": 3,
                "success_criteria": "Goal outcome assessed with next steps defined",
            },
        ]
```

Also add the missing import for `Any` at the top of the method if not already present (it's already imported at line 13).

**Step 2: Commit**

```bash
git add backend/src/onboarding/first_goal.py
git commit -m "feat: Fix 2 — goal decomposition via LLM into 3-5 milestones with agent assignments"
```

---

## Task 5: Fix 3 — Role Dropdown in User Profile Frontend

**Files:**
- Modify: `frontend/src/components/onboarding/UserProfileStep.tsx`

**Step 1: Add role to formData state, add handleSelectChange, add dropdown, update payload, add LinkedIn research indicator**

The component currently has 4 fields: full_name, title, department, linkedin_url. Add `role` as a `<select>` dropdown between department and linkedin_url. Also add a LinkedIn research loading indicator.

In `frontend/src/components/onboarding/UserProfileStep.tsx`:

1. Add `role` to the formData state (line 11-16):
```typescript
  const [formData, setFormData] = useState({
    full_name: "",
    title: "",
    department: "",
    role: "",
    linkedin_url: "",
  });
  const [linkedinResearching, setLinkedinResearching] = useState(false);
```

2. Add a `handleSelectChange` handler after `handleChange` (after line 47):
```typescript
  const handleSelectChange = (e: React.ChangeEvent<HTMLSelectElement>) => {
    const { name, value } = e.target;
    setFormData((prev) => ({ ...prev, [name]: value }));
  };
```

3. Update the profile data loading in useEffect (line 21-35) to include role:
```typescript
  useEffect(() => {
    getFullProfile()
      .then((profile) => {
        const u = profile.user;
        setFormData((prev) => ({
          full_name: u.full_name || prev.full_name,
          title: u.title || prev.title,
          department: u.department || prev.department,
          role: u.role || prev.role,
          linkedin_url: u.linkedin_url || prev.linkedin_url,
        }));
      })
      .catch(() => {
        // No saved data yet
      });
  }, []);
```

4. Add `role` to the payload in handleSubmit (after the department block, around line 85):
```typescript
      if (formData.role) {
        payload.role = formData.role;
      }
```

5. Add the role dropdown JSX between the Department and LinkedIn URL sections. Insert after the Department `</div>` (after line 241) and before the LinkedIn URL section:
```tsx
        {/* Role */}
        <div className="flex flex-col gap-1.5">
          <label
            htmlFor="role"
            className="font-sans text-[13px] font-medium text-secondary"
          >
            Role
          </label>
          <select
            id="role"
            name="role"
            value={formData.role}
            onChange={handleSelectChange}
            disabled={isSubmitting}
            className="
              bg-subtle border border-border rounded-lg px-4 py-3 text-[15px] font-sans
              text-content
              focus:outline-none focus:ring-1 focus:border-interactive focus:ring-interactive
              transition-colors duration-150
              disabled:opacity-50 disabled:cursor-not-allowed
              appearance-none
            "
          >
            <option value="">Select your role...</option>
            <option value="Sales">Sales</option>
            <option value="Business Development">Business Development</option>
            <option value="Marketing">Marketing</option>
            <option value="Operations">Operations</option>
            <option value="Executive">Executive</option>
            <option value="Clinical">Clinical</option>
            <option value="Regulatory">Regulatory</option>
            <option value="Medical Affairs">Medical Affairs</option>
            <option value="Other">Other</option>
          </select>
        </div>
```

6. After the form's submit button area, before the closing `</form>`, add the LinkedIn research indicator:
```tsx
      {/* LinkedIn Research Indicator */}
      {linkedinResearching && (
        <div className="rounded-xl bg-subtle border border-border px-5 py-4 flex items-center gap-3">
          <Loader2
            size={16}
            strokeWidth={1.5}
            className="animate-spin text-interactive"
            aria-hidden="true"
          />
          <p className="font-sans text-[13px] text-secondary">
            ARIA is researching your background...
          </p>
        </div>
      )}
```

7. In handleSubmit, after `onComplete()`, if LinkedIn URL was provided, show the indicator briefly:
```typescript
      await updateUserDetails(payload);
      if (formData.linkedin_url.trim()) {
        setLinkedinResearching(true);
      }
      onComplete();
```

**Step 2: Commit**

```bash
git add frontend/src/components/onboarding/UserProfileStep.tsx
git commit -m "feat: Fix 3 — role dropdown in User Profile step with LinkedIn research indicator"
```

---

## Task 6: Fix 4 — Role Config Influences Behavior

**Files:**
- Modify: `backend/src/services/goal_execution.py:250-261` (inject role context into agent prompts)
- Modify: `backend/src/onboarding/first_conversation.py:224-246` (inject role into first message)
- Modify: `backend/src/onboarding/activation.py:48-151` (adjust agent priorities by role)

**Step 1: Inject role into GoalExecutionService agent prompts**

In `backend/src/services/goal_execution.py`, modify the `_execute_agent` method. In the system prompt (around line 253-258), inject role context:

Replace the current system_prompt string with:

```python
                # Fetch user role for role-aware prompts
                user_profile = context.get("user_profile", {})
                user_role = user_profile.get("role", "")
                user_title = user_profile.get("title", "")
                company_name = context.get("company_name", "")

                role_context = ""
                if user_role or user_title:
                    role_context = (
                        f"\nThe user is a {user_title} in {user_role} at {company_name}. "
                        "Tailor your analysis to their perspective and priorities."
                    )

                response = await self._llm.generate_response(
                    messages=[{"role": "user", "content": prompt}],
                    system_prompt=(
                        "You are ARIA, an AI Department Director for life sciences "
                        "commercial teams. You are performing an initial analysis based "
                        "on onboarding data. Be specific, actionable, and concise. "
                        f"Respond with a JSON object only.{role_context}"
                    ),
                    max_tokens=2048,
                    temperature=0.4,
                )
```

Also update `_gather_execution_context` to include user profile:

```python
        # Add to _gather_execution_context method:
        # Fetch user profile for role context
        profile_result = (
            self._db.table("user_profiles")
            .select("role, title, full_name, company_id")
            .eq("id", user_id)
            .maybe_single()
            .execute()
        )
        if profile_result.data:
            context["user_profile"] = profile_result.data
            # Get company name
            company_id = profile_result.data.get("company_id")
            if company_id:
                company_result = (
                    self._db.table("companies")
                    .select("name")
                    .eq("id", company_id)
                    .maybe_single()
                    .execute()
                )
                if company_result.data:
                    context["company_name"] = company_result.data.get("name", "")
```

**Step 2: Inject role into first conversation prompt**

In `backend/src/onboarding/first_conversation.py`, in the `_compose_message` method (around line 224), add role context to the user_prompt:

After line 227 (`f"- Company classification: {classification or 'Unknown'}\n"`), add:

```python
            f"- User's role: {(user_profile or {}).get('role', 'Unknown')}\n"
            f"- User's title: {(user_profile or {}).get('title', 'Unknown')}\n"
```

**Step 3: Adjust agent priorities by role in activation**

In `backend/src/onboarding/activation.py`, in the `activate` method, after line 79 (`goal_type = user_goal.get("goal_type")`), add role-based priority adjustment:

```python
        # Fetch user role for priority adjustment
        user_role = ""
        try:
            profile_result = (
                self._db.table("user_profiles")
                .select("role")
                .eq("id", user_id)
                .maybe_single()
                .execute()
            )
            if profile_result.data:
                user_role = (profile_result.data.get("role") or "").lower()
        except Exception:
            pass

        # Role-based agent priority mapping
        role_priority_agents: dict[str, list[str]] = {
            "sales": ["hunter", "analyst"],
            "business development": ["hunter", "analyst"],
            "executive": ["strategist", "scout"],
            "marketing": ["scout", "scribe"],
            "operations": ["operator", "analyst"],
            "clinical": ["analyst", "scout"],
            "regulatory": ["analyst", "scout"],
            "medical affairs": ["analyst", "scribe"],
        }
        priority_agents = role_priority_agents.get(user_role, [])
```

Then, when creating each agent's goal, check if the agent is in the priority list. For instance, in `_activate_scout` (and similarly for each agent), when creating the `GoalCreate`, set `"priority": "medium"` if the agent type is in `priority_agents`, else keep `"low"`.

The simplest approach: pass `priority_agents` to each `_activate_*` method and use it:

In `activate()`, replace each `_activate_*` call to pass `priority_agents`:

```python
        activations["scout"] = await self._activate_scout(
            user_id, company_id, company_domain, onboarding_data,
            priority="medium" if "scout" in priority_agents else "low",
        )
        activations["analyst"] = await self._activate_analyst(
            user_id, onboarding_data,
            priority="medium" if "analyst" in priority_agents else "low",
        )
        # ... same pattern for hunter, operator, scribe, strategist
```

Then update each `_activate_*` method signature to accept `priority: str = "low"` and use it in the `GoalCreate` config.

**Step 4: Commit**

```bash
git add backend/src/services/goal_execution.py backend/src/onboarding/first_conversation.py backend/src/onboarding/activation.py
git commit -m "feat: Fix 4 — role config influences agent prompts, first conversation, and activation priorities"
```

---

## Task 7: Fix 5 — Goal Lifecycle Extensions

**Files:**
- Modify: `backend/src/services/goal_service.py`

**Step 1: Add goal status progression and complete_goal**

The GoalService already has `complete_milestone()` (line 548-593) and `generate_retrospective()` (line 595-699). What's missing:

1. Milestone completion should check if all milestones are done and auto-advance goal status
2. A `complete_goal()` method that generates a retrospective

In `backend/src/services/goal_service.py`, modify `complete_milestone` (after line 587 where it returns the milestone):

```python
            # Check if all milestones are complete → advance goal
            all_ms = (
                self._db.table("goal_milestones")
                .select("status")
                .eq("goal_id", goal_id)
                .execute()
            )
            all_statuses = [m.get("status") for m in (all_ms.data or [])]
            if all_statuses and all(s in ("complete", "skipped") for s in all_statuses):
                # Auto-complete the goal
                await self.complete_goal(user_id, goal_id)
```

Add a new `complete_goal` method (after `complete_milestone`):

```python
    async def complete_goal(
        self,
        user_id: str,
        goal_id: str,
    ) -> dict[str, Any] | None:
        """Complete a goal: update status, generate retrospective, update readiness.

        Args:
            user_id: The user's ID.
            goal_id: The goal ID.

        Returns:
            Updated goal dict with retrospective, or None if not found.
        """
        goal = await self.get_goal(user_id, goal_id)
        if not goal:
            return None

        now = datetime.now(UTC).isoformat()
        self._db.table("goals").update({
            "status": "complete",
            "progress": 100,
            "completed_at": now,
            "updated_at": now,
        }).eq("id", goal_id).eq("user_id", user_id).execute()

        # Generate retrospective
        retro = await self.generate_retrospective(user_id, goal_id)

        # Update readiness — goal_clarity domain
        try:
            from src.onboarding.orchestrator import OnboardingOrchestrator

            orch = OnboardingOrchestrator()
            await orch.update_readiness_scores(user_id, {"goal_clarity": 10.0})
        except Exception as e:
            logger.warning(f"Failed to update readiness on goal completion: {e}")

        logger.info(
            "Goal completed",
            extra={"goal_id": goal_id, "user_id": user_id},
        )

        return {**goal, "status": "complete", "retrospective": retro}
```

**Step 2: Add status progression helper**

Add `start_goal` update to include IN_PROGRESS status:

Check if `start_goal` already exists. From the exploration, it does at around line 177. Verify it sets status to "active". It does — `"active"` maps to the IN_PROGRESS concept. No change needed there.

The status flow is: DRAFT → ACTIVE (via `start_goal`) → COMPLETE (via `complete_goal`). This is sufficient.

**Step 3: Commit**

```bash
git add backend/src/services/goal_service.py
git commit -m "feat: Fix 5 — goal lifecycle with auto-completion on milestone finish and retrospective"
```

---

## Task 8: Fix 6 — Activity Feed During Onboarding

**Files:**
- Modify: `backend/src/onboarding/enrichment.py` (add activity record after enrichment)
- Modify: `backend/src/onboarding/document_ingestion.py` (add activity record after doc processing)
- Modify: `backend/src/onboarding/email_bootstrap.py` (add activity record after bootstrap)
- Modify: `backend/src/onboarding/activation.py` (add activity record when activation starts)
- Modify: `backend/src/onboarding/linkedin_research.py` (add activity record)

**Step 1: Add activity record to enrichment.py**

In `backend/src/onboarding/enrichment.py`, in the `_store_results` method (around line 801), after storing facts and hypotheses, add:

```python
        # Record activity for feed
        try:
            from src.services.activity_service import ActivityService

            activity = ActivityService()
            fact_count = len(result.facts)
            company_type = result.classification.company_type

            await activity.record(
                user_id=user_id,
                agent="scout",
                activity_type="enrichment_complete",
                title=f"Researched company background",
                description=(
                    f"ARIA researched the company — discovered {fact_count} facts "
                    f"about their {company_type} business"
                ),
                confidence=0.85,
                related_entity_type="company",
                related_entity_id=company_id,
                metadata={
                    "fact_count": fact_count,
                    "company_type": company_type,
                    "sources_used": result.sources_used,
                },
            )
        except Exception as e:
            logger.warning(f"Failed to record enrichment activity: {e}")
```

**Step 2: Add activity record to document_ingestion.py**

Find the completion point in `document_ingestion.py` (after chunks and entities are stored, near the readiness update). Add:

```python
        # Record activity for feed
        try:
            from src.services.activity_service import ActivityService

            activity = ActivityService()
            await activity.record(
                user_id=user_id,
                agent="analyst",
                activity_type="document_processed",
                title=f"Processed {filename}",
                description=(
                    f"ARIA processed {filename} — extracted {entity_count} entities "
                    f"and {fact_count} facts"
                ),
                confidence=0.8,
                related_entity_type="document",
                related_entity_id=document_id,
            )
        except Exception as e:
            logger.warning(f"Failed to record document activity: {e}")
```

**Step 3: Add activity record to email_bootstrap.py**

Find the completion point in `email_bootstrap.py` (after contacts and deals are processed). Add:

```python
        # Record activity for feed
        try:
            from src.services.activity_service import ActivityService

            activity = ActivityService()
            await activity.record(
                user_id=user_id,
                agent="analyst",
                activity_type="email_bootstrap_complete",
                title="Analyzed email history",
                description=(
                    f"ARIA analyzed {email_count} emails — identified {contact_count} key "
                    f"contacts and {deal_count} active deals"
                ),
                confidence=0.8,
                metadata={
                    "email_count": email_count,
                    "contact_count": contact_count,
                    "deal_count": deal_count,
                },
            )
        except Exception as e:
            logger.warning(f"Failed to record email bootstrap activity: {e}")
```

**Step 4: Add activity record to activation.py**

In `backend/src/onboarding/activation.py`, in the `activate` method, after the activation loop (before the return, around line 139), add:

```python
        # Record activity for feed
        try:
            from src.services.activity_service import ActivityService

            activity = ActivityService()
            activated_agents = [k for k, v in activations.items() if v is not None and k != "skills_installed"]
            await activity.record(
                user_id=user_id,
                agent=None,
                activity_type="agents_activated",
                title="ARIA started working on your goals",
                description=(
                    f"ARIA activated {len(activated_agents)} agents: "
                    f"{', '.join(activated_agents)}. "
                    "Results will appear in your daily briefing."
                ),
                confidence=0.9,
            )
        except Exception as e:
            logger.warning(f"Failed to record activation activity: {e}")
```

**Step 5: Add activity record to linkedin_research.py**

In `backend/src/onboarding/linkedin_research.py`, in the `research_profile` method, after step 5 (record episodic memory) and before step 6 (generate summary), add:

```python
        # 5b. Record activity for feed
        try:
            from src.services.activity_service import ActivityService

            activity = ActivityService()
            await activity.record(
                user_id=user_id,
                agent="analyst",
                activity_type="linkedin_research_complete",
                title="Researched professional background",
                description=(
                    f"ARIA researched {full_name}'s professional background"
                ),
                confidence=0.8,
            )
        except Exception as e:
            logger.warning(f"Failed to record LinkedIn research activity: {e}")
```

**Step 6: Commit all activity feed changes**

```bash
git add backend/src/onboarding/enrichment.py backend/src/onboarding/document_ingestion.py backend/src/onboarding/email_bootstrap.py backend/src/onboarding/activation.py backend/src/onboarding/linkedin_research.py
git commit -m "feat: Fix 6 — activity feed records during onboarding (enrichment, docs, email, activation, LinkedIn)"
```

---

## Task 9: Final Commit — Sprint 4 Complete

**Step 1: Verify no lint errors**

```bash
cd backend && ruff check src/onboarding/linkedin_research.py src/onboarding/first_goal.py src/services/profile_service.py src/services/goal_service.py src/services/goal_execution.py src/onboarding/first_conversation.py src/onboarding/activation.py src/onboarding/enrichment.py
```

```bash
cd frontend && npx tsc --noEmit src/components/onboarding/UserProfileStep.tsx
```

**Step 2: Run tests**

```bash
cd backend && python -m pytest tests/ -v --tb=short -x
```

**Step 3: Squash into final commit if individual commits were made (optional — or just leave as granular commits)**

The individual per-task commits above serve as the commit history. If the user wants a single squash commit, use:

```bash
git reset --soft HEAD~8
git commit -m "feat: Sprint 4 — LinkedIn research, goal decomposition, role config, goal lifecycle, activity feed"
```

---

## Summary of All Changes

| Fix | Files Modified/Created | What It Does |
|-----|----------------------|--------------|
| Migration | `backend/supabase/migrations/20260209100000_sprint4_depth_polish.sql` | Adds `role` column to user_profiles, `agent_type`/`success_criteria` to goal_milestones |
| Fix 1 | `backend/src/onboarding/linkedin_research.py` (NEW) | Exa API triangulation → profile extraction → Digital Twin + semantic memory + episodic memory |
| Fix 1 wire | `backend/src/services/profile_service.py` | Fires LinkedInResearchService as background task after profile save with LinkedIn URL |
| Fix 2 | `backend/src/onboarding/first_goal.py` | LLM decomposes goals into 3-5 milestones with agent_type, estimated_days, success_criteria |
| Fix 3 | `frontend/src/components/onboarding/UserProfileStep.tsx` | Role dropdown (9 options), LinkedIn research indicator |
| Fix 4 | `goal_execution.py`, `first_conversation.py`, `activation.py` | Role injected into agent prompts, first message, and activation priorities |
| Fix 5 | `backend/src/services/goal_service.py` | Auto-complete goal when all milestones done, generate retrospective, update readiness |
| Fix 6 | `enrichment.py`, `document_ingestion.py`, `email_bootstrap.py`, `activation.py`, `linkedin_research.py` | ActivityService.record() calls at key onboarding events |
