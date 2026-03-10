# ARIA Skill: Life Sciences Lead Generation Intelligence v2
## Dynamic, ARIA-Native, End-to-End Pipeline Intelligence

**Skill ID:** `life-sciences-lead-gen`
**Version:** 2.0
**Skill Type:** Layer 2 (LLM-Powered Skill Definition)
**Primary Agent:** Hunter (`agents/hunter.py`)
**Supporting Agents:** Scout (`agents/scout.py`), Analyst (`agents/analyst.py`), Scribe (`agents/scribe.py`), Strategist (`agents/strategist.py`), Operator (`agents/operator.py`)
**ARIA Tables Touched:** `lead_memories`, `lead_memory_events`, `lead_memory_stakeholders`, `lead_memory_insights`, `lead_memory_crm_sync`, `lead_memory_contributions`, `lead_icp_profiles`, `discovered_leads`, `memory_semantic`, `market_signals`, `monitored_entities`, `battle_cards`, `corporate_facts`, `email_drafts`, `calendar_events`, `aria_activity`, `integration_push_queue`
**Memory Systems:** Semantic (Supabase `memory_semantic`), Episodic (Graphiti/Neo4j), Corporate (`corporate_facts`), Lead Memory (6 tables), Knowledge Graph (Graphiti)

---

## DESIGN PHILOSOPHY: DYNAMIC, NOT HARD-CODED

This skill contains ZERO hard-coded company lists, ZERO static sub-industry taxonomies, and ZERO fixed buyer persona templates. Everything is discovered dynamically from three sources:

1. **Onboarding enrichment data** -- ARIA learns the user's sub-industry, modality, competitive landscape, and buyer personas from the 9-stage Exa enrichment pipeline during onboarding (US-903)
2. **User's ICP definition** -- Stored in `lead_icp_profiles`, refined through conversation and observed outcomes
3. **Continuous learning** -- Every won/lost deal, every trigger event response, every outreach outcome feeds back into the skill's understanding of what works for THIS user in THIS sub-industry

The skill provides the FRAMEWORK for how to think about life sciences lead generation. ARIA fills in the specifics dynamically.

---

## PART 1: DYNAMIC SUB-INDUSTRY INTELLIGENCE

### 1.1 How ARIA Learns the User's Context

During onboarding (US-902 + US-903), ARIA's enrichment pipeline classifies the user's company:

```
Enrichment Stage 1 (LLM Classification) produces:
  - company_type: e.g., "CDMO", "CRO", "Equipment Manufacturer", "Biotech", etc.
  - primary_modality: e.g., "Cell & Gene Therapy", "Monoclonal Antibodies", "Small Molecule", etc.
  - company_posture: "Buyer" or "Seller" of services
  - therapeutic_areas: ["Oncology", "Rare Disease", ...]
```

These classifications are stored in `corporate_facts` and `memory_semantic`. The skill uses them to dynamically configure ALL downstream behavior.

### 1.2 The Sub-Industry Context Object

ARIA should build and maintain a `SubIndustryContext` in memory that adapts everything. This is NOT a static taxonomy -- it's built from enrichment data and refined over time.

```
SubIndustryContext (constructed dynamically, stored in memory_semantic):
{
  "user_company": {
    "type": <from enrichment>,
    "modality": <from enrichment>,
    "posture": <from enrichment>,  // "buyer" or "seller"
    "therapeutic_areas": <from enrichment>,
    "company_size": <from enrichment>,
    "geography": <from enrichment>,
    "regulatory_markets": <from enrichment>  // FDA, EMA, PMDA, etc.
  },
  "target_profile": {
    "who_does_user_sell_to": <inferred from posture + type>,
    "typical_buyer_roles": <discovered from enrichment + user input>,
    "typical_sales_cycle_days": <starts with industry default, refined from data>,
    "typical_deal_size": <from user input or inferred>,
    "typical_buying_committee_size": <starts with industry default, refined>
  },
  "competitive_context": {
    "competitors": <from enrichment Stage 5 FindSimilar + monitored_entities>,
    "competitive_positioning": <from enrichment + user input>,
    "differentiators": <from user input during onboarding>
  },
  "trigger_event_relevance": {
    // Dynamically weighted based on sub-industry
    // See Section 2.4 for the dynamic weighting system
  }
}
```

### 1.3 Why This Matters: Same Industry, Radically Different Lead Gen

Consider three users who all check "life sciences" during onboarding:

**User A: CDMO specializing in cell & gene therapy manufacturing**
- Sells TO: Biotech companies with cell/gene therapy pipelines
- Key triggers: IND filings for CGT programs, Phase transitions, FDA CGT guidance changes, facility buildout announcements by competitors
- Key buyers: VP Process Development, VP Manufacturing, Head of Supply Chain
- Key data: ClinicalTrials.gov (CGT trials), FDA (BLA filings, CGT guidance), facility expansion news
- Deal cycle: 6-18 months, relationship-heavy, GMP qualification required

