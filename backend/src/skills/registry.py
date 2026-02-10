"""Unified skill registry for ARIA.

Indexes ALL skill types into a single searchable registry with
priority ordering: native capabilities > LLM definitions > custom
tenant skills > external skills.sh skills.

On startup, scans and registers:
- Native capabilities from src/agents/capabilities/ (auto-discovered)
- LLM skill definitions from src/skills/definitions/*/skill.yaml
- Installed skills.sh skills from skills_index table
- Custom tenant skills from custom_skills table

Usage::

    registry = SkillRegistry()
    await registry.initialize()

    # Semantic search across all skill types
    results = await registry.search("summarize meeting", user_id="...")

    # Get skills ranked by relevance to a task
    ranked = await registry.get_for_task({"type": "company_research", ...})

    # Skills available to a specific agent
    agent_skills = await registry.get_for_agent("hunter")
"""

import importlib
import inspect
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from src.agents.capabilities.base import BaseCapability
from src.db.supabase import SupabaseClient
from src.security.trust_levels import SkillTrustLevel
from src.skills.definitions.base import BaseSkillDefinition, SkillDefinition
from src.skills.index import SkillIndex

logger = logging.getLogger(__name__)

# Directories for auto-discovery
_CAPABILITIES_DIR = Path(__file__).resolve().parent.parent / "agents" / "capabilities"
_DEFINITIONS_DIR = Path(__file__).resolve().parent / "definitions"


class SkillType:
    """Skill source type constants."""

    NATIVE = "native"
    DEFINITION = "definition"
    CUSTOM = "custom"
    EXTERNAL = "external"


# Priority order — lower number = higher priority
_SKILL_TYPE_PRIORITY: dict[str, int] = {
    SkillType.NATIVE: 0,
    SkillType.DEFINITION: 1,
    SkillType.CUSTOM: 2,
    SkillType.EXTERNAL: 3,
}


@dataclass(frozen=True)
class PerformanceMetrics:
    """Execution performance metrics for a skill."""

    success_rate: float = 0.0
    total_executions: int = 0
    avg_execution_time_ms: int = 0


@dataclass(frozen=True)
class SkillEntry:
    """Unified skill entry across all skill types.

    This is the single representation that consumers use regardless
    of whether the skill is a native capability, YAML definition,
    custom tenant skill, or external skills.sh skill.
    """

    id: str
    name: str
    description: str
    skill_type: str  # SkillType constant
    agent_types: list[str]
    trust_level: SkillTrustLevel
    data_classes: list[str]
    performance_metrics: PerformanceMetrics = field(
        default_factory=PerformanceMetrics,
    )

    @property
    def priority(self) -> int:
        """Return sort priority (lower = higher priority)."""
        return _SKILL_TYPE_PRIORITY.get(self.skill_type, 99)


@dataclass
class RankedSkill:
    """A skill entry paired with a relevance score for task matching."""

    entry: SkillEntry
    relevance: float  # 0.0-1.0


