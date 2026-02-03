# Phase 4 Addendum: AGI Enhancements
## Additional Stories for PHASE_4_FEATURES.md

**Instructions:** Append these stories to your existing `PHASE_4_FEATURES.md` file after US-415.

---

### US-420: Cognitive Load Monitor

**As a** user  
**I want** ARIA to detect when I'm stressed or overwhelmed  
**So that** she adapts her communication style automatically

#### Acceptance Criteria
- [ ] Create `CognitiveLoadMonitor` service
- [ ] Detect high load from: message brevity, typos, rapid messages, time of day
- [ ] Track calendar density as load indicator
- [ ] Store load state per user session
- [ ] API endpoint: `GET /api/v1/user/cognitive-load`
- [ ] Expose load state to chat context
- [ ] Response adaptation: concise mode when load is high
- [ ] Load indicators in dashboard (optional, subtle)
- [ ] Unit tests for load detection algorithms
- [ ] Integration tests for state persistence

#### SQL Schema
```sql
CREATE TABLE cognitive_load_snapshots (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID REFERENCES auth.users(id) NOT NULL,
    
    -- Load indicators
    load_level TEXT NOT NULL CHECK (load_level IN ('low', 'medium', 'high', 'critical')),
    load_score FLOAT NOT NULL, -- 0.0 to 1.0
    
    -- Contributing factors
    factors JSONB NOT NULL DEFAULT '{}',
    -- Example: {
    --   "message_brevity": 0.8,
    --   "typo_rate": 0.3,
    --   "message_velocity": 0.6,
    --   "calendar_density": 0.9,
    --   "time_of_day": 0.4
    -- }
    
    -- Context
    session_id UUID,
    measured_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_cognitive_load_user ON cognitive_load_snapshots(user_id, measured_at DESC);

-- RLS
ALTER TABLE cognitive_load_snapshots ENABLE ROW LEVEL SECURITY;
CREATE POLICY "Users can only access own load data" ON cognitive_load_snapshots
    FOR ALL USING (auth.uid() = user_id);
```

