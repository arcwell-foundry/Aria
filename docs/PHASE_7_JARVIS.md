# Phase 7: Jarvis Intelligence
## ARIA PRD - Implementation Phase 7

**Prerequisites:** Phase 6 Complete  
**Estimated Stories:** 10  
**Focus:** Multi-hop reasoning, implication detection, causal chain traversal, predictive processing, mental simulation

---

## Overview

Phase 7 transforms ARIA from an intelligent assistant into a truly "Jarvis-level" intelligence. This phase implements:

- **Causal Chain Traversal** - Trace how events propagate through connected entities
- **Implication Reasoning** - Identify non-obvious consequences of events
- **Predictive Processing** - Constantly predict what will happen next
- **Mental Simulation** - Run "what if" scenarios before acting
- **Multi-Scale Temporal Reasoning** - Simultaneously reason across different time horizons

**Why a New Phase:** These capabilities are genuinely new - they can't be "enhanced in" to existing features. They require the full foundation from Phases 1-6 and represent the leap from "smart tool" to "intelligence that connects dots humans miss."

**Completion Criteria:** ARIA proactively identifies implications of events, predicts user needs before they're expressed, and provides insights that surprise users with their depth.

---

## The Jarvis Test

Before completing any story in this phase, ask:
> "Would a user say 'How did ARIA know that?' or 'I never would have thought of that'?"

If the answer is no, the implementation isn't Jarvis-level yet.

---

## User Stories

### US-701: Causal Chain Traversal Engine

**As** ARIA  
**I want** to trace causal chains through the knowledge graph  
**So that** I can see how events propagate

#### Acceptance Criteria
- [ ] Traverse causal relationships N hops deep (configurable, default 4)
- [ ] Propagate confidence through chain (decay per hop)
- [ ] Return structured chain with each hop explained
- [ ] Handle cycles without infinite loops
- [ ] Support multiple parallel chains from single event
- [ ] Performance: < 500ms for 4-hop traversal
- [ ] Confidence decay formula: `hop_confidence = previous × 0.85`
- [ ] Minimum chain confidence threshold: 0.3
- [ ] Unit tests for graph traversal
- [ ] Integration tests with Neo4j

#### Example
```
Input: "FDA rejected Competitor X's BLA"

Output (4-hop chain):
Hop 1: Competitor X delayed 12-18 months (confidence: 0.95)
  └── Causal link: regulatory_rejection → development_delay
Hop 2: Their customers look for alternatives (confidence: 0.81)
  └── Causal link: supplier_delay → customer_churn_risk
Hop 3: BioGenix partnership affected (confidence: 0.69)
  └── Causal link: BioGenix is Competitor X customer
Hop 4: Our deal timeline accelerated (confidence: 0.58)
  └── Causal link: BioGenix is our active lead
```