**User B: CRO specializing in oncology Phase II/III trials**
- Sells TO: Pharma/biotech with oncology pipeline advancing to late stage
- Key triggers: Phase II data readouts (positive = client needs Phase III CRO), FDA Breakthrough designations, ASCO/AACR poster presentations
- Key buyers: VP Clinical Operations, VP Biostatistics, Head of Regulatory
- Key data: ClinicalTrials.gov (oncology trials by phase), ASCO abstract databases, FDA PDUFA calendar
- Deal cycle: 3-9 months, RFP-driven, competitive bid process

**User C: Lab equipment manufacturer selling chromatography systems**
- Sells TO: CDMOs, pharma manufacturing, biotech R&D labs
- Key triggers: Facility expansions, new manufacturing lines, GMP capacity additions, process development hiring
- Key buyers: Lab Manager, VP R&D, Head of Procurement, Process Development Scientists
- Key data: Job postings (process development), facility expansion announcements, GPO contracts
- Deal cycle: 1-6 months, often procurement-led for capital equipment

**The skill must adapt to all three dynamically.** The ICP criteria, trigger events, buyer personas, data sources, outreach messaging, and scoring weights are ALL different. Nothing is hard-coded.

### 1.4 Dynamic Trigger Event Weighting

Instead of a static list of trigger events with fixed signal strengths, ARIA dynamically weights triggers based on the `SubIndustryContext`:

```
TRIGGER RELEVANCE FRAMEWORK (resolved at runtime):

For each trigger event type, ARIA asks:
  1. Does this trigger create a BUYING need for what the user sells?
  2. How directly? (direct need = high, indirect = medium, tangential = low)
  3. How time-sensitive is the buying window?
  4. Can ARIA detect this trigger from available data sources?

The answers differ by sub-industry:
  - "FDA approval received" is CRITICAL for a CDMO (client needs commercial manufacturing)
    but LOW for a lab equipment company (approval doesn't change lab equipment needs)
  - "Facility expansion announced" is CRITICAL for a lab equipment company
    but MEDIUM for a CRO (facility expansion doesn't mean they need outsourced trials)
  - "Phase II to Phase III advancement" is CRITICAL for a CRO
    but MEDIUM for a CDMO (they may already be contracted for earlier phase work)
```

ARIA should compute trigger relevance weights during onboarding and store them in `memory_semantic` with `source: 'skill_configuration'`. These weights are refined as ARIA observes which triggers actually produce meetings and revenue.

### 1.5 Dynamic Buyer Persona Discovery

Instead of hard-coded persona templates, ARIA discovers buyer personas through:

1. **Onboarding enrichment** -- Leadership mapping (Exa People Search, Stage 6) of target accounts identifies common titles
2. **User's existing contacts** -- Calendar events, email threads, CRM contacts reveal who the user actually sells to
3. **Won deal analysis** -- Which titles were involved in closed deals? Store as `memory_semantic` facts
4. **Industry research** -- Analyst agent researches typical buying committee for this sub-industry

ARIA builds a dynamic persona map and stores it:

```
Memory write (memory_semantic):
  fact: "For [user's sub-industry], typical buying committee includes: [role1], [role2], [role3]"
  confidence: 0.6 (enrichment-derived) -> increases to 0.9+ after deal data confirms
  source: "skill_lead_gen_persona_discovery"
  metadata: {
    "entity_type": "buyer_persona",
    "roles": ["VP Process Development", "Head of Procurement", "VP Quality"],
    "derived_from": "enrichment + calendar_analysis",
    "last_validated": "2026-03-10"
  }
```

---

## PART 2: ARIA-NATIVE LEAD DISCOVERY

### 2.1 ICP Storage and Management

ICPs are stored in ARIA's `lead_icp_profiles` table, NOT in the skill definition:

```sql
-- Table: lead_icp_profiles (already exists)
-- Stores user-defined ICP criteria that ARIA uses for lead discovery
-- Key fields: user_id, criteria (JSONB), name, is_active
```

When the user describes their ICP (in conversation or during onboarding), ARIA should:

1. Parse the ICP into structured criteria
2. Store in `lead_icp_profiles` via `POST /api/v1/leads/icp`
3. Store individual ICP facts in `memory_semantic` for cross-reference:
   ```
   fact: "User targets CDMOs with cell therapy manufacturing capability in North America"
   confidence: 0.95
   source: "user_stated"
   ```
4. Use these criteria for ALL subsequent lead discovery

### 2.2 Lead Discovery: The ARIA Agent Orchestration

Lead discovery is a multi-agent workflow coordinated by the SkillOrchestrator through the OODA loop (`core/ooda.py`):

