# US-935: ARIA Role Configuration & Persona UI — Design Document

**Date:** 2026-02-07
**Story:** US-935 (Phase 9D: ARIA Product Experience)
**Status:** Approved

---

## Summary

Users configure ARIA's focus area, personality traits, domain focus, competitor watchlist, and communication preferences through a settings page at `/settings/aria-config`. Config is stored in `user_settings.preferences.aria_config` and feeds into all agent decisions and the personality system.

---

## Data Model & Storage

Config stored in existing `user_settings.preferences` JSONB column under the `aria_config` key. No new database tables required.

### Backend Pydantic Models (`backend/src/models/aria_config.py`)

```python
class ARIARole(str, Enum):
    SALES_OPS = "sales_ops"
    BD_SALES = "bd_sales"
    MARKETING = "marketing"
    EXECUTIVE_SUPPORT = "executive_support"
    CUSTOM = "custom"

class PersonalityTraits(BaseModel):
    proactiveness: float = Field(0.7, ge=0.0, le=1.0)  # 0=reactive, 1=very proactive
    verbosity: float = Field(0.5, ge=0.0, le=1.0)      # 0=terse, 1=detailed
    formality: float = Field(0.5, ge=0.0, le=1.0)      # 0=casual, 1=formal
    assertiveness: float = Field(0.6, ge=0.0, le=1.0)   # 0=suggestive, 1=directive

class DomainFocus(BaseModel):
    therapeutic_areas: list[str] = Field(default_factory=list)
    modalities: list[str] = Field(default_factory=list)
    geographies: list[str] = Field(default_factory=list)

class CommunicationPrefs(BaseModel):
    preferred_channels: list[str] = Field(default_factory=lambda: ["in_app"])
    notification_frequency: str = "balanced"  # minimal, balanced, aggressive
    response_depth: str = "moderate"          # brief, moderate, detailed
    briefing_time: str = "08:00"

class ARIAConfigUpdate(BaseModel):
    role: ARIARole
    custom_role_description: str | None = None
    personality: PersonalityTraits
    domain_focus: DomainFocus
    competitor_watchlist: list[str] = Field(default_factory=list)
    communication: CommunicationPrefs

class ARIAConfigResponse(BaseModel):
    role: ARIARole
    custom_role_description: str | None
    personality: PersonalityTraits
    domain_focus: DomainFocus
    competitor_watchlist: list[str]
    communication: CommunicationPrefs
    personality_defaults: PersonalityTraits  # calibrated baseline for reset
    updated_at: str | None
```

### Personality Baseline Interaction

- First visit: load auto-calibrated values from `digital_twin.personality_calibration` as defaults
- User overrides stored separately in `aria_config.personality`
- `personality_defaults` stored alongside so reset always has a target
- "Reset to defaults" copies calibrated values back into `aria_config.personality`

---

## Backend API & Service Layer

### Route (`backend/src/api/routes/aria_config.py`)

Prefix: `/api/v1/aria-config`, tags: `["aria-config"]`

```
GET  /api/v1/aria-config              -> ARIAConfigResponse
PUT  /api/v1/aria-config              -> ARIAConfigResponse
POST /api/v1/aria-config/preview      -> PreviewResponse
POST /api/v1/aria-config/reset-personality -> ARIAConfigResponse
```

All endpoints require `CurrentUser` dependency injection. Follow existing `preferences.py` pattern.

### Service (`backend/src/services/aria_config_service.py`)

- `get_config(user_id)` — reads `user_settings.preferences.aria_config`, merges with calibrated defaults for first-time users
- `update_config(user_id, data)` — validates, persists, logs to audit
- `generate_preview(user_id, data)` — builds prompt with config traits, calls Claude to produce a sample response in the configured persona
- `reset_personality(user_id)` — reads `digital_twin.personality_calibration`, writes those values into `aria_config.personality`

---

## Frontend Page — Light Surface

**Route:** `/settings/aria-config` with `ProtectedRoute` wrapper. Added to settings nav sidebar.

**Theme:** Light surface (`bg-[#FAFAF9]`) — settings are "producing work" context per ARIA Design System.

**Page:** `frontend/src/pages/ARIAConfigPage.tsx` — follows `PreferencesSettingsPage` pattern (local state synced from server, auto-save on change, optimistic updates, success toasts).

### Sections

1. **Header** — `font-display text-[32px]` "Configure ARIA", subtitle in `font-sans text-[15px] text-[#6B7280]`

