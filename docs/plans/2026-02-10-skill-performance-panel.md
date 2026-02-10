# Skill Performance Panel Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Replace the Installed tab on the Skills page with an enhanced SkillPerformancePanel that shows performance metrics, satisfaction data, custom skill management, and an integrated audit log.

**Architecture:** New `skill_feedback` database table stores user thumbs-up/down votes per execution. Two new backend endpoints serve performance aggregation and feedback submission. The frontend replaces `InstalledSkills` with `SkillPerformancePanel` — stat cards at top, enhanced skills table with mini donut charts and satisfaction, custom skills section with slide-over editor, and audit log with search/filter at the bottom. Thumbs up/down buttons added to `SkillExecutionInline` post-completion.

**Tech Stack:** Python/FastAPI (backend), React/TypeScript/Tailwind/Recharts (frontend), Supabase PostgreSQL (database)

---

### Task 1: Database migration — `skill_feedback` table

**Files:**
- Create: `backend/supabase/migrations/20260210100000_skill_feedback.sql`

**Step 1: Write the migration SQL**

```sql
-- Migration: Skill Feedback Table
-- Stores user thumbs up/down feedback per skill execution

CREATE TABLE IF NOT EXISTS skill_feedback (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    skill_id TEXT NOT NULL,
    execution_id TEXT NOT NULL,
    feedback TEXT NOT NULL CHECK (feedback IN ('positive', 'negative')),
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- One vote per user per execution
CREATE UNIQUE INDEX IF NOT EXISTS idx_skill_feedback_unique
    ON skill_feedback(user_id, execution_id);

CREATE INDEX IF NOT EXISTS idx_skill_feedback_skill_id
    ON skill_feedback(skill_id);

CREATE INDEX IF NOT EXISTS idx_skill_feedback_user_id
    ON skill_feedback(user_id);

ALTER TABLE skill_feedback ENABLE ROW LEVEL SECURITY;

-- RLS: users manage own feedback only
CREATE POLICY "skill_feedback_select_own" ON skill_feedback
    FOR SELECT USING (user_id = auth.uid());

CREATE POLICY "skill_feedback_insert_own" ON skill_feedback
    FOR INSERT WITH CHECK (user_id = auth.uid());

CREATE POLICY "skill_feedback_update_own" ON skill_feedback
    FOR UPDATE USING (user_id = auth.uid());

CREATE POLICY "skill_feedback_service_role" ON skill_feedback
    FOR ALL USING (auth.role() = 'service_role');

COMMENT ON TABLE skill_feedback IS 'User satisfaction votes (thumbs up/down) for skill executions';
```

**Step 2: Commit**

```bash
git add backend/supabase/migrations/20260210100000_skill_feedback.sql
git commit -m "feat: add skill_feedback table for user satisfaction tracking"
```

---

### Task 2: Backend — feedback and performance endpoints

**Files:**
- Modify: `backend/src/api/routes/skills.py` (add 3 new endpoints + 2 Pydantic models)

**Step 1: Add request/response models to `skills.py`**

Add after the existing `ExecuteSkillRequest` class (around line 97):

```python
class SubmitFeedbackRequest(BaseModel):
    """Request to submit skill execution feedback."""
    feedback: str = Field(..., pattern=r"^(positive|negative)$", description="positive or negative")


class SkillPerformanceResponse(BaseModel):
    """Aggregated performance metrics for a skill."""
    skill_id: str
    success_rate: float = 0.0
    total_executions: int = 0
    avg_execution_time_ms: int = 0
    satisfaction: dict = Field(default_factory=lambda: {"positive": 0, "negative": 0, "ratio": 0.0})
    trust_level: str = "community"
    recent_failures: int = 0


class CustomSkillResponse(BaseModel):
    """A tenant-created custom skill."""
    id: str
    skill_name: str
    description: str | None = None
    skill_type: str
    definition: dict
    trust_level: str = "user"
    performance_metrics: dict = Field(default_factory=dict)
    is_published: bool = False
    version: int = 1
    created_at: str
    updated_at: str


class UpdateCustomSkillRequest(BaseModel):
    """Request to update a custom skill."""
    skill_name: str | None = None
    description: str | None = None
    definition: dict | None = None
```

**Step 2: Add the `POST /skills/{execution_id}/feedback` endpoint**

Add after the existing `execute_skill` endpoint (around line 310):

```python
@router.post("/{execution_id}/feedback")
async def submit_feedback(
    execution_id: str,
    data: SubmitFeedbackRequest,
    current_user: CurrentUser,
) -> StatusResponse:
    """Submit thumbs up/down feedback for a skill execution."""
    from src.db.supabase import get_supabase_client

    client = await get_supabase_client()
    # Upsert: one vote per user per execution
    await client.table("skill_feedback").upsert(
        {
            "user_id": str(current_user.id),
            "skill_id": execution_id.split(":")[0] if ":" in execution_id else execution_id,
            "execution_id": execution_id,
            "feedback": data.feedback,
        },
        on_conflict="user_id,execution_id",
    ).execute()

    logger.info(
        "Skill feedback submitted",
        extra={
            "user_id": current_user.id,
            "execution_id": execution_id,
            "feedback": data.feedback,
        },
    )

    return StatusResponse(status="feedback_recorded")
```

**Step 3: Add the `GET /skills/performance/{skill_id}` endpoint**

Add after the feedback endpoint:

```python
@router.get("/performance/{skill_id}")
async def get_skill_performance(
    skill_id: str,
    current_user: CurrentUser,
) -> SkillPerformanceResponse:
    """Get aggregated performance metrics for a skill."""
    from src.db.supabase import get_supabase_client

    client = await get_supabase_client()

    # Get installed skill info
    skill_row = (
        await client.table("user_skills")
        .select("*")
        .eq("user_id", str(current_user.id))
        .eq("skill_id", skill_id)
        .maybe_single()
        .execute()
    )

    if not skill_row.data:
        raise HTTPException(status_code=404, detail="Skill not installed")

    skill = skill_row.data
    total = int(skill.get("execution_count", 0))
    success = int(skill.get("success_count", 0))
    success_rate = (success / total) if total > 0 else 0.0

    # Get satisfaction from skill_feedback
    feedback_rows = (
        await client.table("skill_feedback")
        .select("feedback")
        .eq("user_id", str(current_user.id))
        .eq("skill_id", skill_id)
        .execute()
    )

    positive = sum(1 for r in (feedback_rows.data or []) if r["feedback"] == "positive")
    negative = sum(1 for r in (feedback_rows.data or []) if r["feedback"] == "negative")
    sat_total = positive + negative
    sat_ratio = (positive / sat_total) if sat_total > 0 else 0.0

    # Get avg execution time from audit log
    audit = _get_audit()
    entries = await audit.get_audit_for_skill(
        str(current_user.id), skill_id, limit=100, offset=0
    )
    times = [e.get("execution_time_ms", 0) for e in entries if e.get("execution_time_ms")]
    avg_time = int(sum(times) / len(times)) if times else 0

    # Recent failures (last 20 executions)
    recent = entries[:20]
    recent_failures = sum(1 for e in recent if not e.get("success", True))

    return SkillPerformanceResponse(
        skill_id=skill_id,
        success_rate=round(success_rate, 3),
        total_executions=total,
        avg_execution_time_ms=avg_time,
        satisfaction={"positive": positive, "negative": negative, "ratio": round(sat_ratio, 3)},
        trust_level=str(skill.get("trust_level", "community")),
        recent_failures=recent_failures,
    )
```

**Step 4: Add custom skills endpoints**

```python
@router.get("/custom")
async def list_custom_skills(
    current_user: CurrentUser,
) -> list[CustomSkillResponse]:
    """List tenant-created custom skills."""
    from src.db.supabase import get_supabase_client

    client = await get_supabase_client()
    result = await client.table("custom_skills").select("*").order("created_at", desc=True).execute()

    return [
        CustomSkillResponse(
            id=str(row["id"]),
            skill_name=row["skill_name"],
            description=row.get("description"),
            skill_type=row["skill_type"],
            definition=row["definition"],
            trust_level=row.get("trust_level", "user"),
            performance_metrics=row.get("performance_metrics", {}),
            is_published=row.get("is_published", False),
            version=row.get("version", 1),
            created_at=str(row["created_at"]),
            updated_at=str(row["updated_at"]),
        )
        for row in (result.data or [])
    ]


@router.put("/custom/{skill_id}")
async def update_custom_skill(
    skill_id: str,
    data: UpdateCustomSkillRequest,
    current_user: CurrentUser,
) -> CustomSkillResponse:
    """Update a tenant-created custom skill. Only works for skills created by the current user."""
    from src.db.supabase import get_supabase_client

    client = await get_supabase_client()

    # Verify ownership
    existing = (
        await client.table("custom_skills")
        .select("*")
        .eq("id", skill_id)
        .eq("created_by", str(current_user.id))
        .maybe_single()
        .execute()
    )

    if not existing.data:
        raise HTTPException(status_code=404, detail="Custom skill not found or not owned by you")

    update_data: dict[str, Any] = {}
    if data.skill_name is not None:
        update_data["skill_name"] = data.skill_name
    if data.description is not None:
        update_data["description"] = data.description
    if data.definition is not None:
        update_data["definition"] = data.definition

    if not update_data:
        raise HTTPException(status_code=400, detail="No fields to update")

    result = (
        await client.table("custom_skills")
        .update(update_data)
        .eq("id", skill_id)
        .eq("created_by", str(current_user.id))
        .select()
        .single()
        .execute()
    )

    row = result.data
    logger.info(
        "Custom skill updated",
        extra={"user_id": current_user.id, "skill_id": skill_id},
    )

    return CustomSkillResponse(
        id=str(row["id"]),
        skill_name=row["skill_name"],
        description=row.get("description"),
        skill_type=row["skill_type"],
        definition=row["definition"],
        trust_level=row.get("trust_level", "user"),
        performance_metrics=row.get("performance_metrics", {}),
        is_published=row.get("is_published", False),
        version=row.get("version", 1),
        created_at=str(row["created_at"]),
        updated_at=str(row["updated_at"]),
    )


@router.delete("/custom/{skill_id}")
async def delete_custom_skill(
    skill_id: str,
    current_user: CurrentUser,
) -> StatusResponse:
    """Delete a tenant-created custom skill."""
    from src.db.supabase import get_supabase_client

    client = await get_supabase_client()
    result = (
        await client.table("custom_skills")
        .delete()
        .eq("id", skill_id)
        .eq("created_by", str(current_user.id))
        .execute()
    )

    if not result.data:
        raise HTTPException(status_code=404, detail="Custom skill not found or not owned by you")

    logger.info(
        "Custom skill deleted",
        extra={"user_id": current_user.id, "skill_id": skill_id},
    )

    return StatusResponse(status="deleted")
```

**Step 5: Verify lint**

Run: `cd /Users/dhruv/aria && ruff check backend/src/api/routes/skills.py`
Expected: No errors (or fix any that appear)

**Step 6: Commit**

```bash
git add backend/src/api/routes/skills.py
git commit -m "feat: add skill performance, feedback, and custom skill API endpoints"
```

---

### Task 3: Frontend API types and functions

**Files:**
- Modify: `frontend/src/api/skills.ts` (add types + 5 functions)

**Step 1: Add new TypeScript interfaces**

Add after the existing `AvailableSkillsFilters` interface (line 113):

```typescript
export interface SkillPerformance {
  skill_id: string;
  success_rate: number;
  total_executions: number;
  avg_execution_time_ms: number;
  satisfaction: { positive: number; negative: number; ratio: number };
  trust_level: TrustLevel;
  recent_failures: number;
}

export interface CustomSkill {
  id: string;
  skill_name: string;
  description: string | null;
  skill_type: string;
  definition: Record<string, unknown>;
  trust_level: TrustLevel;
  performance_metrics: Record<string, unknown>;
  is_published: boolean;
  version: number;
  created_at: string;
  updated_at: string;
}

export interface UpdateCustomSkillData {
  skill_name?: string;
  description?: string;
  definition?: Record<string, unknown>;
}
```

**Step 2: Add API functions**

Add after existing `listPendingPlans` function (line 203):

