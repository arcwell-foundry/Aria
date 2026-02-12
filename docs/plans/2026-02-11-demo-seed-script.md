# Demo Seed Script Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Create `scripts/seed_demo_data.py` that populates Supabase with deterministic life sciences demo data for a 3-minute investor demo, with idempotent `--clean` support.

**Architecture:** Single Python script using Supabase client (matching `seed_roi_data.py` patterns). Seeds in dependency order, tags all rows for cleanup. Deterministic data — no randomization.

**Tech Stack:** Python 3.11+, supabase-py, python-dotenv, argparse

---

### Task 1: Script skeleton with --clean support

**Files:**
- Create: `backend/scripts/seed_demo_data.py`

**Step 1: Write the script skeleton**

Create the script with:
- argparse: `--user-id` (required), `--clean` (flag), `--company-id` (optional, auto-resolved)
- `get_supabase_client()` matching existing pattern
- `clean_demo_data(client, user_id, company_id)` that deletes in reverse dependency order:
  1. `lead_memory_stakeholders` via CASCADE from lead_memories
  2. `email_drafts` WHERE `context->>'demo' = 'true'` AND user_id
  3. `market_signals` WHERE `metadata->>'demo' = 'true'` AND user_id
  4. `aria_action_queue` WHERE `payload->>'demo' = 'true'` AND user_id
  5. `goal_agents` via CASCADE from goals
  6. `goals` WHERE `config->>'demo' = 'true'` AND user_id
  7. `lead_memories` WHERE `metadata->>'demo' = 'true'` AND user_id
  8. `battle_cards` WHERE `update_source = 'demo_seed'` AND company_id
  9. `meeting_briefs` WHERE `brief_content->>'demo' = 'true'` AND user_id
  10. `video_sessions` WHERE tavus_conversation_id LIKE 'demo_%' AND user_id
- `main()` that always cleans before seeding (idempotent)
- Logging with counts for each table cleaned/seeded

**Demo tagging strategy** (tables lack uniform metadata columns):

| Table | Tag Column | Tag Value |
|-------|-----------|-----------|
| lead_memories | metadata | `{"demo": true}` |
| lead_memory_stakeholders | (CASCADE) | — |
| battle_cards | update_source | `'demo_seed'` |
| email_drafts | context | `{"demo": true, ...}` |
| market_signals | metadata | `{"demo": true}` |
| goals | config | `{"demo": true}` |
| goal_agents | (CASCADE) | — |
| aria_action_queue | payload | `{"demo": true, ...}` |
| meeting_briefs | brief_content | `{"demo": true, ...}` |
| video_sessions | tavus_conversation_id | `'demo_briefing'` |

**Step 2: Verify script runs**

Run: `cd backend && python scripts/seed_demo_data.py --help`
Expected: Help text with --user-id and --clean flags

**Step 3: Commit**

```bash
git add backend/scripts/seed_demo_data.py
git commit -m "feat: demo seed script skeleton with clean support"
```

---

### Task 2: Battle cards — 5 bioprocessing competitors

**Files:**
- Modify: `backend/scripts/seed_demo_data.py`

**Step 1: Add `seed_battle_cards(client, company_id)` function**

Seed 5 battle cards with real competitive intelligence:

1. **Lonza** — lonza.com
   - Overview: Global CDMO leader, $6.2B revenue, dominant in mammalian biologics
   - Strengths: Scale, regulatory track record, global footprint
   - Weaknesses: Premium pricing, long lead times, complex contracting
   - Pricing: {"model": "Per-batch + FTE", "range": "$800K-$3.5M per program"}
   - Differentiation: Speed to IND, flexible batch sizes, dedicated suites
   - Objection handlers: "Lonza has more experience" → response

