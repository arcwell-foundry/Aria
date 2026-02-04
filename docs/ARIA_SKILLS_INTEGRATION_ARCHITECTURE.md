# ARIA Skills Integration Architecture
## Secure, Autonomous Skill Orchestration for Enterprise Life Sciences

**Version:** 2.0  
**Date:** February 4, 2026  
**Status:** Architecture Design Document  
**Supersedes:** ARIA_SKILLS_SH_INTEGRATION.md v1.0

---

## Executive Summary

This document defines how ARIA integrates with skills.sh while maintaining enterprise-grade security. Skills become an extension of ARIA's agent system—not a separate capability bolted on, but deeply woven into the existing architecture.

### Design Principles

| Principle | Implementation |
|-----------|----------------|
| **Security First** | Data classification, sandboxing, and audit before any skill executes |
| **Deep Integration** | Skills work with agents, memory, OODA loop—not alongside them |
| **Transparency** | ARIA always shows her work and reasoning |
| **Graduated Autonomy** | Trust builds over time based on outcomes |
| **Context Efficiency** | On-demand loading, sub-agent isolation, working memory |

---

## Part 1: Security Architecture

### 1.1 The Moltbot Lesson

Moltbot/Clawdbot failed security because:
- Any ClawdHub skill could access all user data
- No skill verification or sandboxing
- Skills could exfiltrate data to external servers
- No audit trail of skill actions

**ARIA's Response:** Skills are treated as **untrusted code** until proven otherwise. Customer data flows through a security pipeline before ANY skill sees it.

### 1.2 Data Classification System

Every piece of data in ARIA has a classification:

```python
# backend/src/security/data_classification.py

from enum import Enum
from dataclasses import dataclass
from typing import Optional
import re

class DataClass(Enum):
    """Data classification levels - determines what skills can access."""
    
    PUBLIC = "public"           # Can be shared freely (company names, public info)
    INTERNAL = "internal"       # Company internal (goals, strategies, notes)
    CONFIDENTIAL = "confidential"  # Need-to-know (deal details, contacts)
    RESTRICTED = "restricted"   # Financial, competitive (revenue, pricing, contracts)
    REGULATED = "regulated"     # PHI, PII - legal requirements (HIPAA, GDPR)


@dataclass
class ClassifiedData:
    """Data with its classification and handling rules."""
    data: any
    classification: DataClass
    data_type: str  # "financial", "contact", "health", "competitive", etc.
    source: str     # Where this data came from
    can_be_tokenized: bool = True  # Can we replace with placeholder?
    retention_days: Optional[int] = None  # Auto-delete after N days
    

class DataClassifier:
    """
    Automatically classifies data based on content and context.
    Runs on ALL data before it reaches any skill.
    """
    
    # Patterns that indicate sensitive data
    PATTERNS = {
        DataClass.REGULATED: [
            r'\b\d{3}-\d{2}-\d{4}\b',  # SSN
            r'\b\d{16}\b',  # Credit card
            r'\bDOB\s*:\s*\d{1,2}/\d{1,2}/\d{4}\b',  # Date of birth
            r'\bdiagnosis\b|\bprognosis\b|\bmedication\b',  # PHI indicators
            r'\bpatient\s+id\b|\bmedical\s+record\b',  # Medical records
        ],
        DataClass.RESTRICTED: [
            r'\$\s*[\d,]+\.?\d*\s*(M|K|million|thousand)?',  # Money amounts
            r'\brevenue\b|\bprofits?\b|\bmargin\b',  # Financial terms
            r'\bcontract\s+value\b|\bdeal\s+size\b',  # Deal terms
            r'\bcompetitor\s+pricing\b|\bour\s+pricing\b',  # Pricing intel
            r'\bconfidential\b|\bproprietary\b',  # Explicit markers
        ],
        DataClass.CONFIDENTIAL: [
            r'\b[\w.+-]+@[\w-]+\.[\w.-]+\b',  # Email addresses
            r'\b\d{3}[-.]?\d{3}[-.]?\d{4}\b',  # Phone numbers
            r'\bcontact\b.*\b(name|email|phone)\b',  # Contact info context
        ],
    }
    
    async def classify(self, data: any, context: dict) -> ClassifiedData:
        """
        Classify data based on content patterns and context.
        """
        text = str(data) if not isinstance(data, str) else data
        
        # Check patterns from most to least sensitive
        for classification in [DataClass.REGULATED, DataClass.RESTRICTED, DataClass.CONFIDENTIAL]:
            for pattern in self.PATTERNS.get(classification, []):
                if re.search(pattern, text, re.IGNORECASE):
                    return ClassifiedData(
                        data=data,
                        classification=classification,
                        data_type=self._infer_data_type(text, pattern),
                        source=context.get("source", "unknown"),
                    )
        
        # Check context-based classification
        if context.get("source") == "crm_deal":
            return ClassifiedData(
                data=data,
                classification=DataClass.CONFIDENTIAL,
                data_type="deal_info",
                source="crm",
            )
        
        if context.get("source") == "financial_report":
            return ClassifiedData(
                data=data,
                classification=DataClass.RESTRICTED,
                data_type="financial",
                source="financial_system",
            )
        
        # Default to internal
        return ClassifiedData(
            data=data,
            classification=DataClass.INTERNAL,
            data_type="general",
            source=context.get("source", "unknown"),
        )
```

### 1.3 Skill Trust Levels

Skills have different trust levels that determine what data they can access:

```python
# backend/src/skills/trust_levels.py

from enum import Enum

class SkillTrustLevel(Enum):
    """
    Trust levels for skills - determines data access permissions.
    """
    
    CORE = "core"
    # Built by ARIA team, fully audited, part of the product
    # Can access: ALL data classes with user permission
    # Examples: ARIA's built-in document skills, analysis tools
    
    VERIFIED = "verified"
    # From trusted sources (Anthropic, Vercel, Supabase), security reviewed
    # Can access: PUBLIC, INTERNAL only
    # Examples: anthropics/skills/pdf, vercel-labs/agent-skills
    
    COMMUNITY = "community"
    # From skills.sh, no security review
    # Can access: PUBLIC only
    # Examples: Most skills.sh community skills
    
    USER = "user"
    # Created by this user/tenant
    # Can access: PUBLIC, INTERNAL (their own data only)
    # Examples: Custom skills created within ARIA


# What each trust level can access
TRUST_DATA_ACCESS = {
    SkillTrustLevel.CORE: [
        DataClass.PUBLIC, 
        DataClass.INTERNAL, 
        DataClass.CONFIDENTIAL, 
        DataClass.RESTRICTED,
        # REGULATED requires explicit per-execution approval
    ],
    SkillTrustLevel.VERIFIED: [
        DataClass.PUBLIC, 
        DataClass.INTERNAL,
    ],
    SkillTrustLevel.COMMUNITY: [
        DataClass.PUBLIC,
    ],
    SkillTrustLevel.USER: [
        DataClass.PUBLIC, 
        DataClass.INTERNAL,
    ],
}


# Trusted sources that get VERIFIED status automatically
TRUSTED_SKILL_SOURCES = [
    "anthropics/skills",
    "vercel-labs/agent-skills",
    "supabase/agent-skills",
    "expo/skills",
    "better-auth/skills",
]
```

