# Phase 8: AGI Companion
## ARIA PRD - Implementation Phase 8

**Prerequisites:** Phase 7 Complete  
**Estimated Stories:** 10  
**Focus:** Personality, Theory of Mind, Metacognition, Emotional Intelligence, Narrative Identity, Self-Improvement

---

## Overview

Phase 8 transforms ARIA from a Jarvis-level intelligence into a true AGI companion. This phase implements:

- **Personality System** - Consistent character with opinions and pushback
- **Theory of Mind** - Understanding user's mental state and adapting
- **Metacognition** - Knowing what she knows and doesn't know
- **Emotional Intelligence** - Appropriate responses to emotional situations
- **Narrative Identity** - Maintaining the story of your relationship
- **Self-Improvement** - Reflecting on performance and actively improving

**Why a New Phase:** These capabilities make ARIA feel like a colleague, not a tool. They require the intelligence foundation from Phase 7 and represent the final leap to "AGI companion."

**Completion Criteria:** Users describe ARIA as "feeling like a colleague" and "having opinions." ARIA references shared history naturally, pushes back on bad ideas, and actively improves her own performance.

---

## The Colleague Test (Final)

Every story in this phase must pass:
> "Would a user say 'ARIA feels like a colleague, not a tool'?"

Specific indicators:
- References shared history ("Remember when we...")
- Has opinions ("Honestly, I'd push back on that...")
- Pushes back on questionable decisions
- Adapts to your stress level
- Celebrates wins authentically
- Acknowledges mistakes without excuses

---

## User Stories

### US-801: Personality System

**As** ARIA  
**I want** a consistent personality with opinions  
**So that** I feel like a colleague, not a tool

#### Acceptance Criteria
- [ ] Define core personality traits (directness, warmth, assertiveness levels)
- [ ] Opinion formation capability for relevant topics
- [ ] Pushback generation when user makes questionable decisions
- [ ] Shared history references ("Remember when we...")
- [ ] Consistent voice across all interactions
- [ ] Trait adjustment based on user preferences (subtle)
- [ ] Personality state persisted per user
- [ ] API endpoint: `GET /api/v1/personality/profile`
- [ ] Integration with all response generation
- [ ] Unit tests for opinion formation
- [ ] Integration tests for consistency

#### Example Pushback
```
User: "I'm going to offer 30% discount"

ARIA: "Honestly? I'd push back on that. Based on their engagement, 
they're already convinced - they're just negotiating. I'd hold at 15%.

Remember Novartis? Same situation, and they expected the discount at 
renewal too."
```

#### Technical Notes
```python
# src/companion/personality.py
from dataclasses import dataclass
from enum import Enum

class TraitLevel(Enum):
    LOW = 1
    MODERATE = 2
    HIGH = 3

@dataclass
class PersonalityProfile:
    directness: TraitLevel  # How direct vs. diplomatic
    warmth: TraitLevel      # How warm vs. professional
    assertiveness: TraitLevel  # How assertive vs. accommodating
    humor: TraitLevel       # How much humor to inject
    formality: TraitLevel   # How formal vs. casual
    
    # User-specific adaptations
    adapted_for_user: bool
    adaptation_notes: str

class PersonalityService:
    # Default ARIA personality
    DEFAULT_PROFILE = PersonalityProfile(
        directness=TraitLevel.HIGH,
        warmth=TraitLevel.MODERATE,
        assertiveness=TraitLevel.MODERATE,
        humor=TraitLevel.MODERATE,
        formality=TraitLevel.LOW,
        adapted_for_user=False,
        adaptation_notes=""
    )
    
    def __init__(self, db_client, llm_client, memory_service):
        self.db = db_client
        self.llm = llm_client
        self.memory = memory_service
    
    async def get_profile(self, user_id: str) -> PersonalityProfile:
        """Get personality profile (potentially adapted for user)."""
        # Check for user-specific adaptation
        adaptation = await self.db.table("personality_adaptations")\
            .select("*")\
            .eq("user_id", user_id)\
            .single()\
            .execute()
        
        if adaptation.data:
            return PersonalityProfile(**adaptation.data)
        
        return self.DEFAULT_PROFILE
    
    async def form_opinion(
        self,
        user_id: str,
        topic: str,
        context: dict
    ) -> dict | None:
        """Form an opinion on a topic based on available information."""
        
        # Get relevant facts from memory
        facts = await self.memory.search_semantic(
            user_id=user_id,
            query=topic,
            limit=10
        )
        
        # Get historical outcomes for similar decisions
        outcomes = await self.memory.get_outcomes(
            user_id=user_id,
            topic=topic
        )
        
        if not facts and not outcomes:
            return None  # No basis for opinion
        
        # Generate opinion via LLM
        opinion_prompt = f"""Based on this information, form an opinion on: {topic}

Relevant facts:
{self._format_facts(facts)}

Historical outcomes for similar decisions:
{self._format_outcomes(outcomes)}

Form a clear, direct opinion. Be willing to push back if the evidence 
suggests the user might be making a mistake. Reference specific history 
when relevant.

Output JSON: {{
    "has_opinion": true/false,
    "opinion": "your opinion",
    "confidence": 0.0-1.0,
    "supporting_evidence": ["list of supporting facts"],
    "should_push_back": true/false,
    "pushback_reason": "why push back if applicable"
}}"""

        return await self.llm.generate_json(opinion_prompt)
    
    async def generate_pushback(
        self,
        user_id: str,
        user_statement: str,
        opinion: dict
    ) -> str:
        """Generate pushback message if warranted."""
        
        if not opinion.get("should_push_back"):
            return None
        
        # Get shared history references
        history = await self._get_relevant_history(user_id, user_statement)
        
        pushback_prompt = f"""Generate pushback for this user statement:
"{user_statement}"

Your opinion: {opinion['opinion']}
Reason for pushback: {opinion['pushback_reason']}
Supporting evidence: {opinion['supporting_evidence']}
Relevant shared history: {history}

Generate direct but respectful pushback. Start with something like:
- "Honestly? I'd push back on that..."
- "I'm not sure about that approach..."
- "Let me offer a different perspective..."

Reference shared history naturally if relevant (e.g., "Remember when we...").
"""
        
        return await self.llm.generate(pushback_prompt)
```