2. **Catalent** — catalent.com
   - Overview: Full-service CDMO, $4.8B revenue, strong in gene therapy
   - Strengths: End-to-end capabilities, gene therapy expertise
   - Weaknesses: Quality issues (FDA warning letters), integration challenges post-acquisitions
   - Pricing: {"model": "Milestone + royalty", "range": "$500K-$2.5M per program"}
   - Differentiation: No royalty model, faster tech transfer
   - Objection handlers: "Catalent offers end-to-end" → response

3. **Repligen** — repligen.com
   - Overview: Bioprocessing equipment leader, $785M revenue, filtration and chromatography
   - Strengths: Best-in-class filtration, strong R&D pipeline
   - Weaknesses: Limited CDMO services, equipment-only
   - Pricing: {"model": "Capital + consumables", "range": "$150K-$1.2M per system"}
   - Differentiation: Full workflow solutions vs point products
   - Objection handlers: "Repligen hardware is industry standard" → response

4. **Thermo Fisher** — thermofisher.com
   - Overview: Life sciences conglomerate, $44B revenue, Patheon CDMO division
   - Strengths: One-stop shop, financial stability, massive scale
   - Weaknesses: Bureaucratic, less specialized, account managers rotate
   - Pricing: {"model": "Service contract", "range": "$1M-$5M annually"}
   - Differentiation: Specialized attention, dedicated team continuity
   - Objection handlers: "Thermo Fisher can do everything" → response

5. **WuXi AppTec** — wuxiapptec.com
   - Overview: China-based CRO/CDMO, $5.9B revenue, cost advantage
   - Strengths: Speed, cost-effective, massive capacity
   - Weaknesses: Geopolitical risk (BIOSECURE Act), IP concerns, regulatory uncertainty
   - Pricing: {"model": "Per-project", "range": "$300K-$1.8M per program"}
   - Differentiation: US-based manufacturing, IP protection, regulatory clarity
   - Objection handlers: "WuXi is 40% cheaper" → response

**Step 2: Verify insertion**

Run: `cd backend && python scripts/seed_demo_data.py --user-id <uuid>`
Expected: "Inserted 5 battle_cards records"

**Step 3: Commit**

```bash
git add backend/scripts/seed_demo_data.py
git commit -m "feat: seed 5 bioprocessing competitor battle cards"
```

---

### Task 3: Leads with stakeholders — 15 leads, ~35 contacts

**Files:**
- Modify: `backend/scripts/seed_demo_data.py`

**Step 1: Add `seed_leads(client, user_id)` function**

15 leads across lifecycle stages with realistic bioprocessing companies:

| # | Company | Stage | Status | Health | Expected Value | Stakeholders |
|---|---------|-------|--------|--------|---------------|-------------|
| 1 | Genentech | opportunity | active | 92 | $2,400,000 | 3: VP Mfg (champion/positive), Dir Procurement (decision_maker/positive), Sr Scientist (influencer/neutral) |
| 2 | Amgen | opportunity | active | 85 | $1,800,000 | 3: SVP Operations (decision_maker/positive), Dir Process Dev (champion/positive), Procurement Mgr (influencer/neutral) |
| 3 | Regeneron | opportunity | active | 78 | $1,500,000 | 2: VP Biologics Mfg (decision_maker/neutral), Dir Supply Chain (influencer/positive) |
| 4 | Moderna | lead | active | 71 | $3,200,000 | 2: Chief Manufacturing Officer (decision_maker/neutral), VP External Supply (influencer/neutral) |
| 5 | BioNTech | lead | active | 65 | $2,100,000 | 3: Head of CDMO Relations (decision_maker/neutral), Dir Technical Ops (influencer/positive), Procurement Lead (blocker/negative) |
| 6 | Gilead Sciences | opportunity | active | 88 | $1,900,000 | 2: VP Manufacturing Sciences (champion/positive), Dir Quality (influencer/neutral) |
| 7 | Vertex Pharmaceuticals | lead | active | 58 | $950,000 | 2: Dir Biologics (decision_maker/neutral), Sr Mgr External Mfg (influencer/neutral) |
| 8 | AbbVie | account | active | 95 | $4,500,000 | 3: VP Global Mfg (decision_maker/positive), Dir Procurement (champion/positive), Plant Dir (influencer/positive) |
| 9 | Bristol-Myers Squibb | opportunity | active | 74 | $2,800,000 | 3: SVP Biologics Ops (decision_maker/neutral), VP Procurement (influencer/neutral), Dir Tech Transfer (champion/positive) |
| 10 | Novo Nordisk | lead | active | 45 | $1,200,000 | 2: VP Fill-Finish Ops (decision_maker/neutral), Global Procurement Dir (blocker/negative) |
| 11 | Jazz Pharmaceuticals | lead | active | 52 | $680,000 | 2: Dir External Manufacturing (decision_maker/neutral), Sr Buyer (influencer/neutral) |
| 12 | Sarepta Therapeutics | opportunity | active | 81 | $1,600,000 | 2: VP Gene Therapy Mfg (decision_maker/positive), Dir CMC (champion/positive) |
| 13 | Alnylam Pharmaceuticals | lead | active | 38 | $750,000 | 2: Dir Manufacturing (decision_maker/neutral), Procurement Analyst (influencer/negative) |
| 14 | Biogen | account | won | 91 | $3,100,000 | 3: VP Manufacturing (champion/positive), Dir Supply Planning (decision_maker/positive), Quality VP (influencer/positive) |
| 15 | Alexion (AstraZeneca) | opportunity | active | 69 | $2,200,000 | 2: Head of Biologics Supply (decision_maker/neutral), Dir External Partnerships (influencer/positive) |