### 1.4 Data Sanitization Pipeline

Before ANY data reaches a skill, it passes through sanitization:

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                     DATA SANITIZATION PIPELINE                               │
│                                                                              │
│  User Request + Context Data                                                 │
│           │                                                                  │
│           ▼                                                                  │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │  STEP 1: CLASSIFICATION                                              │   │
│  │  • Scan all data for sensitive patterns                              │   │
│  │  • Assign DataClass to each field                                    │   │
│  │  • Tag source and data type                                          │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│           │                                                                  │
│           ▼                                                                  │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │  STEP 2: PERMISSION CHECK                                            │   │
│  │  • Get skill's trust level                                           │   │
│  │  • Check TRUST_DATA_ACCESS matrix                                    │   │
│  │  • Identify data that skill CANNOT see                               │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│           │                                                                  │
│           ▼                                                                  │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │  STEP 3: TOKENIZATION                                                │   │
│  │  • Replace sensitive values with tokens                              │   │
│  │  • "Revenue: $4.2M" → "Revenue: [FINANCIAL_001]"                     │   │
│  │  • "John Smith" → "[CONTACT_001]"                                    │   │
│  │  • Store token mapping for de-tokenization                           │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│           │                                                                  │
│           ▼                                                                  │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │  STEP 4: REDACTION (if tokenization not possible)                    │   │
│  │  • Some data cannot be tokenized (e.g., SSN)                         │   │
│  │  • Redact completely: "[REDACTED: SSN]"                              │   │
│  │  • Log redaction for audit                                           │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│           │                                                                  │
│           ▼                                                                  │
│  Sanitized Data → Skill Execution                                           │
│           │                                                                  │
│           ▼                                                                  │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │  STEP 5: OUTPUT VALIDATION                                           │   │
│  │  • Scan skill output for data leakage                                │   │
│  │  • Verify no sensitive patterns in output                            │   │
│  │  • De-tokenize authorized data                                       │   │
│  │  • Block if leakage detected                                         │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│           │                                                                  │
│           ▼                                                                  │
│  Clean Output → User / Next Step                                            │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 1.5 Skill Execution Sandbox

Community and user skills run in isolated sandboxes:

```python
# backend/src/skills/sandbox.py

from dataclasses import dataclass
from typing import Optional
import asyncio

@dataclass
class SandboxConfig:
    """Configuration for skill execution sandbox."""
    
    # Resource limits
    timeout_seconds: int = 30
    memory_limit_mb: int = 256
    cpu_limit_percent: int = 50
    
    # Network restrictions
    network_enabled: bool = False  # Default: no network for community skills
    allowed_domains: list[str] = None  # Whitelist if network enabled
    
    # Filesystem restrictions
    filesystem_enabled: bool = False
    allowed_paths: list[str] = None
    
    # What the skill can do
    can_read_files: bool = False
    can_write_files: bool = False
    can_execute_code: bool = False
    can_make_api_calls: bool = False


# Sandbox configs by trust level
SANDBOX_BY_TRUST = {
    SkillTrustLevel.CORE: SandboxConfig(
        timeout_seconds=120,
        memory_limit_mb=1024,
        network_enabled=True,
        allowed_domains=["*"],  # Core skills can access any domain
        can_read_files=True,
        can_write_files=True,
        can_execute_code=True,
        can_make_api_calls=True,
    ),
    SkillTrustLevel.VERIFIED: SandboxConfig(
        timeout_seconds=60,
        memory_limit_mb=512,
        network_enabled=False,  # Verified skills: no network
        can_read_files=True,
        can_write_files=True,  # Can create output files
        can_execute_code=False,
        can_make_api_calls=False,
    ),
    SkillTrustLevel.COMMUNITY: SandboxConfig(
        timeout_seconds=30,
        memory_limit_mb=256,
        network_enabled=False,
        can_read_files=False,
        can_write_files=False,
        can_execute_code=False,
        can_make_api_calls=False,
    ),
    SkillTrustLevel.USER: SandboxConfig(
        timeout_seconds=60,
        memory_limit_mb=512,
        network_enabled=False,
        can_read_files=True,
        can_write_files=True,
        can_execute_code=False,
        can_make_api_calls=False,
    ),
}


class SkillSandbox:
    """
    Executes skills in isolated sandbox with resource limits.
    """
    
    async def execute(
        self,
        skill_content: str,
        input_data: dict,
        config: SandboxConfig,
    ) -> dict:
        """
        Execute skill instructions in sandbox.
        
        For LLM-based skills (most skills), this means:
        - Building a prompt with skill instructions + sanitized input
        - Calling the LLM with resource limits
        - Validating output
        
        For code-based skills (rare, CORE only):
        - Executing in isolated container
        - Strict resource limits
        """
        
        # Apply timeout
        try:
            result = await asyncio.wait_for(
                self._execute_skill(skill_content, input_data, config),
                timeout=config.timeout_seconds,
            )
        except asyncio.TimeoutError:
            raise SkillExecutionError(
                f"Skill execution timed out after {config.timeout_seconds}s"
            )
        
        return result
```

### 1.6 Comprehensive Audit Trail

Every skill operation is logged with chain integrity:

```python
# backend/src/skills/audit.py

@dataclass
class SkillAuditEntry:
    """Immutable audit record for skill operations."""
    
    # Identity
    id: str
    timestamp: datetime
    user_id: str
    tenant_id: str
    
    # Skill info
    skill_id: str
    skill_path: str  # e.g., "anthropics/skills/pdf"
    skill_trust_level: str
    skill_version: str
    
    # Execution context
    task_id: str  # Links to parent task/goal
    agent_id: str  # Which agent invoked this skill
    trigger_reason: str  # Why was this skill used
    
    # Data access (critical for compliance)
    data_classes_requested: list[str]  # What data classes skill wanted
    data_classes_granted: list[str]    # What it actually got
    data_redacted: bool                # Was any data redacted?
    tokens_used: list[str]             # What tokens were used
    
    # Execution
    input_hash: str           # SHA256 of sanitized input
    output_hash: str          # SHA256 of output
    execution_time_ms: int
    success: bool
    error: Optional[str]
    
    # Security
    sandbox_config: dict
    security_flags: list[str]  # Any security events during execution
    
    # Chain integrity
    previous_hash: str
    entry_hash: str


class SkillAuditService:
    """
    Maintains immutable audit trail for all skill operations.
    Integrates with ARIA's existing audit infrastructure.
    """
    
    async def log_skill_execution(
        self,
        execution: SkillExecution,
    ) -> str:
        """Log skill execution with full context."""
        
        # Get previous hash for chain
        previous = await self.get_latest_hash(execution.user_id)
        
        entry = SkillAuditEntry(
            id=str(uuid.uuid4()),
            timestamp=datetime.utcnow(),
            user_id=execution.user_id,
            tenant_id=execution.tenant_id,
            skill_id=execution.skill_id,
            skill_path=execution.skill_path,
            skill_trust_level=execution.trust_level.value,
            skill_version=execution.skill_version,
            task_id=execution.task_id,
            agent_id=execution.agent_id,
            trigger_reason=execution.trigger_reason,
            data_classes_requested=execution.data_requested,
            data_classes_granted=execution.data_granted,
            data_redacted=execution.data_redacted,
            tokens_used=list(execution.token_map.keys()),
            input_hash=self._hash_data(execution.sanitized_input),
            output_hash=self._hash_data(execution.output),
            execution_time_ms=execution.execution_time_ms,
            success=execution.success,
            error=execution.error,
            sandbox_config=asdict(execution.sandbox_config),
            security_flags=execution.security_flags,
            previous_hash=previous,
            entry_hash="",
        )
        
        entry.entry_hash = self._compute_hash(entry)
        
        # Store in audit_log table
        await self.db.table("skill_audit_log").insert(
            asdict(entry)
        ).execute()
        
        # Also log to main audit trail for unified view
        await self.main_audit.log_action(
            user_id=entry.user_id,
            action_type="skill_execution",
            action_params={
                "skill_id": entry.skill_id,
                "skill_path": entry.skill_path,
                "trust_level": entry.skill_trust_level,
            },
            result="success" if entry.success else "failure",
            result_details={"audit_entry_id": entry.id},
            risk_level=self._determine_risk_level(execution),
        )
        
        return entry.id
```