```typescript
export async function getSkillPerformance(
  skillId: string
): Promise<SkillPerformance> {
  const response = await apiClient.get<SkillPerformance>(
    `/skills/performance/${skillId}`
  );
  return response.data;
}

export async function submitSkillFeedback(
  executionId: string,
  feedback: "positive" | "negative"
): Promise<void> {
  await apiClient.post(`/skills/${executionId}/feedback`, { feedback });
}

export async function listCustomSkills(): Promise<CustomSkill[]> {
  const response = await apiClient.get<CustomSkill[]>("/skills/custom");
  return response.data;
}

export async function updateCustomSkill(
  skillId: string,
  data: UpdateCustomSkillData
): Promise<CustomSkill> {
  const response = await apiClient.put<CustomSkill>(
    `/skills/custom/${skillId}`,
    data
  );
  return response.data;
}

export async function deleteCustomSkill(skillId: string): Promise<void> {
  await apiClient.delete(`/skills/custom/${skillId}`);
}
```

**Step 3: Commit**

```bash
git add frontend/src/api/skills.ts
git commit -m "feat: add skill performance, feedback, and custom skill API client functions"
```

---

### Task 4: Frontend React Query hooks

**Files:**
- Modify: `frontend/src/hooks/useSkills.ts` (add 5 hooks + query keys)

**Step 1: Update imports**

Replace the import block at the top of `useSkills.ts`:

```typescript
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  listAvailableSkills,
  listInstalledSkills,
  installSkill,
  uninstallSkill,
  getSkillAudit,
  getExecutionPlan,
  approveExecutionPlan,
  rejectExecutionPlan,
  listPendingPlans,
  approveSkillGlobally,
  getSkillPerformance,
  submitSkillFeedback,
  listCustomSkills,
  updateCustomSkill,
  deleteCustomSkill,
  type AvailableSkillsFilters,
  type UpdateCustomSkillData,
} from "@/api/skills";
```

**Step 2: Add query keys**

Add to the existing `skillKeys` object:

```typescript
export const skillKeys = {
  all: ["skills"] as const,
  available: () => [...skillKeys.all, "available"] as const,
  availableFiltered: (filters?: AvailableSkillsFilters) =>
    [...skillKeys.available(), { filters }] as const,
  installed: () => [...skillKeys.all, "installed"] as const,
  audit: () => [...skillKeys.all, "audit"] as const,
  auditFiltered: (skillId?: string) =>
    [...skillKeys.audit(), { skillId }] as const,
  plans: () => [...skillKeys.all, "plans"] as const,
  pendingPlans: () => [...skillKeys.plans(), "pending"] as const,
  plan: (planId: string) => [...skillKeys.plans(), planId] as const,
  performance: (skillId: string) =>
    [...skillKeys.all, "performance", skillId] as const,
  custom: () => [...skillKeys.all, "custom"] as const,
};
```

**Step 3: Add new hooks at the end of the file**

```typescript
// Skill performance metrics
export function useSkillPerformance(skillId: string | null) {
  return useQuery({
    queryKey: skillKeys.performance(skillId ?? ""),
    queryFn: () => getSkillPerformance(skillId!),
    enabled: !!skillId,
  });
}

// Submit skill feedback (thumbs up/down)
export function useSubmitFeedback() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({
      executionId,
      feedback,
    }: {
      executionId: string;
      feedback: "positive" | "negative";
    }) => submitSkillFeedback(executionId, feedback),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: skillKeys.all });
    },
  });
}

// List custom skills
export function useCustomSkills() {
  return useQuery({
    queryKey: skillKeys.custom(),
    queryFn: () => listCustomSkills(),
  });
}

// Update custom skill
export function useUpdateCustomSkill() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({
      skillId,
      data,
    }: {
      skillId: string;
      data: UpdateCustomSkillData;
    }) => updateCustomSkill(skillId, data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: skillKeys.custom() });
    },
  });
}

// Delete custom skill
export function useDeleteCustomSkill() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (skillId: string) => deleteCustomSkill(skillId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: skillKeys.custom() });
    },
  });
}
```

**Step 4: Commit**

```bash
git add frontend/src/hooks/useSkills.ts
git commit -m "feat: add React Query hooks for skill performance, feedback, and custom skills"
```

---

### Task 5: MiniDonutChart component

**Files:**
- Create: `frontend/src/components/skills/MiniDonutChart.tsx`

**Step 1: Create the component**

```typescript
import { PieChart, Pie, Cell } from "recharts";

interface MiniDonutChartProps {
  /** Value from 0 to 1 */
  value: number;
  /** Size in pixels */
  size?: number;
  /** Color for the filled portion */
  color?: string;
  /** Color for the unfilled portion */
  bgColor?: string;
}

export function MiniDonutChart({
  value,
  size = 40,
  color = "#22c55e",
  bgColor = "#334155",
}: MiniDonutChartProps) {
  const clamped = Math.max(0, Math.min(1, value));
  const data = [
    { value: clamped },
    { value: 1 - clamped },
  ];

  return (
    <PieChart width={size} height={size}>
      <Pie
        data={data}
        cx={size / 2 - 1}
        cy={size / 2 - 1}
        innerRadius={size / 2 - 8}
        outerRadius={size / 2 - 2}
        startAngle={90}
        endAngle={-270}
        dataKey="value"
        stroke="none"
      >
        <Cell fill={color} />
        <Cell fill={bgColor} />
      </Pie>
    </PieChart>
  );
}
```

**Step 2: Commit**

```bash
git add frontend/src/components/skills/MiniDonutChart.tsx
git commit -m "feat: add MiniDonutChart component for inline success rate visualization"
```

---

### Task 6: SkillSatisfactionButtons component

**Files:**
- Create: `frontend/src/components/skills/SkillSatisfactionButtons.tsx`
- Modify: `frontend/src/components/skills/SkillExecutionInline.tsx` (wire up buttons)

**Step 1: Create the satisfaction buttons component**