#### Technical Notes
```python
# src/intelligence/cognitive_load.py
from dataclasses import dataclass
from enum import Enum
from datetime import datetime, timedelta

class LoadLevel(Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"

@dataclass
class CognitiveLoadState:
    level: LoadLevel
    score: float  # 0.0 to 1.0
    factors: dict
    recommendation: str

class CognitiveLoadMonitor:
    # Weights for different factors
    WEIGHTS = {
        "message_brevity": 0.25,
        "typo_rate": 0.15,
        "message_velocity": 0.20,
        "calendar_density": 0.25,
        "time_of_day": 0.15
    }
    
    # Thresholds
    THRESHOLDS = {
        "low": 0.3,
        "medium": 0.5,
        "high": 0.7,
        "critical": 0.85
    }
    
    def __init__(self, db_client, calendar_service):
        self.db = db_client
        self.calendar = calendar_service
    
    async def estimate_load(
        self,
        user_id: str,
        recent_messages: list[dict],
        session_id: str | None = None
    ) -> CognitiveLoadState:
        """Estimate user's current cognitive load."""
        
        factors = {}
        
        # 1. Message brevity (short messages = higher load)
        if recent_messages:
            avg_length = sum(len(m["content"]) for m in recent_messages) / len(recent_messages)
            factors["message_brevity"] = self._normalize_brevity(avg_length)
        else:
            factors["message_brevity"] = 0.5
        
        # 2. Typo rate (more typos = higher load)
        factors["typo_rate"] = await self._calculate_typo_rate(recent_messages)
        
        # 3. Message velocity (rapid messages = higher load)
        factors["message_velocity"] = self._calculate_velocity(recent_messages)
        
        # 4. Calendar density (busy calendar = higher load)
        factors["calendar_density"] = await self._get_calendar_density(user_id)
        
        # 5. Time of day (late hours = higher load)
        factors["time_of_day"] = self._time_of_day_factor()
        
        # Calculate weighted score
        score = sum(
            factors[k] * self.WEIGHTS[k]
            for k in self.WEIGHTS
        )
        
        # Determine level
        level = LoadLevel.LOW
        for level_name, threshold in sorted(
            self.THRESHOLDS.items(),
            key=lambda x: x[1]
        ):
            if score >= threshold:
                level = LoadLevel(level_name)
        
        # Generate recommendation
        recommendation = self._get_recommendation(level, factors)
        
        state = CognitiveLoadState(
            level=level,
            score=score,
            factors=factors,
            recommendation=recommendation
        )
        
        # Store snapshot
        await self._store_snapshot(user_id, state, session_id)
        
        return state
    
    def _normalize_brevity(self, avg_length: float) -> float:
        """Normalize message length to 0-1 (short = high)."""
        # Under 20 chars = very brief = 1.0
        # Over 200 chars = detailed = 0.0
        if avg_length < 20:
            return 1.0
        elif avg_length > 200:
            return 0.0
        else:
            return 1.0 - (avg_length - 20) / 180
    
    async def _calculate_typo_rate(self, messages: list[dict]) -> float:
        """Detect typos and errors in messages."""
        # Simplified: check for common patterns
        # In production, use a spell checker
        if not messages:
            return 0.0
        
        error_indicators = 0
        for msg in messages:
            text = msg.get("content", "")
            # Check for repeated letters (typing fast)
            if any(text.count(c * 3) > 0 for c in "abcdefghijklmnopqrstuvwxyz"):
                error_indicators += 1
            # Check for very short corrections ("*meant")
            if text.startswith("*") and len(text) < 20:
                error_indicators += 2
        
        return min(error_indicators / (len(messages) * 2), 1.0)
    
    def _calculate_velocity(self, messages: list[dict]) -> float:
        """Calculate message sending velocity."""
        if len(messages) < 2:
            return 0.0
        
        # Get timestamps
        timestamps = [m.get("created_at") for m in messages if m.get("created_at")]
        if len(timestamps) < 2:
            return 0.0
        
        # Calculate average gap
        gaps = []
        for i in range(1, len(timestamps)):
            if isinstance(timestamps[i], str):
                t1 = datetime.fromisoformat(timestamps[i-1])
                t2 = datetime.fromisoformat(timestamps[i])
            else:
                t1, t2 = timestamps[i-1], timestamps[i]
            gaps.append((t2 - t1).total_seconds())
        
        avg_gap = sum(gaps) / len(gaps)
        
        # Under 5 seconds = rapid = 1.0
        # Over 60 seconds = relaxed = 0.0
        if avg_gap < 5:
            return 1.0
        elif avg_gap > 60:
            return 0.0
        else:
            return 1.0 - (avg_gap - 5) / 55
    
    async def _get_calendar_density(self, user_id: str) -> float:
        """Check calendar for meeting density."""
        now = datetime.utcnow()
        today_start = now.replace(hour=0, minute=0, second=0)
        today_end = now.replace(hour=23, minute=59, second=59)
        
        events = await self.calendar.get_events(
            user_id=user_id,
            start=today_start,
            end=today_end
        )
        
        # Calculate meeting hours
        total_minutes = sum(
            (e.get("end") - e.get("start")).total_seconds() / 60
            for e in events
            if e.get("start") and e.get("end")
        )
        
        # 8 hours of meetings = 1.0
        return min(total_minutes / 480, 1.0)
    
    def _time_of_day_factor(self) -> float:
        """Factor based on time of day."""
        hour = datetime.now().hour
        
        # Late night (10pm-6am) = high
        if hour >= 22 or hour < 6:
            return 0.8
        # Early morning (6-8am) or evening (6-10pm) = medium
        elif hour < 8 or hour >= 18:
            return 0.4
        # Core hours = low
        else:
            return 0.2
    
    def _get_recommendation(self, level: LoadLevel, factors: dict) -> str:
        """Generate recommendation based on load state."""
        if level == LoadLevel.CRITICAL:
            return "concise_urgent"  # Very brief, offer to handle things
        elif level == LoadLevel.HIGH:
            return "concise"  # Brief responses, minimal questions
        elif level == LoadLevel.MEDIUM:
            return "balanced"  # Normal responses
        else:
            return "detailed"  # Can be thorough


# Integration with chat
class ChatContextBuilder:
    async def build_context(self, user_id: str, messages: list) -> dict:
        # Get cognitive load
        load_state = await self.cognitive_monitor.estimate_load(
            user_id=user_id,
            recent_messages=messages[-5:]
        )
        
        context = {
            "cognitive_load": {
                "level": load_state.level.value,
                "response_style": load_state.recommendation
            }
        }
        
        # Add system instruction based on load
        if load_state.level in [LoadLevel.HIGH, LoadLevel.CRITICAL]:
            context["system_instruction"] = """
The user appears to be under high cognitive load. Be:
- Extremely concise
- Action-oriented
- Offer to handle tasks independently
- Avoid asking multiple questions
- Lead with the most important information
"""
        
        return context
```

