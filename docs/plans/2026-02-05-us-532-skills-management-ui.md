# US-532 UI: Skills Management Frontend Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Build a complete skills management page with browse, installed, and activity tabs — enabling users to discover, install, uninstall, and monitor skill executions from the ARIA frontend.

**Architecture:** Three-layer approach following existing patterns: API client (`api/skills.ts`) → React Query hooks (`hooks/useSkills.ts`) → Components (`components/skills/*`) → Page (`pages/Skills.tsx`). Tab-based layout with Browse, Installed, and Activity views. All components follow the existing dark slate theme with `DashboardLayout` wrapper. The page is wired into the sidebar navigation and router.

**Tech Stack:** React 18, TypeScript (strict), Tailwind CSS v4, React Query (@tanstack/react-query), Axios, React Router v7

**Design Direction:** Refined luxury — matching ARIA's existing dark slate aesthetic with sky blue primary / violet accent. Clean typography (DM Sans), subtle glassmorphism on cards, smooth staggered entry animations, trust level badges with distinct color personalities. The design extends the existing badge/card/modal patterns rather than introducing new paradigms.

---

### Task 1: Create Skills API Client

The API client layer defines TypeScript types matching the backend Pydantic models and wraps each endpoint with typed Axios calls. Follows the exact pattern of `api/goals.ts`.

**Files:**
- Create: `frontend/src/api/skills.ts`

**Step 1: Write the API client**

```typescript
import { apiClient } from "./client";

// Types matching backend Pydantic models

export type TrustLevel = "core" | "verified" | "community" | "user";

export interface AvailableSkill {
  id: string;
  skill_path: string;
  skill_name: string;
  description: string | null;
  author: string | null;
  version: string | null;
  tags: string[];
  trust_level: TrustLevel;
  life_sciences_relevant: boolean;
}

export interface InstalledSkill {
  id: string;
  skill_id: string;
  skill_path: string;
  trust_level: TrustLevel;
  execution_count: number;
  success_count: number;
  installed_at: string;
  last_used_at: string | null;
}

export interface SkillExecution {
  skill_id: string;
  skill_path: string;
  trust_level: TrustLevel;
  success: boolean;
  result: unknown;
  error: string | null;
  execution_time_ms: number;
  sanitized: boolean;
}

export interface AuditEntry {
  id: string;
  user_id: string;
  skill_id: string;
  skill_path: string;
  skill_trust_level: TrustLevel;
  trigger_reason: string;
  data_classes_requested: string[];
  data_classes_granted: string[];
  input_hash: string;
  output_hash: string | null;
  execution_time_ms: number;
  success: boolean;
  error: string | null;
  data_redacted: boolean;
  tokens_used: string[];
  task_id: string | null;
  agent_id: string | null;
  security_flags: string[];
  created_at: string;
}

export interface TrustInfo {
  skill_id: string;
  successful_executions: number;
  failed_executions: number;
  session_trust_granted: boolean;
  globally_approved: boolean;
  globally_approved_at: string | null;
}

export interface AvailableSkillsFilters {
  query?: string;
  trust_level?: TrustLevel;
  life_sciences?: boolean;
  limit?: number;
}

// API functions

export async function listAvailableSkills(
  filters?: AvailableSkillsFilters
): Promise<AvailableSkill[]> {
  const params = new URLSearchParams();
  if (filters?.query) params.append("query", filters.query);
  if (filters?.trust_level) params.append("trust_level", filters.trust_level);
  if (filters?.life_sciences !== undefined)
    params.append("life_sciences", String(filters.life_sciences));
  if (filters?.limit) params.append("limit", String(filters.limit));

  const url = params.toString() ? `/skills/available?${params}` : "/skills/available";
  const response = await apiClient.get<AvailableSkill[]>(url);
  return response.data;
}

export async function listInstalledSkills(): Promise<InstalledSkill[]> {
  const response = await apiClient.get<InstalledSkill[]>("/skills/installed");
  return response.data;
}

export async function installSkill(skillId: string): Promise<InstalledSkill> {
  const response = await apiClient.post<InstalledSkill>("/skills/install", {
    skill_id: skillId,
  });
  return response.data;
}

export async function uninstallSkill(skillId: string): Promise<void> {
  await apiClient.delete(`/skills/${skillId}`);
}

export async function executeSkill(
  skillId: string,
  inputData: Record<string, unknown> = {}
): Promise<SkillExecution> {
  const response = await apiClient.post<SkillExecution>("/skills/execute", {
    skill_id: skillId,
    input_data: inputData,
  });
  return response.data;
}

export async function getSkillAudit(
  skillId?: string,
  limit = 50,
  offset = 0
): Promise<AuditEntry[]> {
  const params = new URLSearchParams();
  if (skillId) params.append("skill_id", skillId);
  params.append("limit", String(limit));
  params.append("offset", String(offset));

  const response = await apiClient.get<AuditEntry[]>(`/skills/audit?${params}`);
  return response.data;
}

export async function getSkillTrust(skillId: string): Promise<TrustInfo> {
  const response = await apiClient.get<TrustInfo>(`/skills/autonomy/${skillId}`);
  return response.data;
}

export async function approveSkillGlobally(skillId: string): Promise<TrustInfo> {
  const response = await apiClient.post<TrustInfo>(
    `/skills/autonomy/${skillId}/approve`
  );
  return response.data;
}
```

**Step 2: Verify the file compiles**

Run: `cd /Users/dhruv/aria/frontend && npx tsc --noEmit src/api/skills.ts 2>&1 | head -20`
Expected: No errors (or only unrelated errors from other files)

**Step 3: Commit**

