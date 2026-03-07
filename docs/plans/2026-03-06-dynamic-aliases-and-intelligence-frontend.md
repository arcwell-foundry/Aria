# Dynamic Company Aliases + Intelligence Page Frontend Enhancements

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Remove hardcoded Repligen-specific company alias mappings from the backend and replace with dynamic DB-driven aliases, then add six frontend enhancements to the Intelligence page (signal expand, company filter, relevance indicators, tooltip fix, therapeutic trends, return briefing).

**Architecture:** Backend rewrites `company_aliases.py` as a dynamic service that builds alias maps from `battle_cards` table per company_id, with in-process caching. All callers are updated to pass company_id + supabase_client where available, falling back to basic suffix-stripping. Frontend enhancements are all scoped to `MarketSignalsFeed.tsx`, `BattleCardPreview.tsx`, and `IntelligencePage.tsx` plus new API client functions.

**Tech Stack:** Python 3.11/FastAPI (backend), React 18/TypeScript/Tailwind/Vite (frontend), Supabase (DB)

---

## Task 1: Rewrite `company_aliases.py` to Dynamic Service

**Files:**
- Rewrite: `backend/src/utils/company_aliases.py`
- Modify: `backend/src/utils/__init__.py` (update re-exports)

**Step 1: Read current file**

Read `backend/src/utils/company_aliases.py` to confirm current state (175 lines, hardcoded COMPANY_CANONICAL_NAMES and PERSON_TO_COMPANY dicts).

**Step 2: Rewrite the file**

Replace entire contents of `backend/src/utils/company_aliases.py` with:

```python
"""
Dynamic company name normalization.

Builds alias mappings from the user's battle_cards table rather than
hardcoded dictionaries. Falls back to basic suffix-stripping when
no DB context is available.

Usage:
    from src.utils.company_aliases import normalize_company_name

    # Basic mode (no DB):
    canonical = normalize_company_name("Sartorius AG")  # -> "Sartorius"

    # Dynamic mode (with DB):
    canonical = normalize_company_name(
        "Thermo Fisher Scientific",
        company_id="...",
        supabase_client=db,
    )
"""

import logging
from typing import Any

logger = logging.getLogger(__name__)

# In-process cache (per company_id). Cleared on restart or explicit clear_cache().
_alias_cache: dict[str, dict[str, str]] = {}
_person_cache: dict[str, dict[str, str]] = {}

# Common corporate suffixes to strip in basic mode
_CORPORATE_SUFFIXES = (
    " Inc", " Inc.", " Corp", " Corp.", " Corporation",
    " Ltd", " Ltd.", " AG", " SE", " GmbH", " S.A.",
    " PLC", " plc", " N.V.", " S.p.A.",
)


def normalize_company_name(
    name: str | None,
    company_id: str | None = None,
    supabase_client: Any | None = None,
) -> str:
    """Return the canonical company name, handling aliases and known people.

    If company_id and supabase_client are provided, dynamically builds an
    alias mapping from the battle_cards table. Otherwise falls back to
    basic normalization (strip corporate suffixes).

    Args:
        name: The company name to normalize (may be None or empty).
        company_id: UUID of the user's company (enables dynamic aliases).
        supabase_client: Supabase client instance for DB queries.

    Returns:
        The canonical company name, or the cleaned original if no mapping exists.
    """
    if not name:
        return name or ""

    # Dynamic mode: look up aliases from battle_cards
    if company_id and supabase_client:
        person_map = _get_or_build_person_map(company_id, supabase_client)
        aliases = _get_or_build_aliases(company_id, supabase_client)

        # Check person mapping first (higher priority)
        if name in person_map:
            return person_map[name]

        # Check alias mapping (exact match)
        if name in aliases:
            return aliases[name]

        # Case-insensitive fallback
        name_lower = name.lower().strip()
        for person, company in person_map.items():
            if person.lower() == name_lower:
                return company
        for variant, canonical in aliases.items():
            if variant.lower() == name_lower:
                return canonical

    # Basic mode: strip common corporate suffixes
    cleaned = name.strip()
    for suffix in _CORPORATE_SUFFIXES:
        if cleaned.endswith(suffix):
            cleaned = cleaned[: -len(suffix)].strip()
            break

    return cleaned


def get_signal_company_names_for_battle_card(
    battle_card_name: str,
    company_id: str | None = None,
    db: Any | None = None,
) -> list[str]:
    """Return all company_name variants that map to this battle card.

    Useful when querying market_signals for signals related to a specific
    battle card, since historical signals may use variant names.

    Args:
        battle_card_name: The canonical competitor name from battle_cards.
        company_id: UUID of the user's company (enables dynamic aliases).
        db: Supabase client instance.

    Returns:
        List of all variant names (including the canonical name).
    """
    names = [battle_card_name]

    if company_id and db:
        aliases = _get_or_build_aliases(company_id, db)
        for variant, canonical in aliases.items():
            if canonical == battle_card_name and variant != battle_card_name:
                names.append(variant)

        person_map = _get_or_build_person_map(company_id, db)
        for person, company in person_map.items():
            if company == battle_card_name:
                names.append(person)

    return names


def is_known_person(
    name: str,
    company_id: str | None = None,
    supabase_client: Any | None = None,
) -> bool:
    """Check if a name is a known person mapped to a company."""
    if not name:
        return False
    if company_id and supabase_client:
        person_map = _get_or_build_person_map(company_id, supabase_client)
        return name in person_map or name.lower() in {p.lower() for p in person_map}
    return False


def get_company_for_person(
    person_name: str,
    company_id: str | None = None,
    supabase_client: Any | None = None,
) -> str | None:
    """Get the company a person should map to."""
    if not person_name:
        return None
    if company_id and supabase_client:
        person_map = _get_or_build_person_map(company_id, supabase_client)
        if person_name in person_map:
            return person_map[person_name]
        person_lower = person_name.lower()
        for person, company in person_map.items():
            if person.lower() == person_lower:
                return company
    return None


def clear_cache() -> None:
    """Clear alias caches. Call when battle_cards are updated."""
    global _alias_cache, _person_cache
    _alias_cache = {}
    _person_cache = {}


# ---------------------------------------------------------------------------
# Internal cache builders
# ---------------------------------------------------------------------------

def _get_or_build_aliases(company_id: str, db: Any) -> dict[str, str]:
    """Build or retrieve cached alias mapping from battle_cards."""
    if company_id in _alias_cache:
        return _alias_cache[company_id]

    try:
        result = (
            db.table("battle_cards")
            .select("competitor_name, competitor_domain")
            .eq("company_id", company_id)
            .execute()
        )

        aliases: dict[str, str] = {}
        if result.data:
            for card in result.data:
                canonical = card["competitor_name"]
                domain = card.get("competitor_domain", "")

                # Canonical name maps to itself
                aliases[canonical] = canonical

                # Auto-generate common variants from multi-word names
                if " " in canonical:
                    parts = canonical.split()
                    last_word = parts[-1]
                    if last_word in (
                        "Corporation", "Corp", "Inc", "AG", "Ltd",
                        "GmbH", "SE", "PLC", "plc",
                    ):
                        # "Pall Corporation" -> also match "Pall"
                        short_name = " ".join(parts[:-1])
                        aliases[short_name] = canonical
                        # Generate suffix variants: "Pall Corp", "Pall Corp.", etc.
                        for suffix in ("Corp", "Corp.", "Corporation", "Inc", "Inc.", "AG", "Ltd"):
                            aliases[f"{short_name} {suffix}"] = canonical

                # Domain-based variant (e.g., "cytiva" from "cytiva.com")
                if domain:
                    domain_name = (
                        domain.replace("https://", "")
                        .replace("http://", "")
                        .replace("www.", "")
                        .replace(".com", "")
                        .replace(".org", "")
                        .replace(".io", "")
                        .strip("/")
                        .strip()
                    )
                    if domain_name and domain_name != canonical.lower():
                        aliases[domain_name] = canonical
                        aliases[domain_name.capitalize()] = canonical

        _alias_cache[company_id] = aliases
        return aliases
    except Exception as e:
        logger.warning("Failed to build aliases for company %s: %s", company_id, e)
        return {}


def _get_or_build_person_map(company_id: str, db: Any) -> dict[str, str]:
    """Build person-to-company mapping. Currently returns empty; future:
    mine semantic memory for 'X is CEO of Y' patterns."""
    if company_id in _person_cache:
        return _person_cache[company_id]

    # Placeholder: will be populated by enrichment pipeline later
    _person_cache[company_id] = {}
    return {}
```