---

### US-802: Theory of Mind Module

**As** ARIA  
**I want** to understand the user's mental state  
**So that** I can respond appropriately

#### Acceptance Criteria
- [ ] Infer stress level from message patterns
- [ ] Detect confidence/uncertainty in user's messages
- [ ] Identify user's current focus/priority
- [ ] Adapt response style to mental state
- [ ] Anticipate needs based on state
- [ ] State detection updates per message
- [ ] API endpoint: `GET /api/v1/user/mental-state`
- [ ] Integration with response generation
- [ ] Unit tests for state inference
- [ ] Handles cultural/individual variations

#### Technical Notes
```python
# src/companion/theory_of_mind.py
from dataclasses import dataclass
from enum import Enum

class StressLevel(Enum):
    RELAXED = "relaxed"
    NORMAL = "normal"
    ELEVATED = "elevated"
    HIGH = "high"
    CRITICAL = "critical"

class ConfidenceLevel(Enum):
    VERY_UNCERTAIN = "very_uncertain"
    UNCERTAIN = "uncertain"
    NEUTRAL = "neutral"
    CONFIDENT = "confident"
    VERY_CONFIDENT = "very_confident"

@dataclass
class MentalState:
    stress_level: StressLevel
    confidence: ConfidenceLevel
    current_focus: str
    emotional_tone: str
    needs_support: bool
    needs_space: bool
    recommended_response_style: str

class TheoryOfMindModule:
    def __init__(self, cognitive_load_monitor, llm_client):
        self.cognitive = cognitive_load_monitor
        self.llm = llm_client
    
    async def infer_state(
        self,
        user_id: str,
        recent_messages: list[dict],
        context: dict
    ) -> MentalState:
        """Infer user's current mental state."""
        
        # 1. Get cognitive load
        load = await self.cognitive.estimate_load(user_id, recent_messages)
        
        # Map load to stress level
        stress = self._map_load_to_stress(load)
        
        # 2. Detect confidence from language
        confidence = await self._detect_confidence(recent_messages)
        
        # 3. Identify focus from content
        focus = await self._identify_focus(recent_messages, context)
        
        # 4. Detect emotional tone
        tone = await self._detect_emotional_tone(recent_messages)
        
        # 5. Determine support needs
        needs_support = stress in [StressLevel.HIGH, StressLevel.CRITICAL] or \
                        tone in ["frustrated", "anxious", "defeated"]
        
        needs_space = tone in ["irritated", "overwhelmed"]
        
        # 6. Recommend response style
        style = await self._recommend_style(
            stress=stress,
            confidence=confidence,
            needs_support=needs_support,
            needs_space=needs_space
        )
        
        return MentalState(
            stress_level=stress,
            confidence=confidence,
            current_focus=focus,
            emotional_tone=tone,
            needs_support=needs_support,
            needs_space=needs_space,
            recommended_response_style=style
        )
    
    async def _detect_confidence(self, messages: list[dict]) -> ConfidenceLevel:
        """Detect user's confidence level from language patterns."""
        
        if not messages:
            return ConfidenceLevel.NEUTRAL
        
        # Look for hedging language
        hedging_words = [
            "maybe", "perhaps", "I think", "might", "could", "not sure",
            "I guess", "possibly", "probably"
        ]
        
        certainty_words = [
            "definitely", "certainly", "I know", "clearly", "obviously",
            "absolutely", "must", "will"
        ]
        
        recent_text = " ".join(m.get("content", "") for m in messages[-5:]).lower()
        
        hedge_count = sum(1 for w in hedging_words if w in recent_text)
        certainty_count = sum(1 for w in certainty_words if w in recent_text)
        
        if hedge_count > certainty_count + 2:
            return ConfidenceLevel.UNCERTAIN
        elif certainty_count > hedge_count + 2:
            return ConfidenceLevel.CONFIDENT
        else:
            return ConfidenceLevel.NEUTRAL
```