---

### US-421: Proactive Memory Surfacing

**As a** user  
**I want** ARIA to volunteer relevant information from memory  
**So that** I benefit from our shared history without having to ask

#### Acceptance Criteria
- [ ] Create `ProactiveMemoryService`
- [ ] Pattern matching: detect when current topic relates to past discussions
- [ ] Connection discovery: find links between current and stored entities
- [ ] Temporal triggers: surface relevant anniversaries, deadlines
- [ ] Goal relevance: surface memories that relate to active goals
- [ ] Relevance scoring for proactive insights
- [ ] Configurable surfacing threshold
- [ ] Maximum 2 proactive insights per response (avoid overwhelm)
- [ ] API endpoint: `GET /api/v1/memory/proactive`
- [ ] Integration with chat context building
- [ ] Cooldown to avoid repeating same insights
- [ ] Unit tests for relevance scoring
- [ ] Integration tests for surfacing logic

#### Technical Notes
```python
# src/memory/proactive.py
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import Enum

class InsightType(Enum):
    PATTERN_MATCH = "pattern_match"
    CONNECTION = "connection"
    TEMPORAL = "temporal"
    GOAL_RELEVANT = "goal_relevant"

@dataclass
class ProactiveInsight:
    type: InsightType
    content: str
    relevance_score: float
    source_memory_id: str
    source_memory_type: str
    explanation: str  # Why this is relevant

class ProactiveMemoryService:
    SURFACING_THRESHOLD = 0.6
    MAX_INSIGHTS_PER_RESPONSE = 2
    COOLDOWN_HOURS = 24  # Don't repeat same insight within this window
    
    def __init__(
        self,
        memory_service,
        graphiti_client,
        salience_service,
        db_client
    ):
        self.memory = memory_service
        self.graphiti = graphiti_client
        self.salience = salience_service
        self.db = db_client
    
    async def find_volunteerable_context(
        self,
        user_id: str,
        current_message: str,
        conversation_messages: list[dict],
        active_goals: list[dict] | None = None
    ) -> list[ProactiveInsight]:
        """Find memories worth volunteering in current context."""
        
        insights = []
        
        # 1. Pattern matching: similar topics discussed before
        topic_matches = await self._find_topic_matches(
            user_id, current_message, conversation_messages
        )
        insights.extend(topic_matches)
        
        # 2. Connection discovery: entities linked to current entities
        connections = await self._find_connections(
            user_id, current_message
        )
        insights.extend(connections)
        
        # 3. Temporal triggers: relevant dates approaching
        temporal = await self._find_temporal_triggers(user_id)
        insights.extend(temporal)
        
        # 4. Goal relevance: memories that affect active goals
        if active_goals:
            goal_relevant = await self._find_goal_relevant(
                user_id, current_message, active_goals
            )
            insights.extend(goal_relevant)
        
        # Filter by threshold and cooldown
        filtered = await self._filter_insights(user_id, insights)
        
        # Sort by relevance and limit
        filtered.sort(key=lambda x: x.relevance_score, reverse=True)
        return filtered[:self.MAX_INSIGHTS_PER_RESPONSE]
    
    async def _find_topic_matches(
        self,
        user_id: str,
        current_message: str,
        conversation: list[dict]
    ) -> list[ProactiveInsight]:
        """Find past discussions on similar topics."""
        insights = []
        
        # Extract topics from current message
        current_topics = await self.graphiti.extract_topics(current_message)
        
        # Search conversation episodes for matching topics
        episodes = await self.db.table("conversation_episodes")\
            .select("*")\
            .eq("user_id", user_id)\
            .overlaps("key_topics", current_topics)\
            .order("current_salience", desc=True)\
            .limit(5)\
            .execute()
        
        for ep in episodes.data:
            # Calculate relevance
            topic_overlap = len(
                set(ep["key_topics"]) & set(current_topics)
            ) / max(len(current_topics), 1)
            
            relevance = topic_overlap * ep["current_salience"]
            
            if relevance >= self.SURFACING_THRESHOLD:
                insights.append(ProactiveInsight(
                    type=InsightType.PATTERN_MATCH,
                    content=ep["summary"],
                    relevance_score=relevance,
                    source_memory_id=ep["id"],
                    source_memory_type="conversation_episode",
                    explanation=f"Similar topic discussed previously"
                ))
        
        return insights
    
    async def _find_connections(
        self,
        user_id: str,
        current_message: str
    ) -> list[ProactiveInsight]:
        """Find entity connections via knowledge graph."""
        insights = []
        
        # Extract entities from current message
        entities = await self.graphiti.extract_entities_from_text(current_message)
        
        for entity in entities:
            # Get related entities from graph
            related = await self.graphiti.get_related_entities(
                entity_name=entity["name"],
                user_id=user_id,
                max_hops=2
            )
            
            for rel in related:
                if rel.get("relationship_type") and rel.get("confidence", 0) > 0.7:
                    insights.append(ProactiveInsight(
                        type=InsightType.CONNECTION,
                        content=f"{entity['name']} → {rel['relationship_type']} → {rel['target_name']}",
                        relevance_score=rel.get("confidence", 0.7),
                        source_memory_id=rel.get("id", "graph"),
                        source_memory_type="knowledge_graph",
                        explanation=f"Connection found in your data"
                    ))
        
        return insights
    
    async def _find_temporal_triggers(
        self,
        user_id: str
    ) -> list[ProactiveInsight]:
        """Find time-based triggers (anniversaries, deadlines)."""
        insights = []
        now = datetime.utcnow()
        
        # Check prospective memory for upcoming deadlines
        upcoming = await self.db.table("prospective_memories")\
            .select("*")\
            .eq("user_id", user_id)\
            .gte("trigger_date", now.isoformat())\
            .lte("trigger_date", (now + timedelta(days=3)).isoformat())\
            .eq("status", "pending")\
            .execute()
        
        for task in upcoming.data:
            days_until = (
                datetime.fromisoformat(task["trigger_date"]) - now
            ).days
            
            urgency = 1.0 - (days_until / 3)  # More urgent = higher score
            
            insights.append(ProactiveInsight(
                type=InsightType.TEMPORAL,
                content=task["description"],
                relevance_score=urgency,
                source_memory_id=task["id"],
                source_memory_type="prospective_memory",
                explanation=f"Due in {days_until} day(s)"
            ))
        
        return insights
    
    async def _find_goal_relevant(
        self,
        user_id: str,
        current_message: str,
        goals: list[dict]
    ) -> list[ProactiveInsight]:
        """Find memories relevant to active goals."""
        insights = []
        
        # Get goal-related facts
        for goal in goals:
            related_facts = await self.memory.search_semantic(
                user_id=user_id,
                query=goal.get("description", ""),
                limit=3
            )
            
            for fact in related_facts:
                if fact.get("confidence", 0) > 0.7:
                    insights.append(ProactiveInsight(
                        type=InsightType.GOAL_RELEVANT,
                        content=fact["content"],
                        relevance_score=fact["confidence"] * goal.get("priority", 0.5),
                        source_memory_id=fact["id"],
                        source_memory_type="semantic_fact",
                        explanation=f"Relates to goal: {goal.get('title', 'Active goal')}"
                    ))
        
        return insights
    
    async def _filter_insights(
        self,
        user_id: str,
        insights: list[ProactiveInsight]
    ) -> list[ProactiveInsight]:
        """Filter by threshold and cooldown."""
        filtered = []
        
        # Get recently surfaced insights
        recent = await self.db.table("surfaced_insights")\
            .select("source_memory_id")\
            .eq("user_id", user_id)\
            .gte("surfaced_at", (
                datetime.utcnow() - timedelta(hours=self.COOLDOWN_HOURS)
            ).isoformat())\
            .execute()
        
        recent_ids = {r["source_memory_id"] for r in recent.data}
        
        for insight in insights:
            if insight.relevance_score >= self.SURFACING_THRESHOLD:
                if insight.source_memory_id not in recent_ids:
                    filtered.append(insight)
        
        return filtered
    
    async def record_surfaced(
        self,
        user_id: str,
        insight: ProactiveInsight
    ) -> None:
        """Record that an insight was surfaced (for cooldown)."""
        await self.db.table("surfaced_insights").insert({
            "user_id": user_id,
            "source_memory_id": insight.source_memory_id,
            "insight_type": insight.type.value,
            "surfaced_at": datetime.utcnow().isoformat()
        }).execute()
```