```typescript
import { useState } from "react";
import { ThumbsUp, ThumbsDown } from "lucide-react";
import { useSubmitFeedback } from "@/hooks/useSkills";

interface SkillSatisfactionButtonsProps {
  executionId: string;
  initialFeedback?: "positive" | "negative" | null;
}

export function SkillSatisfactionButtons({
  executionId,
  initialFeedback = null,
}: SkillSatisfactionButtonsProps) {
  const [selected, setSelected] = useState<"positive" | "negative" | null>(
    initialFeedback
  );
  const submitFeedback = useSubmitFeedback();

  const handleFeedback = (feedback: "positive" | "negative") => {
    const newValue = selected === feedback ? null : feedback;
    setSelected(newValue);
    if (newValue) {
      submitFeedback.mutate({ executionId, feedback: newValue });
    }
  };

  return (
    <span className="inline-flex items-center gap-1 ml-2">
      <button
        onClick={() => handleFeedback("positive")}
        className={`p-1 rounded transition-colors ${
          selected === "positive"
            ? "text-success bg-success/10"
            : "text-slate-500 hover:text-success hover:bg-success/10"
        }`}
        title="Helpful"
      >
        <ThumbsUp className="w-3 h-3" />
      </button>
      <button
        onClick={() => handleFeedback("negative")}
        className={`p-1 rounded transition-colors ${
          selected === "negative"
            ? "text-critical bg-critical/10"
            : "text-slate-500 hover:text-critical hover:bg-critical/10"
        }`}
        title="Not helpful"
      >
        <ThumbsDown className="w-3 h-3" />
      </button>
    </span>
  );
}
```

**Step 2: Add satisfaction buttons to SkillExecutionInline**

In `SkillExecutionInline.tsx`, add import at the top:

```typescript
import { SkillSatisfactionButtons } from "./SkillSatisfactionButtons";
```

In the `SimpleExecution` component, after the execution time `<span>` (around line 58), add within the inline indicator `<div>`:

```typescript
{isDone && execution.executionId && (
  <SkillSatisfactionButtons executionId={execution.executionId} />
)}
```

Also update the `SimpleExecutionProps` interface to include `executionId`:

```typescript
interface SimpleExecutionProps {
  skillName: string;
  status: StepStatus;
  resultSummary?: string | null;
  executionTimeMs?: number | null;
  executionId?: string | null;
}
```

And update `SkillExecutionData` to include `executionId`:

```typescript
export interface SkillExecutionData {
  type: "simple" | "plan";
  skillName?: string;
  status?: StepStatus;
  resultSummary?: string | null;
  executionTimeMs?: number | null;
  executionId?: string | null;
  planId?: string;
}
```

Pass `executionId` through in the `SkillExecutionInline` render:

```typescript
if (execution.type === "simple" && execution.skillName) {
  return (
    <SimpleExecution
      skillName={execution.skillName}
      status={execution.status ?? "pending"}
      resultSummary={execution.resultSummary}
      executionTimeMs={execution.executionTimeMs}
      executionId={execution.executionId}
    />
  );
}
```

**Step 3: Commit**

```bash
git add frontend/src/components/skills/SkillSatisfactionButtons.tsx frontend/src/components/skills/SkillExecutionInline.tsx
git commit -m "feat: add thumbs up/down satisfaction buttons to skill execution results"
```

---

### Task 7: SkillEditSlideOver component

**Files:**
- Create: `frontend/src/components/skills/SkillEditSlideOver.tsx`

**Step 1: Create the slide-over editor**

```typescript
import { useState, useEffect } from "react";
import { X, Save, Loader2 } from "lucide-react";
import type { CustomSkill } from "@/api/skills";
import { useUpdateCustomSkill } from "@/hooks/useSkills";

interface SkillEditSlideOverProps {
  skill: CustomSkill;
  open: boolean;
  onClose: () => void;
}

export function SkillEditSlideOver({
  skill,
  open,
  onClose,
}: SkillEditSlideOverProps) {
  const [name, setName] = useState(skill.skill_name);
  const [description, setDescription] = useState(skill.description ?? "");
  const [definitionJson, setDefinitionJson] = useState(
    JSON.stringify(skill.definition, null, 2)
  );
  const [jsonError, setJsonError] = useState<string | null>(null);
  const updateSkill = useUpdateCustomSkill();

  useEffect(() => {
    setName(skill.skill_name);
    setDescription(skill.description ?? "");
    setDefinitionJson(JSON.stringify(skill.definition, null, 2));
    setJsonError(null);
  }, [skill]);

  const handleSave = () => {
    let parsedDef: Record<string, unknown> | undefined;
    try {
      parsedDef = JSON.parse(definitionJson);
      setJsonError(null);
    } catch {
      setJsonError("Invalid JSON");
      return;
    }

    updateSkill.mutate(
      {
        skillId: skill.id,
        data: {
          skill_name: name !== skill.skill_name ? name : undefined,
          description: description !== (skill.description ?? "") ? description : undefined,
          definition: parsedDef,
        },
      },
      { onSuccess: onClose }
    );
  };

  if (!open) return null;

  return (
    <>
      {/* Backdrop */}
      <div
        className="fixed inset-0 bg-black/50 backdrop-blur-sm z-40"
        onClick={onClose}
      />

      {/* Panel */}
      <div className="fixed right-0 top-0 h-full w-96 bg-slate-900 border-l border-slate-700 z-50 flex flex-col animate-in slide-in-from-right duration-200">
        {/* Header */}
        <div className="flex items-center justify-between p-4 border-b border-slate-700">
          <h3 className="text-lg font-semibold text-white">Edit Skill</h3>
          <button
            onClick={onClose}
            className="p-1.5 text-slate-400 hover:text-white hover:bg-slate-800 rounded-lg transition-colors"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* Form */}
        <div className="flex-1 overflow-y-auto p-4 space-y-4">
          <div>
            <label className="block text-sm font-medium text-slate-300 mb-1">
              Name
            </label>
            <input
              type="text"
              value={name}
              onChange={(e) => setName(e.target.value)}
              className="w-full px-3 py-2 bg-slate-800 border border-slate-700 rounded-lg text-white text-sm focus:outline-none focus:border-primary-500"
            />
          </div>

          <div>
            <label className="block text-sm font-medium text-slate-300 mb-1">
              Description
            </label>
            <textarea
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              rows={3}
              className="w-full px-3 py-2 bg-slate-800 border border-slate-700 rounded-lg text-white text-sm focus:outline-none focus:border-primary-500 resize-none"
            />
          </div>

          <div>
            <label className="block text-sm font-medium text-slate-300 mb-1">
              Definition (JSON)
            </label>
            <textarea
              value={definitionJson}
              onChange={(e) => {
                setDefinitionJson(e.target.value);
                setJsonError(null);
              }}
              rows={12}
              className={`w-full px-3 py-2 bg-slate-800 border rounded-lg text-white text-sm font-mono focus:outline-none resize-none ${
                jsonError
                  ? "border-critical focus:border-critical"
                  : "border-slate-700 focus:border-primary-500"
              }`}
            />
            {jsonError && (
              <p className="mt-1 text-xs text-critical">{jsonError}</p>
            )}
          </div>
        </div>

        {/* Footer */}
        <div className="flex items-center justify-end gap-2 p-4 border-t border-slate-700">
          <button
            onClick={onClose}
            className="px-4 py-2 text-sm font-medium text-slate-400 hover:text-white hover:bg-slate-800 rounded-lg transition-colors"
          >
            Cancel
          </button>
          <button
            onClick={handleSave}
            disabled={!name.trim() || updateSkill.isPending}
            className="inline-flex items-center gap-2 px-4 py-2 text-sm font-medium text-white bg-primary-600 hover:bg-primary-500 rounded-lg transition-colors disabled:opacity-50"
          >
            {updateSkill.isPending ? (
              <Loader2 className="w-4 h-4 animate-spin" />
            ) : (
              <Save className="w-4 h-4" />
            )}
            Save
          </button>
        </div>
      </div>
    </>
  );
}
```