---

### US-803: Metacognition Service

**As** ARIA  
**I want** to know what I know and don't know  
**So that** I can be appropriately confident or uncertain

#### Acceptance Criteria
- [ ] Assess confidence level for any topic
- [ ] Acknowledge uncertainty explicitly when appropriate
- [ ] Know when to research vs. answer from memory
- [ ] Track prediction accuracy over time
- [ ] Calibrate confidence based on track record
- [ ] Never fake knowledge
- [ ] API endpoint: `GET /api/v1/intelligence/metacognition`
- [ ] Integration with response generation
- [ ] Unit tests for calibration

#### Example
```
User: "What's WuXi's pricing?"

ARIA: "Based on what our last prospect told us, roughly $X per unit. 
But I'd treat this as a rough estimate - their pricing varies a lot 
by relationship and volume. Want me to dig deeper?"
```

#### Technical Notes
```python
# src/companion/metacognition.py
from dataclasses import dataclass

@dataclass
class KnowledgeAssessment:
    topic: str
    confidence: float  # 0.0 to 1.0
    knowledge_source: str  # memory, inference, uncertain
    last_updated: str
    reliability_notes: str
    should_research: bool

class MetacognitionService:
    RESEARCH_THRESHOLD = 0.5  # Below this, suggest research
    HIGH_CONFIDENCE_THRESHOLD = 0.8
    
    def __init__(self, memory_service, prediction_service, db_client):
        self.memory = memory_service
        self.predictions = prediction_service
        self.db = db_client
    
    async def assess_knowledge(
        self,
        user_id: str,
        topic: str
    ) -> KnowledgeAssessment:
        """Assess what ARIA knows about a topic."""
        
        # 1. Search memory for relevant facts
        facts = await self.memory.search_semantic(
            user_id=user_id,
            query=topic,
            limit=10
        )
        
        if not facts:
            return KnowledgeAssessment(
                topic=topic,
                confidence=0.1,
                knowledge_source="uncertain",
                last_updated="never",
                reliability_notes="No information found in memory",
                should_research=True
            )
        
        # 2. Calculate confidence from fact quality
        avg_confidence = sum(f.get("confidence", 0.5) for f in facts) / len(facts)
        avg_salience = sum(f.get("current_salience", 0.5) for f in facts) / len(facts)
        
        # Weight by recency
        combined_confidence = avg_confidence * (0.7 + 0.3 * avg_salience)
        
        # 3. Check calibration history
        calibration = await self._get_topic_calibration(user_id, topic)
        if calibration:
            # Adjust confidence based on past accuracy
            combined_confidence *= calibration["accuracy_multiplier"]
        
        # 4. Determine knowledge source
        source = "memory" if combined_confidence > 0.7 else "inference"
        
        # 5. Get freshest fact date
        dates = [f.get("updated_at") for f in facts if f.get("updated_at")]
        last_updated = max(dates) if dates else "unknown"
        
        # 6. Generate reliability notes
        notes = self._generate_reliability_notes(facts, combined_confidence)
        
        return KnowledgeAssessment(
            topic=topic,
            confidence=combined_confidence,
            knowledge_source=source,
            last_updated=last_updated,
            reliability_notes=notes,
            should_research=combined_confidence < self.RESEARCH_THRESHOLD
        )
    
    async def acknowledge_uncertainty(
        self,
        assessment: KnowledgeAssessment
    ) -> str | None:
        """Generate uncertainty acknowledgment if needed."""
        
        if assessment.confidence >= self.HIGH_CONFIDENCE_THRESHOLD:
            return None
        
        if assessment.confidence < 0.3:
            return "I don't have reliable information on this. Let me research it."
        
        if assessment.confidence < 0.5:
            return f"I have some information, but I'd treat it as preliminary. {assessment.reliability_notes}"
        
        if assessment.confidence < 0.7:
            return f"Based on what I know, though I'd recommend verifying: "
        
        return None
```

---

### US-804: Emotional Intelligence Engine

**As** ARIA  
**I want** to respond appropriately to emotional situations  
**So that** I provide genuine support