---

## Part 2: Integration with ARIA Core Systems

### 2.1 Skills + Agents Integration

Skills extend agent capabilities. Each agent has access to relevant skills:

```python
# backend/src/agents/skill_aware_agent.py

from src.agents.base import BaseAgent, AgentResult
from src.skills.orchestrator import SkillOrchestrator

class SkillAwareAgent(BaseAgent):
    """
    Base agent enhanced with skill capabilities.
    All ARIA agents should extend this class.
    """
    
    # Skills this agent type can use
    AGENT_SKILLS: dict[str, list[str]] = {
        "HunterAgent": [
            "competitor-analysis",
            "lead-research",
            "company-profiling",
        ],
        "AnalystAgent": [
            "clinical-trial-analysis",
            "pubmed-research",
            "data-visualization",
            "statistical-analysis",
        ],
        "StrategistAgent": [
            "market-analysis",
            "competitive-positioning",
            "pricing-strategy",
            "launch-strategy",
        ],
        "ScribeAgent": [
            "pdf",
            "docx",
            "pptx",
            "xlsx",
            "email-sequence",
            "copywriting",
        ],
        "OperatorAgent": [
            "calendar-management",
            "crm-operations",
            "workflow-automation",
        ],
        "ScoutAgent": [
            "regulatory-monitor",
            "news-aggregation",
            "signal-detection",
        ],
    }
    
    def __init__(self, llm_client, user_id: str, skill_orchestrator: SkillOrchestrator):
        super().__init__(llm_client, user_id)
        self.skills = skill_orchestrator
        self.available_skills = self._get_available_skills()
    
    def _get_available_skills(self) -> list[str]:
        """Get skills available to this agent type."""
        agent_type = self.__class__.__name__
        return self.AGENT_SKILLS.get(agent_type, [])
    
    async def execute_with_skills(self, task: dict) -> AgentResult:
        """
        Execute task, using skills when beneficial.
        This is the main entry point for skill-aware execution.
        """
        
        # 1. Analyze task to identify skill needs
        skill_analysis = await self._analyze_skill_needs(task)
        
        # 2. If skills needed, delegate to skill orchestrator
        if skill_analysis.skills_needed:
            return await self.skills.execute_with_skills(
                task=task,
                required_skills=skill_analysis.required_skills,
                optional_skills=skill_analysis.optional_skills,
                agent_context={
                    "agent_type": self.__class__.__name__,
                    "agent_id": self.agent_id,
                    "user_id": self.user_id,
                },
            )
        
        # 3. Otherwise, execute normally
        return await self.execute(task)
    
    async def _analyze_skill_needs(self, task: dict) -> SkillAnalysis:
        """
        Determine if this task would benefit from skills.
        Uses LLM to analyze task requirements.
        """
        
        # Build prompt with available skills
        skill_descriptions = await self.skills.get_skill_summaries(
            self.available_skills
        )
        
        prompt = f"""
        Analyze this task and determine which skills would help:
        
        Task: {task.get('description')}
        Goal: {task.get('goal')}
        Context: {task.get('context')}
        
        Available skills:
        {skill_descriptions}
        
        Return JSON:
        {{
            "skills_needed": true/false,
            "required_skills": [
                {{"skill_id": "...", "reason": "...", "critical": true/false}}
            ],
            "optional_skills": [
                {{"skill_id": "...", "reason": "...", "benefit": "..."}}
            ],
            "execution_approach": "sequential" | "parallel" | "hybrid"
        }}
        """
        
        result = await self.llm.generate(prompt)
        return SkillAnalysis.from_json(result)
```

### 2.2 Skills + Memory Integration

Skills can read from and write to ARIA's memory system:

```python
# backend/src/skills/memory_integration.py

class SkillMemoryBridge:
    """
    Connects skills to ARIA's six-type memory system.
    Enforces data classification on all memory access.
    """
    
    def __init__(
        self,
        memory_system: UnifiedMemoryManager,
        data_classifier: DataClassifier,
        skill_trust_level: SkillTrustLevel,
    ):
        self.memory = memory_system
        self.classifier = data_classifier
        self.trust_level = skill_trust_level
    
    async def get_context_for_skill(
        self,
        user_id: str,
        task: dict,
        skill_id: str,
    ) -> dict:
        """
        Gather relevant memory context for skill execution.
        Automatically classifies and sanitizes based on skill trust level.
        """
        
        context = {}
        
        # 1. Get relevant episodic memory (past events)
        episodes = await self.memory.query_episodes(
            user_id=user_id,
            query=task.get("description"),
            limit=5,
        )
        context["relevant_history"] = await self._sanitize_for_skill(
            episodes, "episodic"
        )
        
        # 2. Get relevant semantic facts
        facts = await self.memory.get_related_facts(
            user_id=user_id,
            entities=task.get("entities", []),
            topics=task.get("topics", []),
        )
        context["known_facts"] = await self._sanitize_for_skill(
            facts, "semantic"
        )
        
        # 3. Get relevant procedural knowledge (past successful workflows)
        procedures = await self.memory.get_relevant_procedures(
            user_id=user_id,
            task_type=task.get("type"),
        )
        context["recommended_approach"] = await self._sanitize_for_skill(
            procedures, "procedural"
        )
        
        # 4. Get user preferences (from Digital Twin)
        preferences = await self.memory.get_user_preferences(
            user_id=user_id,
            context=task.get("type"),
        )
        context["user_preferences"] = await self._sanitize_for_skill(
            preferences, "preferences"
        )
        
        return context
    
    async def store_skill_learnings(
        self,
        user_id: str,
        skill_execution: SkillExecution,
    ) -> None:
        """
        Store learnings from skill execution back to memory.
        This enables ARIA to learn and improve over time.
        """
        
        # Store as episode (what happened)
        await self.memory.store_episode(Episode(
            user_id=user_id,
            event_type="skill_execution",
            title=f"Executed {skill_execution.skill_id}",
            content=skill_execution.summary,
            occurred_at=datetime.utcnow(),
            recorded_at=datetime.utcnow(),
            context={
                "skill_id": skill_execution.skill_id,
                "task": skill_execution.task,
                "success": skill_execution.success,
            },
        ))
        
        # Extract and store any new facts learned
        if skill_execution.extracted_facts:
            for fact in skill_execution.extracted_facts:
                await self.memory.add_fact(SemanticFact(
                    user_id=user_id,
                    subject=fact["subject"],
                    predicate=fact["predicate"],
                    object=fact["object"],
                    confidence=0.75,  # Skill-extracted confidence
                    source=FactSource.SKILL_EXTRACTED,
                    valid_from=datetime.utcnow(),
                ))
        
        # Update procedural memory if execution was successful
        if skill_execution.success:
            await self.memory.record_successful_procedure(
                user_id=user_id,
                task_type=skill_execution.task.get("type"),
                skill_sequence=skill_execution.skills_used,
                outcome=skill_execution.outcome,
            )
    
    async def _sanitize_for_skill(
        self,
        data: any,
        data_type: str,
    ) -> any:
        """
        Classify and sanitize data based on skill trust level.
        """
        classified = await self.classifier.classify(
            data, 
            {"source": f"memory_{data_type}"}
        )
        
        allowed_classes = TRUST_DATA_ACCESS[self.trust_level]
        
        if classified.classification in allowed_classes:
            return data
        elif classified.can_be_tokenized:
            return await self._tokenize(data)
        else:
            return f"[REDACTED: {classified.classification.value}]"
```