#### Technical Notes
```python
# src/intelligence/causal.py
from dataclasses import dataclass
from typing import Optional

@dataclass
class CausalHop:
    source_entity: str
    target_entity: str
    relationship: str
    confidence: float
    explanation: str

@dataclass
class CausalChain:
    trigger_event: str
    hops: list[CausalHop]
    final_confidence: float
    time_to_impact: str | None

class CausalChainEngine:
    HOP_DECAY = 0.85
    MIN_CONFIDENCE = 0.3
    MAX_HOPS = 6
    
    def __init__(self, graphiti_client, llm_client):
        self.graphiti = graphiti_client
        self.llm = llm_client
    
    async def traverse(
        self,
        user_id: str,
        trigger_event: str,
        max_hops: int = 4
    ) -> list[CausalChain]:
        """Traverse causal chains from a trigger event."""
        
        # 1. Extract entities from trigger
        entities = await self.graphiti.extract_entities_from_text(trigger_event)
        
        chains = []
        visited = set()
        
        for entity in entities:
            # 2. Start BFS/DFS from each entity
            entity_chains = await self._traverse_from_entity(
                user_id=user_id,
                entity=entity,
                trigger_event=trigger_event,
                max_hops=min(max_hops, self.MAX_HOPS),
                visited=visited
            )
            chains.extend(entity_chains)
        
        # 3. Filter by minimum confidence
        chains = [c for c in chains if c.final_confidence >= self.MIN_CONFIDENCE]
        
        # 4. Sort by impact potential
        chains.sort(key=lambda c: c.final_confidence, reverse=True)
        
        return chains
    
    async def _traverse_from_entity(
        self,
        user_id: str,
        entity: dict,
        trigger_event: str,
        max_hops: int,
        visited: set,
        current_confidence: float = 1.0,
        current_chain: list[CausalHop] = None
    ) -> list[CausalChain]:
        """Recursive traversal with cycle detection."""
        
        if current_chain is None:
            current_chain = []
        
        if len(current_chain) >= max_hops:
            return [CausalChain(
                trigger_event=trigger_event,
                hops=current_chain,
                final_confidence=current_confidence,
                time_to_impact=await self._estimate_time(current_chain)
            )]
        
        entity_key = entity.get("name", str(entity))
        if entity_key in visited:
            return []  # Cycle detected
        
        visited.add(entity_key)
        
        # Get causal relationships from graph
        relationships = await self.graphiti.get_causal_relationships(
            user_id=user_id,
            entity_name=entity_key
        )
        
        chains = []
        for rel in relationships:
            new_confidence = current_confidence * self.HOP_DECAY * rel.get("strength", 0.9)
            
            if new_confidence < self.MIN_CONFIDENCE:
                continue
            
            # Generate explanation for this hop
            explanation = await self._explain_hop(entity_key, rel)
            
            hop = CausalHop(
                source_entity=entity_key,
                target_entity=rel["target"],
                relationship=rel["type"],
                confidence=new_confidence,
                explanation=explanation
            )
            
            # Recurse
            sub_chains = await self._traverse_from_entity(
                user_id=user_id,
                entity={"name": rel["target"]},
                trigger_event=trigger_event,
                max_hops=max_hops,
                visited=visited.copy(),  # Copy to allow parallel paths
                current_confidence=new_confidence,
                current_chain=current_chain + [hop]
            )
            
            chains.extend(sub_chains)
        
        # If no further relationships, end chain here
        if not relationships and current_chain:
            chains.append(CausalChain(
                trigger_event=trigger_event,
                hops=current_chain,
                final_confidence=current_confidence,
                time_to_impact=await self._estimate_time(current_chain)
            ))
        
        return chains
```

---

### US-702: Implication Reasoning Engine

**As** ARIA  
**I want** to identify implications of events for the user  
**So that** I surface insights they'd miss

#### Acceptance Criteria
- [ ] Given an event, trace all relevant causal chains
- [ ] Filter to implications affecting user's goals/deals
- [ ] Rank by: impact × confidence × urgency
- [ ] Generate natural language explanation
- [ ] Link to actionable recommendations
- [ ] Distinguish: opportunities vs. threats
- [ ] API endpoint: `POST /api/v1/intelligence/implications`
- [ ] Integration with Intelligence Pulse delivery
- [ ] Unit tests for ranking algorithm
- [ ] Integration tests for full pipeline

