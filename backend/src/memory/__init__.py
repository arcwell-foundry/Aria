"""Six-type memory system for ARIA.

This module implements ARIA's cognitive memory architecture:
- Working: Current conversation context (in-memory, session only)
- Episodic: Past events and interactions (Graphiti)
- Semantic: Facts and knowledge (Graphiti + pgvector)
- Procedural: Learned workflows (Supabase)
- Prospective: Future tasks/reminders (Supabase)
- Lead: Sales pursuit tracking (Graphiti + Supabase)
- Digital Twin: User writing style fingerprinting (Graphiti)
"""

from src.memory.digital_twin import (
    DigitalTwin,
    TextStyleAnalyzer,
    WritingStyleFingerprint,
)
from src.memory.episodic import Episode, EpisodicMemory
from src.memory.procedural import ProceduralMemory, Workflow
from src.memory.prospective import (
    ProspectiveMemory,
    ProspectiveTask,
    TaskPriority,
    TaskStatus,
    TriggerType,
)
from src.memory.semantic import FactSource, SemanticFact, SemanticMemory
from src.memory.working import (
    WorkingMemory,
    WorkingMemoryManager,
    count_tokens,
)

__all__ = [
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
]