### 2.3 Skills + OODA Loop Integration

Skills participate in ARIA's cognitive OODA loop:

```python
# backend/src/core/ooda_with_skills.py

class OODALoopWithSkills:
    """
    OODA Loop enhanced with skill awareness.
    Skills become tools available during the ACT phase.
    """
    
    async def observe(self, state: OODAState, context: dict) -> OODAState:
        """
        OBSERVE: Gather information.
        Skills can assist with information gathering.
        """
        observations = []
        
        # Standard observations
        observations.extend(await self._gather_memory_context(state, context))
        observations.extend(await self._gather_environment_context(state, context))
        
        # Skill-assisted observations (if relevant skills available)
        if self._needs_research(state):
            research_skills = ["pubmed-research", "clinical-trial-analysis", "news-aggregation"]
            available = await self.skills.filter_available(research_skills)
            
            if available:
                skill_observations = await self.skills.execute_for_observation(
                    skills=available,
                    query=state.goal.get("research_query"),
                    context=context,
                )
                observations.extend(skill_observations)
        
        state.observations = observations
        return state
    
    async def orient(self, state: OODAState) -> OODAState:
        """
        ORIENT: Analyze situation and identify options.
        Include skill capabilities in option generation.
        """
        
        # Analyze observations
        analysis = await self._analyze_observations(state.observations)
        
        # Identify which skills could help achieve the goal
        skill_options = await self.skills.identify_useful_skills(
            goal=state.goal,
            current_situation=analysis,
            available_skills=self.agent.available_skills,
        )
        
        state.orientation = {
            "analysis": analysis,
            "skill_options": skill_options,
            "constraints": await self._identify_constraints(state),
            "opportunities": await self._identify_opportunities(state, skill_options),
        }
        
        return state
    
    async def decide(self, state: OODAState) -> OODAState:
        """
        DECIDE: Select action, potentially involving skills.
        """
        
        # Generate action options
        options = await self._generate_options(state)
        
        # Evaluate each option (including skill-based options)
        scored_options = []
        for option in options:
            score = await self._evaluate_option(
                option=option,
                goal=state.goal,
                constraints=state.orientation["constraints"],
            )
            scored_options.append((option, score))
        
        # Select best option
        scored_options.sort(key=lambda x: x[1], reverse=True)
        best_option = scored_options[0][0]
        
        state.decision = {
            "selected_action": best_option,
            "alternatives_considered": len(options),
            "confidence": scored_options[0][1],
            "reasoning": await self._explain_decision(best_option, scored_options),
        }
        
        return state
    
    async def act(self, state: OODAState) -> OODAState:
        """
        ACT: Execute decision, using skills if indicated.
        """
        action = state.decision["selected_action"]
        
        if action.get("requires_skills"):
            # Execute via skill orchestrator
            result = await self.skills.execute_plan(
                plan=action["skill_plan"],
                context={
                    "goal": state.goal,
                    "ooda_state": state,
                },
                show_progress=True,  # ARIA shows her work
            )
        else:
            # Execute via standard agent action
            result = await self.agent.execute(action)
        
        state.action_result = result
        
        # Record outcome for learning
        await self.memory.record_action_outcome(
            goal_id=state.goal_id,
            action=action,
            result=result,
            iteration=state.iteration,
        )
        
        return state
```

### 2.4 Skills + Working Memory (Context Management)

The critical piece: how skills interact with ARIA's working memory to manage context:

```python
# backend/src/skills/context_management.py

class SkillContextManager:
    """
    Manages context for skill execution.
    Implements the patterns from Anthropic's context engineering guidance:
    - On-demand skill loading
    - Sub-agent isolation
    - Working memory for handoffs
    - Compaction when needed
    """
    
    # Context budget allocation
    ORCHESTRATOR_BUDGET = 2000    # Tokens for orchestrator context
    SKILL_INDEX_BUDGET = 600      # Tokens for skill index
    WORKING_MEMORY_BUDGET = 800   # Tokens for working memory/handoffs
    SKILL_EXECUTION_BUDGET = 6000 # Tokens per skill execution
    
    async def prepare_orchestrator_context(
        self,
        user_id: str,
        task: dict,
        plan: ExecutionPlan,
    ) -> str:
        """
        Prepare minimal context for the orchestrator.
        The orchestrator sees the plan but not full skill instructions.
        """
        
        context_parts = []
        
        # 1. Compact skill index (names + 20-word descriptions)
        skill_index = await self._build_skill_index(plan.skills_needed)
        context_parts.append(f"<available_skills>\n{skill_index}\n</available_skills>")
        
        # 2. Current plan state
        plan_summary = self._summarize_plan(plan)
        context_parts.append(f"<execution_plan>\n{plan_summary}\n</execution_plan>")
        
        # 3. Working memory (summaries from completed steps)
        if plan.completed_steps:
            working_memory = self._build_working_memory(plan.completed_steps)
            context_parts.append(f"<working_memory>\n{working_memory}\n</working_memory>")
        
        # 4. Key user context (minimal)
        user_context = await self._get_essential_user_context(user_id)
        context_parts.append(f"<user_context>\n{user_context}\n</user_context>")
        
        return "\n\n".join(context_parts)
    
    async def prepare_subagent_context(
        self,
        skill_id: str,
        task_briefing: dict,
        input_data: dict,
    ) -> str:
        """
        Prepare ISOLATED context for sub-agent skill execution.
        Sub-agent gets fresh context with ONLY:
        - Task briefing from orchestrator
        - Full skill instructions
        - Sanitized input data
        """
        
        context_parts = []
        
        # 1. Task briefing (what to do)
        briefing = self._format_briefing(task_briefing)
        context_parts.append(f"<task>\n{briefing}\n</task>")
        
        # 2. Full skill instructions (loaded on-demand)
        skill_content = await self.skill_index.get_full_skill(skill_id)
        context_parts.append(f"<skill_instructions>\n{skill_content}\n</skill_instructions>")
        
        # 3. Sanitized input data
        safe_input = self._format_input(input_data)
        context_parts.append(f"<input_data>\n{safe_input}\n</input_data>")
        
        # 4. Output format specification
        output_spec = await self._get_output_spec(skill_id)
        context_parts.append(f"<output_format>\n{output_spec}\n</output_format>")
        
        return "\n\n".join(context_parts)
    
    async def build_working_memory_entry(
        self,
        skill_execution: SkillExecution,
    ) -> dict:
        """
        Build working memory entry from skill execution.
        This is what gets passed to subsequent skills.
        """
        
        # Get skill's declared summary verbosity
        verbosity = await self.skill_index.get_summary_verbosity(
            skill_execution.skill_id
        )
        
        if verbosity == "minimal":
            max_tokens = 300
        elif verbosity == "standard":
            max_tokens = 800
        elif verbosity == "detailed":
            max_tokens = 1500
        else:
            max_tokens = 500
        
        # Generate summary at appropriate verbosity
        summary = await self._generate_summary(
            execution=skill_execution,
            max_tokens=max_tokens,
        )
        
        return {
            "step": skill_execution.step_number,
            "skill_id": skill_execution.skill_id,
            "status": "complete" if skill_execution.success else "failed",
            "summary": summary,
            "artifacts": skill_execution.artifact_paths,
            "extracted_facts": skill_execution.extracted_facts,
            "next_step_hints": skill_execution.next_step_hints,
        }
    
    async def compact_if_needed(
        self,
        current_context: str,
        threshold: float = 0.75,
    ) -> str:
        """
        Compact context if approaching limits.
        Uses structured summarization to preserve key information.
        """
        
        current_tokens = self._count_tokens(current_context)
        max_tokens = self._get_context_limit()
        
        if current_tokens / max_tokens < threshold:
            return current_context  # No compaction needed
        
        # Compact using structured summarization
        compacted = await self._structured_compact(
            context=current_context,
            preserve_sections=["current_step", "artifacts", "key_decisions"],
            summarize_sections=["completed_steps", "observations"],
        )
        
        return compacted
```

---

## Part 3: Skill Orchestration Engine

### 3.1 The Orchestrator

The brain that coordinates multi-skill execution:

```python
# backend/src/skills/orchestrator.py

class SkillOrchestrator:
    """
    Orchestrates multi-skill task execution.
    
    Key responsibilities:
    1. Plan execution (build DAG of skill dependencies)
    2. Execute with parallelization where possible
    3. Manage context across skill executions
    4. Handle failures and retries
    5. Report progress transparently
    """
    
    def __init__(
        self,
        skill_index: SkillIndex,
        context_manager: SkillContextManager,
        security: SkillSecurityService,
        memory: SkillMemoryBridge,
        audit: SkillAuditService,
    ):
        self.index = skill_index
        self.context = context_manager
        self.security = security
        self.memory = memory
        self.audit = audit
    
    async def execute_task(
        self,
        user_id: str,
        task: dict,
        show_progress: bool = True,
    ) -> OrchestrationResult:
        """
        Main entry point for skill-based task execution.
        """
        
        # PHASE 1: PLANNING (Always visible to user)
        plan = await self._create_execution_plan(user_id, task)
        
        if show_progress:
            await self._emit_progress(
                "plan_created",
                plan.to_user_display(),
            )
        
        # Check if approval needed
        if await self._needs_approval(user_id, plan):
            approval = await self._request_approval(user_id, plan)
            if not approval.approved:
                return OrchestrationResult(
                    success=False,
                    message="Execution cancelled by user",
                )
        
        # PHASE 2: EXECUTION
        try:
            result = await self._execute_plan(user_id, plan, show_progress)
        except Exception as e:
            await self.audit.log_failure(user_id, plan, e)
            raise
        
        # PHASE 3: SYNTHESIS
        synthesis = await self._synthesize_results(result)
        
        # Store learnings
        await self.memory.store_skill_learnings(user_id, result)
        
        return OrchestrationResult(
            success=True,
            plan=plan,
            execution_result=result,
            synthesis=synthesis,
        )
    
    async def _create_execution_plan(
        self,
        user_id: str,
        task: dict,
    ) -> ExecutionPlan:
        """
        Create execution plan with dependency DAG.
        Identifies parallel vs sequential execution opportunities.
        """
        
        # Identify required skills
        skill_analysis = await self._analyze_required_skills(task)
        
        # Build dependency graph
        dependencies = await self._build_dependency_graph(
            skill_analysis.required_skills
        )
        
        # Identify parallelization opportunities
        parallel_groups = self._identify_parallel_groups(dependencies)
        
        # Estimate costs and timing
        estimates = await self._estimate_execution(
            skill_analysis.required_skills,
            parallel_groups,
        )
        
        return ExecutionPlan(
            task=task,
            skills_needed=skill_analysis.required_skills,
            dependencies=dependencies,
            parallel_groups=parallel_groups,
            estimated_duration=estimates.duration,
            estimated_cost=estimates.cost,
            risk_level=estimates.risk_level,
        )
    
    async def _execute_plan(
        self,
        user_id: str,
        plan: ExecutionPlan,
        show_progress: bool,
    ) -> ExecutionResult:
        """
        Execute plan respecting dependencies.
        Parallel execution for independent steps.
        """
        
        completed_steps = {}
        working_memory = {}
        
        for group in plan.parallel_groups:
            if show_progress:
                await self._emit_progress(
                    "group_starting",
                    {"steps": [s.skill_id for s in group.steps]},
                )
            
            # Execute group (parallel or sequential based on group type)
            if group.can_parallelize:
                results = await asyncio.gather(*[
                    self._execute_step(
                        user_id=user_id,
                        step=step,
                        working_memory=working_memory,
                        show_progress=show_progress,
                    )
                    for step in group.steps
                ])
            else:
                results = []
                for step in group.steps:
                    result = await self._execute_step(
                        user_id=user_id,
                        step=step,
                        working_memory=working_memory,
                        show_progress=show_progress,
                    )
                    results.append(result)
                    
                    # Update working memory for next step
                    working_memory[step.step_id] = await self.context.build_working_memory_entry(result)
            
            # Record completed steps
            for step, result in zip(group.steps, results):
                completed_steps[step.step_id] = result
                working_memory[step.step_id] = await self.context.build_working_memory_entry(result)
        
        return ExecutionResult(
            plan=plan,
            completed_steps=completed_steps,
            working_memory=working_memory,
            total_duration=sum(r.execution_time_ms for r in completed_steps.values()),
            success=all(r.success for r in completed_steps.values()),
        )
    
    async def _execute_step(
        self,
        user_id: str,
        step: ExecutionStep,
        working_memory: dict,
        show_progress: bool,
    ) -> SkillExecution:
        """
        Execute single skill step as isolated sub-agent.
        """
        
        if show_progress:
            await self._emit_progress(
                "step_starting",
                {"step_id": step.step_id, "skill_id": step.skill_id},
            )
        
        # 1. Get skill details and trust level
        skill = await self.index.get_skill(step.skill_id)
        trust_level = self._determine_trust_level(skill)
        
        # 2. Prepare input (get from working memory + sanitize)
        input_data = await self._prepare_step_input(step, working_memory)
        sanitized_input = await self.security.sanitize_for_skill(
            input_data,
            trust_level,
        )
        
        # 3. Build isolated sub-agent context
        subagent_context = await self.context.prepare_subagent_context(
            skill_id=step.skill_id,
            task_briefing=step.briefing,
            input_data=sanitized_input,
        )
        
        # 4. Execute in sandbox
        sandbox_config = SANDBOX_BY_TRUST[trust_level]
        start_time = time.time()
        
        try:
            raw_result = await self.sandbox.execute(
                skill_content=skill.content,
                input_data=sanitized_input,
                context=subagent_context,
                config=sandbox_config,
            )
            success = True
            error = None
        except Exception as e:
            raw_result = None
            success = False
            error = str(e)
        
        execution_time = int((time.time() - start_time) * 1000)
        
        # 5. Validate output (check for data leakage)
        if success:
            validated_result = await self.security.validate_output(
                raw_result,
                sanitized_input.token_map,
            )
        else:
            validated_result = None
        
        # 6. Build execution record
        execution = SkillExecution(
            skill_id=step.skill_id,
            step_number=step.step_number,
            trust_level=trust_level,
            input_data=sanitized_input.data,
            token_map=sanitized_input.token_map,
            result=validated_result,
            success=success,
            error=error,
            execution_time_ms=execution_time,
            artifacts=self._extract_artifacts(validated_result),
            extracted_facts=self._extract_facts(validated_result),
        )
        
        # 7. Audit log
        await self.audit.log_skill_execution(execution)
        
        if show_progress:
            status = "complete" if success else "failed"
            await self._emit_progress(
                f"step_{status}",
                {"step_id": step.step_id, "summary": execution.summary},
            )
        
        return execution
```