#### SQL Schema (add to migrations)
```sql
CREATE TABLE surfaced_insights (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID REFERENCES auth.users(id) NOT NULL,
    source_memory_id UUID NOT NULL,
    insight_type TEXT NOT NULL,
    surfaced_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_surfaced_insights_user ON surfaced_insights(user_id, surfaced_at DESC);

ALTER TABLE surfaced_insights ENABLE ROW LEVEL SECURITY;
CREATE POLICY "Users can only access own surfaced insights" ON surfaced_insights
    FOR ALL USING (auth.uid() = user_id);
```

---

### US-422: Prediction Registration System

**As a** user  
**I want** ARIA to track her predictions and learn from outcomes  
**So that** she becomes more accurate over time

#### Acceptance Criteria
- [ ] Create `predictions` table
- [ ] Create `PredictionService` for registration and validation
- [ ] Extract predictions from ARIA's responses via LLM
- [ ] Categorize: user_action, external_event, deal_outcome, timing
- [ ] Store confidence level with each prediction
- [ ] Validation workflow when outcomes occur
- [ ] Track accuracy by prediction type
- [ ] Calibration curve calculation
- [ ] API endpoints: register, validate, get accuracy stats
- [ ] Background job to check for expired predictions
- [ ] Dashboard widget showing prediction accuracy
- [ ] Unit tests for calibration math
- [ ] Integration tests for validation flow