**Step 2: Commit**

```bash
git add frontend/src/components/skills/SkillEditSlideOver.tsx
git commit -m "feat: add SkillEditSlideOver component for editing custom skill definitions"
```

---

### Task 8: SkillPerformancePanel component

**Files:**
- Create: `frontend/src/components/skills/SkillPerformancePanel.tsx`

This is the main component that replaces `InstalledSkills` on the "Installed" tab. It has four sections: stat cards, skills table, custom skills, and audit log.

**Step 1: Create the component file**

The component is structured as:
1. `StatCard` — reusable stat card sub-component
2. `PerformanceSkillRow` — enhanced skill row with donut chart + satisfaction
3. `CustomSkillsSection` — custom skills list with edit/delete
4. `AuditSection` — search/filter-enhanced audit log
5. `SkillPerformancePanel` — main export that assembles all sections

```typescript
import { useState, useMemo } from "react";
import {
  Activity,
  CheckCircle2,
  Zap,
  Clock,
  Pencil,
  Trash2,
  Search,
  ChevronDown,
  ChevronUp,
  Sparkles,
  ArrowUpCircle,
} from "lucide-react";
import type { InstalledSkill, AuditEntry, CustomSkill } from "@/api/skills";
import {
  useInstalledSkills,
  useUninstallSkill,
  useSkillAudit,
  useCustomSkills,
  useDeleteCustomSkill,
  useApproveSkillGlobally,
} from "@/hooks/useSkills";
import { TrustLevelBadge } from "./TrustLevelBadge";
import { MiniDonutChart } from "./MiniDonutChart";
import { SkillEditSlideOver } from "./SkillEditSlideOver";

// --- Helpers ---

function formatDuration(ms: number): string {
  if (ms < 1000) return `${ms}ms`;
  return `${(ms / 1000).toFixed(1)}s`;
}

function formatRelative(dateString: string): string {
  const date = new Date(dateString);
  const now = new Date();
  const diffMs = now.getTime() - date.getTime();
  const diffMins = Math.floor(diffMs / 60000);
  const diffHours = Math.floor(diffMins / 60);
  const diffDays = Math.floor(diffHours / 24);

  if (diffMins < 1) return "just now";
  if (diffMins < 60) return `${diffMins}m ago`;
  if (diffHours < 24) return `${diffHours}h ago`;
  if (diffDays < 7) return `${diffDays}d ago`;
  return new Date(dateString).toLocaleDateString("en-US", {
    month: "short",
    day: "numeric",
  });
}

function formatTimestamp(dateString: string): string {
  return new Date(dateString).toLocaleString("en-US", {
    month: "short",
    day: "numeric",
    hour: "numeric",
    minute: "2-digit",
    hour12: true,
  });
}

function successRateColor(rate: number): string {
  if (rate >= 0.8) return "#22c55e"; // success green
  if (rate >= 0.5) return "#f59e0b"; // warning amber
  return "#ef4444"; // critical red
}

// --- Stat Card ---

interface StatCardProps {
  icon: React.ReactNode;
  label: string;
  value: string;
  sub?: string;
}

function StatCard({ icon, label, value, sub }: StatCardProps) {
  return (
    <div className="bg-slate-800/50 border border-slate-700 rounded-xl p-4">
      <div className="flex items-center gap-2 text-slate-400 mb-2">
        {icon}
        <span className="text-xs font-medium">{label}</span>
      </div>
      <div className="text-2xl font-bold text-white">{value}</div>
      {sub && <div className="text-xs text-slate-500 mt-1">{sub}</div>}
    </div>
  );
}

// --- Performance Skill Row ---

interface PerformanceSkillRowProps {
  skill: InstalledSkill;
  onUninstall: () => void;
  isUninstalling: boolean;
}

function PerformanceSkillRow({
  skill,
  onUninstall,
  isUninstalling,
}: PerformanceSkillRowProps) {
  const [confirmUninstall, setConfirmUninstall] = useState(false);
  const approveGlobally = useApproveSkillGlobally();
  const [confirmUpgrade, setConfirmUpgrade] = useState(false);

  const successRate =
    skill.execution_count > 0
      ? skill.success_count / skill.execution_count
      : 0;
  const successPct = Math.round(successRate * 100);

  return (
    <div className="group bg-slate-800/50 border border-slate-700 rounded-xl p-4 transition-all duration-200 hover:bg-slate-800/80 hover:border-slate-600">
      <div className="flex items-center gap-4">
        {/* Mini donut chart */}
        <div className="flex-shrink-0">
          <MiniDonutChart
            value={successRate}
            color={successRateColor(successRate)}
          />
        </div>

        {/* Info */}
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2">
            <h3 className="text-sm font-semibold text-white truncate">
              {skill.skill_path}
            </h3>
            <TrustLevelBadge level={skill.trust_level} size="sm" />
          </div>
          <div className="mt-1 flex flex-wrap items-center gap-3 text-xs text-slate-500">
            <span
              className={
                successPct >= 80
                  ? "text-success"
                  : successPct >= 50
                    ? "text-warning"
                    : "text-critical"
              }
            >
              {successPct}% success
            </span>
            <span>{skill.execution_count} executions</span>
            {skill.last_used_at && (
              <span>{formatRelative(skill.last_used_at)}</span>
            )}
          </div>
        </div>

        {/* Actions */}
        <div className="flex-shrink-0 flex items-center gap-1">
          {/* Upgrade trust (only for USER skills) */}
          {skill.trust_level === "user" && (
            <>
              {confirmUpgrade ? (
                <div className="flex items-center gap-1 mr-2">
                  <button
                    onClick={() => {
                      approveGlobally.mutate(skill.skill_id);
                      setConfirmUpgrade(false);
                    }}
                    className="px-2 py-1 text-xs font-medium text-primary-400 bg-primary-500/10 border border-primary-500/30 hover:bg-primary-500/20 rounded-lg transition-colors"
                  >
                    Confirm
                  </button>
                  <button
                    onClick={() => setConfirmUpgrade(false)}
                    className="px-2 py-1 text-xs text-slate-400 hover:text-white rounded-lg transition-colors"
                  >
                    Cancel
                  </button>
                </div>
              ) : (
                <button
                  onClick={() => setConfirmUpgrade(true)}
                  className="p-1.5 text-slate-500 hover:text-primary-400 hover:bg-primary-500/10 rounded-lg transition-colors opacity-0 group-hover:opacity-100"
                  title="Approve globally"
                >
                  <ArrowUpCircle className="w-4 h-4" />
                </button>
              )}
            </>
          )}

          {/* Uninstall */}
          {confirmUninstall ? (
            <div className="flex items-center gap-1">
              <button
                onClick={() => {
                  onUninstall();
                  setConfirmUninstall(false);
                }}
                disabled={isUninstalling}
                className="px-2 py-1 text-xs font-medium text-critical bg-critical/10 border border-critical/30 hover:bg-critical/20 rounded-lg transition-colors disabled:opacity-50"
              >
                {isUninstalling ? "Removing..." : "Confirm"}
              </button>
              <button
                onClick={() => setConfirmUninstall(false)}
                className="px-2 py-1 text-xs text-slate-400 hover:text-white rounded-lg transition-colors"
              >
                Cancel
              </button>
            </div>
          ) : (
            <button
              onClick={() => setConfirmUninstall(true)}
              className="p-1.5 text-slate-500 hover:text-critical hover:bg-critical/10 rounded-lg transition-colors opacity-0 group-hover:opacity-100"
              title="Uninstall"
            >
              <Trash2 className="w-4 h-4" />
            </button>
          )}
        </div>
      </div>
    </div>
  );
}

// --- Custom Skills Section ---

function CustomSkillsSection() {
  const { data: skills, isLoading } = useCustomSkills();
  const deleteSkill = useDeleteCustomSkill();
  const [editingSkill, setEditingSkill] = useState<CustomSkill | null>(null);
  const [confirmDeleteId, setConfirmDeleteId] = useState<string | null>(null);

  if (isLoading) {
    return (
      <div className="space-y-2">
        {[1, 2].map((i) => (
          <div
            key={i}
            className="bg-slate-800/30 border border-slate-700/50 rounded-lg p-4 animate-pulse"
          >
            <div className="h-4 bg-slate-700 rounded w-40" />
          </div>
        ))}
      </div>
    );
  }

  if (!skills || skills.length === 0) {
    return (
      <div className="text-center py-8">
        <Sparkles className="w-8 h-8 text-slate-600 mx-auto mb-2" />
        <p className="text-sm text-slate-500">
          Create custom skills to extend ARIA&apos;s capabilities.
        </p>
      </div>
    );
  }

  return (
    <>
      <div className="space-y-2">
        {skills.map((skill) => (
          <div
            key={skill.id}
            className="group bg-slate-800/30 border border-slate-700/50 rounded-lg p-4 flex items-center justify-between transition-colors hover:bg-slate-800/50"
          >
            <div className="min-w-0">
              <div className="flex items-center gap-2">
                <span className="text-sm font-medium text-white">
                  {skill.skill_name}
                </span>
                <span className="px-1.5 py-0.5 text-xs text-slate-400 bg-slate-700/50 rounded">
                  v{skill.version}
                </span>
              </div>
              {skill.description && (
                <p className="text-xs text-slate-500 mt-0.5 truncate max-w-md">
                  {skill.description}
                </p>
              )}
            </div>

            <div className="flex items-center gap-1 flex-shrink-0">
              <button
                onClick={() => setEditingSkill(skill)}
                className="p-1.5 text-slate-500 hover:text-primary-400 hover:bg-primary-500/10 rounded-lg transition-colors opacity-0 group-hover:opacity-100"
                title="Edit"
              >
                <Pencil className="w-4 h-4" />
              </button>
              {confirmDeleteId === skill.id ? (
                <div className="flex items-center gap-1">
                  <button
                    onClick={() => {
                      deleteSkill.mutate(skill.id);
                      setConfirmDeleteId(null);
                    }}
                    className="px-2 py-1 text-xs text-critical bg-critical/10 border border-critical/30 rounded-lg"
                  >
                    Delete
                  </button>
                  <button
                    onClick={() => setConfirmDeleteId(null)}
                    className="px-2 py-1 text-xs text-slate-400 rounded-lg"
                  >
                    Cancel
                  </button>
                </div>
              ) : (
                <button
                  onClick={() => setConfirmDeleteId(skill.id)}
                  className="p-1.5 text-slate-500 hover:text-critical hover:bg-critical/10 rounded-lg transition-colors opacity-0 group-hover:opacity-100"
                  title="Delete"
                >
                  <Trash2 className="w-4 h-4" />
                </button>
              )}
            </div>
          </div>
        ))}
      </div>

      {editingSkill && (
        <SkillEditSlideOver
          skill={editingSkill}
          open={!!editingSkill}
          onClose={() => setEditingSkill(null)}
        />
      )}
    </>
  );
}

// --- Audit Section ---

type AuditFilter = "all" | "success" | "failed";

function AuditSection() {
  const { data: entries, isLoading } = useSkillAudit();
  const [search, setSearch] = useState("");
  const [filter, setFilter] = useState<AuditFilter>("all");
  const [expandedId, setExpandedId] = useState<string | null>(null);

  const filtered = useMemo(() => {
    if (!entries) return [];
    return entries.filter((e: AuditEntry) => {
      if (filter === "success" && !e.success) return false;
      if (filter === "failed" && e.success) return false;
      if (search && !e.skill_path.toLowerCase().includes(search.toLowerCase()))
        return false;
      return true;
    });
  }, [entries, filter, search]);

  if (isLoading) {
    return (
      <div className="space-y-2">
        {[1, 2, 3].map((i) => (
          <div
            key={i}
            className="bg-slate-800/30 border border-slate-700/50 rounded-lg p-4 animate-pulse"
          >
            <div className="flex gap-3">
              <div className="w-2 h-2 mt-1.5 bg-slate-700 rounded-full" />
              <div className="flex-1 space-y-2">
                <div className="h-4 bg-slate-700 rounded w-40" />
                <div className="h-3 bg-slate-700 rounded w-24" />
              </div>
            </div>
          </div>
        ))}
      </div>
    );
  }

  return (
    <div className="space-y-3">
      {/* Search + filters */}
      <div className="flex items-center gap-2">
        <div className="relative flex-1">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-500" />
          <input
            type="text"
            placeholder="Search by skill name..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="w-full pl-9 pr-3 py-2 bg-slate-800/50 border border-slate-700 rounded-lg text-sm text-white placeholder-slate-500 focus:outline-none focus:border-primary-500"
          />
        </div>
        <div className="flex gap-1">
          {(["all", "success", "failed"] as AuditFilter[]).map((f) => (
            <button
              key={f}
              onClick={() => setFilter(f)}
              className={`px-3 py-2 text-xs font-medium rounded-lg transition-colors capitalize ${
                filter === f
                  ? "bg-primary-600/20 text-primary-400"
                  : "text-slate-400 hover:text-white hover:bg-slate-700/50"
              }`}
            >
              {f}
            </button>
          ))}
        </div>
      </div>

      {/* Entries */}
      {filtered.length === 0 ? (
        <p className="text-sm text-slate-500 text-center py-6">
          No matching audit entries.
        </p>
      ) : (
        <div className="space-y-1.5">
          {filtered.map((entry: AuditEntry) => {
            const isExpanded = expandedId === entry.id;
            return (
              <div
                key={entry.id}
                className="bg-slate-800/30 border border-slate-700/50 rounded-lg transition-colors hover:bg-slate-800/50"
              >
                <button
                  onClick={() =>
                    setExpandedId(isExpanded ? null : entry.id)
                  }
                  className="w-full p-3 flex items-center justify-between text-left"
                >
                  <div className="flex items-center gap-3 min-w-0">
                    <div
                      className={`flex-shrink-0 w-2 h-2 rounded-full ${
                        entry.success ? "bg-success" : "bg-critical"
                      }`}
                    />
                    <span className="text-sm font-medium text-white truncate">
                      {entry.skill_path}
                    </span>
                    <TrustLevelBadge
                      level={entry.skill_trust_level}
                      size="sm"
                    />
                    <span className="text-xs text-slate-500">
                      {formatTimestamp(entry.created_at)}
                    </span>
                    <span className="text-xs text-slate-500">
                      {formatDuration(entry.execution_time_ms)}
                    </span>
                  </div>
                  {isExpanded ? (
                    <ChevronUp className="w-4 h-4 text-slate-500 flex-shrink-0" />
                  ) : (
                    <ChevronDown className="w-4 h-4 text-slate-500 flex-shrink-0" />
                  )}
                </button>

                {isExpanded && (
                  <div className="px-3 pb-3 border-t border-slate-700/50 pt-2 space-y-2 text-xs">
                    {entry.agent_id && (
                      <div>
                        <span className="text-slate-500">Agent:</span>{" "}
                        <span className="text-slate-300">{entry.agent_id}</span>
                      </div>
                    )}
                    <div>
                      <span className="text-slate-500">Data requested:</span>{" "}
                      <span className="text-slate-300">
                        {entry.data_classes_requested.join(", ") || "none"}
                      </span>
                    </div>
                    <div>
                      <span className="text-slate-500">Data granted:</span>{" "}
                      <span className="text-slate-300">
                        {entry.data_classes_granted.join(", ") || "none"}
                      </span>
                    </div>
                    {entry.security_flags.length > 0 && (
                      <div className="flex flex-wrap gap-1">
                        {entry.security_flags.map((flag) => (
                          <span
                            key={flag}
                            className="px-1.5 py-0.5 text-warning bg-warning/10 border border-warning/20 rounded"
                          >
                            {flag}
                          </span>
                        ))}
                      </div>
                    )}
                    {entry.data_redacted && (
                      <span className="text-slate-500">
                        Data was sanitized during execution
                      </span>
                    )}
                    {entry.error && (
                      <div className="p-2 bg-critical/10 border border-critical/20 rounded text-critical">
                        {entry.error}
                      </div>
                    )}
                  </div>
                )}
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}

// --- Skill Discovery Placeholder ---

function SkillDiscoveryPlaceholder() {
  return (
    <div className="bg-slate-800/30 border border-dashed border-slate-700 rounded-xl p-6 text-center">
      <Sparkles className="w-6 h-6 text-primary-400 mx-auto mb-2" />
      <p className="text-sm text-slate-400">
        ARIA will recommend skills based on your usage patterns
      </p>
      <p className="text-xs text-slate-600 mt-1">Coming in Wave 6</p>
    </div>
  );
}

// --- Main Component ---

export function SkillPerformancePanel() {
  const { data: skills, isLoading, error } = useInstalledSkills();
  const uninstallSkill = useUninstallSkill();

  // Aggregate stats
  const stats = useMemo(() => {
    if (!skills || skills.length === 0) {
      return {
        total: 0,
        avgSuccess: 0,
        totalExecutions: 0,
        avgTime: "—",
      };
    }

    const totalExec = skills.reduce(
      (sum: number, s: InstalledSkill) => sum + s.execution_count,
      0
    );
    const totalSuccess = skills.reduce(
      (sum: number, s: InstalledSkill) => sum + s.success_count,
      0
    );
    const avgSuccess =
      totalExec > 0 ? Math.round((totalSuccess / totalExec) * 100) : 0;

    return {
      total: skills.length,
      avgSuccess,
      totalExecutions: totalExec,
      avgTime: "—", // Would need per-skill perf data for this; placeholder
    };
  }, [skills]);

  if (error) {
    return (
      <div className="bg-critical/10 border border-critical/30 rounded-xl p-4">
        <p className="text-critical">
          Failed to load skills. Please try again.
        </p>
      </div>
    );
  }

  if (isLoading) {
    return (
      <div className="space-y-6">
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
          {[1, 2, 3, 4].map((i) => (
            <div
              key={i}
              className="bg-slate-800/50 border border-slate-700 rounded-xl p-4 animate-pulse"
            >
              <div className="h-3 bg-slate-700 rounded w-20 mb-3" />
              <div className="h-7 bg-slate-700 rounded w-12" />
            </div>
          ))}
        </div>
        <div className="space-y-3">
          {[1, 2, 3].map((i) => (
            <div
              key={i}
              className="bg-slate-800/50 border border-slate-700 rounded-xl p-5 animate-pulse"
            >
              <div className="flex items-center gap-4">
                <div className="w-10 h-10 bg-slate-700 rounded-full" />
                <div className="flex-1 space-y-2">
                  <div className="h-4 bg-slate-700 rounded w-48" />
                  <div className="h-3 bg-slate-700 rounded w-32" />
                </div>
              </div>
            </div>
          ))}
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-8">
      {/* Stat cards */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        <StatCard
          icon={<Activity className="w-4 h-4" />}
          label="Installed"
          value={String(stats.total)}
          sub={`${stats.total} skill${stats.total !== 1 ? "s" : ""}`}
        />
        <StatCard
          icon={<CheckCircle2 className="w-4 h-4" />}
          label="Success Rate"
          value={`${stats.avgSuccess}%`}
          sub="across all skills"
        />
        <StatCard
          icon={<Zap className="w-4 h-4" />}
          label="Executions"
          value={stats.totalExecutions.toLocaleString()}
          sub="total runs"
        />
        <StatCard
          icon={<Clock className="w-4 h-4" />}
          label="Avg Time"
          value={stats.avgTime}
          sub="per execution"
        />
      </div>

      {/* Skill discovery placeholder */}
      <SkillDiscoveryPlaceholder />

      {/* Installed skills table */}
      {skills && skills.length > 0 ? (
        <div>
          <h2 className="text-sm font-semibold text-slate-300 uppercase tracking-wider mb-3">
            Installed Skills
          </h2>
          <div className="space-y-2">
            {skills.map((skill: InstalledSkill, index: number) => (
              <div
                key={skill.id}
                className="animate-in fade-in slide-in-from-bottom-4"
                style={{
                  animationDelay: `${index * 50}ms`,
                  animationFillMode: "both",
                }}
              >
                <PerformanceSkillRow
                  skill={skill}
                  onUninstall={() => uninstallSkill.mutate(skill.skill_id)}
                  isUninstalling={
                    uninstallSkill.isPending &&
                    uninstallSkill.variables === skill.skill_id
                  }
                />
              </div>
            ))}
          </div>
        </div>
      ) : (
        <div className="flex flex-col items-center justify-center py-12">
          <div className="w-16 h-16 bg-slate-800 border border-slate-700 rounded-2xl flex items-center justify-center mb-4">
            <Zap className="w-8 h-8 text-slate-500" />
          </div>
          <h3 className="text-lg font-semibold text-white">
            No skills installed
          </h3>
          <p className="mt-1 text-slate-400 text-sm">
            Browse the catalog to install skills.
          </p>
        </div>
      )}

      {/* Custom skills */}
      <div>
        <h2 className="text-sm font-semibold text-slate-300 uppercase tracking-wider mb-3">
          Custom Skills
        </h2>
        <CustomSkillsSection />
      </div>

      {/* Audit log */}
      <div>
        <h2 className="text-sm font-semibold text-slate-300 uppercase tracking-wider mb-3">
          Recent Activity
        </h2>
        <AuditSection />
      </div>
    </div>
  );
}
```