```bash
git add frontend/src/api/skills.ts
git commit -m "feat(ui): add skills API client with types"
```

---

### Task 2: Create Skills React Query Hooks

Custom hooks for data fetching (queries) and mutations following the exact pattern in `hooks/useGoals.ts` — query key factory, `useQuery` for reads, `useMutation` with cache invalidation for writes.

**Files:**
- Create: `frontend/src/hooks/useSkills.ts`

**Step 1: Write the hooks**

```typescript
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  listAvailableSkills,
  listInstalledSkills,
  installSkill,
  uninstallSkill,
  getSkillAudit,
  type AvailableSkillsFilters,
} from "@/api/skills";

// Query keys
export const skillKeys = {
  all: ["skills"] as const,
  available: () => [...skillKeys.all, "available"] as const,
  availableFiltered: (filters?: AvailableSkillsFilters) =>
    [...skillKeys.available(), { filters }] as const,
  installed: () => [...skillKeys.all, "installed"] as const,
  audit: () => [...skillKeys.all, "audit"] as const,
  auditFiltered: (skillId?: string) =>
    [...skillKeys.audit(), { skillId }] as const,
};

// List available skills
export function useAvailableSkills(filters?: AvailableSkillsFilters) {
  return useQuery({
    queryKey: skillKeys.availableFiltered(filters),
    queryFn: () => listAvailableSkills(filters),
  });
}

// List installed skills
export function useInstalledSkills() {
  return useQuery({
    queryKey: skillKeys.installed(),
    queryFn: () => listInstalledSkills(),
  });
}

// Install skill mutation
export function useInstallSkill() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (skillId: string) => installSkill(skillId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: skillKeys.installed() });
      queryClient.invalidateQueries({ queryKey: skillKeys.available() });
    },
  });
}

// Uninstall skill mutation
export function useUninstallSkill() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (skillId: string) => uninstallSkill(skillId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: skillKeys.installed() });
      queryClient.invalidateQueries({ queryKey: skillKeys.available() });
    },
  });
}

// Skill audit log
export function useSkillAudit(skillId?: string) {
  return useQuery({
    queryKey: skillKeys.auditFiltered(skillId),
    queryFn: () => getSkillAudit(skillId),
  });
}
```

**Step 2: Verify the file compiles**

Run: `cd /Users/dhruv/aria/frontend && npx tsc --noEmit src/hooks/useSkills.ts 2>&1 | head -20`
Expected: No errors

**Step 3: Commit**

```bash
git add frontend/src/hooks/useSkills.ts
git commit -m "feat(ui): add React Query hooks for skills"
```

---

### Task 3: Create TrustLevelBadge Component

A reusable badge component for displaying skill trust levels (Core, Verified, Community, User). Follows the exact pattern of `GoalStatusBadge` — config map, size variants, color-coded with icons.

**Files:**
- Create: `frontend/src/components/skills/TrustLevelBadge.tsx`

**Step 1: Write the badge component**

```tsx
import type { TrustLevel } from "@/api/skills";

interface TrustLevelBadgeProps {
  level: TrustLevel;
  size?: "sm" | "md";
}

const trustConfig: Record<
  TrustLevel,
  { label: string; color: string; icon: string }
> = {
  core: {
    label: "Core",
    color: "bg-primary-500/20 text-primary-400 border-primary-500/30",
    icon: "M9 12l2 2 4-4m5.618-4.016A11.955 11.955 0 0112 2.944a11.955 11.955 0 01-8.618 3.04A12.02 12.02 0 003 9c0 5.591 3.824 10.29 9 11.622 5.176-1.332 9-6.03 9-11.622 0-1.042-.133-2.052-.382-3.016z",
  },
  verified: {
    label: "Verified",
    color: "bg-emerald-500/20 text-emerald-400 border-emerald-500/30",
    icon: "M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z",
  },
  community: {
    label: "Community",
    color: "bg-amber-500/20 text-amber-400 border-amber-500/30",
    icon: "M17 20h5v-2a3 3 0 00-5.356-1.857M17 20H7m10 0v-2c0-.656-.126-1.283-.356-1.857M7 20H2v-2a3 3 0 015.356-1.857M7 20v-2c0-.656.126-1.283.356-1.857m0 0a5.002 5.002 0 019.288 0M15 7a3 3 0 11-6 0 3 3 0 016 0z",
  },
  user: {
    label: "User",
    color: "bg-slate-500/20 text-slate-400 border-slate-500/30",
    icon: "M16 7a4 4 0 11-8 0 4 4 0 018 0zM12 14a7 7 0 00-7 7h14a7 7 0 00-7-7z",
  },
};

export function TrustLevelBadge({ level, size = "md" }: TrustLevelBadgeProps) {
  const config = trustConfig[level];
  const sizeClasses =
    size === "sm" ? "px-2 py-0.5 text-xs" : "px-2.5 py-1 text-sm";

  return (
    <span
      className={`inline-flex items-center gap-1.5 rounded-full border font-medium ${config.color} ${sizeClasses}`}
    >
      <svg
        className={size === "sm" ? "w-3 h-3" : "w-3.5 h-3.5"}
        fill="none"
        stroke="currentColor"
        viewBox="0 0 24 24"
      >
        <path
          strokeLinecap="round"
          strokeLinejoin="round"
          strokeWidth={2}
          d={config.icon}
        />
      </svg>
      {config.label}
    </span>
  );
}
```

**Step 2: Commit**

```bash
git add frontend/src/components/skills/TrustLevelBadge.tsx
git commit -m "feat(ui): add TrustLevelBadge component"
```

---

### Task 4: Create SkillCard Component