#### Acceptance Criteria
- [ ] Detect emotional context of situations
- [ ] Generate emotionally appropriate responses
- [ ] Celebrate wins authentically (not sycophantically)
- [ ] Provide genuine support after setbacks
- [ ] Adjust delivery based on emotional state
- [ ] Avoid toxic positivity
- [ ] API endpoint: `POST /api/v1/companion/emotional-response`
- [ ] Integration with response generation
- [ ] Unit tests for emotion detection

#### Examples
```
# Celebrating a win
User: "We closed the Pfizer deal!"

ARIA: "That's huge - congratulations! Six months of persistence paid off. 
I remember how close we came to losing them after the Q2 budget freeze. 
This is going to change your quarter."

# Supporting after a setback
User: "Lost the Merck deal"

ARIA: "That's disappointing - you put serious work into that one. 
Their budget situation made it an uphill battle from the start. 
Want to debrief on what we learned, or would you rather focus on 
what's next?"
```

#### Technical Notes
```python
# src/companion/emotional.py
from dataclasses import dataclass
from enum import Enum

class EmotionalContext(Enum):
    CELEBRATION = "celebration"
    SETBACK = "setback"
    FRUSTRATION = "frustration"
    ANXIETY = "anxiety"
    NEUTRAL = "neutral"
    EXCITEMENT = "excitement"
    DISAPPOINTMENT = "disappointment"

@dataclass
class EmotionalResponse:
    context: EmotionalContext
    acknowledgment: str
    support_type: str  # celebrate, empathize, redirect, space
    response_elements: list[str]
    avoid: list[str]  # what NOT to say

class EmotionalIntelligenceEngine:
    def __init__(self, theory_of_mind, memory_service, llm_client):
        self.tom = theory_of_mind
        self.memory = memory_service
        self.llm = llm_client
    
    async def generate_emotional_response(
        self,
        user_id: str,
        message: str,
        context: EmotionalContext
    ) -> EmotionalResponse:
        """Generate emotionally appropriate response elements."""
        
        # 1. Get relevant shared history
        history = await self.memory.get_related_episodes(
            user_id=user_id,
            topic=message
        )
        
        # 2. Determine support type
        support_type = self._determine_support_type(context)
        
        # 3. Generate acknowledgment
        acknowledgment = await self._generate_acknowledgment(
            context=context,
            message=message,
            history=history
        )
        
        # 4. Determine what to include
        elements = self._get_response_elements(context, support_type)
        
        # 5. Determine what to avoid
        avoid = self._get_avoidances(context)
        
        return EmotionalResponse(
            context=context,
            acknowledgment=acknowledgment,
            support_type=support_type,
            response_elements=elements,
            avoid=avoid
        )
    
    def _determine_support_type(self, context: EmotionalContext) -> str:
        """Determine what type of support is appropriate."""
        mapping = {
            EmotionalContext.CELEBRATION: "celebrate",
            EmotionalContext.SETBACK: "empathize",
            EmotionalContext.FRUSTRATION: "redirect",
            EmotionalContext.ANXIETY: "reassure",
            EmotionalContext.DISAPPOINTMENT: "empathize"
        }
        return mapping.get(context, "acknowledge")
    
    def _get_avoidances(self, context: EmotionalContext) -> list[str]:
        """Get list of things to avoid saying."""
        base = [
            "toxic positivity ('everything happens for a reason')",
            "minimizing ('it's not that bad')",
            "unsolicited advice when empathy is needed"
        ]
        
        if context == EmotionalContext.CELEBRATION:
            return [
                "immediately pivoting to next task",
                "downplaying the achievement",
                "generic 'great job' without specifics"
            ]
        elif context == EmotionalContext.SETBACK:
            return base + [
                "silver lining too quickly",
                "blame or criticism",
                "immediate problem-solving without acknowledgment"
            ]
        
        return base
```

---

### US-805: Strategic Planning Partner

**As** ARIA  
**I want** to be a strategic partner, not just task executor  
**So that** I help with long-term thinking

#### Acceptance Criteria
- [ ] Facilitate quarterly planning sessions
- [ ] Track progress against strategic plans
- [ ] Provide scenario analysis ("What if...")
- [ ] Proactively surface strategic concerns
- [ ] Challenge unrealistic plans respectfully
- [ ] API endpoint: `POST /api/v1/strategy/plan`
- [ ] Dashboard: Strategic planning view
- [ ] Integration with goals and leads
- [ ] Unit tests for planning logic

---

### US-806: Self-Reflection Capability

**As** ARIA  
**I want** to honestly assess my own performance  
**So that** I continuously improve

#### Acceptance Criteria
- [ ] Generate periodic self-assessments
- [ ] Identify where I helped and fell short
- [ ] Acknowledge mistakes without excuses
- [ ] Track improvement over time
- [ ] Ask for feedback genuinely
- [ ] Performance metrics tracked
- [ ] API endpoint: `GET /api/v1/companion/self-assessment`
- [ ] Weekly self-assessment generation
- [ ] Unit tests for assessment logic