### 3.2 Progress Reporting (Transparency)

ARIA always shows her work:

```python
# backend/src/skills/progress.py

class SkillProgressReporter:
    """
    Reports skill execution progress to user.
    Implements the "ARIA shows her work" principle.
    """
    
    async def emit(
        self,
        user_id: str,
        event_type: str,
        data: dict,
    ) -> None:
        """
        Emit progress event via WebSocket.
        """
        
        message = self._format_progress_message(event_type, data)
        
        await self.websocket.send(
            user_id=user_id,
            channel="skill_progress",
            message=message,
        )
    
    def _format_progress_message(
        self,
        event_type: str,
        data: dict,
    ) -> dict:
        """
        Format progress for user display.
        """
        
        if event_type == "plan_created":
            return {
                "type": "plan",
                "message": "I'll need to use these skills:",
                "steps": [
                    {
                        "step": s["step"],
                        "skill": s["skill_id"],
                        "description": s["description"],
                        "can_parallelize": s.get("parallel_with", []),
                    }
                    for s in data["steps"]
                ],
                "estimated_time": data["estimated_duration"],
                "requires_approval": data.get("requires_approval", False),
            }
        
        elif event_type == "step_starting":
            return {
                "type": "progress",
                "step": data["step_id"],
                "skill": data["skill_id"],
                "status": "running",
                "message": f"Running {data['skill_id']}...",
            }
        
        elif event_type == "step_complete":
            return {
                "type": "progress",
                "step": data["step_id"],
                "skill": data["skill_id"],
                "status": "complete",
                "summary": data["summary"],
            }
        
        elif event_type == "step_failed":
            return {
                "type": "progress",
                "step": data["step_id"],
                "skill": data["skill_id"],
                "status": "failed",
                "error": data["error"],
                "can_retry": data.get("can_retry", False),
            }
        
        elif event_type == "synthesis":
            return {
                "type": "complete",
                "message": data["summary"],
                "artifacts": data["artifacts"],
                "next_steps": data.get("suggested_next_steps", []),
            }
```

---

## Part 4: Autonomy & Trust System

### 4.1 Graduated Autonomy

Trust builds over time based on outcomes:

```python
# backend/src/skills/autonomy.py

class SkillAutonomyService:
    """
    Manages ARIA's autonomy around skill operations.
    Trust builds over time based on successful executions.
    """
    
    # Risk levels for skill operations
    SKILL_RISK_LEVELS = {
        "LOW": {
            "examples": ["pdf", "docx", "xlsx", "pptx", "research"],
            "initial_approval_required": True,
            "auto_execute_after": 3,  # successful uses
        },
        "MEDIUM": {
            "examples": ["email-sequence", "calendar-management", "crm-operations"],
            "initial_approval_required": True,
            "auto_execute_after": 10,
        },
        "HIGH": {
            "examples": ["external-api-calls", "payment-processing"],
            "initial_approval_required": True,
            "auto_execute_after": None,  # Always ask, but can "trust for session"
        },
        "CRITICAL": {
            "examples": ["data-deletion", "financial-transactions"],
            "initial_approval_required": True,
            "auto_execute_after": None,  # Always ask, no session trust
        },
    }
    
    async def should_request_approval(
        self,
        user_id: str,
        skill_id: str,
        plan: ExecutionPlan,
    ) -> tuple[bool, str]:
        """
        Determine if approval is needed for this skill execution.
        Returns (needs_approval, reason).
        """
        
        # Get skill's risk level
        risk_level = await self._get_skill_risk_level(skill_id)
        risk_config = self.SKILL_RISK_LEVELS[risk_level]
        
        # Critical always needs approval
        if risk_level == "CRITICAL":
            return True, "This operation requires explicit approval"
        
        # Check user's trust history with this skill
        trust_history = await self._get_trust_history(user_id, skill_id)
        
        # High risk: check for session trust
        if risk_level == "HIGH":
            if trust_history.session_trust_granted:
                return False, "Session trust granted"
            return True, "High-risk operation requires approval"
        
        # Medium/Low risk: check execution count
        threshold = risk_config["auto_execute_after"]
        if threshold and trust_history.successful_executions >= threshold:
            return False, f"Auto-approved after {threshold} successful uses"
        
        # Check if user has globally approved this skill
        if trust_history.globally_approved:
            return False, "User has globally approved this skill"
        
        return True, "Initial approval required"
    
    async def record_execution_outcome(
        self,
        user_id: str,
        skill_id: str,
        success: bool,
        user_feedback: Optional[str] = None,
    ) -> None:
        """
        Record outcome to build/reduce trust.
        Negative outcomes reset trust.
        """
        
        history = await self._get_trust_history(user_id, skill_id)
        
        if success and user_feedback != "negative":
            history.successful_executions += 1
            history.last_success = datetime.utcnow()
        else:
            # Negative outcome resets trust
            history.successful_executions = 0
            history.session_trust_granted = False
            history.globally_approved = False
        
        await self._save_trust_history(user_id, skill_id, history)
    
    async def request_autonomy_upgrade(
        self,
        user_id: str,
        skill_id: str,
    ) -> dict:
        """
        ARIA can request increased autonomy after good track record.
        """
        
        history = await self._get_trust_history(user_id, skill_id)
        
        if history.successful_executions >= 10:
            return {
                "can_request": True,
                "message": f"I've successfully used {skill_id} {history.successful_executions} times "
                          f"without issues. Would you like me to handle this automatically in the future?",
                "options": [
                    {"id": "session", "label": "Yes, for this session"},
                    {"id": "always", "label": "Yes, always"},
                    {"id": "no", "label": "No, keep asking"},
                ],
            }
        
        return {"can_request": False}
```