2. **Role Selector** — Grid of 5 cards: Sales Ops, BD/Sales, Marketing, Executive Support, Custom
   - Card spec: `bg-white border border-[#E2E0DC] rounded-xl p-6 shadow-sm`
   - Selected: `border-[#5B6E8A] bg-[#5B6E8A]/5`
   - Each card: Lucide icon (24x24, stroke-width 1.5), role name, brief description
   - Custom: reveals textarea following form input spec

3. **Personality Sliders** — Four horizontal range inputs
   - Proactiveness: "Wait for instructions" <-> "Take initiative"
   - Verbosity: "Just the headlines" <-> "Full analysis"
   - Formality: "Casual colleague" <-> "Professional advisor"
   - Assertiveness: "Suggest options" <-> "Give recommendations"
   - Track: `bg-[#E2E0DC]`, fill: `bg-[#5B6E8A]`, thumb: 44px minimum touch target
   - Extreme labels: `font-sans text-[13px] text-[#6B7280]`
   - Current value: `font-mono text-[13px]`
   - "Reset to defaults" ghost button below sliders

4. **Domain Focus** — Three tag inputs with suggestion dropdowns
   - Therapeutic Areas (suggestions: oncology, immunology, rare disease, neurology, cardiology, etc.)
   - Modalities (suggestions: biologics, small molecule, cell therapy, gene therapy, ADC, etc.)
   - Geographies (suggestions: North America, EU, APAC, etc.)
   - Tags as chips: `bg-[#F5F5F0] border border-[#E2E0DC] rounded-lg px-3 py-1 font-sans text-[13px]`
   - Type to filter suggestions, Enter to add custom values

5. **Competitor Watchlist** — Single tag input, same chip pattern as domain focus

6. **Communication Preferences**
   - Channel toggles: In-App, Email, Slack
   - Notification frequency: segmented control (Minimal / Balanced / Aggressive)
   - Response depth: segmented control (Brief / Moderate / Detailed)
   - Briefing time: time input

7. **Preview Panel** — `bg-white border border-[#E2E0DC] rounded-xl p-6`
   - Static template updates instantly as settings change (per-role templates with trait-adjusted language)
   - "Generate preview" secondary button triggers LLM call for accurate sample
   - ARIA's voice in italic `font-display`

### Design System Compliance

- Spacing: 32px between sections, 24px within sections, 16px between elements (4px base)
- Focus rings: `ring-2 ring-[#7B8EAA] ring-offset-2` on all interactive elements
- Touch targets: 44px minimum
- Labels: proper `<label>` with `htmlFor`
- Keyboard navigation for all controls
- Motion: 200-300ms ease-in-out for surface transitions, 120-180ms ease-out for micro-interactions
- No neon, no gradients, no bright accents — muted slate-blue tonal system only

---

## Frontend Supporting Files

### API Client (`frontend/src/api/ariaConfig.ts`)

Type definitions matching backend models. Async functions calling `apiClient.get()` / `apiClient.put()` / `apiClient.post()`.

### Hook (`frontend/src/hooks/useAriaConfig.ts`)

React Query pattern matching `usePreferences.ts`:
- `useAriaConfig()` — query for fetching config
- `useUpdateAriaConfig()` — mutation with optimistic updates and rollback
- `useGeneratePreview()` — mutation for LLM preview
- `useResetPersonality()` — mutation for reset to defaults

### Route Registration (`frontend/src/App.tsx`)

Add `/settings/aria-config` route with `ProtectedRoute` wrapper.

### Settings Nav

Add "ARIA Config" entry to settings navigation sidebar with appropriate Lucide icon (Sliders).

---

## Tests

### Backend (`backend/tests/test_aria_config.py`)

- **Model validation:** reject personality values outside 0.0-1.0, require `custom_role_description` when role is `custom`, validate briefing_time format HH:MM, validate enum values for frequency/depth
- **Service layer:** `get_config` returns calibrated defaults for first-time users, `update_config` persists to `user_settings.preferences.aria_config`, `reset_personality` copies calibration values back, `generate_preview` returns well-formed response
- **API endpoints:** GET returns 401 without auth, GET returns defaults for new user, PUT saves and returns updated config, PUT validates payload, POST `/preview` returns sample message, POST `/reset-personality` restores calibrated values
- **Integration:** config feeds into personality calibrator

### Frontend (`frontend/src/pages/__tests__/ARIAConfigPage.test.tsx`)

- Renders all sections (role cards, sliders, tag inputs, communication prefs)
- Role card selection updates state and highlights card
- Custom role shows/hides textarea
- Slider changes trigger auto-save
- Tag input add/remove works
- Reset to defaults restores slider values
- Loading skeleton and error retry states

### Quality Gates

`pytest`, `mypy --strict`, `ruff check`, `ruff format`, `npm run typecheck`, `npm run lint`