**Step 3: Update `__init__.py` re-exports**

Edit `backend/src/utils/__init__.py` to remove `COMPANY_CANONICAL_NAMES` and `PERSON_TO_COMPANY` from exports (they no longer exist as module-level constants):

```python
"""Utility modules for ARIA backend."""

from src.utils.company_aliases import (
    get_signal_company_names_for_battle_card,
    normalize_company_name,
    clear_cache,
)

__all__ = [
    "normalize_company_name",
    "get_signal_company_names_for_battle_card",
    "clear_cache",
]
```

**Step 4: Verify no other files import the removed constants**

Run: `grep -rn "COMPANY_CANONICAL_NAMES\|PERSON_TO_COMPANY" backend/src/ --include="*.py" | grep -v __pycache__ | grep -v company_aliases.py`

If any matches, update those files to remove the import (they should use the function API instead).

**Step 5: Commit**

```bash
git add backend/src/utils/company_aliases.py backend/src/utils/__init__.py
git commit -m "refactor: make company alias normalization dynamic from battle_cards DB"
```

---

## Task 2: Update All Backend Callers

**Files:**
- Modify: `backend/src/services/battle_card_service.py:301` (has `self._db` + can get `company_id` from card)
- Modify: `backend/src/services/scheduler.py:1527-1555` (has `db` + can get `company_id` from card)
- Modify: `backend/src/jobs/scout_signal_scan_job.py:102` (has `db` + `user_id`)
- Modify: `backend/src/services/signal_service.py:62` (has `self._db` + `user_id`)
- Modify: `backend/src/onboarding/enrichment.py:1305` (already has `company_id`)

### Step 1: Update `battle_card_service.py`

The `get_recent_signals` method at line 301 calls `get_signal_company_names_for_battle_card(company_name)`. The service has `self._db` and the battle card's `company_id` is available from the card itself.

Read `backend/src/services/battle_card_service.py` lines 1-20 to find the class constructor and understand how `self._db` is set.

Then update line 301 to also get the `company_id` from the card. The `get_recent_signals` method takes `user_id` and `company_name` — we need to also accept/resolve `company_id`:

Change the `get_recent_signals` method signature and body:
```python
async def get_recent_signals(
    self,
    user_id: str,
    company_name: str,
    company_id: str | None = None,
    limit: int = 10,
) -> tuple[list[dict[str, Any]], int]:
    """Get recent market signals for a competitor, plus total count."""
    variant_names = get_signal_company_names_for_battle_card(
        company_name, company_id=company_id, db=self._db,
    )
    # ... rest unchanged ...
```

Then update the caller in `backend/src/api/routes/battle_cards.py` (around line 106-111) that calls `svc.get_recent_signals(current_user.id, competitor_name)` to also pass `company_id=card.get("company_id")`.

### Step 2: Update `scheduler.py`

At line 1555, `get_signal_company_names_for_battle_card(competitor_name)` is called. The card object from the DB query at line 1533 already has `company_id` if we add it to the select. Update:

1. Line 1534: Change `.select("id, competitor_name, analysis")` to `.select("id, competitor_name, company_id, analysis")`
2. Line 1555: Change to `get_signal_company_names_for_battle_card(competitor_name, company_id=card.get("company_id"), db=db)`

### Step 3: Update `scout_signal_scan_job.py`

At line 102, `normalize_company_name(raw_company_name)` is called. The function has `user_id` and `db`. We need to look up `company_id` from `user_profiles`:

Add a company_id lookup near the top of the user loop (after line 64). Then pass to `normalize_company_name`:

```python
# Look up company_id for this user (inside the user loop, cache it)
company_id = None
try:
    profile = db.table("user_profiles").select("company_id").eq("user_id", user_id).limit(1).execute()
    if profile.data:
        company_id = profile.data[0].get("company_id")
except Exception:
    pass

# Then at line 102:
canonical_company_name = normalize_company_name(raw_company_name, company_id=company_id, supabase_client=db)
```

### Step 4: Update `signal_service.py`

At line 62, `normalize_company_name(data.company_name)` is called. The `create_signal` method receives `user_id`. Add a company_id lookup:

```python
# Inside create_signal, before normalize call:
company_id = None
try:
    profile = self._db.table("user_profiles").select("company_id").eq("user_id", user_id).limit(1).execute()
    if profile.data:
        company_id = profile.data[0].get("company_id")
except Exception:
    pass

canonical_company_name = normalize_company_name(
    data.company_name, company_id=company_id, supabase_client=self._db,
)
```

### Step 5: Update `enrichment.py`

At line 1305, `normalize_company_name(_co_name)` is called. The `_store_results` method already has `company_id` as a parameter. Pass it:

```python
_co_name = normalize_company_name(_co_name, company_id=company_id, supabase_client=self._db)
```

The enrichment engine's `__init__` should already have `self._db = SupabaseClient.get_client()` — confirm.

### Step 6: Commit

```bash
git add backend/src/services/battle_card_service.py backend/src/services/scheduler.py \
    backend/src/jobs/scout_signal_scan_job.py backend/src/services/signal_service.py \
    backend/src/onboarding/enrichment.py backend/src/api/routes/battle_cards.py
git commit -m "feat: wire dynamic company aliases through all backend callers"
```

---

## Task 3: Fix Hardcoded User ID in backfill_insights.py

**Files:**
- Modify: `backend/src/intelligence/backfill_insights.py`

**Step 1: Read the file** (116 lines)

Read `backend/src/intelligence/backfill_insights.py`.

**Step 2: Update to accept user_id from command line**

Change the `backfill()` function signature to `async def backfill(user_id: str):` and replace all 3 hardcoded UUID strings with the `user_id` parameter.

Update the `if __name__` block:

```python
if __name__ == "__main__":
    import sys

    target_user_id = sys.argv[1] if len(sys.argv) > 1 else None
    if not target_user_id:
        # Auto-discover: find the first user with market signals
        from src.db.supabase import SupabaseClient
        _db = SupabaseClient.get_client()
        _users = _db.table("market_signals").select("user_id").limit(100).execute()
        _unique_ids = list({r["user_id"] for r in (_users.data or []) if r.get("user_id")})
        if _unique_ids:
            target_user_id = _unique_ids[0]
            logger.info("Auto-discovered user: %s", target_user_id)
        else:
            logger.error("No users with market signals found. Pass user_id as argument.")
            sys.exit(1)

    asyncio.run(backfill(target_user_id))
```

**Step 3: Also fix hardcoded competitor names**

Line 44 has `competitor_names = {"Cytiva", "Sartorius", ...}`. Replace with a dynamic lookup:

```python
# Get competitors from battle_cards for this user
from src.db.supabase import SupabaseClient as _SC
_bc_db = _SC.get_client()
_bc_result = _bc_db.table("battle_cards").select("competitor_name").eq("user_id", user_id).execute()
competitor_names = {r["competitor_name"] for r in (_bc_result.data or [])}
if not competitor_names:
    # Fallback: treat all companies as equally important
    competitor_names = set()
```

Note: battle_cards likely uses `company_id` not `user_id`. Check the table schema. If it uses `company_id`, look up via user_profiles first.

**Step 4: Commit**

```bash
git add backend/src/intelligence/backfill_insights.py
git commit -m "fix: remove hardcoded user ID from backfill_insights, accept as CLI arg"
```

---

## Task 4: Audit and Fix Remaining Hardcoded Repligen References

**Files:**
- Modify: `backend/src/intelligence/supply_chain_intelligence.py:95`
- Modify: `backend/src/intelligence/clinical_trial_intelligence.py:136`
- Modify: `backend/src/integrations/tavus_persona.py:111`
- Review only (keep as-is): `backend/src/intelligence/orchestrator.py:954` (keyword list for scoring — "Repligen" is one of many specificity keywords; removing is debatable but harmless as a match check)
- Review only (keep as-is): `backend/src/intelligence/causal/engine.py:306` (example text in LLM prompt — serves as illustration)

**Step 1: Fix supply_chain_intelligence.py**

Line 95 has a hardcoded prompt: `"What Repligen products are direct replacements?"`. This should use the user's company name. Check if the function has access to the user's company name (likely passed as context). Replace `"Repligen"` with the user's company name variable, or if not available, use a generic phrase like `"our company's products"`.

**Step 2: Fix clinical_trial_intelligence.py**

Line 136 has `"Identify which Repligen products map to these needs"`. Same approach — replace with user's company name or generic text.

**Step 3: Fix tavus_persona.py**

Line 111 has "Repligen" in a company names list. This list should come from the user's profile/company data, not be hardcoded.

**Step 4: Decide on orchestrator.py and causal/engine.py**