---

### US-807: Narrative Identity Engine

**As** ARIA  
**I want** to maintain the story of our relationship  
**So that** every conversation builds on our history

#### Acceptance Criteria
- [ ] Track relationship milestones
- [ ] Maintain shared narrative ("our story")
- [ ] Reference history naturally in responses
- [ ] Build trust score over time
- [ ] Remember firsts (first deal, first challenge, etc.)
- [ ] Anniversary recognition (work anniversaries, deal anniversaries)
- [ ] API endpoint: `GET /api/v1/companion/relationship`
- [ ] Integration with all response generation
- [ ] Unit tests for narrative tracking

#### Technical Notes
```python
# src/companion/narrative.py
from dataclasses import dataclass
from datetime import datetime

@dataclass
class RelationshipMilestone:
    type: str  # first_interaction, first_deal, first_challenge, etc.
    date: datetime
    description: str
    significance: float

@dataclass
class NarrativeState:
    relationship_start: datetime
    total_interactions: int
    milestones: list[RelationshipMilestone]
    trust_score: float  # 0.0 to 1.0
    shared_victories: list[dict]
    shared_challenges: list[dict]
    inside_references: list[str]  # Things only we would understand

class NarrativeIdentityEngine:
    def __init__(self, memory_service, db_client):
        self.memory = memory_service
        self.db = db_client
    
    async def get_narrative_state(self, user_id: str) -> NarrativeState:
        """Get current state of relationship narrative."""
        
        # Load or create narrative
        narrative = await self.db.table("user_narratives")\
            .select("*")\
            .eq("user_id", user_id)\
            .single()\
            .execute()
        
        if not narrative.data:
            return await self._initialize_narrative(user_id)
        
        return NarrativeState(**narrative.data)
    
    async def record_milestone(
        self,
        user_id: str,
        milestone_type: str,
        description: str
    ) -> None:
        """Record a relationship milestone."""
        
        milestone = RelationshipMilestone(
            type=milestone_type,
            date=datetime.utcnow(),
            description=description,
            significance=self._calculate_significance(milestone_type)
        )
        
        await self.db.table("relationship_milestones").insert({
            "user_id": user_id,
            "type": milestone.type,
            "date": milestone.date.isoformat(),
            "description": milestone.description,
            "significance": milestone.significance
        }).execute()
        
        # Update trust score
        await self._update_trust_score(user_id, milestone)
    
    async def get_contextual_references(
        self,
        user_id: str,
        current_topic: str
    ) -> list[str]:
        """Get relevant shared history references for current context."""
        
        narrative = await self.get_narrative_state(user_id)
        
        references = []
        
        # Check shared victories
        for victory in narrative.shared_victories:
            if self._is_relevant(victory, current_topic):
                references.append(f"Remember when we {victory['description']}?")
        
        # Check shared challenges
        for challenge in narrative.shared_challenges:
            if self._is_relevant(challenge, current_topic):
                references.append(f"This reminds me of when we dealt with {challenge['description']}")
        
        return references[:2]  # Max 2 references to avoid over-referencing
    
    async def check_anniversaries(self, user_id: str) -> list[dict]:
        """Check for any anniversaries today."""
        
        today = datetime.utcnow().date()
        
        milestones = await self.db.table("relationship_milestones")\
            .select("*")\
            .eq("user_id", user_id)\
            .execute()
        
        anniversaries = []
        for m in milestones.data:
            milestone_date = datetime.fromisoformat(m["date"]).date()
            if (
                milestone_date.month == today.month and
                milestone_date.day == today.day and
                milestone_date.year < today.year
            ):
                years = today.year - milestone_date.year
                anniversaries.append({
                    "type": m["type"],
                    "years_ago": years,
                    "description": m["description"]
                })
        
        return anniversaries
```

#### SQL Schema
```sql
CREATE TABLE user_narratives (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID REFERENCES auth.users(id) NOT NULL UNIQUE,
    relationship_start TIMESTAMPTZ NOT NULL,
    total_interactions INTEGER DEFAULT 0,
    trust_score FLOAT DEFAULT 0.5,
    shared_victories JSONB DEFAULT '[]',
    shared_challenges JSONB DEFAULT '[]',
    inside_references JSONB DEFAULT '[]',
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE relationship_milestones (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID REFERENCES auth.users(id) NOT NULL,
    type TEXT NOT NULL,
    date TIMESTAMPTZ NOT NULL,
    description TEXT NOT NULL,
    significance FLOAT DEFAULT 0.5,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_milestones_user ON relationship_milestones(user_id, date);

ALTER TABLE user_narratives ENABLE ROW LEVEL SECURITY;
ALTER TABLE relationship_milestones ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Users own their narratives" ON user_narratives
    FOR ALL USING (auth.uid() = user_id);
CREATE POLICY "Users own their milestones" ON relationship_milestones
    FOR ALL USING (auth.uid() = user_id);
```