#### SQL Schema
```sql
CREATE TABLE predictions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID REFERENCES auth.users(id) NOT NULL,
    
    -- Prediction content
    prediction_type TEXT NOT NULL CHECK (
        prediction_type IN ('user_action', 'external_event', 'deal_outcome', 'timing')
    ),
    content TEXT NOT NULL,
    predicted_outcome TEXT,
    confidence FLOAT NOT NULL CHECK (confidence >= 0 AND confidence <= 1),
    
    -- Context
    source_message_id UUID,
    source_conversation_id UUID,
    related_entity_id UUID,
    related_entity_type TEXT,
    
    -- Timeline
    expected_resolution TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    
    -- Outcome
    status TEXT DEFAULT 'pending' CHECK (
        status IN ('pending', 'validated_correct', 'validated_incorrect', 'expired', 'cancelled')
    ),
    actual_outcome TEXT,
    validated_at TIMESTAMPTZ,
    validation_notes TEXT
);

-- Calibration tracking
CREATE TABLE prediction_calibration (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID REFERENCES auth.users(id) NOT NULL,
    prediction_type TEXT NOT NULL,
    confidence_bucket FLOAT NOT NULL, -- 0.1, 0.2, ..., 0.9, 1.0
    total_predictions INTEGER DEFAULT 0,
    correct_predictions INTEGER DEFAULT 0,
    last_updated TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(user_id, prediction_type, confidence_bucket)
);

-- Indexes
CREATE INDEX idx_predictions_user ON predictions(user_id);
CREATE INDEX idx_predictions_status ON predictions(status, expected_resolution);
CREATE INDEX idx_predictions_type ON predictions(user_id, prediction_type);

-- RLS
ALTER TABLE predictions ENABLE ROW LEVEL SECURITY;
CREATE POLICY "Users can only access own predictions" ON predictions
    FOR ALL USING (auth.uid() = user_id);

ALTER TABLE prediction_calibration ENABLE ROW LEVEL SECURITY;
CREATE POLICY "Users can only access own calibration" ON prediction_calibration
    FOR ALL USING (auth.uid() = user_id);
```