class SkillRegistry:
    """Unified registry that indexes all skill types.

    Provides a single interface for searching, filtering, and ranking
    skills regardless of their source. Native capabilities are preferred
    over marketplace skills via priority ordering.
    """

    def __init__(self) -> None:
        self._entries: dict[str, SkillEntry] = {}
        self._capability_classes: dict[str, type[BaseCapability]] = {}
        self._capability_instances: dict[str, BaseCapability] = {}
        self._definitions: dict[str, BaseSkillDefinition] = {}
        self._skill_index = SkillIndex()
        self._initialized = False

    async def initialize(self) -> None:
        """Scan and register all skill types.

        Call once at application startup. Populates the registry with
        native capabilities, LLM definitions, custom skills, and
        external skills.
        """
        logger.info("Initializing unified skill registry")

        self._discover_capabilities()
        self._discover_definitions()
        await self._load_external_skills()
        await self._load_custom_skills()

        self._initialized = True
        logger.info(
            "Skill registry initialized",
            extra={
                "native": sum(
                    1 for e in self._entries.values() if e.skill_type == SkillType.NATIVE
                ),
                "definitions": sum(
                    1 for e in self._entries.values() if e.skill_type == SkillType.DEFINITION
                ),
                "custom": sum(
                    1 for e in self._entries.values() if e.skill_type == SkillType.CUSTOM
                ),
                "external": sum(
                    1 for e in self._entries.values() if e.skill_type == SkillType.EXTERNAL
                ),
                "total": len(self._entries),
            },
        )

    # ------------------------------------------------------------------
    # Registration methods
    # ------------------------------------------------------------------

    def register_capability(self, capability: BaseCapability) -> None:
        """Register a native capability instance.

        Registers both the class (for metadata) and the live instance
        (for ``can_handle()`` invocation during task matching).

        Args:
            capability: An instantiated BaseCapability subclass.
        """
        cls = type(capability)
        entry_id = f"native:{cls.capability_name}"

        self._capability_classes[entry_id] = cls
        self._capability_instances[entry_id] = capability

        entry = SkillEntry(
            id=entry_id,
            name=cls.capability_name,
            description=cls.__doc__.split("\n")[0] if cls.__doc__ else cls.capability_name,
            skill_type=SkillType.NATIVE,
            agent_types=list(cls.agent_types),
            trust_level=SkillTrustLevel.CORE,
            data_classes=capability.get_data_classes_accessed(),
        )
        self._entries[entry_id] = entry
        logger.debug("Registered native capability: %s", cls.capability_name)

    def register_definition(self, definition: BaseSkillDefinition) -> None:
        """Register an LLM skill definition.

        Args:
            definition: A loaded BaseSkillDefinition instance.
        """
        defn: SkillDefinition = definition.definition
        entry_id = f"definition:{defn.name}"

        self._definitions[entry_id] = definition

        entry = SkillEntry(
            id=entry_id,
            name=defn.name,
            description=defn.description,
            skill_type=SkillType.DEFINITION,
            agent_types=list(defn.agent_assignment),
            trust_level=definition.trust_level,
            data_classes=[],
        )
        self._entries[entry_id] = entry
        logger.debug("Registered skill definition: %s", defn.name)

    async def refresh_external(self) -> None:
        """Re-sync skills_index from skills.sh.

        Delegates to SkillIndex.sync_from_skills_sh() then reloads
        external skill entries.
        """
        logger.info("Refreshing external skills from skills.sh")
        synced = await self._skill_index.sync_from_skills_sh()
        logger.info("Synced %d external skills", synced)

        # Remove stale external entries and reload
        stale_ids = [eid for eid, e in self._entries.items() if e.skill_type == SkillType.EXTERNAL]
        for eid in stale_ids:
            del self._entries[eid]

        await self._load_external_skills()

    # ------------------------------------------------------------------
    # Query methods
    # ------------------------------------------------------------------

    async def search(self, query: str, user_id: str) -> list[SkillEntry]:
        """Semantic search across all skills.

        Performs case-insensitive keyword matching on name, description,
        and agent_types. Results are ordered by skill type priority
        (native first, external last).

        Args:
            query: Free-text search query.
            user_id: ID of the requesting user (for custom skill access).

        Returns:
            Matching SkillEntry objects sorted by priority.
        """
        query_lower = query.lower()
        tokens = query_lower.split()
        results: list[SkillEntry] = []

        for entry in self._entries.values():
            searchable = f"{entry.name} {entry.description} {' '.join(entry.agent_types)}".lower()
            if any(tok in searchable for tok in tokens):
                results.append(entry)

        # Also query custom skills this user can access but that may
        # not be loaded yet (other tenants' published skills, etc.)
        await self._search_custom_skills(query, user_id, results)

        results.sort(key=lambda e: e.priority)
        return results

    async def get_for_task(self, task: dict[str, Any]) -> list[RankedSkill]:
        """Return skills ranked by relevance to a task.

        For native capabilities, calls ``can_handle(task)`` to get a
        real confidence score. For other skill types, uses keyword
        heuristics against the task description.

        Args:
            task: Task specification dict.

        Returns:
            Skills with relevance > 0, sorted by relevance descending.
        """
        ranked: list[RankedSkill] = []

        for entry_id, entry in self._entries.items():
            relevance = 0.0

            if entry.skill_type == SkillType.NATIVE:
                # Use real can_handle() for native capabilities
                instance = self._capability_instances.get(entry_id)
                if instance is not None:
                    try:
                        relevance = await instance.can_handle(task)
                    except Exception as exc:
                        logger.warning(
                            "can_handle() failed for %s: %s",
                            entry.name,
                            exc,
                        )
                        relevance = 0.0
            else:
                # Keyword heuristic for non-native skills
                relevance = self._keyword_relevance(entry, task)

            if relevance > 0.0:
                ranked.append(RankedSkill(entry=entry, relevance=relevance))

        # Sort by relevance descending, then priority ascending for ties
        ranked.sort(key=lambda r: (-r.relevance, r.entry.priority))
        return ranked

    async def get_for_agent(self, agent_type: str) -> list[SkillEntry]:
        """Get skills available to a specific agent type.

        Args:
            agent_type: Agent identifier (e.g. "hunter", "analyst").

        Returns:
            SkillEntry list filtered to those assigned to this agent,
            sorted by priority.
        """
        results = [entry for entry in self._entries.values() if agent_type in entry.agent_types]
        results.sort(key=lambda e: e.priority)
        return results

    async def get_all_available(self, user_id: str) -> list[SkillEntry]:
        """Get everything this user can access.

        Includes all native, definition, and external skills plus
        custom skills belonging to the user's tenant.

        Args:
            user_id: Authenticated user UUID.

        Returns:
            All accessible SkillEntry objects sorted by priority.
        """
        results = list(self._entries.values())

        # Ensure custom skills for this user's tenant are loaded
        await self._ensure_custom_skills_for_user(user_id, results)

        results.sort(key=lambda e: e.priority)
        return results

    # ------------------------------------------------------------------
    # Auto-discovery: native capabilities
    # ------------------------------------------------------------------

    def _discover_capabilities(self) -> None:
        """Scan agents/capabilities/ for BaseCapability subclasses.

        Uses importlib to import every .py file in the capabilities
        directory and registers any class that is a concrete subclass
        of BaseCapability (i.e. has capability_name set).
        """
        if not _CAPABILITIES_DIR.is_dir():
            logger.debug("Capabilities directory not found: %s", _CAPABILITIES_DIR)
            return

        for py_file in _CAPABILITIES_DIR.glob("*.py"):
            if py_file.name.startswith("_"):
                continue

            module_name = f"src.agents.capabilities.{py_file.stem}"
            try:
                module = importlib.import_module(module_name)
            except Exception as exc:
                logger.warning("Failed to import capability module %s: %s", module_name, exc)
                continue

            for _name, obj in inspect.getmembers(module, inspect.isclass):
                if (
                    issubclass(obj, BaseCapability)
                    and obj is not BaseCapability
                    and getattr(obj, "capability_name", "")
                ):
                    entry_id = f"native:{obj.capability_name}"
                    self._capability_classes[entry_id] = obj

                    entry = SkillEntry(
                        id=entry_id,
                        name=obj.capability_name,
                        description=(
                            obj.__doc__.split("\n")[0] if obj.__doc__ else obj.capability_name
                        ),
                        skill_type=SkillType.NATIVE,
                        agent_types=list(obj.agent_types),
                        trust_level=SkillTrustLevel.CORE,
                        data_classes=[],  # Requires instantiation for full data
                    )
                    self._entries[entry_id] = entry
                    logger.debug(
                        "Discovered native capability: %s",
                        obj.capability_name,
                    )

    # ------------------------------------------------------------------
    # Auto-discovery: LLM skill definitions
    # ------------------------------------------------------------------

    def _discover_definitions(self) -> None:
        """Scan skills/definitions/ for skill.yaml files.

        Each subdirectory containing a ``skill.yaml`` is loaded as a
        BaseSkillDefinition (without an LLM client — metadata only).
        """
        if not _DEFINITIONS_DIR.is_dir():
            logger.debug("Definitions directory not found: %s", _DEFINITIONS_DIR)
            return

        for skill_dir in _DEFINITIONS_DIR.iterdir():
            if not skill_dir.is_dir() or skill_dir.name.startswith("_"):
                continue

            yaml_path = skill_dir / "skill.yaml"
            if not yaml_path.exists():
                continue

            try:
                # Load definition metadata without LLM client
                defn = BaseSkillDefinition.__new__(BaseSkillDefinition)
                defn._skill_name = skill_dir.name
                defn._base_dir = _DEFINITIONS_DIR
                defn._definition = defn._load_definition()

                entry_id = f"definition:{defn._definition.name}"
                self._definitions[entry_id] = defn

                entry = SkillEntry(
                    id=entry_id,
                    name=defn._definition.name,
                    description=defn._definition.description,
                    skill_type=SkillType.DEFINITION,
                    agent_types=list(defn._definition.agent_assignment),
                    trust_level=defn.trust_level,
                    data_classes=[],
                )
                self._entries[entry_id] = entry
                logger.debug("Discovered skill definition: %s", defn._definition.name)

            except Exception as exc:
                logger.warning(
                    "Failed to load skill definition from %s: %s",
                    skill_dir.name,
                    exc,
                )

    # ------------------------------------------------------------------
    # Database loading: external skills.sh
    # ------------------------------------------------------------------

    async def _load_external_skills(self) -> None:
        """Load skills from the skills_index table."""
        try:
            client = SupabaseClient.get_client()
            response = client.table("skills_index").select("*").execute()

            for row in response.data:
                index_entry = self._skill_index._db_row_to_entry(row)
                entry_id = f"external:{index_entry.id}"

                entry = SkillEntry(
                    id=entry_id,
                    name=index_entry.skill_name,
                    description=index_entry.description or "",
                    skill_type=SkillType.EXTERNAL,
                    agent_types=[],  # External skills don't declare agent affinity
                    trust_level=index_entry.trust_level,
                    data_classes=[],
                    performance_metrics=PerformanceMetrics(),
                )
                self._entries[entry_id] = entry

        except Exception as exc:
            logger.error("Failed to load external skills: %s", exc)

    # ------------------------------------------------------------------
    # Database loading: custom tenant skills
    # ------------------------------------------------------------------

    async def _load_custom_skills(self) -> None:
        """Load custom tenant skills from the custom_skills table."""
        try:
            client = SupabaseClient.get_client()
            response = client.table("custom_skills").select("*").execute()

            for row in response.data:
                self._register_custom_skill_row(row)

        except Exception as exc:
            logger.error("Failed to load custom skills: %s", exc)

    def _register_custom_skill_row(self, row: dict[str, Any]) -> None:
        """Convert a custom_skills DB row to a SkillEntry and register it."""
        entry_id = f"custom:{row['id']}"

        trust_str = row.get("trust_level", "user")
        try:
            trust_level = SkillTrustLevel(trust_str)
        except ValueError:
            trust_level = SkillTrustLevel.USER

        perf = row.get("performance_metrics") or {}
        metrics = PerformanceMetrics(
            success_rate=perf.get("success_rate", 0.0),
            total_executions=perf.get("executions", 0),
            avg_execution_time_ms=0,
        )

        # Determine agent types from skill_type or definition
        definition = row.get("definition") or {}
        agent_types = definition.get("agent_assignment", [])

        entry = SkillEntry(
            id=entry_id,
            name=row.get("skill_name", ""),
            description=row.get("description", ""),
            skill_type=SkillType.CUSTOM,
            agent_types=agent_types,
            trust_level=trust_level,
            data_classes=[],
            performance_metrics=metrics,
        )
        self._entries[entry_id] = entry

    async def _search_custom_skills(
        self,
        query: str,
        user_id: str,
        existing: list[SkillEntry],
    ) -> None:
        """Search custom_skills table for additional matches.

        Custom skills are tenant-scoped. This queries the DB for the
        user's tenant and adds any matching skills not already in results.
        """
        existing_ids = {e.id for e in existing}

        try:
            client = SupabaseClient.get_client()

            # Get user's tenant
            user_resp = (
                client.table("user_profiles")
                .select("company_id")
                .eq("id", user_id)
                .single()
                .execute()
            )
            tenant_id = user_resp.data.get("company_id") if user_resp.data else None

            if not tenant_id:
                return

            sanitized = query.replace("%", "\\%").replace("_", "\\_")
            response = (
                client.table("custom_skills")
                .select("*")
                .eq("tenant_id", tenant_id)
                .or_(f"skill_name.ilike.%{sanitized}%,description.ilike.%{sanitized}%")
                .execute()
            )

            for row in response.data:
                entry_id = f"custom:{row['id']}"
                if entry_id not in existing_ids:
                    self._register_custom_skill_row(row)
                    existing.append(self._entries[entry_id])

        except Exception as exc:
            logger.debug("Custom skill search failed: %s", exc)

    async def _ensure_custom_skills_for_user(
        self,
        user_id: str,
        results: list[SkillEntry],
    ) -> None:
        """Ensure custom skills for user's tenant are in the results."""
        try:
            client = SupabaseClient.get_client()

            user_resp = (
                client.table("user_profiles")
                .select("company_id")
                .eq("id", user_id)
                .single()
                .execute()
            )
            tenant_id = user_resp.data.get("company_id") if user_resp.data else None

            if not tenant_id:
                return

            response = (
                client.table("custom_skills").select("*").eq("tenant_id", tenant_id).execute()
            )

            existing_ids = {e.id for e in results}
            for row in response.data:
                entry_id = f"custom:{row['id']}"
                if entry_id not in existing_ids:
                    self._register_custom_skill_row(row)
                    results.append(self._entries[entry_id])

        except Exception as exc:
            logger.debug("Failed to load custom skills for user %s: %s", user_id, exc)

    # ------------------------------------------------------------------
    # Relevance scoring helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _keyword_relevance(entry: SkillEntry, task: dict[str, Any]) -> float:
        """Score relevance of a non-native skill to a task via keywords.

        Examines the task's type, description, and other string fields
        against the skill's name, description, and agent_types.

        Args:
            entry: The skill to score.
            task: Task specification dict.

        Returns:
            Float in [0.0, 1.0]. Higher = more relevant.
        """
        # Build searchable text from the task
        task_parts: list[str] = []
        for key in ("type", "description", "query", "goal", "objective"):
            val = task.get(key)
            if isinstance(val, str):
                task_parts.append(val.lower())
        task_text = " ".join(task_parts)

        if not task_text:
            return 0.0

        # Tokenize skill metadata
        skill_tokens = set(f"{entry.name} {entry.description}".lower().split())
        # Remove very common words
        skill_tokens -= {"the", "a", "an", "and", "or", "for", "to", "of", "in", "is"}

        if not skill_tokens:
            return 0.0

        # Count matches
        matches = sum(1 for tok in skill_tokens if tok in task_text)
        score = min(matches / max(len(skill_tokens), 1), 1.0)

        # Boost if task type exactly matches skill name
        task_type = task.get("type", "")
        if isinstance(task_type, str) and task_type.lower() == entry.name.lower():
            score = min(score + 0.4, 1.0)

        return score