---

## Part 5: Database Schema

### 5.1 New Tables for Skills

```sql
-- Skill index cache (synced from skills.sh)
CREATE TABLE skills_index (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    skill_path TEXT NOT NULL UNIQUE,        -- "anthropics/skills/pdf"
    skill_name TEXT NOT NULL,               -- "pdf"
    description TEXT,                        -- 20-word summary
    full_content TEXT,                       -- Full SKILL.md (loaded on-demand)
    content_hash TEXT,                       -- SHA256 for integrity
    author TEXT,
    version TEXT,
    tags TEXT[],
    install_count INT DEFAULT 0,
    trust_level TEXT DEFAULT 'community',   -- core, verified, community, user
    security_verified BOOLEAN DEFAULT FALSE,
    life_sciences_relevant BOOLEAN DEFAULT FALSE,
    declared_permissions TEXT[],             -- What skill declares it needs
    summary_verbosity TEXT DEFAULT 'standard', -- minimal, standard, detailed
    last_synced TIMESTAMPTZ DEFAULT NOW(),
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- User skill installations
CREATE TABLE user_skills (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID REFERENCES auth.users(id) NOT NULL,
    tenant_id UUID REFERENCES tenants(id) NOT NULL,
    skill_id TEXT NOT NULL,                  -- References skills_index.skill_name
    skill_path TEXT NOT NULL,                -- Full path for audit
    trust_level TEXT NOT NULL,               -- Trust level at install time
    permissions_granted TEXT[],              -- What user approved
    installed_at TIMESTAMPTZ DEFAULT NOW(),
    installed_by UUID REFERENCES auth.users(id),
    auto_installed BOOLEAN DEFAULT FALSE,    -- Was this auto-installed?
    last_used_at TIMESTAMPTZ,
    execution_count INT DEFAULT 0,
    success_count INT DEFAULT 0,
    UNIQUE(user_id, skill_id)
);

-- User trust history per skill
CREATE TABLE skill_trust_history (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID REFERENCES auth.users(id) NOT NULL,
    skill_id TEXT NOT NULL,
    successful_executions INT DEFAULT 0,
    failed_executions INT DEFAULT 0,
    last_success TIMESTAMPTZ,
    last_failure TIMESTAMPTZ,
    session_trust_granted BOOLEAN DEFAULT FALSE,
    session_trust_expires TIMESTAMPTZ,
    globally_approved BOOLEAN DEFAULT FALSE,
    globally_approved_at TIMESTAMPTZ,
    trust_reset_count INT DEFAULT 0,         -- How many times trust was reset
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(user_id, skill_id)
);

-- Custom skills (user/tenant created)
CREATE TABLE custom_skills (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID REFERENCES tenants(id) NOT NULL,
    skill_name TEXT NOT NULL,
    skill_description TEXT NOT NULL,
    skill_content TEXT NOT NULL,             -- Full SKILL.md
    content_hash TEXT NOT NULL,
    tags TEXT[],
    declared_permissions TEXT[],
    summary_verbosity TEXT DEFAULT 'standard',
    created_by UUID REFERENCES auth.users(id) NOT NULL,
    is_published BOOLEAN DEFAULT FALSE,      -- Published to skills.sh?
    github_repo TEXT,                        -- If published
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(tenant_id, skill_name)
);

-- Skill execution audit log (immutable)
CREATE TABLE skill_audit_log (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    timestamp TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    user_id UUID REFERENCES auth.users(id) NOT NULL,
    tenant_id UUID REFERENCES tenants(id) NOT NULL,
    
    -- Skill identification
    skill_id TEXT NOT NULL,
    skill_path TEXT NOT NULL,
    skill_trust_level TEXT NOT NULL,
    skill_version TEXT,
    
    -- Execution context
    task_id UUID,                            -- Links to goals/tasks
    agent_id TEXT,                           -- Which agent invoked
    trigger_reason TEXT,                     -- Why was skill used
    
    -- Data access (critical for compliance)
    data_classes_requested TEXT[],
    data_classes_granted TEXT[],
    data_redacted BOOLEAN DEFAULT FALSE,
    tokens_used TEXT[],                      -- Tokenization tokens used
    
    -- Execution details
    input_hash TEXT NOT NULL,                -- SHA256 of sanitized input
    output_hash TEXT,                        -- SHA256 of output
    execution_time_ms INT,
    success BOOLEAN NOT NULL,
    error TEXT,
    
    -- Sandbox config used
    sandbox_config JSONB,
    
    -- Security
    security_flags TEXT[],                   -- Any security events
    
    -- Chain integrity
    previous_hash TEXT NOT NULL,
    entry_hash TEXT NOT NULL
);

-- Execution plans (for multi-skill tasks)
CREATE TABLE skill_execution_plans (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID REFERENCES auth.users(id) NOT NULL,
    tenant_id UUID REFERENCES tenants(id) NOT NULL,
    task_description TEXT NOT NULL,
    skills_planned TEXT[] NOT NULL,
    dependency_graph JSONB NOT NULL,
    parallel_groups JSONB NOT NULL,
    estimated_duration_ms INT,
    estimated_cost_level TEXT,               -- low, medium, high
    risk_level TEXT NOT NULL,
    approval_required BOOLEAN DEFAULT FALSE,
    approval_status TEXT,                    -- pending, approved, rejected
    approved_by UUID REFERENCES auth.users(id),
    approved_at TIMESTAMPTZ,
    execution_started_at TIMESTAMPTZ,
    execution_completed_at TIMESTAMPTZ,
    success BOOLEAN,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Working memory for skill handoffs
CREATE TABLE skill_working_memory (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    plan_id UUID REFERENCES skill_execution_plans(id) NOT NULL,
    step_number INT NOT NULL,
    skill_id TEXT NOT NULL,
    status TEXT NOT NULL,                    -- pending, running, complete, failed
    summary TEXT,                            -- Summary for next step
    artifacts JSONB,                         -- File paths, etc.
    extracted_facts JSONB,                   -- Facts learned
    next_step_hints JSONB,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(plan_id, step_number)
);

-- RLS Policies
ALTER TABLE skills_index ENABLE ROW LEVEL SECURITY;
ALTER TABLE user_skills ENABLE ROW LEVEL SECURITY;
ALTER TABLE skill_trust_history ENABLE ROW LEVEL SECURITY;
ALTER TABLE custom_skills ENABLE ROW LEVEL SECURITY;
ALTER TABLE skill_audit_log ENABLE ROW LEVEL SECURITY;
ALTER TABLE skill_execution_plans ENABLE ROW LEVEL SECURITY;
ALTER TABLE skill_working_memory ENABLE ROW LEVEL SECURITY;

-- Skills index is readable by all authenticated users
CREATE POLICY "skills_index_read" ON skills_index
    FOR SELECT TO authenticated USING (true);

-- User skills: users can only see/manage their own
CREATE POLICY "user_skills_own" ON user_skills
    FOR ALL TO authenticated
    USING (user_id = auth.uid());

-- Trust history: users can only see their own
CREATE POLICY "trust_history_own" ON skill_trust_history
    FOR ALL TO authenticated
    USING (user_id = auth.uid());

-- Custom skills: tenant isolation
CREATE POLICY "custom_skills_tenant" ON custom_skills
    FOR ALL TO authenticated
    USING (tenant_id = (SELECT tenant_id FROM users WHERE id = auth.uid()));

-- Audit log: read-only, own records only
CREATE POLICY "audit_log_read_own" ON skill_audit_log
    FOR SELECT TO authenticated
    USING (user_id = auth.uid());

-- Execution plans: own records only
CREATE POLICY "plans_own" ON skill_execution_plans
    FOR ALL TO authenticated
    USING (user_id = auth.uid());

-- Working memory: access via plan ownership
CREATE POLICY "working_memory_via_plan" ON skill_working_memory
    FOR ALL TO authenticated
    USING (
        plan_id IN (
            SELECT id FROM skill_execution_plans WHERE user_id = auth.uid()
        )
    );
```