**OBSERVE Phase:**
- Scout (`agents/scout.py`) monitors trigger events from:
  - `market_signals` table (existing signals, 238+ for test user)
  - Exa Search (category="news") for tracked companies via `monitored_entities`
  - Job posting monitoring via Exa Search
  - SEC filing monitoring for earnings language
- Scout writes new signals to `market_signals`:
  ```sql
  INSERT INTO market_signals (id, user_id, company_name, signal_type, headline, summary, source_url, relevance_score, metadata, created_at)
  VALUES (gen_random_uuid(), user_id, company_name, signal_type, headline, summary, url, relevance, metadata, NOW());
  ```

**ORIENT Phase:**
- Analyst (`agents/analyst.py`) enriches detected signals:
  - ClinicalTrials.gov API (v2) for pipeline data
  - OpenFDA API for regulatory history
  - PubMed E-utilities for publication/KOL data
  - SEC EDGAR for financial data
  - Exa Company Search for structured company data
  - Exa People Search for contact discovery
- Analyst writes enrichment facts to `memory_semantic`:
  ```sql
  INSERT INTO memory_semantic (id, user_id, fact, confidence, source, metadata, created_at, updated_at)
  VALUES (gen_random_uuid(), user_id, fact_text, confidence_score, 'analyst_enrichment',
    jsonb_build_object('entity_type', 'company', 'company_name', name, 'data_source', api_name),
    NOW(), NOW());
  ```

**DECIDE Phase:**
- Strategist (`agents/strategist.py`) evaluates:
  - Does this company match the active ICP from `lead_icp_profiles`?
  - What is the computed lead score? (see Section 3)
  - What action should ARIA recommend?
- Strategist uses the dynamic `SubIndustryContext` to adjust scoring weights

**ACT Phase:**
- Hunter (`agents/hunter.py`) executes the decision:
  - Creates lead in `lead_memories`:
    ```sql
    INSERT INTO lead_memories (id, user_id, company_name, lifecycle_stage, status, health_score, metadata, first_touch_at, created_at, updated_at)
    VALUES (gen_random_uuid(), user_id, company_name, 'lead', 'active', computed_score,
      jsonb_build_object('source', 'signal_triggered', 'trigger_type', signal_type, 'icp_match_score', match_score),
      NOW(), NOW(), NOW());
    ```
  - Creates stakeholder records in `lead_memory_stakeholders`:
    ```sql
    INSERT INTO lead_memory_stakeholders (id, lead_memory_id, contact_email, contact_name, title, role, influence_level, sentiment, created_at)
    VALUES (gen_random_uuid(), lead_id, email, name, title, inferred_role, inferred_influence, 'unknown', NOW());
    ```
  - Logs discovery event in `lead_memory_events`:
    ```sql
    INSERT INTO lead_memory_events (id, lead_memory_id, event_type, direction, subject, content, occurred_at, source, metadata, created_at)
    VALUES (gen_random_uuid(), lead_id, 'signal', NULL, 'Lead discovered via [trigger_type]',
      event_detail, NOW(), 'aria_discovery',
      jsonb_build_object('trigger_signal_id', signal_id, 'icp_match_score', score), NOW());
    ```
  - Logs activity in `aria_activity`:
    ```sql
    INSERT INTO aria_activity (id, user_id, activity_type, title, description, metadata, created_at)
    VALUES (gen_random_uuid(), user_id, 'lead_discovered', 'New lead: [company]',
      'Discovered via [trigger_type]. ICP match: [score]%.',
      jsonb_build_object('lead_id', lead_id, 'company_name', name), NOW());
    ```
  - Presents to user via Action Queue (`/actions` page) or chat message for approval

### 2.3 Discovery Data Sources: ARIA's Actual Integrations

ARIA uses these ACTUAL integrations (not hypothetical):

| Data Source | ARIA Integration | Agent | API/Method |
|-------------|-----------------|-------|------------|
| ClinicalTrials.gov | `agents/analyst.py` | Analyst | v2 REST API with retry logic |
| PubMed/NCBI | `agents/analyst.py` | Analyst | E-utilities search + summary |
| OpenFDA | `agents/analyst.py` | Analyst | REST API (drug, device data) |
| ChEMBL | `agents/analyst.py` | Analyst | REST API (chemical data) |
| Exa Company Search | `agents/capabilities/enrichment_providers/exa.py` | Hunter | `category="company"` |
| Exa People Search | `agents/capabilities/enrichment_providers/exa.py` | Hunter | `category="people"` |
| Exa Research | `agents/capabilities/enrichment_providers/exa.py` | Analyst | Agentic end-to-end research |
| Exa FindSimilar | `agents/capabilities/enrichment_providers/exa.py` | Hunter | Lookalike company discovery |
| Exa News Search | `agents/capabilities/enrichment_providers/exa.py` | Scout | `category="news"` with date filter |
| Exa Websets | `agents/capabilities/enrichment_providers/exa.py` | Hunter | Async bulk lead generation |
| Perplexity API | Private beta (March 2026) | Scout/Analyst | Real-time web intelligence |
| Gmail/Outlook | Composio OAuth | Operator/Scribe | Email threading, response tracking |
| Salesforce/HubSpot | Composio OAuth (Direct OAuth planned) | Operator | CRM bidirectional sync |
| Google Calendar | Composio OAuth | Operator | Meeting detection, contact extraction |
| LinkedIn | Composio OAuth | Hunter | Profile enrichment, relationship mapping |
| SEC EDGAR | Public API (no auth) | Scout/Analyst | Earnings transcripts, 10-K/10-Q filings |