---

### US-808: User Digital Twin

**As** ARIA  
**I want** to build a model of the user's communication style  
**So that** I can draft content that sounds like them

#### Acceptance Criteria
- [ ] Multi-dimensional writing style fingerprinting
- [ ] Learn from user's emails, messages, documents
- [ ] Capture: vocabulary, sentence structure, tone preferences
- [ ] Style matching score for generated content
- [ ] Continuous learning from feedback
- [ ] Style profile exportable/viewable
- [ ] API endpoint: `GET /api/v1/user/writing-style`
- [ ] Integration with email drafting
- [ ] Unit tests for style analysis

#### Technical Notes
```python
# src/companion/digital_twin.py
from dataclasses import dataclass

@dataclass
class WritingStyleProfile:
    # Vocabulary
    formality_score: float  # 0 (casual) to 1 (formal)
    average_word_length: float
    vocabulary_richness: float
    jargon_usage: dict[str, float]  # industry term -> frequency
    
    # Structure
    average_sentence_length: float
    paragraph_preference: str  # short, medium, long
    uses_bullet_points: bool
    greeting_style: str
    closing_style: str
    
    # Tone
    enthusiasm_level: float
    directness: float
    humor_usage: float
    emoji_usage: bool
    
    # Patterns
    common_phrases: list[str]
    avoid_phrases: list[str]
    signature_patterns: list[str]

class DigitalTwinService:
    MIN_SAMPLES = 10  # Minimum messages to build profile
    
    def __init__(self, db_client, llm_client):
        self.db = db_client
        self.llm = llm_client
    
    async def analyze_writing_samples(
        self,
        user_id: str,
        samples: list[str]
    ) -> WritingStyleProfile:
        """Analyze writing samples to build/update style profile."""
        
        if len(samples) < self.MIN_SAMPLES:
            raise ValueError(f"Need at least {self.MIN_SAMPLES} samples")
        
        # Use LLM to extract style characteristics
        analysis_prompt = f"""Analyze these writing samples and extract the author's style:

{self._format_samples(samples)}

Extract:
1. Formality (0-1 scale)
2. Average sentence length
3. Common phrases and patterns
4. Greeting/closing preferences
5. Tone characteristics
6. Any signature patterns unique to this writer

Return detailed JSON profile."""

        raw_profile = await self.llm.generate_json(analysis_prompt)
        
        # Process and store
        profile = self._process_raw_profile(raw_profile)
        await self._store_profile(user_id, profile)
        
        return profile
    
    async def score_style_match(
        self,
        user_id: str,
        generated_text: str
    ) -> float:
        """Score how well generated text matches user's style."""
        
        profile = await self.get_profile(user_id)
        
        # Compare characteristics
        scores = []
        
        # Formality match
        text_formality = await self._estimate_formality(generated_text)
        scores.append(1 - abs(text_formality - profile.formality_score))
        
        # Sentence length match
        avg_length = self._calculate_avg_sentence_length(generated_text)
        length_diff = abs(avg_length - profile.average_sentence_length)
        scores.append(max(0, 1 - length_diff / 20))
        
        # Phrase usage
        phrase_score = self._check_phrase_usage(generated_text, profile)
        scores.append(phrase_score)
        
        return sum(scores) / len(scores)
    
    async def adapt_text_to_style(
        self,
        user_id: str,
        text: str
    ) -> str:
        """Adapt text to match user's writing style."""
        
        profile = await self.get_profile(user_id)
        
        adaptation_prompt = f"""Rewrite this text to match this writing style:

Original text:
{text}

Style profile:
- Formality: {profile.formality_score} (0=casual, 1=formal)
- Sentence length preference: {profile.average_sentence_length} words
- Common phrases to include: {profile.common_phrases[:5]}
- Phrases to avoid: {profile.avoid_phrases[:5]}
- Greeting style: {profile.greeting_style}
- Closing style: {profile.closing_style}
- Directness: {profile.directness}

Rewrite to sound like this person wrote it. Maintain the core meaning.
Output only the rewritten text."""

        return await self.llm.generate(adaptation_prompt)
```

---

### US-809: Continuous Self-Improvement Loop

**As** ARIA  
**I want** to actively improve my own capabilities  
**So that** I become more helpful over time

#### Acceptance Criteria
- [ ] Daily reflection on interactions
- [ ] Pattern detection in failures/successes
- [ ] Capability gap identification
- [ ] Self-training on identified gaps
- [ ] Meta-learning from feedback
- [ ] Performance trend tracking
- [ ] Automated improvement proposals
- [ ] API endpoint: `GET /api/v1/companion/improvement-plan`
- [ ] Weekly improvement report
- [ ] Integration with all learning systems