#### Technical Notes
```python
# src/intelligence/implications.py
from dataclasses import dataclass
from enum import Enum

class ImplicationType(Enum):
    OPPORTUNITY = "opportunity"
    THREAT = "threat"
    NEUTRAL = "neutral"

@dataclass
class Implication:
    content: str
    type: ImplicationType
    impact_score: float  # 0-1
    confidence: float  # 0-1
    urgency: float  # 0-1
    combined_score: float
    causal_chain: list[dict]
    affected_goals: list[str]
    recommended_actions: list[str]

class ImplicationEngine:
    IMPACT_WEIGHT = 0.4
    CONFIDENCE_WEIGHT = 0.35
    URGENCY_WEIGHT = 0.25
    
    def __init__(self, causal_engine, goal_service, llm_client):
        self.causal = causal_engine
        self.goals = goal_service
        self.llm = llm_client
    
    async def analyze_event(
        self,
        user_id: str,
        event: str
    ) -> list[Implication]:
        """Analyze an event for implications."""
        
        # 1. Get causal chains
        chains = await self.causal.traverse(
            user_id=user_id,
            trigger_event=event,
            max_hops=4
        )
        
        # 2. Get user's active goals
        goals = await self.goals.get_active_goals(user_id)
        
        implications = []
        
        for chain in chains:
            # 3. Check if chain affects any goals
            affected = await self._find_affected_goals(chain, goals)
            
            if not affected:
                continue
            
            # 4. Classify as opportunity or threat
            impl_type = await self._classify_implication(chain, affected)
            
            # 5. Calculate scores
            impact = await self._calculate_impact(chain, affected)
            urgency = await self._calculate_urgency(chain)
            
            combined = (
                impact * self.IMPACT_WEIGHT +
                chain.final_confidence * self.CONFIDENCE_WEIGHT +
                urgency * self.URGENCY_WEIGHT
            )
            
            # 6. Generate natural language
            content = await self._generate_explanation(event, chain, affected)
            
            # 7. Generate recommendations
            actions = await self._generate_recommendations(chain, impl_type)
            
            implications.append(Implication(
                content=content,
                type=impl_type,
                impact_score=impact,
                confidence=chain.final_confidence,
                urgency=urgency,
                combined_score=combined,
                causal_chain=[hop.__dict__ for hop in chain.hops],
                affected_goals=[g["id"] for g in affected],
                recommended_actions=actions
            ))
        
        # Sort by combined score
        implications.sort(key=lambda x: x.combined_score, reverse=True)
        
        return implications
```

---

### US-703: Butterfly Effect Detection

**As** ARIA  
**I want** to detect when small events will have large effects  
**So that** I can warn users early

#### Acceptance Criteria
- [ ] Monitor incoming events for cascade potential
- [ ] Calculate "amplification factor" for each event
- [ ] Identify events with amplification > threshold
- [ ] Calculate time-to-impact for each cascade
- [ ] Generate early warning pulses
- [ ] Track prediction accuracy for calibration
- [ ] Sensitivity tuning per user (avoid alert fatigue)
- [ ] API endpoint: `POST /api/v1/intelligence/detect-butterfly`
- [ ] Background job for continuous monitoring
- [ ] Unit tests for amplification calculation

#### Technical Notes
```python
# src/intelligence/butterfly.py
@dataclass
class ButterflyEffect:
    trigger_event: str
    amplification_factor: float  # How much bigger final impact vs trigger
    cascade_depth: int  # How many hops
    time_to_full_impact: str
    final_implications: list[str]
    warning_level: str  # low, medium, high, critical

class ButterflyDetector:
    AMPLIFICATION_THRESHOLD = 3.0  # 3x amplification = notable
    
    async def detect(
        self,
        user_id: str,
        event: str
    ) -> ButterflyEffect | None:
        """Detect if an event has butterfly effect potential."""
        
        # 1. Get implications
        implications = await self.implication_engine.analyze_event(
            user_id=user_id,
            event=event
        )
        
        if not implications:
            return None
        
        # 2. Calculate amplification
        # Trigger event has base impact of 1.0
        # Sum of implication impacts is amplified impact
        total_impact = sum(i.impact_score for i in implications)
        amplification = total_impact  # Since base is 1.0
        
        if amplification < self.AMPLIFICATION_THRESHOLD:
            return None
        
        # 3. Find deepest cascade
        max_depth = max(
            len(i.causal_chain) for i in implications
        )
        
        # 4. Estimate time to full impact
        time_estimate = await self._estimate_cascade_time(implications)
        
        # 5. Determine warning level
        warning = self._calculate_warning_level(amplification, max_depth)
        
        return ButterflyEffect(
            trigger_event=event,
            amplification_factor=amplification,
            cascade_depth=max_depth,
            time_to_full_impact=time_estimate,
            final_implications=[i.content for i in implications[:5]],
            warning_level=warning
        )
```