**Latency tiers** (per ARIA_EXA_INTEGRATION_ARCHITECTURE.md):
- Tier 1 (<500ms): Exa Instant -- real-time chat answers
- Tier 2 (2-10s): Exa Fast + Company/People Search -- interactive enrichment
- Tier 3 (5-30s): Exa Deep + Research -- onboarding enrichment
- Tier 4 (minutes): Exa Research + Websets -- async background jobs (daily briefing, bulk lead gen)

### 2.4 Discovery Workflows (ARIA-Native)

**Workflow 1: Territory Discovery (Goal-Driven)**
```
User creates goal: "Build pipeline in [territory/segment]"
  -> Goal system (goals table) creates goal with sub-tasks
  -> goal_agents dispatches Hunter via GoalExecutionService
  -> Hunter.execute() with task:
     {
       "icp": <from lead_icp_profiles>,
       "target_count": N,
       "exclusions": <from lead_memories WHERE status != 'lost'>
     }
  -> Hunter queries Exa Company Search with ICP criteria
  -> For each result: Analyst enriches, Hunter scores
  -> Results written to lead_memories + lead_memory_stakeholders
  -> Strategist builds account plan (account_plans table)
  -> User sees results on /pipeline page + /actions approval queue
```

**Workflow 2: Signal-Triggered Discovery (Autonomous)**
```
Scout's daily signal scan detects trigger at [company]:
  -> market_signals INSERT
  -> Scout checks: Does company match any active ICP in lead_icp_profiles?
  -> If match:
     -> Hunter creates lead_memories record (lifecycle_stage: 'signal_detected')
     -> Analyst enriches company
     -> Hunter finds contacts via Exa People Search
     -> Present to user as Action Queue item:
        "ARIA detected [trigger] at [company]. They match your ICP. Add to pipeline?"
  -> If already a lead:
     -> lead_memory_events INSERT (event_type: 'signal')
     -> Health score recalculated via health_score.py HealthScoreCalculator
     -> If health_score changed significantly (20+ points): surface alert on /pipeline
```

**Workflow 3: Relationship-Based Discovery**
```
Calendar event or email detected with new company:
  -> EventTriggerService (event_trigger_service.py) classifies event
  -> If new company detected (not in lead_memories):
     -> Hunter auto-creates lead (lifecycle_stage: 'engaged', source: 'inbound')
     -> Contact extracted from calendar/email -> lead_memory_stakeholders
     -> lead_memory_events INSERT (event_type: 'meeting' or 'email_received')
     -> Memory write: memory_semantic fact about new relationship
     -> Activity: aria_activity INSERT
```

**Workflow 4: Lookalike Discovery**
```
User asks: "Find companies like [existing lead/account]"
  -> Analyst builds profile from lead_memories metadata + corporate_facts
  -> Hunter queries Exa FindSimilar with reference company URL
  -> Hunter queries Exa Company Search with extracted attributes
  -> Dedup against existing lead_memories (case-insensitive company_name)
  -> Score and present
```

---

## PART 3: DYNAMIC LEAD SCORING

### 3.1 Scoring Architecture

ARIA already has `health_score.py` (HealthScoreCalculator) with a 5-factor weighted model:
- Communication frequency: 25%
- Response time: 20%
- Sentiment: 20%
- Stakeholder breadth: 20%
- Stage velocity: 15%

This skill EXTENDS that for lead discovery scoring (pre-engagement). The discovery score determines whether a newly detected company should become a lead.

### 3.2 Discovery Score (0-100, Dynamic Weights)

The weights are NOT fixed. They're adjusted based on `SubIndustryContext`:

**Dimension 1: ICP Fit (base weight: 30%, adjustable 20-40%)**
- Criteria match against active `lead_icp_profiles`
- Sub-industry match, modality match, geography match, size match
- Weight increases when user has a narrow, well-defined ICP
- Weight decreases when user is exploring new market segments