Card component for displaying a single skill in the browse view. Shows name, description, author, tags, trust level badge, and an install/installed indicator. Follows the `GoalCard` pattern: dark slate background, gradient hover effect, hover-revealed actions.

**Files:**
- Create: `frontend/src/components/skills/SkillCard.tsx`

**Step 1: Write the card component**

```tsx
import type { AvailableSkill } from "@/api/skills";
import { TrustLevelBadge } from "./TrustLevelBadge";

interface SkillCardProps {
  skill: AvailableSkill;
  isInstalled: boolean;
  onInstall: () => void;
  isInstalling?: boolean;
}

export function SkillCard({
  skill,
  isInstalled,
  onInstall,
  isInstalling = false,
}: SkillCardProps) {
  return (
    <div className="group relative bg-slate-800/50 border border-slate-700 rounded-xl p-5 transition-all duration-200 hover:bg-slate-800/80 hover:border-slate-600 hover:shadow-lg hover:shadow-slate-900/50">
      {/* Gradient border effect on hover */}
      <div className="absolute inset-0 rounded-xl bg-gradient-to-r from-primary-500/0 via-primary-500/10 to-accent-500/0 opacity-0 group-hover:opacity-100 transition-opacity duration-300 pointer-events-none" />

      <div className="relative">
        {/* Header: name + action */}
        <div className="flex items-start justify-between gap-3">
          <div className="flex-1 min-w-0">
            <h3 className="text-lg font-semibold text-white truncate group-hover:text-primary-400 transition-colors">
              {skill.skill_name}
            </h3>
            {skill.author && (
              <p className="mt-0.5 text-xs text-slate-500">
                by {skill.author}
                {skill.version && (
                  <span className="ml-2 text-slate-600">v{skill.version}</span>
                )}
              </p>
            )}
          </div>

          {/* Install button */}
          {isInstalled ? (
            <span className="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium text-emerald-400 bg-emerald-500/10 border border-emerald-500/20 rounded-lg">
              <svg
                className="w-3.5 h-3.5"
                fill="none"
                stroke="currentColor"
                viewBox="0 0 24 24"
              >
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  strokeWidth={2}
                  d="M5 13l4 4L19 7"
                />
              </svg>
              Installed
            </span>
          ) : (
            <button
              onClick={onInstall}
              disabled={isInstalling}
              className="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium text-white bg-primary-600 hover:bg-primary-500 disabled:opacity-50 disabled:cursor-not-allowed rounded-lg transition-colors shadow-sm"
            >
              {isInstalling ? (
                <>
                  <svg
                    className="w-3.5 h-3.5 animate-spin"
                    fill="none"
                    viewBox="0 0 24 24"
                  >
                    <circle
                      className="opacity-25"
                      cx="12"
                      cy="12"
                      r="10"
                      stroke="currentColor"
                      strokeWidth="4"
                    />
                    <path
                      className="opacity-75"
                      fill="currentColor"
                      d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z"
                    />
                  </svg>
                  Installing
                </>
              ) : (
                <>
                  <svg
                    className="w-3.5 h-3.5"
                    fill="none"
                    stroke="currentColor"
                    viewBox="0 0 24 24"
                  >
                    <path
                      strokeLinecap="round"
                      strokeLinejoin="round"
                      strokeWidth={2}
                      d="M12 4v16m8-8H4"
                    />
                  </svg>
                  Install
                </>
              )}
            </button>
          )}
        </div>

        {/* Description */}
        {skill.description && (
          <p className="mt-2 text-sm text-slate-400 line-clamp-2">
            {skill.description}
          </p>
        )}

        {/* Footer: badges + tags */}
        <div className="mt-3 flex flex-wrap items-center gap-2">
          <TrustLevelBadge level={skill.trust_level} size="sm" />
          {skill.life_sciences_relevant && (
            <span className="inline-flex items-center gap-1 px-2 py-0.5 text-xs font-medium text-violet-400 bg-violet-500/15 border border-violet-500/20 rounded-full">
              <svg
                className="w-3 h-3"
                fill="none"
                stroke="currentColor"
                viewBox="0 0 24 24"
              >
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  strokeWidth={2}
                  d="M19.428 15.428a2 2 0 00-1.022-.547l-2.387-.477a6 6 0 00-3.86.517l-.318.158a6 6 0 01-3.86.517L6.05 15.21a2 2 0 00-1.806.547M8 4h8l-1 1v5.172a2 2 0 00.586 1.414l5 5c1.26 1.26.367 3.414-1.415 3.414H4.828c-1.782 0-2.674-2.154-1.414-3.414l5-5A2 2 0 009 10.172V5L8 4z"
                />
              </svg>
              Life Sciences
            </span>
          )}
          {skill.tags.slice(0, 3).map((tag) => (
            <span
              key={tag}
              className="px-2 py-0.5 text-xs text-slate-500 bg-slate-700/50 rounded-full"
            >
              {tag}
            </span>
          ))}
        </div>
      </div>
    </div>
  );
}
```

**Step 2: Commit**

```bash
git add frontend/src/components/skills/SkillCard.tsx
git commit -m "feat(ui): add SkillCard component"
```

---

### Task 5: Create SkillBrowser Component

The Browse tab content: search input, trust level filter pills, and a grid of `SkillCard` components. Handles search debouncing, filter state, and install actions. Shows loading skeletons and empty state.

**Files:**
- Create: `frontend/src/components/skills/SkillBrowser.tsx`

**Step 1: Write the browser component**

