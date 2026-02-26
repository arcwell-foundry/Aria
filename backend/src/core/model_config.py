from dataclasses import dataclass
from typing import Optional
from src.core.task_types import TaskType

@dataclass
class ModelConfig:
    model: str
    max_tokens: int = 4096
    temperature: float = 0.7
    timeout: int = 60
    fallback: Optional[str] = None

CLAUDE_SONNET = "anthropic/claude-sonnet-4-20250514"
CLAUDE_HAIKU = "anthropic/claude-haiku-4-5-20251001"

MODEL_ROUTES: dict[TaskType, ModelConfig] = {
    TaskType.CHAT_RESPONSE:         ModelConfig(CLAUDE_SONNET, max_tokens=4096, temperature=0.7),
    TaskType.CHAT_STREAM:           ModelConfig(CLAUDE_SONNET, max_tokens=4096, temperature=0.7),
    TaskType.SCRIBE_DRAFT_EMAIL:    ModelConfig(CLAUDE_SONNET, max_tokens=2048, temperature=0.6),
    TaskType.STRATEGIST_PLAN:       ModelConfig(CLAUDE_SONNET, max_tokens=4096, temperature=0.5),
    TaskType.STRATEGIST_BATTLECARD: ModelConfig(CLAUDE_SONNET, max_tokens=4096, temperature=0.5),
    TaskType.ANALYST_RESEARCH:      ModelConfig(CLAUDE_SONNET, max_tokens=4096, temperature=0.3),
    TaskType.OODA_DECIDE:           ModelConfig(CLAUDE_SONNET, max_tokens=2048, temperature=0.5),
    TaskType.ONBOARD_FIRST_CONVO:   ModelConfig(CLAUDE_SONNET, max_tokens=4096, temperature=0.7),
    TaskType.ONBOARD_PERSONALITY:   ModelConfig(CLAUDE_SONNET, max_tokens=2048, temperature=0.6),
    TaskType.OODA_OBSERVE:          ModelConfig(CLAUDE_SONNET, max_tokens=2048, temperature=0.3),
    TaskType.OODA_ORIENT:           ModelConfig(CLAUDE_SONNET, max_tokens=2048, temperature=0.4),
    TaskType.OODA_ACT:              ModelConfig(CLAUDE_SONNET, max_tokens=2048, temperature=0.5),
    TaskType.SCOUT_FILTER:          ModelConfig(CLAUDE_SONNET, max_tokens=1024, temperature=0.2),
    TaskType.SCOUT_SUMMARIZE:       ModelConfig(CLAUDE_SONNET, max_tokens=2048, temperature=0.4),
    TaskType.SCRIBE_CLASSIFY_EMAIL: ModelConfig(CLAUDE_SONNET, max_tokens=512,  temperature=0.1),
    TaskType.HUNTER_ENRICH:         ModelConfig(CLAUDE_SONNET, max_tokens=2048, temperature=0.3),
    TaskType.HUNTER_QUALIFY:        ModelConfig(CLAUDE_SONNET, max_tokens=1024, temperature=0.2),
    TaskType.ANALYST_SUMMARIZE:     ModelConfig(CLAUDE_SONNET, max_tokens=2048, temperature=0.4),
    TaskType.OPERATOR_ACTION:       ModelConfig(CLAUDE_SONNET, max_tokens=1024, temperature=0.3),
    TaskType.ONBOARD_ENRICH:        ModelConfig(CLAUDE_SONNET, max_tokens=2048, temperature=0.3),
    TaskType.SKILL_EXECUTE:         ModelConfig(CLAUDE_SONNET, max_tokens=4096, temperature=0.5),
    TaskType.SIGNAL_CLASSIFY:       ModelConfig(CLAUDE_SONNET, max_tokens=512,  temperature=0.1),
    TaskType.ENTITY_EXTRACT:        ModelConfig(CLAUDE_SONNET, max_tokens=1024, temperature=0.1),
    TaskType.MEMORY_SUMMARIZE:      ModelConfig(CLAUDE_SONNET, max_tokens=2048, temperature=0.3),
    TaskType.MEMORY_CONSOLIDATE:    ModelConfig(CLAUDE_SONNET, max_tokens=2048, temperature=0.3),
    TaskType.GENERAL:               ModelConfig(CLAUDE_SONNET, max_tokens=4096, temperature=0.7),
}

DEFAULT_CONFIG = ModelConfig(CLAUDE_SONNET)