**Dimension 2: Trigger Signal Relevance (base weight: 30%, adjustable 20-40%)**
- Based on dynamic trigger relevance weights (Section 1.4)
- Multiple concurrent triggers compound (+bonus)
- Recency multiplier: last 30 days = 1.0x, 31-60 = 0.8x, 61-90 = 0.6x
- Weight increases for sub-industries with clear trigger-to-purchase correlation
- Weight decreases for sub-industries with long, relationship-driven cycles

**Dimension 3: Relationship & Access (base weight: 25%, adjustable 15-35%)**
- Does user know anyone at this company? (check `memory_semantic` for relationship facts)
- Previous interaction history in ARIA (lead_memory_events count)
- Shared conference attendance (calendar_events overlap)
- Warm introduction available (LinkedIn mutual connections)
- Weight increases for sub-industries where relationships drive purchasing (CDMOs, consultants)

**Dimension 4: Buying Readiness (base weight: 15%, adjustable 10-25%)**
- Hiring signals for relevant roles (Exa search, job postings)
- Technology evaluation signals (if detectable)
- Budget cycle alignment (fiscal year timing)
- Competitive displacement opportunity (competitor issues detected in market_signals)
- Weight increases for transactional sub-industries (consumables, reagents)

### 3.3 Score Storage

Discovery scores are stored in `lead_memories.health_score` (0-100) and detailed breakdown in `lead_memories.metadata`:

```json
{
  "discovery_score": {
    "total": 78,
    "icp_fit": {"score": 85, "weight": 0.30, "weighted": 25.5},
    "trigger_relevance": {"score": 90, "weight": 0.30, "weighted": 27.0, "triggers": ["phase_3_advancement", "hiring_vp_manufacturing"]},
    "relationship": {"score": 60, "weight": 0.25, "weighted": 15.0, "mutual_contacts": 1},
    "buying_readiness": {"score": 70, "weight": 0.15, "weighted": 10.5, "signals": ["hiring_relevant_roles"]}
  },
  "scoring_context": {
    "sub_industry": "CDMO - Cell & Gene Therapy",
    "weights_source": "dynamic_from_enrichment",
    "scored_at": "2026-03-10T14:30:00Z"
  }
}
```

### 3.4 Lifecycle Stage Transitions

ARIA uses `lead_memories.lifecycle_stage` with these values:
- `lead` -- Matches ICP, may have trigger signals
- `opportunity` -- Active engagement, meeting set or demo requested
- `account` -- Closed won, ongoing relationship

Transitions are tracked in `lead_memory_events` and trigger:
1. `lead_memory_events` INSERT (event_type: 'stage_transition')
2. Health score recalculation
3. CRM push via `integration_push_queue` (if CRM connected)
4. `memory_semantic` fact update
5. `aria_activity` INSERT

---

## PART 4: ENRICHMENT PROTOCOL (ARIA'S 9-STAGE PIPELINE)

When ARIA enriches a lead, it runs the same 9-stage Exa enrichment pipeline used during onboarding (per ARIA_EXA_INTEGRATION_ARCHITECTURE.md Section 5), adapted for lead context:

```
Stage 1: Classification (LLM) -> company_type, modality, posture
Stage 2: Structured Data (Exa Company Search) -> HQ, workforce, funding
Stage 3: Deep Research (Exa Research) -> products, customers, strategy
Stage 4: Product Catalog (Exa Deep + Contents) -> product details
Stage 5: Competitor ID (Exa FindSimilar + Company Search) -> competitive map
Stage 6: Leadership Mapping (Exa People Search) -> buying committee contacts
Stage 7: News & Signals (Exa Search, news) -> recent events
Stage 8: Scientific/Regulatory (Exa + PubMed + ClinicalTrials.gov + OpenFDA) -> pipeline/regulatory
Stage 9: Causal Hypotheses (LLM) -> inferred insights for knowledge graph
```

**Every stage writes to ARIA's memory:**
- Stages 1-5: `memory_semantic` (facts about the company, confidence scored, source attributed)
- Stage 6: `lead_memory_stakeholders` (contacts discovered)
- Stage 7: `market_signals` (recent events about this company)
- Stage 8: `memory_semantic` (scientific/regulatory facts)
- Stage 9: Graphiti/Neo4j (causal edges for knowledge graph)

**Enrichment quality score** (stored in `lead_memories.metadata.enrichment_quality`):
- 0-20: Classification only
- 20-40: Basic research
- 40-60: Good intelligence
- 60-80: Comprehensive
- 80-100: Full corporate memory

---

## PART 5: OUTREACH INTELLIGENCE (ARIA-NATIVE)

### 5.1 Dynamic Outreach: Scribe + Digital Twin