```tsx
import { useState, useMemo } from "react";
import type { TrustLevel } from "@/api/skills";
import {
  useAvailableSkills,
  useInstalledSkills,
  useInstallSkill,
} from "@/hooks/useSkills";
import { SkillCard } from "./SkillCard";

const trustFilters: { value: TrustLevel | "all"; label: string }[] = [
  { value: "all", label: "All" },
  { value: "core", label: "Core" },
  { value: "verified", label: "Verified" },
  { value: "community", label: "Community" },
  { value: "user", label: "User" },
];

export function SkillBrowser() {
  const [search, setSearch] = useState("");
  const [trustFilter, setTrustFilter] = useState<TrustLevel | "all">("all");

  const filters = useMemo(
    () => ({
      query: search || undefined,
      trust_level: trustFilter === "all" ? undefined : trustFilter,
    }),
    [search, trustFilter]
  );

  const { data: skills, isLoading, error } = useAvailableSkills(filters);
  const { data: installed } = useInstalledSkills();
  const installSkill = useInstallSkill();

  const installedIds = useMemo(
    () => new Set(installed?.map((s) => s.skill_id) ?? []),
    [installed]
  );

  return (
    <div>
      {/* Search + filters */}
      <div className="flex flex-col sm:flex-row gap-3 mb-6">
        <div className="relative flex-1">
          <svg
            className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-500"
            fill="none"
            stroke="currentColor"
            viewBox="0 0 24 24"
          >
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              strokeWidth={2}
              d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z"
            />
          </svg>
          <input
            type="text"
            placeholder="Search skills..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="w-full pl-10 pr-4 py-2.5 bg-slate-800 border border-slate-700 rounded-lg text-white placeholder-slate-500 focus:outline-none focus:border-primary-500 focus:ring-1 focus:ring-primary-500 transition-colors"
          />
        </div>
      </div>

      {/* Trust level filter pills */}
      <div className="flex gap-2 mb-6 overflow-x-auto pb-2">
        {trustFilters.map((filter) => (
          <button
            key={filter.value}
            onClick={() => setTrustFilter(filter.value)}
            className={`px-4 py-2 text-sm font-medium rounded-lg whitespace-nowrap transition-colors ${
              trustFilter === filter.value
                ? "bg-primary-600/20 text-primary-400 border border-primary-500/30"
                : "text-slate-400 hover:text-white hover:bg-slate-800"
            }`}
          >
            {filter.label}
          </button>
        ))}
      </div>

      {/* Error */}
      {error && (
        <div className="bg-red-500/10 border border-red-500/30 rounded-xl p-4 mb-6">
          <p className="text-red-400">
            Failed to load skills. Please try again.
          </p>
        </div>
      )}

      {/* Loading skeleton */}
      {isLoading && (
        <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
          {[1, 2, 3, 4, 5, 6].map((i) => (
            <div
              key={i}
              className="bg-slate-800/50 border border-slate-700 rounded-xl p-5 animate-pulse"
            >
              <div className="flex items-start justify-between mb-3">
                <div className="flex-1 space-y-2">
                  <div className="h-5 bg-slate-700 rounded w-3/4" />
                  <div className="h-3 bg-slate-700 rounded w-1/3" />
                </div>
                <div className="h-8 w-20 bg-slate-700 rounded-lg" />
              </div>
              <div className="h-4 bg-slate-700 rounded w-full mb-2" />
              <div className="h-4 bg-slate-700 rounded w-2/3 mb-3" />
              <div className="flex gap-2">
                <div className="h-6 bg-slate-700 rounded-full w-20" />
                <div className="h-6 bg-slate-700 rounded-full w-16" />
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Empty state */}
      {!isLoading && skills && skills.length === 0 && (
        <div className="flex flex-col items-center justify-center py-16 px-4">
          <div className="relative">
            <div className="absolute inset-0 bg-primary-500/20 blur-3xl rounded-full" />
            <div className="relative w-24 h-24 bg-slate-800 border border-slate-700 rounded-2xl flex items-center justify-center">
              <svg
                className="w-12 h-12 text-slate-500"
                fill="none"
                stroke="currentColor"
                viewBox="0 0 24 24"
              >
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  strokeWidth={1.5}
                  d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z"
                />
              </svg>
            </div>
          </div>
          <h3 className="mt-6 text-xl font-semibold text-white">
            No skills found
          </h3>
          <p className="mt-2 text-slate-400 text-center max-w-md">
            {search
              ? `No skills match "${search}". Try a different search term.`
              : "No skills available with the current filters."}
          </p>
        </div>
      )}

      {/* Skills grid */}
      {!isLoading && skills && skills.length > 0 && (
        <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
          {skills.map((skill, index) => (
            <div
              key={skill.id}
              className="animate-in fade-in slide-in-from-bottom-4"
              style={{
                animationDelay: `${index * 50}ms`,
                animationFillMode: "both",
              }}
            >
              <SkillCard
                skill={skill}
                isInstalled={installedIds.has(skill.id)}
                onInstall={() => installSkill.mutate(skill.id)}
                isInstalling={
                  installSkill.isPending &&
                  installSkill.variables === skill.id
                }
              />
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
```

**Step 2: Commit**

```bash
git add frontend/src/components/skills/SkillBrowser.tsx
git commit -m "feat(ui): add SkillBrowser component with search and filters"
```

---

### Task 6: Create InstalledSkills Component

The Installed tab content: lists all installed skills with usage stats (execution count, success rate, last used). Each card has an uninstall button with confirmation. Shows empty state when no skills installed.

**Files:**
- Create: `frontend/src/components/skills/InstalledSkills.tsx`

**Step 1: Write the installed skills component**