- `orchestrator.py:954` — "Repligen" in `specificity_keywords` list. This is used for scoring how specific an action is. The keyword is alongside generic terms like "battle card", "pricing", "territory". The user's company name should be dynamically included. Read the surrounding code to find if `company_name` is available in scope, and if so, add it dynamically to the list.
- `causal/engine.py:306` — "Repligen" as an example in an LLM prompt alongside "Sartorius", "Cytiva". These are illustrative examples for the LLM. Changing to the user's actual competitors would be better but is low priority. If the function receives user context, swap in their actual competitors; otherwise leave as-is (example names in prompts are fine).

**Step 5: Commit**

```bash
git add backend/src/intelligence/supply_chain_intelligence.py \
    backend/src/intelligence/clinical_trial_intelligence.py \
    backend/src/integrations/tavus_persona.py \
    backend/src/intelligence/orchestrator.py
git commit -m "fix: replace hardcoded Repligen references with dynamic company context"
```

---

## Task 5: Signal Card Click-to-Expand + Relevance Indicator

**Files:**
- Modify: `frontend/src/components/intelligence/MarketSignalsFeed.tsx`
- Modify: `frontend/src/api/signals.ts` (add missing fields to Signal interface)

**Step 1: Update Signal interface**

The `Signal` interface in `frontend/src/api/signals.ts` is missing fields that the backend returns. The backend's `signal_service.py` maps `headline` → `content`, `source_name` → `source`, `detected_at` → `created_at`. But the backend also returns `summary`, `source_url`, and `relevance_score` which aren't in the frontend type. Add them:

```typescript
export interface Signal {
  id: string;
  user_id: string;
  signal_type: string;
  company_name: string | null;
  content: string;        // headline mapped by backend
  summary?: string;       // full summary text
  source: string | null;  // source_name mapped by backend
  source_url?: string;    // direct URL to source
  relevance_score?: number;
  read_at: string | null;
  dismissed_at: string | null;
  created_at: string;
}
```

**IMPORTANT:** Verify the backend `signal_service.py` `get_signals()` method actually includes these fields in its response. Read `backend/src/services/signal_service.py` lines 80-200 to check the field mapping in the `get_signals` method. If `summary`, `source_url`, and `relevance_score` are NOT returned by `get_signals`, update the backend to include them. The `select` query likely needs: `"id, user_id, company_name, signal_type, headline, summary, source_name, source_url, relevance_score, read_at, dismissed_at, detected_at"`.

**Step 2: Add expand state to SignalCard**

In `MarketSignalsFeed.tsx`, update the `SignalCard` component:

```tsx
function SignalCard({
  signal,
  onMarkRead,
  onDismiss,
}: {
  signal: Signal;
  onMarkRead: (id: string) => void;
  onDismiss: (id: string) => void;
}) {
  const [expanded, setExpanded] = useState(false);
  const config = getSignalConfig(signal.signal_type);
  const Icon = config.icon;
  const isUnread = !signal.read_at;
  const relevance = signal.relevance_score ?? 0;

  return (
    <div
      onClick={() => setExpanded(!expanded)}
      className={cn(
        "flex items-start gap-3 p-4 rounded-lg border transition-all cursor-pointer",
        "hover:bg-[var(--bg-subtle)]"
      )}
      style={{
        backgroundColor: "var(--bg-elevated)",
        borderColor: expanded ? "var(--accent)" : "var(--border)",
        borderLeftWidth: isUnread ? "3px" : "1px",
        borderLeftColor: isUnread ? config.color : "var(--border)",
      }}
    >
      {/* Icon */}
      <div
        className="flex-shrink-0 w-8 h-8 rounded-full flex items-center justify-center mt-0.5"
        style={{ backgroundColor: `${config.color}18` }}
      >
        <Icon className="w-4 h-4" style={{ color: config.color }} />
      </div>

      {/* Content */}
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-2 mb-1">
          {signal.company_name && (
            <span className="text-sm font-medium truncate" style={{ color: "var(--text-primary)" }}>
              {signal.company_name}
            </span>
          )}
          <span
            className="px-1.5 py-0.5 rounded text-[10px] font-medium uppercase tracking-wide"
            style={{ backgroundColor: `${config.color}18`, color: config.color }}
          >
            {config.label}
          </span>
          {/* Relevance indicator */}
          {relevance >= 0.9 && (
            <span className="inline-flex items-center gap-1 text-[10px] font-medium" style={{ color: "#3b82f6" }}>
              <span className="w-1.5 h-1.5 rounded-full" style={{ backgroundColor: "#3b82f6" }} />
              High
            </span>
          )}
          {relevance >= 0.7 && relevance < 0.9 && (
            <span className="w-1.5 h-1.5 rounded-full" style={{ backgroundColor: "#22c55e" }} />
          )}
          {isUnread && (
            <span className="w-2 h-2 rounded-full flex-shrink-0" style={{ backgroundColor: "var(--accent)" }} />
          )}
        </div>

        {/* Collapsed: 2-line clamp. Expanded: full content */}
        <p
          className={cn("text-sm leading-relaxed", !expanded && "line-clamp-2")}
          style={{ color: "var(--text-secondary)" }}
        >
          {sanitizeSignalText(signal.content, expanded ? 2000 : 300)}
        </p>

        {/* Expanded details */}
        {expanded && (
          <div className="mt-3 space-y-2">
            {signal.summary && (
              <p className="text-sm leading-relaxed" style={{ color: "var(--text-secondary)" }}>
                {sanitizeSignalText(signal.summary, 1000)}
              </p>
            )}
            <div className="flex items-center gap-3 flex-wrap">
              {signal.source_url && (
                <a
                  href={signal.source_url}
                  target="_blank"
                  rel="noopener noreferrer"
                  onClick={(e) => e.stopPropagation()}
                  className="text-xs font-medium underline"
                  style={{ color: "var(--accent)" }}
                >
                  View Source ↗
                </a>
              )}
              {signal.created_at && (
                <span className="text-xs" style={{ color: "var(--text-tertiary, var(--text-secondary))" }}>
                  {new Date(signal.created_at).toLocaleDateString("en-US", {
                    month: "short", day: "numeric", year: "numeric",
                  })}
                </span>
              )}
              {relevance > 0 && (
                <span className="text-xs" style={{ color: "var(--text-tertiary, var(--text-secondary))" }}>
                  Relevance: {Math.round(relevance * 100)}%
                </span>
              )}
            </div>
          </div>
        )}

        {/* Footer (always visible) */}
        {!expanded && (
          <div className="flex items-center gap-3 mt-2">
            {signal.source && (
              <span className="text-xs font-mono truncate max-w-[160px]" style={{ color: "var(--text-tertiary, var(--text-secondary))" }}>
                {formatSourceName(signal.source)}
              </span>
            )}
            <span className="text-xs font-mono" style={{ color: "var(--text-tertiary, var(--text-secondary))" }}>
              {formatRelativeTime(signal.created_at)}
            </span>
          </div>
        )}
      </div>

      {/* Actions */}
      <div className="flex-shrink-0 flex items-center gap-1" onClick={(e) => e.stopPropagation()}>
        {isUnread && (
          <button onClick={() => onMarkRead(signal.id)} className="p-1.5 rounded-md hover:bg-[var(--bg-subtle)] transition-colors" title="Mark as read">
            <Eye className="w-3.5 h-3.5" style={{ color: "var(--text-secondary)" }} />
          </button>
        )}
        <button onClick={() => onDismiss(signal.id)} className="p-1.5 rounded-md hover:bg-[var(--bg-subtle)] transition-colors" title="Dismiss">
          <X className="w-3.5 h-3.5" style={{ color: "var(--text-secondary)" }} />
        </button>
      </div>
    </div>
  );
}
```