ARIA's outreach is generated by the Scribe agent (`agents/scribe.py`), which:
1. Reads the user's Digital Twin for writing style, tone, and preferences
2. Reads `SubIndustryContext` for domain-appropriate language
3. Reads `lead_memories` + `lead_memory_stakeholders` for personalization
4. Reads `memory_semantic` for facts about the target company
5. Reads `market_signals` for the specific trigger to reference

**Scribe writes drafts to `email_drafts`:**
```sql
INSERT INTO email_drafts (id, user_id, recipient, recipient_company, subject, body, status, metadata, created_at, updated_at)
VALUES (gen_random_uuid(), user_id, contact_email, company_name, subject, body, 'draft',
  jsonb_build_object('lead_memory_id', lead_id, 'trigger_signal_id', signal_id, 'persona_type', persona,
    'sequence_position', touch_number, 'sequence_total', 7),
  NOW(), NOW());
```

### 5.2 Dynamic Persona Adaptation

Instead of hard-coded persona templates, Scribe adapts based on:

**From `lead_memory_stakeholders.title`:** Determines seniority and function
**From `lead_memory_stakeholders.role`:** decision_maker, influencer, champion, blocker, user
**From `memory_semantic` facts about the contact:** Education (PhD? -> technical language), career history, publications
**From `SubIndustryContext.target_profile.typical_buyer_roles`:** Confirms which persona map to apply

Scribe selects messaging approach dynamically:
- **Senior executive** (C-suite, VP+): Strategic, ROI-focused, competitive insight-led. Short.
- **Technical leader** (PhD, scientist, engineer): Evidence-based, scientifically precise, peer-level.
- **Procurement / Operations**: TCO, compliance, efficiency metrics, vendor qualification.
- **Quality / Regulatory**: Compliance-first, validation status, risk mitigation.

### 5.3 Outreach Sequencing with Memory Tracking

Every outreach touch is tracked end-to-end:

```
Touch 1 (Day 1, Email):
  -> Scribe drafts -> email_drafts INSERT (status: 'draft')
  -> User approves on /communications page or chat
  -> Operator sends via Composio (Gmail/Outlook)
  -> lead_memory_events INSERT (event_type: 'email_sent', direction: 'outbound')
  -> aria_activity INSERT
  -> health_score recalculated

Touch 2 (Day 4, LinkedIn):
  -> Scribe drafts connection request
  -> lead_memory_events INSERT (event_type: 'linkedin_outreach', direction: 'outbound')

Touch 3-7: Same pattern, each tracked in lead_memory_events

Response detected (inbound email via EventTriggerService):
  -> EventTriggerService classifies email
  -> lead_memory_events INSERT (event_type: 'email_received', direction: 'inbound')
  -> LeadInsightService analyzes for buying signals
  -> lead_memory_insights INSERT (insight_type: 'buying_signal' or 'objection')
  -> health_score recalculated (response = significant positive signal)
  -> lead_memories.lifecycle_stage transition if appropriate
  -> CRM push via integration_push_queue
```

### 5.4 Timing Intelligence

ARIA learns optimal send times from outcome data, but starts with industry-informed defaults:

**ARIA stores timing preferences in `memory_semantic`:**
```
fact: "Optimal email send time for [sub-industry] contacts: Tuesday-Thursday, 7-9 AM recipient local time"
confidence: 0.5 (industry default) -> refined based on response data
source: "skill_lead_gen_timing"
```

**Conference blackout logic:**
- ARIA checks `calendar_events` for conference entries
- Cross-references with `lead_memory_stakeholders` company to infer attendance
- Suppresses outreach during conference week, queues for week after
- Stores conference calendar as `memory_semantic` facts for future reference

---

## PART 6: CRM INTEGRATION (END-TO-END)

### 6.1 CRM Sync Architecture

ARIA's CRM sync is bidirectional via `crm_sync.py` (CRMSyncService) + `deep_sync.py` (DeepSyncService):

**ARIA -> CRM (Push):**
Every significant lead action queues a CRM update:
```sql
INSERT INTO integration_push_queue (id, user_id, integration_type, action, payload, status, created_at)
VALUES (gen_random_uuid(), user_id, 'salesforce', 'upsert_lead', 
  jsonb_build_object('lead_data', lead_data, 'aria_insights', insights), 
  'pending', NOW());
```

Push triggers:
- New lead created -> CRM lead/contact creation
- Lifecycle stage change -> CRM opportunity stage update
- New stakeholder discovered -> CRM contact creation
- Health score significant change -> CRM custom field update
- Meeting set -> CRM activity creation

**CRM -> ARIA (Pull):**
- Scheduled sync via `deep_sync.py`
- Webhook receiver for real-time CRM updates
- Conflict resolution (per US-511):
  - CRM wins: lifecycle_stage, expected_value, expected_close_date
  - ARIA wins: health_score, insights, stakeholder_map