```tsx
import { useState } from "react";
import type { InstalledSkill } from "@/api/skills";
import { useInstalledSkills, useUninstallSkill } from "@/hooks/useSkills";
import { TrustLevelBadge } from "./TrustLevelBadge";

function formatDate(dateString: string): string {
  return new Date(dateString).toLocaleDateString("en-US", {
    month: "short",
    day: "numeric",
    year: "numeric",
  });
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
  return formatDate(dateString);
}

interface InstalledSkillRowProps {
  skill: InstalledSkill;
  onUninstall: () => void;
  isUninstalling: boolean;
}

function InstalledSkillRow({
  skill,
  onUninstall,
  isUninstalling,
}: InstalledSkillRowProps) {
  const [confirmUninstall, setConfirmUninstall] = useState(false);
  const successRate =
    skill.execution_count > 0
      ? Math.round((skill.success_count / skill.execution_count) * 100)
      : null;

  return (
    <div className="group bg-slate-800/50 border border-slate-700 rounded-xl p-5 transition-all duration-200 hover:bg-slate-800/80 hover:border-slate-600">
      <div className="flex items-start justify-between gap-4">
        {/* Left: info */}
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2">
            <h3 className="text-base font-semibold text-white truncate">
              {skill.skill_path}
            </h3>
            <TrustLevelBadge level={skill.trust_level} size="sm" />
          </div>

          {/* Stats row */}
          <div className="mt-2 flex flex-wrap items-center gap-4 text-xs text-slate-500">
            <span className="inline-flex items-center gap-1">
              <svg
                className="w-3.5 h-3.5"
                fill="none"
                stroke="currentColor"
                viewBox="0 0 24 24"
              >
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  strokeWidth={2}
                  d="M13 10V3L4 14h7v7l9-11h-7z"
                />
              </svg>
              {skill.execution_count} execution
              {skill.execution_count !== 1 ? "s" : ""}
            </span>
            {successRate !== null && (
              <span
                className={`inline-flex items-center gap-1 ${
                  successRate >= 80
                    ? "text-emerald-500"
                    : successRate >= 50
                      ? "text-amber-500"
                      : "text-red-500"
                }`}
              >
                <svg
                  className="w-3.5 h-3.5"
                  fill="none"
                  stroke="currentColor"
                  viewBox="0 0 24 24"
                >
                  <path
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    strokeWidth={2}
                    d="M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z"
                  />
                </svg>
                {successRate}% success
              </span>
            )}
            {skill.last_used_at && (
              <span className="inline-flex items-center gap-1">
                <svg
                  className="w-3.5 h-3.5"
                  fill="none"
                  stroke="currentColor"
                  viewBox="0 0 24 24"
                >
                  <path
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    strokeWidth={2}
                    d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z"
                  />
                </svg>
                Last used {formatRelative(skill.last_used_at)}
              </span>
            )}
            <span>Installed {formatDate(skill.installed_at)}</span>
          </div>
        </div>

        {/* Right: uninstall */}
        <div className="flex-shrink-0">
          {confirmUninstall ? (
            <div className="flex items-center gap-2">
              <button
                onClick={() => {
                  onUninstall();
                  setConfirmUninstall(false);
                }}
                disabled={isUninstalling}
                className="px-3 py-1.5 text-xs font-medium text-red-400 bg-red-500/10 border border-red-500/30 hover:bg-red-500/20 rounded-lg transition-colors disabled:opacity-50"
              >
                {isUninstalling ? "Removing..." : "Confirm"}
              </button>
              <button
                onClick={() => setConfirmUninstall(false)}
                className="px-3 py-1.5 text-xs font-medium text-slate-400 hover:text-white hover:bg-slate-700 rounded-lg transition-colors"
              >
                Cancel
              </button>
            </div>
          ) : (
            <button
              onClick={() => setConfirmUninstall(true)}
              className="p-2 text-slate-500 hover:text-red-400 hover:bg-red-500/10 rounded-lg transition-colors opacity-0 group-hover:opacity-100"
              title="Uninstall skill"
            >
              <svg
                className="w-4 h-4"
                fill="none"
                stroke="currentColor"
                viewBox="0 0 24 24"
              >
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  strokeWidth={2}
                  d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16"
                />
              </svg>
            </button>
          )}
        </div>
      </div>
    </div>
  );
}

export function InstalledSkills() {
  const { data: skills, isLoading, error } = useInstalledSkills();
  const uninstallSkill = useUninstallSkill();

  // Error
  if (error) {
    return (
      <div className="bg-red-500/10 border border-red-500/30 rounded-xl p-4">
        <p className="text-red-400">
          Failed to load installed skills. Please try again.
        </p>
      </div>
    );
  }

  // Loading
  if (isLoading) {
    return (
      <div className="space-y-3">
        {[1, 2, 3].map((i) => (
          <div
            key={i}
            className="bg-slate-800/50 border border-slate-700 rounded-xl p-5 animate-pulse"
          >
            <div className="flex items-start justify-between">
              <div className="flex-1 space-y-2">
                <div className="flex items-center gap-2">
                  <div className="h-5 bg-slate-700 rounded w-48" />
                  <div className="h-5 bg-slate-700 rounded-full w-20" />
                </div>
                <div className="flex gap-4">
                  <div className="h-4 bg-slate-700 rounded w-24" />
                  <div className="h-4 bg-slate-700 rounded w-20" />
                  <div className="h-4 bg-slate-700 rounded w-28" />
                </div>
              </div>
            </div>
          </div>
        ))}
      </div>
    );
  }

  // Empty
  if (!skills || skills.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center py-16 px-4">
        <div className="relative">
          <div className="absolute inset-0 bg-primary-500/20 blur-3xl rounded-full" />
          <div className="relative w-24 h-24 bg-slate-800 border border-slate-700 rounded-2xl flex items-center justify-center">
            <svg
              className="w-12 h-12 text-slate-500"
              fill="none"
              stroke="currentColor"
              viewBox="0 0 24 24"
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth={1.5}
                d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4"
              />
            </svg>
          </div>
        </div>
        <h3 className="mt-6 text-xl font-semibold text-white">
          No skills installed
        </h3>
        <p className="mt-2 text-slate-400 text-center max-w-md">
          Browse the skill catalog and install skills to extend ARIA&apos;s capabilities.
        </p>
      </div>
    );
  }

  // List
  return (
    <div className="space-y-3">
      {skills.map((skill, index) => (
        <div
          key={skill.id}
          className="animate-in fade-in slide-in-from-bottom-4"
          style={{
            animationDelay: `${index * 50}ms`,
            animationFillMode: "both",
          }}
        >
          <InstalledSkillRow
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
  );
}
```