---

## Part 6: API Endpoints

```python
# backend/src/api/routes/skills.py

from fastapi import APIRouter, Depends, HTTPException
from src.auth.dependencies import get_current_user
from src.skills.orchestrator import SkillOrchestrator

router = APIRouter(prefix="/skills", tags=["skills"])


@router.get("/available")
async def get_available_skills(
    category: Optional[str] = None,
    life_sciences_only: bool = False,
    user: User = Depends(get_current_user),
):
    """Get skills available to user (installed + recommended)."""
    pass


@router.get("/index")
async def get_skill_index(
    user: User = Depends(get_current_user),
):
    """Get compact skill index for context."""
    pass


@router.get("/{skill_id}")
async def get_skill_details(
    skill_id: str,
    user: User = Depends(get_current_user),
):
    """Get full skill details (for viewing, not execution)."""
    pass


@router.post("/install")
async def install_skill(
    request: InstallSkillRequest,
    user: User = Depends(get_current_user),
):
    """Install a skill from skills.sh."""
    pass


@router.delete("/{skill_id}")
async def uninstall_skill(
    skill_id: str,
    user: User = Depends(get_current_user),
):
    """Uninstall a skill."""
    pass


@router.post("/execute")
async def execute_skill_task(
    request: ExecuteSkillTaskRequest,
    user: User = Depends(get_current_user),
):
    """Execute a task using skills (creates execution plan)."""
    pass


@router.get("/plans/{plan_id}")
async def get_execution_plan(
    plan_id: str,
    user: User = Depends(get_current_user),
):
    """Get execution plan details."""
    pass


@router.post("/plans/{plan_id}/approve")
async def approve_execution_plan(
    plan_id: str,
    user: User = Depends(get_current_user),
):
    """Approve an execution plan."""
    pass


@router.get("/audit")
async def get_skill_audit_log(
    skill_id: Optional[str] = None,
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None,
    user: User = Depends(get_current_user),
):
    """Get skill execution audit log."""
    pass


@router.post("/custom")
async def create_custom_skill(
    request: CreateCustomSkillRequest,
    user: User = Depends(get_current_user),
):
    """Create a custom skill for this tenant."""
    pass


@router.post("/custom/{skill_id}/publish")
async def publish_custom_skill(
    skill_id: str,
    user: User = Depends(get_current_user),
):
    """Publish custom skill to skills.sh."""
    pass


@router.get("/autonomy/{skill_id}")
async def get_skill_autonomy(
    skill_id: str,
    user: User = Depends(get_current_user),
):
    """Get autonomy level for a skill."""
    pass


@router.post("/autonomy/{skill_id}/upgrade")
async def request_autonomy_upgrade(
    skill_id: str,
    upgrade_type: str,  # "session" or "always"
    user: User = Depends(get_current_user),
):
    """Grant increased autonomy for a skill."""
    pass
```

---

## Part 7: Implementation Phases

### Phase A: Security Foundation (Week 1)
- [ ] Data classification system
- [ ] Trust level framework
- [ ] Sanitization pipeline
- [ ] Skill sandbox implementation
- [ ] Audit log schema and service

### Phase B: Core Integration (Week 2)
- [ ] Skill index sync from skills.sh
- [ ] Skills database schema
- [ ] Skill context manager
- [ ] Memory bridge
- [ ] Basic skill execution

### Phase C: Orchestration (Week 3)
- [ ] Execution plan builder
- [ ] Dependency DAG
- [ ] Parallel execution
- [ ] Working memory handoffs
- [ ] Progress reporting WebSocket

### Phase D: Agent Integration (Week 4)
- [ ] SkillAwareAgent base class
- [ ] Update all 6 agents to extend SkillAwareAgent
- [ ] OODA loop skill integration
- [ ] Agent-skill mapping

### Phase E: Autonomy & Polish (Week 5)
- [ ] Trust history tracking
- [ ] Graduated autonomy
- [ ] Autonomy upgrade requests
- [ ] Custom skill creation
- [ ] UI components

---

## Part 8: Success Metrics

| Metric | Target | Measurement |
|--------|--------|-------------|
| **Security** | | |
| Data leakage incidents | 0 | Audit log review |
| Unauthorized data access | 0 | Security event log |
| Audit log completeness | 100% | All executions logged |
| **Performance** | | |
| Skill execution <30s | 95% | P95 latency |
| Context overhead | <3000 tokens | Orchestrator context size |
| **Adoption** | | |
| Skills per user | 5+ | Average installed |
| Auto-approval rate | 80% | After trust established |
| Task completion with skills | +25% | Before/after comparison |
| **Quality** | | |
| Skill execution success | >90% | Success rate |
| User satisfaction | >4.5/5 | Post-execution feedback |

---

*Document Version: 2.0*  
*Created: February 4, 2026*  
*Author: ARIA Architecture Team*