**Sync state tracked in `lead_memory_crm_sync`:**
```sql
-- One row per lead, tracks sync state
UPDATE lead_memory_crm_sync 
SET last_push_at = NOW(), status = 'synced', pending_changes = '[]'
WHERE lead_memory_id = lead_id;
```

### 6.2 What ARIA Pushes to CRM (Tagged [ARIA])

Per US-511, ARIA pushes summaries to CRM notes tagged `[ARIA]`:
- Meeting prep briefs
- Lead intelligence summaries
- Health score explanations
- Buying signal detections
- Recommended next actions

---

## PART 7: MEMORY WRITE PROTOCOL

### 7.1 Every Lead Gen Action Writes to Memory

This is the critical integration point. NOTHING should happen in lead gen without a corresponding memory write:

| Action | Primary Table | Secondary Writes |
|--------|--------------|------------------|
| New lead discovered | `lead_memories` INSERT | `lead_memory_events`, `aria_activity`, `memory_semantic` (company facts) |
| Contact found | `lead_memory_stakeholders` INSERT | `memory_semantic` (contact facts), Graphiti (relationship edge) |
| Trigger event detected | `market_signals` INSERT | `lead_memory_events` (if linked to existing lead), `aria_activity` |
| Enrichment completed | `memory_semantic` (multiple INSERTs) | `lead_memories.metadata.enrichment_quality` UPDATE, Graphiti (entity nodes + edges) |
| Email sent | `email_drafts` UPDATE (status: 'sent') | `lead_memory_events` INSERT, `aria_activity`, `integration_push_queue` (CRM) |
| Response received | `lead_memory_events` INSERT | `lead_memory_insights` (buying signals), `health_score` recalc, `lead_memory_crm_sync` |
| Meeting scheduled | `calendar_events` | `lead_memory_events`, `lead_memories.lifecycle_stage` transition, `integration_push_queue` |
| Stage transition | `lead_memories` UPDATE | `lead_memory_events`, `health_score_history`, `integration_push_queue`, `aria_activity` |
| Lead won/lost | `lead_memories` UPDATE | `memory_semantic` (outcome facts for learning), `goal_retrospectives`, Graphiti |
| ICP refined | `lead_icp_profiles` UPDATE | `memory_semantic` (ICP facts) |
| Score recalculated | `lead_memories.health_score` UPDATE | `health_score_history` INSERT |
| Battle card created | `battle_cards` INSERT | `memory_semantic` (competitive facts), `monitored_entities` (if new competitor) |
| Competitor detected | `monitored_entities` INSERT | `battle_cards` INSERT (auto-generated), `memory_semantic` |

### 7.2 Memory Confidence Hierarchy

When writing to `memory_semantic`, ARIA uses this confidence hierarchy (per US-911):
- `user_stated` (0.95): User explicitly told ARIA something
- `crm_import` (0.85): Data from CRM system
- `document_upload` (0.80): Extracted from user's documents
- `email_bootstrap` (0.75): Inferred from email content
- `enrichment` (0.60-0.70): From Exa/web research
- `inferred` (0.40-0.60): ARIA's causal hypotheses
- `skill_configuration` (0.50): Skill defaults, refined over time

### 7.3 Graphiti Knowledge Graph Integration

For relationship intelligence, ARIA writes to Graphiti (Neo4j):
- **Entity nodes:** Companies, people, products, therapeutic areas
- **Relationship edges:** "works_at", "sells_to", "competes_with", "attended_meeting_with"
- **Causal edges:** "Phase III advancement -> manufacturing capacity need" (tagged `inferred_during_enrichment`)

This powers meeting prep briefs and relationship-based lead discovery.

---

## PART 8: PROACTIVE BEHAVIORS (AUTONOMOUS)

ARIA should fire these autonomously, not wait for user to ask:

### 8.1 Daily Briefing Integration
Scout's daily signal scan feeds into `daily_briefings` generation:
```
"3 new trigger events in your territory:
  - [Company A]: Phase III data readout positive (pipeline trigger)
  - [Company B]: VP Manufacturing hired (hiring trigger)  
  - [Company C]: Facility expansion announced (capacity trigger)
All three match your ICP. Want me to create leads?"
```

### 8.2 Pipeline Health Alerts
ARIA monitors `lead_memories` and surfaces via Action Queue:
- "5 leads haven't been contacted in 30+ days" (stale lead alert)
- "Lead [company] health dropped from 72 to 48" (health drop alert)
- "[Company]'s competitor just had a product recall -- opportunity to re-engage" (competitive displacement)

### 8.3 Conference Preparation
When calendar event matches a known conference name:
- Cross-reference exhibitor/attendee list with ICP
- Present target list with talking points
- Pre-draft outreach for post-conference follow-up