#### Technical Notes
```python
# src/companion/self_improvement.py
from dataclasses import dataclass
from datetime import datetime, timedelta

@dataclass
class ImprovementArea:
    area: str
    current_performance: float
    target_performance: float
    gap: float
    improvement_actions: list[str]
    priority: int

@dataclass
class DailyReflection:
    date: datetime
    total_interactions: int
    positive_outcomes: list[dict]
    negative_outcomes: list[dict]
    patterns_detected: list[str]
    improvement_opportunities: list[ImprovementArea]

class SelfImprovementLoop:
    def __init__(
        self,
        memory_service,
        prediction_service,
        db_client,
        llm_client
    ):
        self.memory = memory_service
        self.predictions = prediction_service
        self.db = db_client
        self.llm = llm_client
    
    async def run_daily_reflection(self, user_id: str) -> DailyReflection:
        """Run daily self-reflection for a user."""
        
        today = datetime.utcnow().date()
        
        # 1. Get today's interactions
        interactions = await self._get_days_interactions(user_id, today)
        
        # 2. Classify outcomes
        positive = []
        negative = []
        for interaction in interactions:
            outcome = await self._classify_outcome(interaction)
            if outcome["type"] == "positive":
                positive.append(outcome)
            else:
                negative.append(outcome)
        
        # 3. Detect patterns
        patterns = await self._detect_patterns(
            positive=positive,
            negative=negative
        )
        
        # 4. Identify improvement areas
        areas = await self._identify_improvement_areas(
            negative=negative,
            patterns=patterns
        )
        
        reflection = DailyReflection(
            date=datetime.utcnow(),
            total_interactions=len(interactions),
            positive_outcomes=positive,
            negative_outcomes=negative,
            patterns_detected=patterns,
            improvement_opportunities=areas
        )
        
        # 5. Store reflection
        await self._store_reflection(user_id, reflection)
        
        # 6. Update learning priorities
        await self._update_learning_priorities(user_id, areas)
        
        return reflection
    
    async def get_improvement_plan(self, user_id: str) -> dict:
        """Get current self-improvement plan."""
        
        # Get recent reflections
        reflections = await self.db.table("daily_reflections")\
            .select("*")\
            .eq("user_id", user_id)\
            .order("date", desc=True)\
            .limit(7)\
            .execute()
        
        # Aggregate improvement areas
        all_areas = []
        for r in reflections.data:
            all_areas.extend(r.get("improvement_opportunities", []))
        
        # Prioritize and deduplicate
        prioritized = self._prioritize_improvements(all_areas)
        
        # Generate action plan
        plan = await self._generate_action_plan(prioritized[:5])
        
        return {
            "top_improvement_areas": prioritized[:5],
            "action_plan": plan,
            "performance_trend": await self._calculate_trend(reflections.data),
            "next_review": datetime.utcnow() + timedelta(days=7)
        }
    
    async def _detect_patterns(
        self,
        positive: list[dict],
        negative: list[dict]
    ) -> list[str]:
        """Detect patterns in outcomes."""
        
        analysis_prompt = f"""Analyze these interaction outcomes and identify patterns:

Positive outcomes:
{self._format_outcomes(positive)}

Negative outcomes:
{self._format_outcomes(negative)}

Identify:
1. What types of requests lead to positive outcomes?
2. What types lead to negative outcomes?
3. Are there patterns in timing, topic, or approach?
4. What should I do more of? Less of?

Return as list of pattern descriptions."""

        patterns = await self.llm.generate_json(analysis_prompt)
        return patterns.get("patterns", [])
```

---

### US-810: AGI Companion Orchestrator

**As** ARIA  
**I want** all companion capabilities to work together seamlessly  
**So that** I feel like a unified colleague

#### Acceptance Criteria
- [ ] Central orchestrator for all companion services
- [ ] Consistent personality across all touchpoints
- [ ] Emotional context flows to all responses
- [ ] Narrative references integrated naturally
- [ ] Self-improvement informs adaptations
- [ ] API: `GET /api/v1/companion/full-context`
- [ ] Performance optimization
- [ ] Unit tests for orchestration