**Step 2: Commit**

```bash
git add frontend/src/components/skills/InstalledSkills.tsx
git commit -m "feat(ui): add InstalledSkills component with uninstall"
```

---

### Task 7: Create SkillAuditLog Component

The Activity tab content: displays the audit log of skill executions. Each entry shows skill path, trust level, success/failure, execution time, timestamp, and security flags. Entries are listed chronologically with colored status indicators.

**Files:**
- Create: `frontend/src/components/skills/SkillAuditLog.tsx`

**Step 1: Write the audit log component**

```tsx
import type { AuditEntry } from "@/api/skills";
import { useSkillAudit } from "@/hooks/useSkills";
import { TrustLevelBadge } from "./TrustLevelBadge";

function formatTimestamp(dateString: string): string {
  const date = new Date(dateString);
  return date.toLocaleString("en-US", {
    month: "short",
    day: "numeric",
    hour: "numeric",
    minute: "2-digit",
    hour12: true,
  });
}

function formatDuration(ms: number): string {
  if (ms < 1000) return `${ms}ms`;
  return `${(ms / 1000).toFixed(1)}s`;
}

function AuditEntryRow({ entry }: { entry: AuditEntry }) {
  return (
    <div className="group bg-slate-800/30 border border-slate-700/50 rounded-lg p-4 transition-colors hover:bg-slate-800/50">
      <div className="flex items-start justify-between gap-3">
        {/* Left: status + skill info */}
        <div className="flex items-start gap-3 min-w-0">
          {/* Status indicator */}
          <div
            className={`mt-0.5 flex-shrink-0 w-2 h-2 rounded-full ${
              entry.success ? "bg-emerald-400" : "bg-red-400"
            }`}
          />

          <div className="min-w-0">
            <div className="flex items-center gap-2 flex-wrap">
              <span className="text-sm font-medium text-white truncate">
                {entry.skill_path}
              </span>
              <TrustLevelBadge level={entry.skill_trust_level} size="sm" />
            </div>

            <div className="mt-1 flex flex-wrap items-center gap-3 text-xs text-slate-500">
              <span>{formatTimestamp(entry.created_at)}</span>
              <span>{formatDuration(entry.execution_time_ms)}</span>
              {entry.trigger_reason && (
                <span className="text-slate-600">{entry.trigger_reason}</span>
              )}
            </div>

            {/* Error message */}
            {entry.error && (
              <p className="mt-1.5 text-xs text-red-400 line-clamp-1">
                {entry.error}
              </p>
            )}

            {/* Security flags */}
            {entry.security_flags.length > 0 && (
              <div className="mt-1.5 flex flex-wrap gap-1">
                {entry.security_flags.map((flag) => (
                  <span
                    key={flag}
                    className="px-1.5 py-0.5 text-xs text-amber-400 bg-amber-500/10 border border-amber-500/20 rounded"
                  >
                    {flag}
                  </span>
                ))}
              </div>
            )}

            {/* Data redaction indicator */}
            {entry.data_redacted && (
              <span className="mt-1.5 inline-flex items-center gap-1 text-xs text-slate-500">
                <svg
                  className="w-3 h-3"
                  fill="none"
                  stroke="currentColor"
                  viewBox="0 0 24 24"
                >
                  <path
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    strokeWidth={2}
                    d="M12 15v2m-6 4h12a2 2 0 002-2v-6a2 2 0 00-2-2H6a2 2 0 00-2 2v6a2 2 0 002 2zm10-10V7a4 4 0 00-8 0v4h8z"
                  />
                </svg>
                Data sanitized
              </span>
            )}
          </div>
        </div>

        {/* Right: success/fail badge */}
        <span
          className={`flex-shrink-0 px-2 py-0.5 text-xs font-medium rounded ${
            entry.success
              ? "text-emerald-400 bg-emerald-500/10"
              : "text-red-400 bg-red-500/10"
          }`}
        >
          {entry.success ? "Success" : "Failed"}
        </span>
      </div>
    </div>
  );
}

export function SkillAuditLog() {
  const { data: entries, isLoading, error } = useSkillAudit();

  // Error
  if (error) {
    return (
      <div className="bg-red-500/10 border border-red-500/30 rounded-xl p-4">
        <p className="text-red-400">
          Failed to load audit log. Please try again.
        </p>
      </div>
    );
  }

  // Loading
  if (isLoading) {
    return (
      <div className="space-y-3">
        {[1, 2, 3, 4, 5].map((i) => (
          <div
            key={i}
            className="bg-slate-800/30 border border-slate-700/50 rounded-lg p-4 animate-pulse"
          >
            <div className="flex items-start gap-3">
              <div className="w-2 h-2 mt-1.5 bg-slate-700 rounded-full" />
              <div className="flex-1 space-y-2">
                <div className="flex items-center gap-2">
                  <div className="h-4 bg-slate-700 rounded w-40" />
                  <div className="h-4 bg-slate-700 rounded-full w-16" />
                </div>
                <div className="flex gap-3">
                  <div className="h-3 bg-slate-700 rounded w-24" />
                  <div className="h-3 bg-slate-700 rounded w-12" />
                </div>
              </div>
            </div>
          </div>
        ))}
      </div>
    );
  }

  // Empty
  if (!entries || entries.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center py-16 px-4">
        <div className="relative">
          <div className="absolute inset-0 bg-primary-500/20 blur-3xl rounded-full" />
          <div className="relative w-24 h-24 bg-slate-800 border border-slate-700 rounded-2xl flex items-center justify-center">
            <svg
              className="w-12 h-12 text-slate-500"
              fill="none"
              stroke="currentColor"
              viewBox="0 0 24 24"
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth={1.5}
                d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2"
              />
            </svg>
          </div>
        </div>
        <h3 className="mt-6 text-xl font-semibold text-white">
          No activity yet
        </h3>
        <p className="mt-2 text-slate-400 text-center max-w-md">
          Skill execution history will appear here once skills are used.
        </p>
      </div>
    );
  }

  // List
  return (
    <div className="space-y-2">
      {entries.map((entry, index) => (
        <div
          key={entry.id}
          className="animate-in fade-in slide-in-from-bottom-4"
          style={{
            animationDelay: `${index * 30}ms`,
            animationFillMode: "both",
          }}
        >
          <AuditEntryRow entry={entry} />
        </div>
      ))}
    </div>
  );
}
```