### 8.4 Win/Loss Learning Loop
After every `lead_memories.status` change to 'won' or 'lost':
- ARIA stores outcome facts in `memory_semantic`
- Analyzes: Which trigger originated this? Which persona responded? What was the cycle time?
- Adjusts scoring weights in `SubIndustryContext`
- Stores learning: `memory_semantic` INSERT with `source: 'win_loss_analysis'`

---

## PART 9: LIFE SCIENCES DOMAIN KNOWLEDGE

### 9.1 What ARIA Must Understand (Dynamically Deepened)

ARIA starts with foundational life sciences knowledge and deepens it based on the user's sub-industry:

**Universal knowledge (all life sciences):**
- Regulatory bodies: FDA, EMA, PMDA, NMPA, Health Canada, TGA
- Quality standards: GMP, GLP, GCP, GDP, ISO 13485 (devices)
- Compliance: 21 CFR Part 11, HIPAA, GDPR, Sunshine Act
- Sales cycle characteristics: Long, multi-stakeholder, compliance-constrained, science-driven credibility
- Key data sources: ClinicalTrials.gov, PubMed, OpenFDA, SEC EDGAR, USPTO

**Sub-industry-specific knowledge (learned during enrichment):**
- ARIA deepens its knowledge of the user's specific sub-industry by:
  1. Enrichment Stage 3 (Exa Research) on the user's company and competitors
  2. Analyst research on the user's therapeutic areas and modalities
  3. Ongoing Scout monitoring of the user's market
  4. User corrections and feedback stored as high-confidence `memory_semantic` facts

### 9.2 Terminology Correctness

ARIA must use terminology correctly. Misusing a term in outreach destroys credibility. Rather than a static glossary, ARIA should:

1. During enrichment, build a dynamic glossary of terms relevant to the user's sub-industry
2. Store in `memory_semantic` with `entity_type: 'terminology'`
3. Reference when generating outreach via Scribe
4. Flag uncertain terminology for user review before sending

### 9.3 Anti-Patterns (Universal)

These apply regardless of sub-industry:

1. Never send identical messages to multiple contacts at the same company
2. Never reference a clinical trial failure without sensitivity
3. Never guess at scientific terminology -- research first
4. Never ignore the quality/regulatory stakeholder in regulated environments
5. Never spam during conference weeks
6. Never make product claims that haven't been through the user's MLR review process
7. Never share one company's proprietary intelligence with another
8. Never assume a company's sub-industry classification is permanent -- companies pivot, expand, and diversify

---

## PART 10: CONTINUOUS LEARNING & SELF-IMPROVEMENT

### 10.1 Feedback Loops

The skill improves itself through these feedback loops:

| Signal | What ARIA Learns | Memory Update |
|--------|-----------------|---------------|
| Email responded to | Which trigger + persona + message style works | `memory_semantic`: "Outreach referencing [trigger_type] to [persona] at [sub_industry] got response" |
| Meeting booked | Which leads convert to meetings | Increase trigger weight for that trigger type |
| Deal won | Full lifecycle analysis | Win factors stored; scoring weights adjusted |
| Deal lost | What went wrong | Loss factors stored; disqualification criteria refined |
| User edits ARIA's draft | What ARIA got wrong about tone/content | Digital Twin refined; persona approach adjusted |
| User overrides score | ARIA's scoring was off | Weight adjustment for relevant dimension |
| User adds contact manually | ARIA missed a stakeholder | Improve People Search queries for this sub-industry |

### 10.2 Learning Storage

All learning is stored in `memory_semantic` with structured metadata:
```json
{
  "entity_type": "skill_learning",
  "skill_id": "life-sciences-lead-gen", 
  "learning_type": "trigger_effectiveness",
  "data": {
    "trigger_type": "phase_3_advancement",
    "sub_industry": "CRO - Oncology",
    "outcome": "meeting_booked",
    "cycle_days": 14,
    "recorded_at": "2026-03-10"
  }
}
```

This enables ARIA to answer meta-questions like:
- "Which trigger events have produced the most meetings for me?"
- "What's my average cycle time for CDMO leads vs. biotech leads?"
- "Which outreach sequences have the best response rate?"

### 10.3 ICP Refinement Recommendations

After accumulating 10+ outcomes, ARIA should proactively suggest ICP refinements:
- "Your win rate is 3x higher for companies with 200-500 employees vs. 1000+. Consider narrowing your ICP."
- "Leads from funding round triggers close 40% faster than facility expansion triggers."

Store recommendations in `lead_memory_insights` for the portfolio level, not individual leads.

---

*Skill Version: 2.0*
*Created: March 2026*
*Status: ARIA-Native, Dynamic, End-to-End*
*This skill contains NO hard-coded sub-industry data, company lists, or static persona templates.*
*All intelligence is discovered dynamically from ARIA's enrichment pipeline, stored in ARIA's memory system, and refined through observed outcomes.*