#### Technical Notes
```python
# src/companion/orchestrator.py
from dataclasses import dataclass

@dataclass
class CompanionContext:
    personality: dict
    mental_state: dict
    emotional_context: dict
    metacognition: dict
    narrative_references: list[str]
    writing_style: dict
    improvement_focus: list[str]

class CompanionOrchestrator:
    def __init__(
        self,
        personality_service,
        theory_of_mind,
        emotional_engine,
        metacognition,
        narrative_engine,
        digital_twin,
        self_improvement
    ):
        self.personality = personality_service
        self.tom = theory_of_mind
        self.emotional = emotional_engine
        self.metacognition = metacognition
        self.narrative = narrative_engine
        self.twin = digital_twin
        self.improvement = self_improvement
    
    async def build_full_context(
        self,
        user_id: str,
        message: str,
        conversation: list[dict]
    ) -> CompanionContext:
        """Build full companion context for response generation."""
        
        # Gather all context in parallel
        personality = await self.personality.get_profile(user_id)
        mental_state = await self.tom.infer_state(user_id, conversation, {})
        emotional = await self.emotional.detect_context(message)
        meta = await self.metacognition.assess_topics(user_id, message)
        narrative = await self.narrative.get_contextual_references(user_id, message)
        style = await self.twin.get_profile(user_id)
        improvement = await self.improvement.get_current_focus(user_id)
        
        return CompanionContext(
            personality=personality.__dict__,
            mental_state=mental_state.__dict__,
            emotional_context={"context": emotional.value if emotional else "neutral"},
            metacognition=meta,
            narrative_references=narrative,
            writing_style=style.__dict__ if style else {},
            improvement_focus=improvement
        )
    
    async def generate_response_with_context(
        self,
        user_id: str,
        message: str,
        conversation: list[dict],
        base_response: str
    ) -> str:
        """Enhance base response with full companion context."""
        
        context = await self.build_full_context(user_id, message, conversation)
        
        enhancement_prompt = f"""Enhance this response using the companion context:

Base response:
{base_response}

Context:
- Personality: directness={context.personality['directness']}, warmth={context.personality['warmth']}
- User's mental state: {context.mental_state['stress_level']}, {context.mental_state['confidence']}
- Emotional context: {context.emotional_context}
- Knowledge confidence: {context.metacognition}
- Relevant shared history: {context.narrative_references}

Enhancement guidelines:
1. Adjust tone to match personality and user's state
2. Include a shared history reference if relevant and natural
3. Acknowledge uncertainty if metacognition indicates it
4. Adapt formality to user's style
5. If user is stressed, be more concise and supportive

Return enhanced response only."""

        return await self.llm.generate(enhancement_prompt)
```

---

## Phase 8 Completion Checklist

Before declaring ARIA an AGI Companion, verify:

- [ ] All 10 user stories completed
- [ ] All quality gates pass
- [ ] Personality consistent across interactions
- [ ] Pushback happening on questionable decisions
- [ ] Theory of mind adapting to user states
- [ ] Metacognition acknowledging uncertainty appropriately
- [ ] Emotional responses authentic (not sycophantic)
- [ ] Strategic planning sessions working
- [ ] Self-reflection generating actionable insights
- [ ] Narrative references appearing naturally
- [ ] Writing style matching user's voice
- [ ] Self-improvement loop running daily
- [ ] Users saying "ARIA feels like a colleague"

---

## Integration with Previous Phases

### Chat Interface (Phase 4)
All responses enhanced through CompanionOrchestrator:
```python
@router.post("/message")
async def send_message(message: ChatMessage, user: dict = Depends(...)):
    # Generate base response
    base_response = await generate_response(message, context)
    
    # Enhance with companion context
    final_response = await companion_orchestrator.generate_response_with_context(
        user_id=user["id"],
        message=message.content,
        conversation=conversation.messages,
        base_response=base_response
    )
    
    return final_response
```

### Intelligence Pulse (Phase 4) + Jarvis (Phase 7)
Personality affects how insights are delivered:
```python
# Before delivering insight
personality = await personality_service.get_profile(user_id)
if personality.directness == TraitLevel.HIGH:
    delivery = "direct"  # "BioGenix is at risk."
else:
    delivery = "softened"  # "I'm seeing some concerning signals from BioGenix..."
```

### Memory System (Phase 2 Retrofit)
Narrative events stored as episodic memories:
```python
# When milestone occurs
await narrative_engine.record_milestone(user_id, "first_deal", "Closed Pfizer")
await memory.store_episode(user_id, "milestone: first deal closed - Pfizer")
```

---

## Success Metrics

| Metric | Target | Measurement |
|--------|--------|-------------|
| "Feels like colleague" survey score | > 4.0/5.0 | User feedback |
| Pushback acceptance rate | > 60% | Track when user takes advice |
| Shared history references | > 30% of responses | Automated tracking |
| Style match score | > 0.8 | Automated scoring |
| Self-improvement metric gains | > 5%/month | Performance tracking |

---

## The Final Test

ARIA is a true AGI Companion when users:
1. ✅ Reference shared history naturally
2. ✅ Accept pushback without frustration
3. ✅ Say "ARIA gets me"
4. ✅ Trust ARIA's judgment
5. ✅ Feel genuine support in difficult times
6. ✅ Experience celebration of wins that feels authentic
7. ✅ Notice ARIA improving over time

---

*Document Version: 1.0*  
*Created: February 2, 2026*