**Step 2: Commit**

```bash
git add frontend/src/components/skills/SkillAuditLog.tsx
git commit -m "feat(ui): add SkillAuditLog component"
```

---

### Task 8: Create Skills Component Barrel Export

Create the barrel `index.ts` for the `components/skills/` directory, following the pattern in `components/goals/index.ts`.

**Files:**
- Create: `frontend/src/components/skills/index.ts`

**Step 1: Write the barrel export**

```typescript
export { SkillAuditLog } from "./SkillAuditLog";
export { SkillBrowser } from "./SkillBrowser";
export { SkillCard } from "./SkillCard";
export { InstalledSkills } from "./InstalledSkills";
export { TrustLevelBadge } from "./TrustLevelBadge";
```

**Step 2: Commit**

```bash
git add frontend/src/components/skills/index.ts
git commit -m "feat(ui): add skills component barrel export"
```

---

### Task 9: Create Skills Page

The main page component with three tabs (Browse, Installed, Activity). Follows the `GoalsPage` pattern: `DashboardLayout` wrapper, radial gradient background, header with title/subtitle, tab navigation, and conditionally rendered tab content.

**Files:**
- Create: `frontend/src/pages/Skills.tsx`

**Step 1: Write the page component**

```tsx
import { useState } from "react";
import { DashboardLayout } from "@/components/DashboardLayout";
import { SkillBrowser, InstalledSkills, SkillAuditLog } from "@/components/skills";

type SkillTab = "browse" | "installed" | "activity";

const tabs: { value: SkillTab; label: string; icon: string }[] = [
  {
    value: "browse",
    label: "Browse",
    icon: "M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z",
  },
  {
    value: "installed",
    label: "Installed",
    icon: "M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4",
  },
  {
    value: "activity",
    label: "Activity",
    icon: "M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2",
  },
];

export function SkillsPage() {
  const [activeTab, setActiveTab] = useState<SkillTab>("browse");

  return (
    <DashboardLayout>
      <div className="relative">
        {/* Background pattern */}
        <div className="absolute inset-0 bg-[radial-gradient(ellipse_at_top,_var(--tw-gradient-stops))] from-slate-800 via-slate-900 to-slate-900 pointer-events-none" />

        <div className="relative max-w-6xl mx-auto px-4 py-8 lg:px-8">
          {/* Header */}
          <div className="mb-8">
            <h1 className="text-3xl font-bold text-white">Skills</h1>
            <p className="mt-1 text-slate-400">
              Discover, install, and manage skills that extend ARIA&apos;s capabilities
            </p>
          </div>

          {/* Tab navigation */}
          <div className="flex gap-1 mb-8 bg-slate-800/50 border border-slate-700/50 rounded-xl p-1 w-fit">
            {tabs.map((tab) => (
              <button
                key={tab.value}
                onClick={() => setActiveTab(tab.value)}
                className={`inline-flex items-center gap-2 px-4 py-2.5 text-sm font-medium rounded-lg transition-all duration-200 ${
                  activeTab === tab.value
                    ? "bg-primary-600/20 text-primary-400 shadow-sm"
                    : "text-slate-400 hover:text-white hover:bg-slate-700/50"
                }`}
              >
                <svg
                  className="w-4 h-4"
                  fill="none"
                  stroke="currentColor"
                  viewBox="0 0 24 24"
                >
                  <path
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    strokeWidth={2}
                    d={tab.icon}
                  />
                </svg>
                {tab.label}
              </button>
            ))}
          </div>

          {/* Tab content */}
          {activeTab === "browse" && <SkillBrowser />}
          {activeTab === "installed" && <InstalledSkills />}
          {activeTab === "activity" && <SkillAuditLog />}
        </div>
      </div>
    </DashboardLayout>
  );
}
```

**Step 2: Commit**

```bash
git add frontend/src/pages/Skills.tsx
git commit -m "feat(ui): add Skills page with tabbed navigation"
```

---

### Task 10: Wire Skills into Router, Navigation, and Page Barrel

Add the Skills page to three integration points: the page barrel export, the React Router routes in `App.tsx`, and the sidebar navigation in `DashboardLayout.tsx`.