---

### US-704: Cross-Domain Connection Engine

**As** ARIA  
**I want** to connect seemingly unrelated events  
**So that** I surface non-obvious insights

#### Acceptance Criteria
- [ ] Analyze recent events for hidden connections
- [ ] Use entity overlap to find direct links
- [ ] Use causal model to find indirect connections
- [ ] Generate "connection insight" with explanation
- [ ] Score connection novelty (how surprising)
- [ ] Filter out obvious connections
- [ ] API endpoint: `GET /api/v1/intelligence/connections`
- [ ] Background job runs daily
- [ ] Integration with Intelligence Pulse
- [ ] Unit tests for connection detection

#### Example
```
Event A: "FDA issues new guidance on biosimilars"
Event B: "BioGenix concerns about regulatory timeline"  
Event C: "WuXi announces expansion in biologics manufacturing"

Connection Insight:
"The FDA's new biosimilar guidance may accelerate BioGenix's timeline 
concerns (they're focused on biosimilars), while WuXi's expansion 
positions them as an alternative manufacturing partner. This creates 
an opportunity to propose WuXi as a solution to BioGenix's concerns."

Novelty Score: 0.85 (high - not obvious)
```

---

### US-705: Time Horizon Analysis

**As** ARIA  
**I want** to categorize implications by when they'll materialize  
**So that** users know when to act

#### Acceptance Criteria
- [ ] Categorize: Immediate (days), Short-term (weeks), Medium (months), Long (quarters+)
- [ ] Use causal chain time delays
- [ ] Factor in external constraints (budget cycles, regulatory timelines)
- [ ] Recommend optimal action timing
- [ ] Visualize timeline in UI
- [ ] Alert when action window is closing
- [ ] API endpoint: `GET /api/v1/intelligence/timeline`
- [ ] Unit tests for time estimation

---

### US-706: Goal Impact Mapping

**As** ARIA  
**I want** to automatically map events to user goals  
**So that** I prioritize what matters to this user

#### Acceptance Criteria
- [ ] For each implication, score impact on each active goal
- [ ] Highlight implications that affect multiple goals
- [ ] De-prioritize implications with no goal impact
- [ ] Update goal progress tracking based on implications
- [ ] API endpoint: `GET /api/v1/intelligence/goal-impact`
- [ ] Dashboard widget showing goal impact summary
- [ ] Unit tests for impact scoring

---

### US-707: Predictive Processing Engine

**As** ARIA  
**I want** to constantly predict what will happen next  
**So that** I can be proactively helpful and learn from prediction errors

#### Acceptance Criteria
- [ ] Background prediction generation for active contexts
- [ ] Predict: user's next action, next topic, next need
- [ ] Prediction confidence scoring
- [ ] Prediction error detection (reality differs from prediction)
- [ ] Error-driven attention allocation (surprise = importance)
- [ ] Prediction accuracy tracking per user/context
- [ ] Calibration adjustment based on track record
- [ ] API endpoint: `GET /api/v1/intelligence/predictions/active`
- [ ] Performance: predictions generated < 200ms
- [ ] Unit tests for prediction logic
- [ ] Integration tests for error detection