**Note on `sanitizeSignalText`:** Check if it accepts a `maxLength` parameter. Read `frontend/src/utils/sanitizeSignalText.ts` to confirm. If it takes `maxLength` as second param, the above code works. If not, adapt accordingly (or just don't pass maxLength when expanded).

**Step 3: Add `useState` import** (already imported in the file)

**Step 4: Commit**

```bash
git add frontend/src/api/signals.ts frontend/src/components/intelligence/MarketSignalsFeed.tsx
git commit -m "feat: add signal click-to-expand and relevance indicator"
```

---

## Task 6: Company Filter for Market Signals

**Files:**
- Modify: `frontend/src/components/intelligence/MarketSignalsFeed.tsx`

**Step 1: Add company filter state**

In the `MarketSignalsFeed` component, add:

```tsx
const [selectedCompany, setSelectedCompany] = useState<string | undefined>(undefined);
```

**Step 2: Compute company chips from signal data**

After `visibleSignals` memo, add:

```tsx
// Build company filter chips from loaded signals
const companyChips = useMemo(() => {
  const counts: Record<string, number> = {};
  for (const s of signals ?? []) {
    if (s.company_name && !s.dismissed_at) {
      counts[s.company_name] = (counts[s.company_name] || 0) + 1;
    }
  }
  // Show companies with 3+ signals as individual chips, rest as "Other"
  const entries = Object.entries(counts).sort((a, b) => b[1] - a[1]);
  const named = entries.filter(([, c]) => c >= 3).map(([name]) => name);
  const hasOther = entries.some(([, c]) => c < 3);
  return { named, hasOther };
}, [signals]);
```

**Step 3: Filter visibleSignals by company too**

Update the `visibleSignals` memo:

```tsx
const visibleSignals = useMemo(() => {
  let filtered = (signals ?? []).filter((s) => !s.dismissed_at);
  if (selectedCompany === "__other__") {
    const namedSet = new Set(companyChips.named);
    filtered = filtered.filter((s) => s.company_name && !namedSet.has(s.company_name));
  } else if (selectedCompany) {
    filtered = filtered.filter((s) => s.company_name === selectedCompany);
  }
  return filtered;
}, [signals, selectedCompany, companyChips.named]);
```

**Step 4: Add company filter row below type filters**

Inside the toolbar `div` (after the type filter chips div, before the right actions div), add a second row:

```tsx
{/* Company filter chips */}
{companyChips.named.length > 0 && (
  <div className="flex items-center gap-2 overflow-x-auto no-scrollbar px-4 pb-3 border-b" style={{ borderColor: "var(--border)" }}>
    <span className="text-[10px] uppercase tracking-wider font-semibold flex-shrink-0" style={{ color: "var(--text-tertiary, var(--text-secondary))" }}>
      Company
    </span>
    <FilterChip label="All" active={!selectedCompany} onClick={() => setSelectedCompany(undefined)} />
    {companyChips.named.map((name) => (
      <FilterChip
        key={name}
        label={name}
        active={selectedCompany === name}
        onClick={() => setSelectedCompany(selectedCompany === name ? undefined : name)}
      />
    ))}
    {companyChips.hasOther && (
      <FilterChip
        label="Other"
        active={selectedCompany === "__other__"}
        onClick={() => setSelectedCompany(selectedCompany === "__other__" ? undefined : "__other__")}
      />
    )}
  </div>
)}
```

**Note:** The toolbar structure currently has a single flex row. You may need to restructure it slightly — wrap the type filter and company filter rows in a `flex flex-col` container, with each row being its own flex div. Keep the right actions (Unread toggle, Mark all) aligned to the type filter row.

**Step 5: Update `hasFilters`**

```tsx
const hasFilters = !!selectedType || !!selectedCompany || unreadOnly;
```

**Step 6: Commit**

```bash
git add frontend/src/components/intelligence/MarketSignalsFeed.tsx
git commit -m "feat: add company filter chips for market signals"
```

---

## Task 7: Fix BattleCardPreview Tooltips

**Files:**
- Modify: `frontend/src/components/intelligence/BattleCardPreview.tsx`

**Step 1: Read current tooltip implementation**

The file already has a custom `Tooltip` component (lines 59-93) using `useState` with `onMouseEnter`/`onMouseLeave`. The implementation looks correct — it has `position: absolute`, `z-index: 50`, and toggles visibility via `show` state.

**Step 2: Diagnose the issue**

The tooltip is inside an `<span className="relative inline-flex">` wrapper. The card itself has `onClick={handleClick}` which navigates on click. Check:

1. The tooltip uses `pointer-events: none` — this is NOT set in the current code. The tooltip text itself might intercept hover events.
2. The parent card has `overflow: hidden` via the `overflow-hidden` class — **this would clip the tooltip!** Check if the card div has `overflow-hidden`. Looking at line 167: `className="rounded-xl border cursor-pointer"` — no overflow hidden.
3. The tooltip `z-index: 50` might be blocked by sibling cards in the grid.

Most likely issue: The parent card container in `IntelligencePage.tsx` grid does NOT clip, but the card itself might not have `overflow: visible` set (it's default visible so should be fine).

**Actual fix needed:** Add `pointer-events: none` to the tooltip popup span to prevent it from stealing hover events, and ensure the tooltip wrapper correctly prevents the card click from firing:

```tsx
function Tooltip({ text, children }: { text: string; children: React.ReactNode }) {
  const [show, setShow] = useState(false);

  if (!text) return <>{children}</>;

  return (
    <span
      className="relative inline-flex"
      onMouseEnter={() => setShow(true)}
      onMouseLeave={() => setShow(false)}
    >
      {children}
      {show && (
        <span
          className="absolute z-50 bottom-full left-1/2 -translate-x-1/2 mb-2 px-3 py-2 rounded-lg text-xs leading-relaxed whitespace-normal max-w-[280px] w-max pointer-events-none"
          style={{
            backgroundColor: '#1E293B',
            color: '#F1F5F9',
            boxShadow: '0 4px 12px rgba(0,0,0,0.15)',
            animation: 'fadeIn 0.15s ease',
          }}
        >
          {text}
          <span
            className="absolute top-full left-1/2 -translate-x-1/2 -mt-px"
            style={{
              width: 0,
              height: 0,
              borderLeft: '5px solid transparent',
              borderRight: '5px solid transparent',
              borderTop: '5px solid #1E293B',
            }}
          />
        </span>
      )}
    </span>
  );
}
```

Key fix: Added `pointer-events-none` class to the tooltip span and the `if (!text) return <>{children}</>` guard.

Also add `onClick={(e) => e.stopPropagation()}` to the Tooltip wrapper span to prevent tooltip hover areas from accidentally navigating:

Actually, we should NOT stopPropagation on the wrapper since the dots/pills are inline within the clickable card. The issue is likely that tooltips are working but being cut off by the grid. Check if the grid has `overflow-hidden` on any parent.

**Step 3: Verify in browser**

After the fix, hover over the threat dot and momentum pill to confirm tooltips render above the card.

**Step 4: Commit**

```bash
git add frontend/src/components/intelligence/BattleCardPreview.tsx
git commit -m "fix: ensure battle card preview tooltips render correctly"
```

---

## Task 8: Therapeutic Trends Section

**Files:**
- Create: `frontend/src/api/therapeuticTrends.ts`
- Modify: `frontend/src/hooks/useIntelPanelData.ts` (add hook)
- Modify: `frontend/src/components/pages/IntelligencePage.tsx` (add section)

**Step 1: Create API client**

Create `frontend/src/api/therapeuticTrends.ts`:

```typescript
import { apiClient } from "./client";

export interface TherapeuticTrend {
  trend_type: "therapeutic_area" | "manufacturing_modality";
  name: string;
  signal_count: number;
  companies_involved: string[];
  company_count: number;
  description: string;
  recent_signals?: Array<{
    headline: string;
    company_name: string;
    signal_type: string;
    detected_at: string;
  }>;
}

export async function getTherapeuticTrends(
  days: number = 30,
  minSignals: number = 3,
): Promise<TherapeuticTrend[]> {
  const params = new URLSearchParams();
  params.append("days", days.toString());
  params.append("min_signals", minSignals.toString());
  const response = await apiClient.get<{ trends: TherapeuticTrend[] }>(
    `/intelligence/therapeutic-trends?${params}`,
  );
  return response.data.trends ?? response.data as unknown as TherapeuticTrend[];
}
```

**Note:** The exact response shape depends on the backend's `TherapeuticTrendsListResponse` model. Read `backend/src/api/routes/intelligence.py` around lines 2305-2371 to confirm. The response likely wraps trends in a `{ trends: [...] }` object based on the `ListResponse` naming convention. Adjust the client accordingly.

**Step 2: Add React Query hook**

In `frontend/src/hooks/useIntelPanelData.ts`, add:

```typescript
import { getTherapeuticTrends, type TherapeuticTrend } from "@/api/therapeuticTrends";

export function useTherapeuticTrends(days = 30) {
  return useQuery<TherapeuticTrend[]>({
    queryKey: ["intel", "therapeutic-trends", days],
    queryFn: () => getTherapeuticTrends(days),
    staleTime: 5 * 60_000, // 5 minutes
  });
}
```

**Step 3: Build the Therapeutic Trends section component**

In `IntelligencePage.tsx`, add a new section component above the Market Signals section. Create it as a local component within the file:

```tsx
import { FlaskConical, ChevronDown, ChevronUp } from 'lucide-react';
import { useTherapeuticTrends } from '@/hooks/useIntelPanelData';

function TherapeuticTrendsSection() {
  const { data: trends } = useTherapeuticTrends();
  const [expandedTrend, setExpandedTrend] = useState<string | null>(null);

  if (!trends || trends.length === 0) return null;

  return (
    <section>
      <h2
        className="text-base font-medium mb-4 flex items-center gap-2"
        style={{ color: 'var(--text-primary)' }}
      >
        <FlaskConical className="w-4 h-4" style={{ color: 'var(--text-secondary)' }} />
        Therapeutic & Manufacturing Trends
      </h2>
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
        {trends.map((trend) => {
          const isExpanded = expandedTrend === trend.name;
          const maxSignals = Math.max(...trends.map(t => t.signal_count));
          const barWidth = maxSignals > 0 ? (trend.signal_count / maxSignals) * 100 : 0;

          return (
            <div
              key={trend.name}
              onClick={() => setExpandedTrend(isExpanded ? null : trend.name)}
              className="rounded-xl border p-4 cursor-pointer transition-all hover:-translate-y-0.5"
              style={{
                backgroundColor: '#FFFFFF',
                borderColor: isExpanded ? 'var(--accent)' : '#E2E8F0',
                boxShadow: '0 1px 3px rgba(0,0,0,0.04)',
              }}
            >
              <div className="flex items-start justify-between mb-2">
                <h3 className="text-sm font-semibold" style={{ color: '#1E293B' }}>
                  {trend.name}
                </h3>
                {isExpanded ? (
                  <ChevronUp className="w-4 h-4" style={{ color: '#94A3B8' }} />
                ) : (
                  <ChevronDown className="w-4 h-4" style={{ color: '#94A3B8' }} />
                )}
              </div>
              <div className="flex items-center gap-4 text-xs mb-2" style={{ color: '#5B6E8A' }}>
                <span>{trend.signal_count} signals</span>
                <span>{trend.company_count} companies</span>
              </div>
              {/* Strength bar */}
              <div className="h-1.5 rounded-full overflow-hidden" style={{ backgroundColor: '#F1F5F9' }}>
                <div
                  className="h-full rounded-full transition-all"
                  style={{
                    width: `${barWidth}%`,
                    backgroundColor: trend.trend_type === 'therapeutic_area' ? '#a855f7' : '#06b6d4',
                  }}
                />
              </div>
              {/* Expanded: recent signals */}
              {isExpanded && trend.recent_signals && trend.recent_signals.length > 0 && (
                <div className="mt-3 pt-3 space-y-2" style={{ borderTop: '1px solid #F1F5F9' }}>
                  {trend.recent_signals.slice(0, 3).map((sig, i) => (
                    <div key={i} className="text-xs" style={{ color: '#5B6E8A' }}>
                      <span className="font-medium" style={{ color: '#1E293B' }}>{sig.company_name}</span>
                      {' — '}
                      {sig.headline}
                    </div>
                  ))}
                </div>
              )}
            </div>
          );
        })}
      </div>
    </section>
  );
}
```

**Step 4: Insert the section between Battle Cards and Market Signals**

In the `IntelligenceOverview` component, between the `</section>` for Battle Cards and the `<section>` for Market Signals, add:

```tsx
{/* Therapeutic Trends Section */}
<TherapeuticTrendsSection />
```

**Step 5: Commit**

```bash
git add frontend/src/api/therapeuticTrends.ts \
    frontend/src/hooks/useIntelPanelData.ts \
    frontend/src/components/pages/IntelligencePage.tsx
git commit -m "feat: add therapeutic trends section to intelligence page"
```

---

## Task 9: Return Briefing Banner

**Files:**
- Create: `frontend/src/api/returnBriefing.ts`
- Modify: `frontend/src/hooks/useIntelPanelData.ts` (add hook)
- Modify: `frontend/src/components/pages/IntelligencePage.tsx` (add banner)

**Step 1: Create API client**

Create `frontend/src/api/returnBriefing.ts`:

```typescript
import { apiClient } from "./client";

export interface ReturnBriefing {
  hours_away: number;
  last_active: string;
  generated_at: string;
  changes: {
    new_signals?: { count?: number; by_company?: Record<string, number> };
    new_insights?: { count?: number };
    competitive_changes?: Array<{ type: string; company: string; summary: string }>;
    email_intel?: Record<string, unknown>;
  };
  summary: string;
  priority_items: Array<{
    type: string;
    company?: string;
    text: string;
    priority: number;
  }>;
}

export async function getReturnBriefing(): Promise<ReturnBriefing | null> {
  try {
    const response = await apiClient.get<ReturnBriefing>("/intelligence/return-briefing");
    // Backend returns empty/error if not needed
    if (!response.data || (response.data as any).status === "no_briefing_needed") {
      return null;
    }
    return response.data;
  } catch {
    return null;
  }
}
```

**Step 2: Add hook**

In `frontend/src/hooks/useIntelPanelData.ts`:

```typescript
import { getReturnBriefing, type ReturnBriefing } from "@/api/returnBriefing";

export function useReturnBriefing() {
  return useQuery<ReturnBriefing | null>({
    queryKey: ["intel", "return-briefing"],
    queryFn: getReturnBriefing,
    staleTime: 30 * 60_000, // 30 minutes — don't re-fetch often
    retry: false,
  });
}
```

**Step 3: Build the banner component**

In `IntelligencePage.tsx`, add a `ReturnBriefingBanner` component:

```tsx
function ReturnBriefingBanner() {
  const { data: briefing } = useReturnBriefing();
  const [dismissed, setDismissed] = useState(() => {
    return sessionStorage.getItem("aria_briefing_dismissed") === "true";
  });

  if (!briefing || dismissed) return null;

  const handleDismiss = () => {
    setDismissed(true);
    sessionStorage.setItem("aria_briefing_dismissed", "true");
  };

  const hoursAway = Math.round(briefing.hours_away);
  const daysAway = hoursAway >= 24 ? Math.round(hoursAway / 24) : null;
  const awayText = daysAway ? `${daysAway} day${daysAway > 1 ? "s" : ""}` : `${hoursAway} hours`;

  const signalCount = briefing.changes?.new_signals?.count ?? 0;
  const companyCount = briefing.changes?.new_signals?.by_company
    ? Object.keys(briefing.changes.new_signals.by_company).length
    : 0;
  const insightCount = briefing.changes?.new_insights?.count ?? 0;

  return (
    <div
      className="rounded-lg p-5 mb-6"
      style={{
        backgroundColor: "#EFF6FF",
        borderLeft: "4px solid #3B82F6",
      }}
    >
      <div className="flex items-start justify-between mb-2">
        <h3 className="text-sm font-semibold" style={{ color: "#1E40AF" }}>
          Welcome back! Here's what changed while you were away:
        </h3>
        <button
          onClick={handleDismiss}
          className="text-xs font-medium px-2 py-1 rounded hover:bg-blue-100 transition-colors"
          style={{ color: "#3B82F6" }}
        >
          Dismiss
        </button>
      </div>

      <p className="text-sm mb-3" style={{ color: "#1E40AF" }}>
        You were away for {awayText}.
        {signalCount > 0 && ` ${signalCount} new market signal${signalCount !== 1 ? "s" : ""}`}
        {companyCount > 0 && ` across ${companyCount} compan${companyCount !== 1 ? "ies" : "y"}`}
        {signalCount > 0 && "."}
        {insightCount > 0 && ` ${insightCount} new intelligence insight${insightCount !== 1 ? "s" : ""}.`}
      </p>

      {briefing.priority_items && briefing.priority_items.length > 0 && (
        <div className="space-y-1.5">
          <span className="text-xs font-semibold uppercase tracking-wider" style={{ color: "#1E40AF" }}>
            Priority items:
          </span>
          {briefing.priority_items.map((item, i) => (
            <p key={i} className="text-sm" style={{ color: "#334155" }}>
              <span className="font-mono text-[10px] px-1 py-0.5 rounded mr-1.5" style={{ backgroundColor: "#DBEAFE", color: "#1E40AF" }}>
                {item.type?.toUpperCase()}
              </span>
              {item.company && <span className="font-medium">{item.company}: </span>}
              {item.text}
            </p>
          ))}
        </div>
      )}
    </div>
  );
}
```

**Step 4: Insert at top of IntelligenceOverview**

In the `IntelligenceOverview` component, right after the header `<div className="mb-8">` section and before the Loading State section, add:

```tsx
{/* Return Briefing */}
<ReturnBriefingBanner />
```

**Step 5: Import hooks**

Add `useReturnBriefing` to the imports from `@/hooks/useIntelPanelData`.

**Step 6: Commit**

```bash
git add frontend/src/api/returnBriefing.ts \
    frontend/src/hooks/useIntelPanelData.ts \
    frontend/src/components/pages/IntelligencePage.tsx
git commit -m "feat: add return briefing banner to intelligence page"
```

---

## Task 10: Backend Verification

**Step 1: Check backend starts without import errors**

```bash
cd backend && PYTHONPATH=. python3 -c "
from src.utils.company_aliases import normalize_company_name, get_signal_company_names_for_battle_card, clear_cache

# Test basic mode (no DB)
assert normalize_company_name('Pall Corporation') == 'Pall', f'Got: {normalize_company_name(\"Pall Corporation\")}'
assert normalize_company_name('Sartorius AG') == 'Sartorius'
assert normalize_company_name('Unknown Company') == 'Unknown Company'
assert normalize_company_name(None) == ''
assert normalize_company_name('') == ''
print('Basic mode: PASS')

# Test get_signal_company_names basic mode
names = get_signal_company_names_for_battle_card('Cytiva')
assert 'Cytiva' in names
print(f'Basic signal names for Cytiva: {names}')
print('All basic tests: PASS')
"
```

**Step 2: Verify no hardcoded user IDs in production code**

```bash
grep -rn "41475700" backend/src/ --include="*.py" | grep -v test | grep -v __pycache__
# Should return 0 lines
```

**Step 3: Verify no direct COMPANY_CANONICAL_NAMES imports**

```bash
grep -rn "COMPANY_CANONICAL_NAMES\|PERSON_TO_COMPANY" backend/src/ --include="*.py" | grep -v __pycache__ | grep -v company_aliases.py
# Should return 0 lines
```

---

## Task 11: Frontend Verification

**Step 1: TypeScript compilation check**

```bash
cd frontend && npx tsc --noEmit
```

Fix any type errors.

**Step 2: Lint check**

```bash
cd frontend && npm run lint
```

Fix any lint errors.

**Step 3: Build check**

```bash
cd frontend && npm run build
```

Ensure clean build.

**Step 4: Final commit if any fixes needed**

```bash
git add -A
git commit -m "fix: resolve type and lint errors from intelligence page enhancements"
```

---

## Task 12: Final Commit + Summary

**Step 1: Verify git status is clean**

```bash
git status
```

**Step 2: Review all commits made**

```bash
git log --oneline -10
```

Expected commits (newest first):
1. `fix: resolve type and lint errors...` (if needed)
2. `feat: add return briefing banner to intelligence page`
3. `feat: add therapeutic trends section to intelligence page`
4. `fix: ensure battle card preview tooltips render correctly`
5. `feat: add company filter chips for market signals`
6. `feat: add signal click-to-expand and relevance indicator`
7. `fix: replace hardcoded Repligen references with dynamic company context`
8. `fix: remove hardcoded user ID from backfill_insights`
9. `feat: wire dynamic company aliases through all backend callers`
10. `refactor: make company alias normalization dynamic from battle_cards DB`