**Files:**
- Modify: `frontend/src/pages/index.ts` (add SkillsPage export)
- Modify: `frontend/src/App.tsx` (add /dashboard/skills route)
- Modify: `frontend/src/components/DashboardLayout.tsx` (add Skills nav item)

**Step 1: Add SkillsPage to pages barrel**

In `frontend/src/pages/index.ts`, add this line after the existing exports (maintain alphabetical order):

```typescript
export { SkillsPage } from "./Skills";
```

The full file should look like:

```typescript
export { AriaChatPage } from "./AriaChat";
export { BattleCardsPage } from "./BattleCards";
export { DashboardPage } from "./Dashboard";
export { EmailDraftsPage } from "./EmailDrafts";
export { GoalsPage } from "./Goals";
export { IntegrationsCallbackPage } from "./IntegrationsCallback";
export { LeadDetailPage } from "./LeadDetail";
export { LeadsPage } from "./Leads";
export { IntegrationsSettingsPage } from "./IntegrationsSettings";
export { LoginPage } from "./Login";
export { MeetingBriefPage } from "./MeetingBrief";
export { NotificationsPage } from "./NotificationsPage";
export { PreferencesSettingsPage } from "./PreferencesSettings";
export { SignupPage } from "./Signup";
export { SkillsPage } from "./Skills";
```

**Step 2: Add route in App.tsx**

In `frontend/src/App.tsx`, add `SkillsPage` to the import:

```typescript
import {
  AriaChatPage,
  BattleCardsPage,
  EmailDraftsPage,
  IntegrationsCallbackPage,
  IntegrationsSettingsPage,
  LeadDetailPage,
  LeadsPage,
  LoginPage,
  MeetingBriefPage,
  NotificationsPage,
  PreferencesSettingsPage,
  SignupPage,
  DashboardPage,
  GoalsPage,
  SkillsPage,
} from "@/pages";
```

Then add this route block after the `/dashboard/drafts` route and before the `/settings/integrations` route:

```tsx
            <Route
              path="/dashboard/skills"
              element={
                <ProtectedRoute>
                  <SkillsPage />
                </ProtectedRoute>
              }
            />
```

**Step 3: Add Skills nav item in DashboardLayout.tsx**

In `frontend/src/components/DashboardLayout.tsx`, add a new entry to the `navItems` array. Insert it after the "Integrations" entry (index 5) and before "Lead Memory" (index 6):

```typescript
  { name: "Skills", href: "/dashboard/skills", icon: "skills" },
```

The `navItems` array should become:

```typescript
const navItems = [
  { name: "Dashboard", href: "/dashboard", icon: "home" },
  { name: "ARIA Chat", href: "/dashboard/aria", icon: "chat" },
  { name: "Goals", href: "/goals", icon: "target" },
  { name: "Battle Cards", href: "/dashboard/battlecards", icon: "swords" },
  { name: "Email Drafts", href: "/dashboard/drafts", icon: "mail" },
  { name: "Integrations", href: "/settings/integrations", icon: "integration" },
  { name: "Skills", href: "/dashboard/skills", icon: "skills" },
  { name: "Lead Memory", href: "/dashboard/leads", icon: "users" },
  { name: "Daily Briefing", href: "/briefing", icon: "calendar" },
  { name: "Settings", href: "/settings", icon: "settings" },
];
```

Then add the "skills" icon to the `NavIcon` component's `icons` record:

```tsx
    skills: (
      <svg
        className="w-5 h-5"
        fill="none"
        stroke="currentColor"
        viewBox="0 0 24 24"
      >
        <path
          strokeLinecap="round"
          strokeLinejoin="round"
          strokeWidth={2}
          d="M19.428 15.428a2 2 0 00-1.022-.547l-2.387-.477a6 6 0 00-3.86.517l-.318.158a6 6 0 01-3.86.517L6.05 15.21a2 2 0 00-1.806.547M8 4h8l-1 1v5.172a2 2 0 00.586 1.414l5 5c1.26 1.26.367 3.414-1.415 3.414H4.828c-1.782 0-2.674-2.154-1.414-3.414l5-5A2 2 0 009 10.172V5L8 4z"
        />
      </svg>
    ),
```

Add it after the `integration` icon entry in the `icons` record inside `NavIcon`.

**Step 4: Verify frontend compiles**

Run: `cd /Users/dhruv/aria/frontend && npx tsc --noEmit 2>&1 | tail -20`
Expected: No errors (or only pre-existing errors unrelated to skills)

**Step 5: Commit**

```bash
git add frontend/src/pages/index.ts frontend/src/App.tsx frontend/src/components/DashboardLayout.tsx
git commit -m "feat(ui): wire Skills page into router and sidebar navigation"
```

---

### Task 11: Verify Full Build and Manual Smoke Test

Final verification that everything compiles, the dev server starts, and the Skills page renders.

**Files:** (no new files)

**Step 1: Run TypeScript type check**

Run: `cd /Users/dhruv/aria/frontend && npx tsc --noEmit 2>&1 | tail -30`
Expected: No errors related to skills files

**Step 2: Run Vite build**

Run: `cd /Users/dhruv/aria/frontend && npm run build 2>&1 | tail -20`
Expected: Build succeeds with no errors

**Step 3: Run lint**

Run: `cd /Users/dhruv/aria/frontend && npm run lint 2>&1 | tail -20`
Expected: No lint errors in skills files

**Step 4: Commit (if any fixes were needed)**

Only if lint/type fixes were required:

```bash
git add -u frontend/src/
git commit -m "fix(ui): address lint and type issues in skills UI"
```