#### Technical Notes
```python
# src/intelligence/predictive.py
from dataclasses import dataclass
from datetime import datetime, timedelta

@dataclass
class ActivePrediction:
    id: str
    prediction_type: str  # next_action, next_topic, next_need
    predicted_value: str
    confidence: float
    context: dict
    generated_at: datetime
    expires_at: datetime

@dataclass
class PredictionError:
    prediction_id: str
    predicted: str
    actual: str
    surprise_level: float  # How unexpected
    learning_signal: str  # What to update

class PredictiveEngine:
    PREDICTION_TYPES = ["next_action", "next_topic", "next_need", "response_to_message"]
    
    def __init__(self, llm_client, memory_service, db_client):
        self.llm = llm_client
        self.memory = memory_service
        self.db = db_client
    
    async def generate_predictions(
        self,
        user_id: str,
        current_context: dict
    ) -> list[ActivePrediction]:
        """Generate predictions about what will happen next."""
        
        predictions = []
        
        # Get user patterns from memory
        patterns = await self.memory.get_user_patterns(user_id)
        
        for pred_type in self.PREDICTION_TYPES:
            prediction = await self._generate_prediction(
                user_id=user_id,
                prediction_type=pred_type,
                context=current_context,
                patterns=patterns
            )
            if prediction:
                predictions.append(prediction)
        
        # Store active predictions
        for pred in predictions:
            await self._store_prediction(user_id, pred)
        
        return predictions
    
    async def check_predictions(
        self,
        user_id: str,
        actual_event: str,
        event_type: str
    ) -> list[PredictionError]:
        """Check active predictions against actual events."""
        
        # Get relevant active predictions
        active = await self.db.table("active_predictions")\
            .select("*")\
            .eq("user_id", user_id)\
            .eq("prediction_type", event_type)\
            .gt("expires_at", datetime.utcnow().isoformat())\
            .execute()
        
        errors = []
        
        for pred in active.data:
            # Compare prediction to actual
            match_score = await self._compare_prediction_to_actual(
                predicted=pred["predicted_value"],
                actual=actual_event
            )
            
            if match_score < 0.7:  # Prediction was wrong
                surprise = 1.0 - match_score
                
                error = PredictionError(
                    prediction_id=pred["id"],
                    predicted=pred["predicted_value"],
                    actual=actual_event,
                    surprise_level=surprise,
                    learning_signal=await self._generate_learning_signal(pred, actual_event)
                )
                
                errors.append(error)
                
                # Record for calibration
                await self._record_prediction_outcome(
                    prediction_id=pred["id"],
                    was_correct=False,
                    actual=actual_event
                )
            else:
                await self._record_prediction_outcome(
                    prediction_id=pred["id"],
                    was_correct=True,
                    actual=actual_event
                )
        
        return errors
    
    async def allocate_attention(
        self,
        user_id: str,
        errors: list[PredictionError]
    ) -> dict:
        """Allocate attention based on prediction errors."""
        
        attention = {
            "high_priority_topics": [],
            "reprocess_contexts": [],
            "update_patterns": []
        }
        
        for error in errors:
            if error.surprise_level > 0.8:
                # Very surprising = high priority
                attention["high_priority_topics"].append({
                    "topic": error.actual,
                    "reason": "Highly unexpected - needs attention"
                })
            
            if error.surprise_level > 0.5:
                # Moderately surprising = reprocess
                attention["reprocess_contexts"].append({
                    "context": error.prediction_id,
                    "learning_signal": error.learning_signal
                })
        
        return attention
```

---

### US-708: Mental Simulation Engine

**As** ARIA  
**I want** to simulate future scenarios before taking action  
**So that** I can give better advice and avoid mistakes

#### Acceptance Criteria
- [ ] "Episodic Future Thinking" - simulate specific scenarios
- [ ] Compare multiple action paths
- [ ] Premortem analysis on proposed plans
- [ ] Risk identification through simulation
- [ ] Output: ranked options with simulated outcomes
- [ ] Support for "what if" queries from user
- [ ] Simulation confidence based on available data
- [ ] API endpoint: `POST /api/v1/intelligence/simulate`
- [ ] Performance: < 3s for single scenario
- [ ] Unit tests for simulation logic

