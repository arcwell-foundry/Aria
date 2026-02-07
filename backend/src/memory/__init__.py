"""Six-type memory system for ARIA.

This module implements ARIA's cognitive memory architecture:
- Working: Current conversation context (in-memory, session only)
- Episodic: Past events and interactions (Graphiti)
- Semantic: Facts and knowledge (Graphiti + pgvector)
- Procedural: Learned workflows (Supabase)
- Prospective: Future tasks/reminders (Supabase)
- Lead: Sales pursuit tracking (Graphiti + Supabase)
- Digital Twin: User writing style fingerprinting (Graphiti)
- Corporate: Company-level shared knowledge (Graphiti + Supabase)
"""

from src.memory.audit import (
    AuditLogEntry,
    MemoryAuditLogger,
    MemoryOperation,
    MemoryType,
    log_memory_operation,
)
from src.memory.confidence import ConfidenceScorer
from src.memory.conversation import ConversationEpisode, ConversationService
from src.memory.conversation_intelligence import ConversationIntelligence, Insight
from src.memory.corporate import (
    CORPORATE_SOURCE_CONFIDENCE,
    CorporateFact,
    CorporateFactSource,
    CorporateMemory,
)
from src.memory.delta_presenter import (
    CorrectionRequest,
    MemoryDelta,
    MemoryDeltaPresenter,
    MemoryFact,
)
from src.memory.digital_twin import (
    DigitalTwin,
    TextStyleAnalyzer,
    WritingStyleFingerprint,
)
from src.memory.episodic import Episode, EpisodicMemory
from src.memory.health_score import (
    HealthScoreCalculator,
    HealthScoreHistory,
)
from src.memory.lead_memory import (
    LeadMemory,
    LeadMemoryService,
    LeadStatus,
    LifecycleStage,
)
from src.memory.lead_memory import (
    TriggerType as LeadTriggerType,
)
from src.memory.lead_memory_events import LeadEvent, LeadEventService
from src.memory.lead_memory_graph import (
    LeadMemoryGraph,
    LeadMemoryNode,
    LeadRelationshipType,
)
from src.memory.lead_patterns import (
    ClosingTimePattern,
    EngagementPattern,
    LeadPatternDetector,
    LeadWarning,
    ObjectionPattern,
    SilentLead,
)
from src.memory.lead_triggers import LeadTriggerService
from src.memory.retroactive_enrichment import (
    EnrichmentResult,
    EnrichmentTrigger,
    RetroactiveEnrichmentService,
)
from src.memory.priming import ConversationContext, ConversationPrimingService
from src.memory.procedural import ProceduralMemory, Workflow
from src.memory.prospective import (
    ProspectiveMemory,
    ProspectiveTask,
    TaskPriority,
    TaskStatus,
    TriggerType,
)
from src.memory.salience import SalienceService
from src.memory.semantic import FactSource, SemanticFact, SemanticMemory
from src.memory.working import (
    WorkingMemory,
    WorkingMemoryManager,
    count_tokens,
)
from src.models.lead_memory import Direction, EventType

__all__ = [
    # Memory Audit
    "AuditLogEntry",
    "MemoryAuditLogger",
    "MemoryOperation",
    "MemoryType",
    "log_memory_operation",
    # Confidence Scoring
    "ConfidenceScorer",
    # Memory Delta Presenter
    "CorrectionRequest",
    "MemoryDelta",
    "MemoryDeltaPresenter",
    "MemoryFact",
    # Salience Service
    "SalienceService",
    # Working Memory
    "WorkingMemory",
    "WorkingMemoryManager",
    "count_tokens",
    # Episodic Memory
    "Episode",
    "EpisodicMemory",
    # Semantic Memory
    "FactSource",
    "SemanticFact",
    "SemanticMemory",
    # Procedural Memory
    "ProceduralMemory",
    "Workflow",
    # Prospective Memory
    "ProspectiveMemory",
    "ProspectiveTask",
    "TriggerType",
    "TaskStatus",
    "TaskPriority",
    # Digital Twin
    "DigitalTwin",
    "TextStyleAnalyzer",
    "WritingStyleFingerprint",
    # Corporate Memory
    "CorporateFact",
    "CorporateFactSource",
    "CorporateMemory",
    "CORPORATE_SOURCE_CONFIDENCE",
    # Conversation Episodes
    "ConversationEpisode",
    "ConversationService",
    # Conversation Priming
    "ConversationContext",
    "ConversationPrimingService",
    # Lead Memory
    "LeadMemory",
    "LeadMemoryService",
    "LeadStatus",
    "LifecycleStage",
    "LeadTriggerType",
    "LeadTriggerService",
    # Lead Memory Events
    "LeadEvent",
    "LeadEventService",
    "EventType",
    "Direction",
    # Lead Memory Graph
    "LeadMemoryGraph",
    "LeadMemoryNode",
    "LeadRelationshipType",
    # Health Score
    "HealthScoreCalculator",
    "HealthScoreHistory",
    # Conversation Intelligence
    "ConversationIntelligence",
    "Insight",
    # Lead Pattern Detection
    "LeadPatternDetector",
    "ClosingTimePattern",
    "ObjectionPattern",
    "EngagementPattern",
    "SilentLead",
    "LeadWarning",
    # Retroactive Enrichment (US-923)
    "RetroactiveEnrichmentService",
    "EnrichmentResult",
    "EnrichmentTrigger",
]