**Step 2: Add `seed_stakeholders(client, lead_map)` function**

Insert stakeholders linked to lead_memory IDs returned from Step 1.

Each stakeholder has:
- Realistic name, email (`firstname.lastname@company.com`), title
- role: decision_maker | champion | influencer | blocker
- sentiment: positive | neutral | negative
- influence_level: 6-10 for decision_makers, 4-7 for influencers, 7-9 for champions, 5-8 for blockers
- personality_insights: `{"communication_style": "data-driven" | "relationship-focused" | "direct", "demo": true}`

**Step 3: Verify insertion**

Run with `--clean` to test idempotency.
Expected: "Inserted 15 lead_memories", "Inserted ~35 stakeholders"

**Step 4: Commit**

```bash
git add backend/scripts/seed_demo_data.py
git commit -m "feat: seed 15 leads with 35 stakeholders for demo"
```

---

### Task 4: Email drafts, market signals, goals, actions, meetings

**Files:**
- Modify: `backend/scripts/seed_demo_data.py`

**Step 1: Add `seed_email_drafts(client, user_id, lead_ids)` — 3 drafts**

1. Follow-up to Genentech VP Mfg — status: "draft", tone: "friendly", purpose: "follow_up"
   Subject: "Following up on single-use bioreactor discussion"
2. Intro to Moderna CMO — status: "draft", tone: "formal", purpose: "intro"
   Subject: "Flexible manufacturing capacity for mRNA programs"
3. Proposal to Sarepta Dir — status: "sent", tone: "formal", purpose: "proposal"
   Subject: "Gene therapy CDMO partnership proposal"

**Step 2: Add `seed_market_signals(client, user_id)` — 5 signals**

1. "Catalent CFO Resigns Amid Restructuring" — signal_type: "leadership_change", relevance: 0.92
2. "Repligen Acquires FlexBiosys for $380M" — signal_type: "acquisition", relevance: 0.88
3. "Genentech Expands South San Francisco Biologics Facility" — signal_type: "expansion", relevance: 0.85
4. "FDA Warning Letter to WuXi Biologics Shanghai Site" — signal_type: "regulatory", relevance: 0.95
5. "Moderna Signs $1.2B Manufacturing Agreement" — signal_type: "partnership", relevance: 0.79

**Step 3: Add `seed_goals(client, user_id)` — 2 active goals with agents**