#### Technical Notes
```python
# src/intelligence/simulation.py
from dataclasses import dataclass

@dataclass
class SimulatedOutcome:
    scenario: str
    probability: float
    positive_outcomes: list[str]
    negative_outcomes: list[str]
    key_uncertainties: list[str]
    recommended: bool
    reasoning: str

@dataclass  
class SimulationResult:
    query: str
    scenarios_simulated: int
    best_option: str
    outcomes: list[SimulatedOutcome]
    premortem_risks: list[str]
    confidence: float

class MentalSimulationEngine:
    MAX_SCENARIOS = 5
    
    def __init__(self, causal_engine, llm_client, memory_service):
        self.causal = causal_engine
        self.llm = llm_client
        self.memory = memory_service
    
    async def simulate(
        self,
        user_id: str,
        action: str,
        context: dict | None = None
    ) -> SimulationResult:
        """Simulate outcomes of a proposed action."""
        
        # 1. Generate possible scenarios
        scenarios = await self._generate_scenarios(action, context)
        
        outcomes = []
        for scenario in scenarios[:self.MAX_SCENARIOS]:
            # 2. Trace causal chains for this scenario
            chains = await self.causal.traverse(
                user_id=user_id,
                trigger_event=scenario,
                max_hops=3
            )
            
            # 3. Classify outcomes as positive/negative
            positive = []
            negative = []
            for chain in chains:
                classification = await self._classify_outcome(chain)
                if classification == "positive":
                    positive.append(chain.hops[-1].explanation if chain.hops else scenario)
                else:
                    negative.append(chain.hops[-1].explanation if chain.hops else scenario)
            
            # 4. Identify uncertainties
            uncertainties = await self._identify_uncertainties(scenario, chains)
            
            # 5. Calculate probability (based on historical patterns)
            probability = await self._estimate_probability(
                user_id=user_id,
                scenario=scenario
            )
            
            outcomes.append(SimulatedOutcome(
                scenario=scenario,
                probability=probability,
                positive_outcomes=positive,
                negative_outcomes=negative,
                key_uncertainties=uncertainties,
                recommended=len(positive) > len(negative),
                reasoning=await self._generate_reasoning(scenario, positive, negative)
            ))
        
        # 6. Run premortem
        premortem = await self._run_premortem(action, outcomes)
        
        # 7. Determine best option
        best = max(outcomes, key=lambda o: o.probability * (1 if o.recommended else 0.5))
        
        return SimulationResult(
            query=action,
            scenarios_simulated=len(outcomes),
            best_option=best.scenario,
            outcomes=outcomes,
            premortem_risks=premortem,
            confidence=self._calculate_confidence(outcomes)
        )
    
    async def compare_options(
        self,
        user_id: str,
        options: list[str],
        context: dict | None = None
    ) -> dict:
        """Compare multiple options through simulation."""
        
        results = {}
        for option in options:
            results[option] = await self.simulate(
                user_id=user_id,
                action=option,
                context=context
            )
        
        # Rank options
        ranked = sorted(
            results.items(),
            key=lambda x: x[1].outcomes[0].probability if x[1].outcomes else 0,
            reverse=True
        )
        
        return {
            "ranked_options": [r[0] for r in ranked],
            "simulations": results,
            "recommendation": ranked[0][0] if ranked else None,
            "comparison_summary": await self._generate_comparison(ranked)
        }
```

---

### US-709: Multi-Scale Temporal Reasoning

**As** ARIA  
**I want** to simultaneously reason across different time horizons  
**So that** I balance immediate tactics with long-term strategy

#### Acceptance Criteria
- [ ] Maintain separate context windows for: immediate (hours), tactical (days), strategic (weeks), visionary (months+)
- [ ] Cross-scale impact detection (tactical decision affects strategic outcome)
- [ ] Time-appropriate recommendations based on horizon
- [ ] Conflict detection between short and long-term goals
- [ ] API endpoint: `GET /api/v1/intelligence/temporal-analysis`
- [ ] Dashboard view with multi-scale timeline
- [ ] Unit tests for cross-scale reasoning