#### Technical Notes
```python
# src/intelligence/predictions.py
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import Enum
import math

class PredictionType(Enum):
    USER_ACTION = "user_action"
    EXTERNAL_EVENT = "external_event"
    DEAL_OUTCOME = "deal_outcome"
    TIMING = "timing"

class PredictionStatus(Enum):
    PENDING = "pending"
    VALIDATED_CORRECT = "validated_correct"
    VALIDATED_INCORRECT = "validated_incorrect"
    EXPIRED = "expired"
    CANCELLED = "cancelled"

@dataclass
class Prediction:
    id: str
    prediction_type: PredictionType
    content: str
    predicted_outcome: str
    confidence: float
    expected_resolution: datetime
    status: PredictionStatus
    actual_outcome: str | None = None

@dataclass
class CalibrationStats:
    prediction_type: str
    confidence_bucket: float
    accuracy: float
    sample_size: int
    is_calibrated: bool  # accuracy ≈ confidence

class PredictionService:
    def __init__(self, db_client, llm_client):
        self.db = db_client
        self.llm = llm_client
    
    async def extract_and_register(
        self,
        user_id: str,
        response_text: str,
        conversation_id: str,
        message_id: str
    ) -> list[Prediction]:
        """Extract predictions from ARIA's response and register them."""
        
        # Use LLM to extract predictions
        extraction_prompt = f"""Analyze this response and extract any predictions made:

{response_text}

For each prediction found, return JSON with:
- content: what is being predicted
- predicted_outcome: the expected result
- prediction_type: one of [user_action, external_event, deal_outcome, timing]
- confidence: estimated confidence 0.0-1.0
- timeframe: when this should resolve (days from now)

Return array of predictions, or empty array if none.
JSON only."""

        extracted = await self.llm.generate_json(extraction_prompt)
        
        predictions = []
        for pred_data in extracted:
            prediction = await self.register(
                user_id=user_id,
                prediction_type=PredictionType(pred_data["prediction_type"]),
                content=pred_data["content"],
                predicted_outcome=pred_data["predicted_outcome"],
                confidence=pred_data["confidence"],
                expected_resolution=datetime.utcnow() + timedelta(
                    days=pred_data.get("timeframe", 30)
                ),
                source_conversation_id=conversation_id,
                source_message_id=message_id
            )
            predictions.append(prediction)
        
        return predictions
    
    async def register(
        self,
        user_id: str,
        prediction_type: PredictionType,
        content: str,
        predicted_outcome: str,
        confidence: float,
        expected_resolution: datetime,
        source_conversation_id: str | None = None,
        source_message_id: str | None = None,
        related_entity_id: str | None = None,
        related_entity_type: str | None = None
    ) -> Prediction:
        """Register a new prediction."""
        result = await self.db.table("predictions").insert({
            "user_id": user_id,
            "prediction_type": prediction_type.value,
            "content": content,
            "predicted_outcome": predicted_outcome,
            "confidence": confidence,
            "expected_resolution": expected_resolution.isoformat(),
            "source_conversation_id": source_conversation_id,
            "source_message_id": source_message_id,
            "related_entity_id": related_entity_id,
            "related_entity_type": related_entity_type
        }).execute()
        
        return Prediction(**result.data[0])
    
    async def validate(
        self,
        prediction_id: str,
        actual_outcome: str,
        is_correct: bool,
        notes: str | None = None
    ) -> Prediction:
        """Validate a prediction with actual outcome."""
        # Get prediction
        pred = await self.db.table("predictions")\
            .select("*")\
            .eq("id", prediction_id)\
            .single()\
            .execute()
        
        status = (
            PredictionStatus.VALIDATED_CORRECT if is_correct 
            else PredictionStatus.VALIDATED_INCORRECT
        )
        
        # Update prediction
        result = await self.db.table("predictions").update({
            "status": status.value,
            "actual_outcome": actual_outcome,
            "validated_at": datetime.utcnow().isoformat(),
            "validation_notes": notes
        }).eq("id", prediction_id).execute()
        
        # Update calibration
        await self._update_calibration(
            user_id=pred.data["user_id"],
            prediction_type=pred.data["prediction_type"],
            confidence=pred.data["confidence"],
            is_correct=is_correct
        )
        
        return Prediction(**result.data[0])
    
    async def _update_calibration(
        self,
        user_id: str,
        prediction_type: str,
        confidence: float,
        is_correct: bool
    ) -> None:
        """Update calibration statistics."""
        # Round confidence to bucket (0.1, 0.2, ..., 1.0)
        bucket = round(confidence * 10) / 10
        bucket = max(0.1, min(1.0, bucket))
        
        # Upsert calibration record
        await self.db.rpc("upsert_calibration", {
            "p_user_id": user_id,
            "p_prediction_type": prediction_type,
            "p_confidence_bucket": bucket,
            "p_is_correct": is_correct
        }).execute()
    
    async def get_calibration_stats(
        self,
        user_id: str,
        prediction_type: str | None = None
    ) -> list[CalibrationStats]:
        """Get calibration statistics."""
        query = self.db.table("prediction_calibration")\
            .select("*")\
            .eq("user_id", user_id)
        
        if prediction_type:
            query = query.eq("prediction_type", prediction_type)
        
        result = await query.execute()
        
        stats = []
        for row in result.data:
            accuracy = (
                row["correct_predictions"] / row["total_predictions"]
                if row["total_predictions"] > 0 else 0
            )
            
            # Check if calibrated (accuracy within 10% of confidence)
            is_calibrated = abs(accuracy - row["confidence_bucket"]) <= 0.1
            
            stats.append(CalibrationStats(
                prediction_type=row["prediction_type"],
                confidence_bucket=row["confidence_bucket"],
                accuracy=accuracy,
                sample_size=row["total_predictions"],
                is_calibrated=is_calibrated
            ))
        
        return stats
    
    async def get_pending_predictions(
        self,
        user_id: str,
        check_expired: bool = True
    ) -> list[Prediction]:
        """Get pending predictions, optionally marking expired ones."""
        now = datetime.utcnow()
        
        if check_expired:
            # Mark expired predictions
            await self.db.table("predictions").update({
                "status": "expired"
            }).eq("user_id", user_id)\
              .eq("status", "pending")\
              .lt("expected_resolution", now.isoformat())\
              .execute()
        
        result = await self.db.table("predictions")\
            .select("*")\
            .eq("user_id", user_id)\
            .eq("status", "pending")\
            .order("expected_resolution")\
            .execute()
        
        return [Prediction(**p) for p in result.data]
    
    async def get_accuracy_summary(
        self,
        user_id: str
    ) -> dict:
        """Get overall prediction accuracy summary."""
        result = await self.db.table("predictions")\
            .select("status, prediction_type")\
            .eq("user_id", user_id)\
            .in_("status", ["validated_correct", "validated_incorrect"])\
            .execute()
        
        total = len(result.data)
        correct = len([p for p in result.data if p["status"] == "validated_correct"])
        
        by_type = {}
        for pred in result.data:
            ptype = pred["prediction_type"]
            if ptype not in by_type:
                by_type[ptype] = {"total": 0, "correct": 0}
            by_type[ptype]["total"] += 1
            if pred["status"] == "validated_correct":
                by_type[ptype]["correct"] += 1
        
        return {
            "overall_accuracy": correct / total if total > 0 else None,
            "total_predictions": total,
            "correct_predictions": correct,
            "by_type": {
                k: v["correct"] / v["total"] if v["total"] > 0 else None
                for k, v in by_type.items()
            }
        }
```

