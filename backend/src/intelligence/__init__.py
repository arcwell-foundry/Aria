"""Intelligence modules for ARIA's cognitive capabilities."""

from src.intelligence.causal import (
    CausalChain,
    CausalChainEngine,
    CausalChainStore,
    CausalHop,
    CausalTraversalRequest,
    CausalTraversalResponse,
)
from src.intelligence.causal_reasoning import (
    CausalReasoningResult,
    SalesAction,
    SalesCausalReasoningEngine,
)
from src.intelligence.cognitive_load import CognitiveLoadMonitor
from src.intelligence.orchestrator import JarvisOrchestrator, create_orchestrator
from src.intelligence.proactive_memory import ProactiveMemoryService
from src.intelligence.simulation import (
    MentalSimulationEngine,
    OutcomeClassification,
    QuickSimulationResponse,
    ScenarioType,
    SimulationOutcome,
    SimulationRequest,
    SimulationResponse,
    SimulationResult,
    SimulationScenario,
)
from src.intelligence.user_model import UserMentalModel, UserMentalModelService

__all__ = [
    "CognitiveLoadMonitor",
    "ProactiveMemoryService",
    # Phase 7: Causal Intelligence
    "CausalChainEngine",
    "CausalChainStore",
    "CausalChain",
    "CausalHop",
    "CausalTraversalRequest",
    "CausalTraversalResponse",
    # Phase 7: Mental Simulation (US-708)
    "MentalSimulationEngine",
    "OutcomeClassification",
    "ScenarioType",
    "SimulationOutcome",
    "SimulationRequest",
    "SimulationResponse",
    "SimulationResult",
    "SimulationScenario",
    "QuickSimulationResponse",
    # Phase 7: Intelligence Orchestrator (US-710)
    "JarvisOrchestrator",
    "create_orchestrator",
    # Sales Causal Reasoning
    "SalesCausalReasoningEngine",
    "SalesAction",
    "CausalReasoningResult",
    # User Mental Model
    "UserMentalModelService",
    "UserMentalModel",
]