#### Technical Notes
```python
# src/intelligence/temporal.py
from dataclasses import dataclass
from enum import Enum

class TimeScale(Enum):
    IMMEDIATE = "immediate"  # hours
    TACTICAL = "tactical"    # days
    STRATEGIC = "strategic"  # weeks
    VISIONARY = "visionary"  # months+

@dataclass
class ScaleContext:
    scale: TimeScale
    active_concerns: list[str]
    decisions_pending: list[str]
    goals: list[str]
    constraints: list[str]

@dataclass
class CrossScaleImpact:
    source_scale: TimeScale
    target_scale: TimeScale
    source_decision: str
    impact_on_target: str
    alignment: str  # supports, conflicts, neutral

class TemporalReasoningEngine:
    def __init__(self, goal_service, memory_service, llm_client):
        self.goals = goal_service
        self.memory = memory_service
        self.llm = llm_client
    
    async def analyze_decision(
        self,
        user_id: str,
        decision: str,
        primary_scale: TimeScale
    ) -> dict:
        """Analyze a decision across all time scales."""
        
        # 1. Get context for each scale
        contexts = {}
        for scale in TimeScale:
            contexts[scale] = await self._get_scale_context(user_id, scale)
        
        # 2. Analyze impact on each scale
        impacts = []
        for scale in TimeScale:
            if scale != primary_scale:
                impact = await self._analyze_cross_scale_impact(
                    decision=decision,
                    source_scale=primary_scale,
                    target_scale=scale,
                    target_context=contexts[scale]
                )
                if impact:
                    impacts.append(impact)
        
        # 3. Detect conflicts
        conflicts = [i for i in impacts if i.alignment == "conflicts"]
        
        # 4. Generate recommendations per scale
        recommendations = {}
        for scale in TimeScale:
            recommendations[scale] = await self._generate_scale_recommendation(
                decision=decision,
                scale=scale,
                context=contexts[scale],
                impacts=[i for i in impacts if i.target_scale == scale]
            )
        
        return {
            "decision": decision,
            "primary_scale": primary_scale.value,
            "cross_scale_impacts": [i.__dict__ for i in impacts],
            "conflicts_detected": len(conflicts),
            "conflict_details": [c.__dict__ for c in conflicts],
            "recommendations": recommendations,
            "overall_alignment": "aligned" if not conflicts else "needs_reconciliation"
        }
```

---

### US-710: Jarvis Intelligence Orchestrator

**As** ARIA  
**I want** all Jarvis intelligence capabilities to work together seamlessly  
**So that** insights are coherent and actionable