#### SQL Function for Calibration Upsert
```sql
CREATE OR REPLACE FUNCTION upsert_calibration(
    p_user_id UUID,
    p_prediction_type TEXT,
    p_confidence_bucket FLOAT,
    p_is_correct BOOLEAN
) RETURNS VOID AS $$
BEGIN
    INSERT INTO prediction_calibration (
        user_id, prediction_type, confidence_bucket,
        total_predictions, correct_predictions
    ) VALUES (
        p_user_id, p_prediction_type, p_confidence_bucket,
        1, CASE WHEN p_is_correct THEN 1 ELSE 0 END
    )
    ON CONFLICT (user_id, prediction_type, confidence_bucket)
    DO UPDATE SET
        total_predictions = prediction_calibration.total_predictions + 1,
        correct_predictions = prediction_calibration.correct_predictions + 
            CASE WHEN p_is_correct THEN 1 ELSE 0 END,
        last_updated = NOW();
END;
$$ LANGUAGE plpgsql;
```

---

## Update Phase 4 Completion Checklist

Add to the existing checklist:

- [ ] **US-420:** Cognitive Load Monitor working
- [ ] **US-421:** Proactive Memory Surfacing operational
- [ ] **US-422:** Prediction Registration system active
- [ ] Load detection adapting response style
- [ ] Proactive insights appearing in relevant contexts
- [ ] Predictions being extracted and tracked
- [ ] Calibration stats calculating correctly

---

*Document Version: 1.0*  
*Created: February 2, 2026*