**Step 2: Commit**

```bash
git add frontend/src/components/skills/SkillPerformancePanel.tsx
git commit -m "feat: add SkillPerformancePanel component with stats, donut charts, custom skills, and audit log"
```

---

### Task 9: Wire SkillPerformancePanel into Skills page

**Files:**
- Modify: `frontend/src/components/skills/index.ts` (add exports)
- Modify: `frontend/src/pages/Skills.tsx` (swap InstalledSkills → SkillPerformancePanel)

**Step 1: Update barrel exports**

Add to `frontend/src/components/skills/index.ts`:

```typescript
export { MiniDonutChart } from "./MiniDonutChart";
export { SkillSatisfactionButtons } from "./SkillSatisfactionButtons";
export { SkillEditSlideOver } from "./SkillEditSlideOver";
export { SkillPerformancePanel } from "./SkillPerformancePanel";
```

**Step 2: Update Skills page**

In `frontend/src/pages/Skills.tsx`:

1. Replace `InstalledSkills` import with `SkillPerformancePanel`:

```typescript
import { SkillBrowser, SkillPerformancePanel, SkillAuditLog } from "@/components/skills";
```

2. Replace the tab content render (line 79):

```typescript
{activeTab === "installed" && <SkillPerformancePanel />}
```

**Step 3: Run lint and type-check**

Run: `cd /Users/dhruv/aria/frontend && npm run lint && npm run typecheck`
Expected: No errors

**Step 4: Commit**

```bash
git add frontend/src/components/skills/index.ts frontend/src/pages/Skills.tsx
git commit -m "feat: wire SkillPerformancePanel into Skills page, replacing InstalledSkills tab"
```

---

### Task 10: Verify and fix lint/type errors

**Files:**
- Any files that have lint or type errors

**Step 1: Run full frontend checks**

Run: `cd /Users/dhruv/aria/frontend && npm run typecheck && npm run lint`

**Step 2: Run backend checks**

Run: `cd /Users/dhruv/aria && ruff check backend/src/api/routes/skills.py && ruff format backend/src/api/routes/skills.py`

**Step 3: Fix any issues found**

Address each error individually — type mismatches, missing imports, unused variables, etc.

**Step 4: Commit fixes if needed**

```bash
git add -A
git commit -m "fix: resolve lint and type-check issues in skill performance panel"
```