#### Acceptance Criteria
- [ ] Central orchestrator coordinates all intelligence engines
- [ ] Deduplication of overlapping insights
- [ ] Prioritization across all intelligence sources
- [ ] Context sharing between engines
- [ ] Unified API: `GET /api/v1/intelligence/briefing`
- [ ] Performance budget management (don't run everything always)
- [ ] Graceful degradation under load
- [ ] Insight quality scoring
- [ ] Integration with Intelligence Pulse delivery
- [ ] Dashboard: "Jarvis Insights" panel
- [ ] Unit tests for orchestration logic
- [ ] Integration tests for full pipeline

#### Technical Notes
```python
# src/intelligence/orchestrator.py
from dataclasses import dataclass

@dataclass
class JarvisInsight:
    source: str  # which engine
    type: str
    content: str
    priority: float
    confidence: float
    actionable: bool
    actions: list[str]

class JarvisOrchestrator:
    PERFORMANCE_BUDGET_MS = 5000  # 5 second total budget
    
    def __init__(
        self,
        causal_engine,
        implication_engine,
        butterfly_detector,
        predictive_engine,
        simulation_engine,
        temporal_engine
    ):
        self.engines = {
            "causal": causal_engine,
            "implications": implication_engine,
            "butterfly": butterfly_detector,
            "predictive": predictive_engine,
            "simulation": simulation_engine,
            "temporal": temporal_engine
        }
    
    async def generate_briefing(
        self,
        user_id: str,
        context: dict,
        budget_ms: int | None = None
    ) -> list[JarvisInsight]:
        """Generate comprehensive intelligence briefing."""
        
        budget = budget_ms or self.PERFORMANCE_BUDGET_MS
        insights = []
        
        # Run engines in priority order with time budget
        start = time.time()
        
        # 1. Predictive (fast, always run)
        predictions = await self.engines["predictive"].generate_predictions(
            user_id, context
        )
        insights.extend(self._convert_predictions(predictions))
        
        elapsed = (time.time() - start) * 1000
        if elapsed > budget * 0.8:
            return self._finalize(insights)
        
        # 2. Implications (medium, run if relevant events)
        if context.get("recent_events"):
            for event in context["recent_events"][:3]:
                implications = await self.engines["implications"].analyze_event(
                    user_id, event
                )
                insights.extend(self._convert_implications(implications))
        
        elapsed = (time.time() - start) * 1000
        if elapsed > budget * 0.8:
            return self._finalize(insights)
        
        # 3. Butterfly (run on new events only)
        if context.get("new_event"):
            butterfly = await self.engines["butterfly"].detect(
                user_id, context["new_event"]
            )
            if butterfly:
                insights.append(self._convert_butterfly(butterfly))
        
        # 4. Continue with remaining engines as budget allows...
        
        return self._finalize(insights)
    
    def _finalize(self, insights: list[JarvisInsight]) -> list[JarvisInsight]:
        """Deduplicate, prioritize, and return insights."""
        
        # Deduplicate by content similarity
        unique = self._deduplicate(insights)
        
        # Sort by priority
        unique.sort(key=lambda x: x.priority * x.confidence, reverse=True)
        
        # Return top insights
        return unique[:10]
```

---

## Phase 7 Completion Checklist

Before moving to Phase 8, verify:

- [ ] All 10 user stories completed
- [ ] All quality gates pass
- [ ] Causal chain traversal working with Neo4j
- [ ] Implications surfacing for real events
- [ ] Butterfly effects being detected
- [ ] Cross-domain connections finding non-obvious links
- [ ] Time horizon analysis categorizing correctly
- [ ] Goal impact mapping working
- [ ] Predictive processing generating accurate predictions
- [ ] Mental simulation producing useful scenarios
- [ ] Multi-scale temporal reasoning detecting conflicts
- [ ] Orchestrator coordinating all engines
- [ ] Performance within budget (< 5s for full briefing)
- [ ] Users saying "How did ARIA know that?"

---

## Integration Points

### Intelligence Pulse (Phase 4)
Jarvis insights feed into Intelligence Pulse for delivery:
```python
# In pulse generation
jarvis_insights = await orchestrator.generate_briefing(user_id, context)
for insight in jarvis_insights:
    if insight.priority > 0.7:
        await pulse_service.schedule_delivery(
            user_id=user_id,
            content=insight.content,
            priority=insight.priority
        )
```

### Chat Interface
Jarvis capabilities available during conversation:
```python
# When user asks "what if" questions
if intent == "simulation_request":
    result = await simulation_engine.simulate(user_id, user_query)
    # Include simulation in response
```

### Memory System
All insights strengthen relevant memories:
```python
# After generating insight
for entity in insight.related_entities:
    await salience_service.record_access(
        memory_id=entity.memory_id,
        memory_type=entity.type,
        user_id=user_id,
        context=f"jarvis_insight: {insight.type}"
    )
```

---

## Next Phase

Proceed to `PHASE_8_AGI_COMPANION.md` for personality, theory of mind, and metacognition.

---

*Document Version: 1.0*  
*Created: February 2, 2026*