1. "Expand Repligen Relationship" — type: "outreach", progress: 65, status: "active"
   - strategy: milestones, stakeholder mapping, competitive positioning
   - Agents: hunter (complete), analyst (running), scribe (pending)

2. "Win Catalent Displacement at BioNTech" — type: "analysis", progress: 30, status: "active"
   - strategy: leverage Catalent quality issues, position on reliability
   - Agents: strategist (running), scout (running), analyst (pending)

**Step 4: Add `seed_action_queue(client, user_id)` — 2 actions**

1. "Draft competitive comparison for BioNTech" — agent: "strategist", risk: "medium", status: "pending"
   - reasoning: "BioNTech procurement lead raised concerns about switching costs..."
2. "Update CRM with Genentech meeting notes" — agent: "operator", risk: "low", status: "auto_approved"

**Step 5: Add `seed_meetings(client, user_id)` — 3 today's meetings**

1. "Morning Pipeline Review" — 9:00 AM today, status: "completed"
2. "Genentech Q2 Planning Call" — 2:00 PM today, attendees: ["Sarah Kim", "James Chen"], status: "pending"
3. "Weekly Forecast Review with Leadership" — 4:30 PM today, status: "pending"

**Step 6: Verify full seed + clean cycle**

Run: `cd backend && python scripts/seed_demo_data.py --user-id <uuid>`
Run: `cd backend && python scripts/seed_demo_data.py --user-id <uuid> --clean`
Run: `cd backend && python scripts/seed_demo_data.py --user-id <uuid>`
Expected: Same counts each time, no duplicates

**Step 7: Commit**

```bash
git add backend/scripts/seed_demo_data.py
git commit -m "feat: seed drafts, signals, goals, actions, meetings for demo"
```

---

### Task 5: Tavus briefing session config

**Files:**
- Modify: `backend/scripts/seed_demo_data.py`

**Step 1: Add `seed_tavus_briefing(client, user_id)` function**

Insert a `video_sessions` row:
- tavus_conversation_id: "demo_briefing"
- session_type: "briefing"
- status: "created"

Also seed a `conversational_context` document in user_settings.preferences that the Tavus integration can read at session start:

```json
{
  "briefing_context": {
    "greeting": "Good morning Dhruv. I've prepared your daily briefing.",
    "key_highlights": [
      "Genentech pipeline progressing well — health score at 92, Q2 planning call at 2 PM today",
      "Catalent CFO resignation creates displacement opportunity at BioNTech — goal is 30% complete",
      "Repligen relationship expansion on track at 65% — analyst agent currently mapping stakeholder network",
      "FDA warning letter to WuXi Shanghai may accelerate nearshoring conversations with 3 prospects",
      "AbbVie account renewal ($4.5M) on track — all stakeholders showing positive sentiment"
    ],
    "demo": true
  }
}
```

**Step 2: Verify insertion**

Run: `cd backend && python scripts/seed_demo_data.py --user-id <uuid>`
Expected: "Inserted 1 video_sessions record", "Updated briefing context"

**Step 3: Commit**

```bash
git add backend/scripts/seed_demo_data.py
git commit -m "feat: seed Tavus briefing session config for demo"
```

---

### Task 6: Final integration test + make executable

**Files:**
- Modify: `backend/scripts/seed_demo_data.py`

**Step 1: Add shebang, chmod, summary output**

- Add `#!/usr/bin/env python3`
- Print summary table at end showing all seeded counts
- Print demo flow talking points reminder

**Step 2: Full end-to-end test**

```bash
cd backend
python scripts/seed_demo_data.py --user-id <uuid>
# Verify: all counts printed
python scripts/seed_demo_data.py --user-id <uuid>
# Verify: clean runs first, same counts (idempotent)
python scripts/seed_demo_data.py --user-id <uuid> --clean
# Verify: only cleans, no seeding
```

**Step 3: Final commit**

```bash
git add backend/scripts/seed_demo_data.py
git commit -m "feat: finalize demo seed script with summary output"
```
