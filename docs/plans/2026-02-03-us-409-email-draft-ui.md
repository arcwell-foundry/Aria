# US-409: Email Draft UI Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Build a premium email drafts management UI at `/dashboard/drafts` with Apple-inspired luxury aesthetics, allowing users to create, edit, preview, regenerate, and send AI-generated email drafts.

**Architecture:** Single-page application with list/detail views, modals for create/preview/send confirmation. Uses React Query for server state, TipTap for rich text editing. Follows existing BattleCards pattern for CRUD operations with Apple-style refinements.

**Tech Stack:** React 18, TypeScript, Tailwind CSS, TanStack Query, TipTap rich text editor, Lucide icons. Integrates with `/api/v1/drafts` endpoints (US-408 backend complete).

---

## Task 1: Create API Client for Drafts

**Files:**
- Create: `frontend/src/api/drafts.ts`

**Step 1: Write the failing test**

No test for API client - this is a thin wrapper. Move to implementation.

**Step 2: Create the API client with TypeScript types**

```typescript
import { apiClient } from "./client";

// Enums matching backend
export type EmailDraftPurpose = "intro" | "follow_up" | "proposal" | "thank_you" | "check_in" | "other";
export type EmailDraftTone = "formal" | "friendly" | "urgent";
export type EmailDraftStatus = "draft" | "sent" | "failed";

// Response types
export interface EmailDraft {
  id: string;
  user_id: string;
  recipient_email: string;
  recipient_name?: string;
  subject: string;
  body: string;
  purpose: EmailDraftPurpose;
  tone: EmailDraftTone;
  context?: {
    user_context?: string;
    lead_context?: unknown;
  };
  lead_memory_id?: string;
  style_match_score?: number;
  status: EmailDraftStatus;
  sent_at?: string;
  error_message?: string;
  created_at: string;
  updated_at: string;
}

export interface EmailDraftListItem {
  id: string;
  recipient_email: string;
  recipient_name?: string;
  subject: string;
  purpose: EmailDraftPurpose;
  tone: EmailDraftTone;
  status: EmailDraftStatus;
  style_match_score?: number;
  created_at: string;
}

// Request types
export interface CreateEmailDraftRequest {
  recipient_email: string;
  recipient_name?: string;
  subject_hint?: string;
  purpose: EmailDraftPurpose;
  context?: string;
  tone?: EmailDraftTone;
  lead_memory_id?: string;
}

export interface UpdateEmailDraftRequest {
  recipient_email?: string;
  recipient_name?: string;
  subject?: string;
  body?: string;
  tone?: EmailDraftTone;
}

export interface RegenerateDraftRequest {
  tone?: EmailDraftTone;
  additional_context?: string;
}

export interface SendDraftResponse {
  id: string;
  status: EmailDraftStatus;
  sent_at?: string;
  error_message?: string;
}

// API functions
export async function listDrafts(status?: EmailDraftStatus, limit = 50): Promise<EmailDraftListItem[]> {
  const params = new URLSearchParams();
  if (status) params.append("status", status);
  params.append("limit", String(limit));
  const query = params.toString();
  const response = await apiClient.get<EmailDraftListItem[]>(`/drafts${query ? `?${query}` : ""}`);
  return response.data;
}

export async function getDraft(draftId: string): Promise<EmailDraft> {
  const response = await apiClient.get<EmailDraft>(`/drafts/${draftId}`);
  return response.data;
}

export async function createDraft(data: CreateEmailDraftRequest): Promise<EmailDraft> {
  const response = await apiClient.post<EmailDraft>("/drafts/email", data);
  return response.data;
}

export async function updateDraft(draftId: string, data: UpdateEmailDraftRequest): Promise<EmailDraft> {
  const response = await apiClient.put<EmailDraft>(`/drafts/${draftId}`, data);
  return response.data;
}

export async function deleteDraft(draftId: string): Promise<void> {
  await apiClient.delete(`/drafts/${draftId}`);
}

export async function regenerateDraft(draftId: string, data?: RegenerateDraftRequest): Promise<EmailDraft> {
  const response = await apiClient.post<EmailDraft>(`/drafts/${draftId}/regenerate`, data || {});
  return response.data;
}

export async function sendDraft(draftId: string): Promise<SendDraftResponse> {
  const response = await apiClient.post<SendDraftResponse>(`/drafts/${draftId}/send`);
  return response.data;
}
```

**Step 3: Commit**

```bash
git add frontend/src/api/drafts.ts
git commit -m "feat(api): add email drafts API client

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```

---

## Task 2: Create React Query Hooks for Drafts

**Files:**
- Create: `frontend/src/hooks/useDrafts.ts`

**Step 1: Create the hooks file with query key factory pattern**

```typescript
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  listDrafts,
  getDraft,
  createDraft,
  updateDraft,
  deleteDraft,
  regenerateDraft,
  sendDraft,
  type CreateEmailDraftRequest,
  type UpdateEmailDraftRequest,
  type RegenerateDraftRequest,
  type EmailDraftStatus,
} from "@/api/drafts";

// Query keys factory
export const draftKeys = {
  all: ["drafts"] as const,
  lists: () => [...draftKeys.all, "list"] as const,
  list: (status?: EmailDraftStatus) => [...draftKeys.lists(), { status }] as const,
  details: () => [...draftKeys.all, "detail"] as const,
  detail: (id: string) => [...draftKeys.details(), id] as const,
};

// List drafts
export function useDrafts(status?: EmailDraftStatus) {
  return useQuery({
    queryKey: draftKeys.list(status),
    queryFn: () => listDrafts(status),
  });
}

// Get single draft
export function useDraft(draftId: string) {
  return useQuery({
    queryKey: draftKeys.detail(draftId),
    queryFn: () => getDraft(draftId),
    enabled: !!draftId,
  });
}

// Create draft mutation
export function useCreateDraft() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (data: CreateEmailDraftRequest) => createDraft(data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: draftKeys.lists() });
    },
  });
}

// Update draft mutation
export function useUpdateDraft() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({ draftId, data }: { draftId: string; data: UpdateEmailDraftRequest }) =>
      updateDraft(draftId, data),
    onSuccess: (updatedDraft) => {
      queryClient.invalidateQueries({ queryKey: draftKeys.lists() });
      queryClient.setQueryData(draftKeys.detail(updatedDraft.id), updatedDraft);
    },
  });
}

// Delete draft mutation
export function useDeleteDraft() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (draftId: string) => deleteDraft(draftId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: draftKeys.lists() });
    },
  });
}

// Regenerate draft mutation
export function useRegenerateDraft() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({ draftId, data }: { draftId: string; data?: RegenerateDraftRequest }) =>
      regenerateDraft(draftId, data),
    onSuccess: (updatedDraft) => {
      queryClient.invalidateQueries({ queryKey: draftKeys.lists() });
      queryClient.setQueryData(draftKeys.detail(updatedDraft.id), updatedDraft);
    },
  });
}

// Send draft mutation
export function useSendDraft() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (draftId: string) => sendDraft(draftId),
    onSuccess: (result) => {
      queryClient.invalidateQueries({ queryKey: draftKeys.lists() });
      queryClient.invalidateQueries({ queryKey: draftKeys.detail(result.id) });
    },
  });
}
```

**Step 2: Commit**

```bash
git add frontend/src/hooks/useDrafts.ts
git commit -m "feat(hooks): add React Query hooks for email drafts

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```

---

## Task 3: Install TipTap Rich Text Editor

**Files:**
- Modify: `frontend/package.json`

**Step 1: Install TipTap dependencies**

```bash
cd frontend && npm install @tiptap/react @tiptap/starter-kit @tiptap/extension-placeholder @tiptap/extension-underline
```

**Step 2: Commit**

```bash
git add frontend/package.json frontend/package-lock.json
git commit -m "chore(deps): add TipTap rich text editor dependencies

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```

---

## Task 4: Create Draft Components - Empty State

**Files:**
- Create: `frontend/src/components/drafts/EmptyDrafts.tsx`
- Create: `frontend/src/components/drafts/index.ts`

**Step 1: Create EmptyDrafts component with Apple-inspired styling**

```typescript
// frontend/src/components/drafts/EmptyDrafts.tsx
interface EmptyDraftsProps {
  onCreateClick: () => void;
  hasFilter?: boolean;
}

export function EmptyDrafts({ onCreateClick, hasFilter = false }: EmptyDraftsProps) {
  return (
    <div className="flex flex-col items-center justify-center py-20 px-6">
      {/* Elegant envelope illustration */}
      <div className="relative mb-8">
        <div className="w-32 h-24 bg-gradient-to-br from-slate-700/50 to-slate-800/50 rounded-2xl border border-slate-600/30 transform -rotate-6 absolute -left-4 -top-2" />
        <div className="w-32 h-24 bg-gradient-to-br from-slate-700/80 to-slate-800/80 rounded-2xl border border-slate-600/50 relative flex items-center justify-center">
          <svg className="w-12 h-12 text-slate-500" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              strokeWidth={1.5}
              d="M3 8l7.89 5.26a2 2 0 002.22 0L21 8M5 19h14a2 2 0 002-2V7a2 2 0 00-2-2H5a2 2 0 00-2 2v10a2 2 0 002 2z"
            />
          </svg>
        </div>
      </div>

      <h3 className="text-xl font-semibold text-white mb-2">
        {hasFilter ? "No drafts match your filter" : "No email drafts yet"}
      </h3>
      <p className="text-slate-400 text-center max-w-sm mb-8">
        {hasFilter
          ? "Try adjusting your filter or create a new draft."
          : "Let ARIA help you compose the perfect email. Your drafts will appear here."}
      </p>

      <button
        onClick={onCreateClick}
        className="group inline-flex items-center gap-3 px-6 py-3.5 bg-gradient-to-r from-primary-600 to-primary-500 hover:from-primary-500 hover:to-primary-400 text-white font-medium rounded-2xl transition-all duration-300 shadow-lg shadow-primary-600/25 hover:shadow-primary-500/40 hover:scale-[1.02]"
      >
        <svg className="w-5 h-5 transition-transform group-hover:rotate-90 duration-300" fill="none" viewBox="0 0 24 24" stroke="currentColor">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 4v16m8-8H4" />
        </svg>
        Compose New Draft
      </button>
    </div>
  );
}
```

**Step 2: Create barrel export**

```typescript
// frontend/src/components/drafts/index.ts
export { EmptyDrafts } from "./EmptyDrafts";
```

**Step 3: Commit**

```bash
git add frontend/src/components/drafts/
git commit -m "feat(ui): add EmptyDrafts component with elegant empty state

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```

---

## Task 5: Create Draft Card Component

**Files:**
- Create: `frontend/src/components/drafts/DraftCard.tsx`
- Modify: `frontend/src/components/drafts/index.ts`

**Step 1: Create DraftCard with Apple-inspired card styling**

```typescript
// frontend/src/components/drafts/DraftCard.tsx
import type { EmailDraftListItem } from "@/api/drafts";
import { StyleMatchIndicator } from "./StyleMatchIndicator";

interface DraftCardProps {
  draft: EmailDraftListItem;
  onView: () => void;
  onDelete: () => void;
}

const purposeLabels: Record<string, string> = {
  intro: "Introduction",
  follow_up: "Follow Up",
  proposal: "Proposal",
  thank_you: "Thank You",
  check_in: "Check In",
  other: "Other",
};

const toneLabels: Record<string, { label: string; color: string }> = {
  formal: { label: "Formal", color: "bg-blue-500/20 text-blue-400 border-blue-500/30" },
  friendly: { label: "Friendly", color: "bg-emerald-500/20 text-emerald-400 border-emerald-500/30" },
  urgent: { label: "Urgent", color: "bg-amber-500/20 text-amber-400 border-amber-500/30" },
};

const statusConfig: Record<string, { label: string; color: string; icon: JSX.Element }> = {
  draft: {
    label: "Draft",
    color: "bg-slate-500/20 text-slate-400",
    icon: (
      <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M11 5H6a2 2 0 00-2 2v11a2 2 0 002 2h11a2 2 0 002-2v-5m-1.414-9.414a2 2 0 112.828 2.828L11.828 15H9v-2.828l8.586-8.586z" />
      </svg>
    ),
  },
  sent: {
    label: "Sent",
    color: "bg-emerald-500/20 text-emerald-400",
    icon: (
      <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
      </svg>
    ),
  },
  failed: {
    label: "Failed",
    color: "bg-red-500/20 text-red-400",
    icon: (
      <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
      </svg>
    ),
  },
};

export function DraftCard({ draft, onView, onDelete }: DraftCardProps) {
  const status = statusConfig[draft.status];
  const tone = toneLabels[draft.tone];
  const formattedDate = new Date(draft.created_at).toLocaleDateString("en-US", {
    month: "short",
    day: "numeric",
    hour: "numeric",
    minute: "2-digit",
  });

  return (
    <div
      onClick={onView}
      className="group relative bg-slate-800/50 hover:bg-slate-800/80 border border-slate-700/50 hover:border-slate-600/50 rounded-2xl p-5 cursor-pointer transition-all duration-300 hover:shadow-xl hover:shadow-black/20 hover:-translate-y-0.5"
    >
      {/* Subtle gradient overlay on hover */}
      <div className="absolute inset-0 bg-gradient-to-br from-primary-500/5 to-transparent opacity-0 group-hover:opacity-100 rounded-2xl transition-opacity duration-300 pointer-events-none" />

      <div className="relative">
        {/* Header row */}
        <div className="flex items-start justify-between gap-3 mb-3">
          <div className="flex-1 min-w-0">
            <h3 className="font-semibold text-white truncate group-hover:text-primary-300 transition-colors">
              {draft.subject || "No subject"}
            </h3>
            <p className="text-sm text-slate-400 truncate mt-0.5">
              To: {draft.recipient_name || draft.recipient_email}
            </p>
          </div>

          {/* Status badge */}
          <span className={`inline-flex items-center gap-1.5 px-2.5 py-1 text-xs font-medium rounded-lg ${status.color}`}>
            {status.icon}
            {status.label}
          </span>
        </div>

        {/* Tags row */}
        <div className="flex items-center gap-2 mb-4">
          <span className="px-2.5 py-1 text-xs font-medium bg-slate-700/50 text-slate-300 rounded-lg">
            {purposeLabels[draft.purpose]}
          </span>
          <span className={`px-2.5 py-1 text-xs font-medium rounded-lg border ${tone.color}`}>
            {tone.label}
          </span>
        </div>

        {/* Footer row */}
        <div className="flex items-center justify-between">
          {/* Style match score */}
          {draft.style_match_score !== undefined && (
            <StyleMatchIndicator score={draft.style_match_score} size="sm" />
          )}
          {draft.style_match_score === undefined && <div />}

          <div className="flex items-center gap-3">
            <span className="text-xs text-slate-500">{formattedDate}</span>

            {/* Delete button - appears on hover */}
            <button
              onClick={(e) => {
                e.stopPropagation();
                onDelete();
              }}
              className="opacity-0 group-hover:opacity-100 p-1.5 text-slate-400 hover:text-red-400 hover:bg-red-500/10 rounded-lg transition-all duration-200"
              title="Delete draft"
            >
              <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
              </svg>
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
```

**Step 2: Update barrel export**

```typescript
// frontend/src/components/drafts/index.ts
export { EmptyDrafts } from "./EmptyDrafts";
export { DraftCard } from "./DraftCard";
```

**Step 3: Commit**

```bash
git add frontend/src/components/drafts/
git commit -m "feat(ui): add DraftCard component with status badges and hover effects

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```

---

## Task 6: Create Style Match Indicator Component

**Files:**
- Create: `frontend/src/components/drafts/StyleMatchIndicator.tsx`
- Modify: `frontend/src/components/drafts/index.ts`

**Step 1: Create elegant circular progress indicator**

```typescript
// frontend/src/components/drafts/StyleMatchIndicator.tsx
interface StyleMatchIndicatorProps {
  score: number; // 0-1 scale
  size?: "sm" | "md" | "lg";
  showLabel?: boolean;
}

export function StyleMatchIndicator({ score, size = "md", showLabel = true }: StyleMatchIndicatorProps) {
  const percentage = Math.round(score * 100);

  const sizeConfig = {
    sm: { ring: 28, stroke: 3, text: "text-[10px]", label: "text-xs" },
    md: { ring: 40, stroke: 4, text: "text-xs", label: "text-sm" },
    lg: { ring: 56, stroke: 5, text: "text-sm", label: "text-base" },
  };

  const config = sizeConfig[size];
  const radius = (config.ring - config.stroke) / 2;
  const circumference = radius * 2 * Math.PI;
  const offset = circumference - (score * circumference);

  // Color based on score
  const getColor = () => {
    if (percentage >= 80) return { stroke: "stroke-emerald-500", text: "text-emerald-400", bg: "bg-emerald-500/10" };
    if (percentage >= 60) return { stroke: "stroke-primary-500", text: "text-primary-400", bg: "bg-primary-500/10" };
    if (percentage >= 40) return { stroke: "stroke-amber-500", text: "text-amber-400", bg: "bg-amber-500/10" };
    return { stroke: "stroke-red-500", text: "text-red-400", bg: "bg-red-500/10" };
  };

  const colors = getColor();

  return (
    <div className="flex items-center gap-2">
      <div className={`relative ${config.bg} rounded-full p-1`}>
        <svg
          width={config.ring}
          height={config.ring}
          className="transform -rotate-90"
        >
          {/* Background ring */}
          <circle
            cx={config.ring / 2}
            cy={config.ring / 2}
            r={radius}
            stroke="currentColor"
            strokeWidth={config.stroke}
            fill="none"
            className="text-slate-700/50"
          />
          {/* Progress ring */}
          <circle
            cx={config.ring / 2}
            cy={config.ring / 2}
            r={radius}
            strokeWidth={config.stroke}
            fill="none"
            strokeLinecap="round"
            className={`${colors.stroke} transition-all duration-500 ease-out`}
            style={{
              strokeDasharray: circumference,
              strokeDashoffset: offset,
            }}
          />
        </svg>
        {/* Percentage text */}
        <span className={`absolute inset-0 flex items-center justify-center font-semibold ${colors.text} ${config.text}`}>
          {percentage}
        </span>
      </div>

      {showLabel && (
        <span className={`${config.label} text-slate-400`}>Style Match</span>
      )}
    </div>
  );
}
```

**Step 2: Update barrel export**

```typescript
// frontend/src/components/drafts/index.ts
export { EmptyDrafts } from "./EmptyDrafts";
export { DraftCard } from "./DraftCard";
export { StyleMatchIndicator } from "./StyleMatchIndicator";
```

**Step 3: Commit**

```bash
git add frontend/src/components/drafts/
git commit -m "feat(ui): add StyleMatchIndicator with animated progress ring

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```

---

## Task 7: Create Rich Text Editor Component

**Files:**
- Create: `frontend/src/components/drafts/RichTextEditor.tsx`
- Modify: `frontend/src/components/drafts/index.ts`

**Step 1: Create TipTap-based rich text editor**

```typescript
// frontend/src/components/drafts/RichTextEditor.tsx
import { useEditor, EditorContent } from "@tiptap/react";
import StarterKit from "@tiptap/starter-kit";
import Placeholder from "@tiptap/extension-placeholder";
import Underline from "@tiptap/extension-underline";
import { useEffect } from "react";

interface RichTextEditorProps {
  content: string;
  onChange: (html: string) => void;
  placeholder?: string;
  disabled?: boolean;
}

export function RichTextEditor({
  content,
  onChange,
  placeholder = "Start writing...",
  disabled = false,
}: RichTextEditorProps) {
  const editor = useEditor({
    extensions: [
      StarterKit.configure({
        heading: { levels: [1, 2, 3] },
      }),
      Underline,
      Placeholder.configure({ placeholder }),
    ],
    content,
    editable: !disabled,
    onUpdate: ({ editor }) => {
      onChange(editor.getHTML());
    },
  });

  // Update content when prop changes
  useEffect(() => {
    if (editor && content !== editor.getHTML()) {
      editor.commands.setContent(content);
    }
  }, [content, editor]);

  // Update editable state
  useEffect(() => {
    if (editor) {
      editor.setEditable(!disabled);
    }
  }, [disabled, editor]);

  if (!editor) return null;

  return (
    <div className={`border border-slate-700 rounded-xl overflow-hidden ${disabled ? "opacity-60" : ""}`}>
      {/* Toolbar */}
      <div className="flex items-center gap-1 p-2 bg-slate-800/50 border-b border-slate-700">
        <ToolbarButton
          onClick={() => editor.chain().focus().toggleBold().run()}
          isActive={editor.isActive("bold")}
          disabled={disabled}
          title="Bold"
        >
          <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2.5}>
            <path strokeLinecap="round" strokeLinejoin="round" d="M6 4h8a4 4 0 014 4 4 4 0 01-4 4H6z" />
            <path strokeLinecap="round" strokeLinejoin="round" d="M6 12h9a4 4 0 014 4 4 4 0 01-4 4H6z" />
          </svg>
        </ToolbarButton>

        <ToolbarButton
          onClick={() => editor.chain().focus().toggleItalic().run()}
          isActive={editor.isActive("italic")}
          disabled={disabled}
          title="Italic"
        >
          <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
            <path strokeLinecap="round" strokeLinejoin="round" d="M10 4h4m-2 0l-4 16m0 0h4" />
          </svg>
        </ToolbarButton>

        <ToolbarButton
          onClick={() => editor.chain().focus().toggleUnderline().run()}
          isActive={editor.isActive("underline")}
          disabled={disabled}
          title="Underline"
        >
          <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
            <path strokeLinecap="round" strokeLinejoin="round" d="M7 8v4a5 5 0 0010 0V8M5 20h14" />
          </svg>
        </ToolbarButton>

        <div className="w-px h-5 bg-slate-600 mx-1" />

        <ToolbarButton
          onClick={() => editor.chain().focus().toggleBulletList().run()}
          isActive={editor.isActive("bulletList")}
          disabled={disabled}
          title="Bullet List"
        >
          <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
            <path strokeLinecap="round" strokeLinejoin="round" d="M4 6h16M4 12h16M4 18h16" />
          </svg>
        </ToolbarButton>

        <ToolbarButton
          onClick={() => editor.chain().focus().toggleOrderedList().run()}
          isActive={editor.isActive("orderedList")}
          disabled={disabled}
          title="Numbered List"
        >
          <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
            <path strokeLinecap="round" strokeLinejoin="round" d="M7 8h10M7 12h10M7 16h10M4 6v.01M4 12v.01M4 18v.01" />
          </svg>
        </ToolbarButton>

        <div className="w-px h-5 bg-slate-600 mx-1" />

        <ToolbarButton
          onClick={() => editor.chain().focus().toggleBlockquote().run()}
          isActive={editor.isActive("blockquote")}
          disabled={disabled}
          title="Quote"
        >
          <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
            <path strokeLinecap="round" strokeLinejoin="round" d="M8 10h.01M12 10h.01M16 10h.01M9 16H5a2 2 0 01-2-2V6a2 2 0 012-2h14a2 2 0 012 2v8a2 2 0 01-2 2h-5l-5 5v-5z" />
          </svg>
        </ToolbarButton>
      </div>

      {/* Editor content */}
      <EditorContent
        editor={editor}
        className="prose prose-invert prose-sm max-w-none p-4 min-h-[200px] focus:outline-none [&_.ProseMirror]:outline-none [&_.ProseMirror]:min-h-[168px] [&_.ProseMirror_p.is-editor-empty:first-child::before]:text-slate-500 [&_.ProseMirror_p.is-editor-empty:first-child::before]:content-[attr(data-placeholder)] [&_.ProseMirror_p.is-editor-empty:first-child::before]:float-left [&_.ProseMirror_p.is-editor-empty:first-child::before]:pointer-events-none [&_.ProseMirror_p.is-editor-empty:first-child::before]:h-0"
      />
    </div>
  );
}

interface ToolbarButtonProps {
  onClick: () => void;
  isActive: boolean;
  disabled: boolean;
  title: string;
  children: React.ReactNode;
}

function ToolbarButton({ onClick, isActive, disabled, title, children }: ToolbarButtonProps) {
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={disabled}
      title={title}
      className={`p-1.5 rounded-lg transition-colors ${
        isActive
          ? "bg-primary-600/30 text-primary-400"
          : "text-slate-400 hover:bg-slate-700 hover:text-white"
      } disabled:opacity-50 disabled:cursor-not-allowed`}
    >
      {children}
    </button>
  );
}
```

**Step 2: Update barrel export**

```typescript
// frontend/src/components/drafts/index.ts
export { EmptyDrafts } from "./EmptyDrafts";
export { DraftCard } from "./DraftCard";
export { StyleMatchIndicator } from "./StyleMatchIndicator";
export { RichTextEditor } from "./RichTextEditor";
```

**Step 3: Commit**

```bash
git add frontend/src/components/drafts/
git commit -m "feat(ui): add RichTextEditor component with TipTap

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```

---

## Task 8: Create Tone Selector Component

**Files:**
- Create: `frontend/src/components/drafts/ToneSelector.tsx`
- Modify: `frontend/src/components/drafts/index.ts`

**Step 1: Create Apple-style segmented control**

```typescript
// frontend/src/components/drafts/ToneSelector.tsx
import type { EmailDraftTone } from "@/api/drafts";

interface ToneSelectorProps {
  value: EmailDraftTone;
  onChange: (tone: EmailDraftTone) => void;
  disabled?: boolean;
}

const tones: { value: EmailDraftTone; label: string; description: string }[] = [
  { value: "formal", label: "Formal", description: "Professional & polished" },
  { value: "friendly", label: "Friendly", description: "Warm & approachable" },
  { value: "urgent", label: "Urgent", description: "Direct & action-oriented" },
];

export function ToneSelector({ value, onChange, disabled = false }: ToneSelectorProps) {
  return (
    <div className="flex flex-col gap-2">
      <label className="text-sm font-medium text-slate-300">Tone</label>
      <div className="relative flex bg-slate-800/50 rounded-xl p-1 border border-slate-700/50">
        {/* Sliding background indicator */}
        <div
          className="absolute top-1 bottom-1 bg-primary-600/20 border border-primary-500/30 rounded-lg transition-all duration-300 ease-out"
          style={{
            left: `${(tones.findIndex((t) => t.value === value) * 100) / 3 + 0.5}%`,
            width: `${100 / 3 - 1}%`,
          }}
        />

        {tones.map((tone) => (
          <button
            key={tone.value}
            type="button"
            onClick={() => !disabled && onChange(tone.value)}
            disabled={disabled}
            className={`relative flex-1 px-4 py-2.5 rounded-lg text-sm font-medium transition-colors z-10 ${
              value === tone.value
                ? "text-primary-400"
                : "text-slate-400 hover:text-white"
            } disabled:opacity-50 disabled:cursor-not-allowed`}
          >
            {tone.label}
          </button>
        ))}
      </div>
      <p className="text-xs text-slate-500">
        {tones.find((t) => t.value === value)?.description}
      </p>
    </div>
  );
}
```

**Step 2: Update barrel export**

```typescript
// frontend/src/components/drafts/index.ts
export { EmptyDrafts } from "./EmptyDrafts";
export { DraftCard } from "./DraftCard";
export { StyleMatchIndicator } from "./StyleMatchIndicator";
export { RichTextEditor } from "./RichTextEditor";
export { ToneSelector } from "./ToneSelector";
```

**Step 3: Commit**

```bash
git add frontend/src/components/drafts/
git commit -m "feat(ui): add ToneSelector with sliding indicator animation

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```

---

## Task 9: Create Purpose Selector Component

**Files:**
- Create: `frontend/src/components/drafts/PurposeSelector.tsx`
- Modify: `frontend/src/components/drafts/index.ts`

**Step 1: Create elegant pill button selector**

```typescript
// frontend/src/components/drafts/PurposeSelector.tsx
import type { EmailDraftPurpose } from "@/api/drafts";

interface PurposeSelectorProps {
  value: EmailDraftPurpose;
  onChange: (purpose: EmailDraftPurpose) => void;
  disabled?: boolean;
}

const purposes: { value: EmailDraftPurpose; label: string; icon: JSX.Element }[] = [
  {
    value: "intro",
    label: "Introduction",
    icon: (
      <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M7 11.5V14m0-2.5v-6a1.5 1.5 0 113 0m-3 6a1.5 1.5 0 00-3 0v2a7.5 7.5 0 0015 0v-5a1.5 1.5 0 00-3 0m-6-3V11m0-5.5v-1a1.5 1.5 0 013 0v1m0 0V11m0-5.5a1.5 1.5 0 013 0v3m0 0V11" />
      </svg>
    ),
  },
  {
    value: "follow_up",
    label: "Follow Up",
    icon: (
      <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M3 10h10a8 8 0 018 8v2M3 10l6 6m-6-6l6-6" />
      </svg>
    ),
  },
  {
    value: "proposal",
    label: "Proposal",
    icon: (
      <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
      </svg>
    ),
  },
  {
    value: "thank_you",
    label: "Thank You",
    icon: (
      <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4.318 6.318a4.5 4.5 0 000 6.364L12 20.364l7.682-7.682a4.5 4.5 0 00-6.364-6.364L12 7.636l-1.318-1.318a4.5 4.5 0 00-6.364 0z" />
      </svg>
    ),
  },
  {
    value: "check_in",
    label: "Check In",
    icon: (
      <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8 12h.01M12 12h.01M16 12h.01M21 12c0 4.418-4.03 8-9 8a9.863 9.863 0 01-4.255-.949L3 20l1.395-3.72C3.512 15.042 3 13.574 3 12c0-4.418 4.03-8 9-8s9 3.582 9 8z" />
      </svg>
    ),
  },
  {
    value: "other",
    label: "Other",
    icon: (
      <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 12h.01M12 12h.01M19 12h.01M6 12a1 1 0 11-2 0 1 1 0 012 0zm7 0a1 1 0 11-2 0 1 1 0 012 0zm7 0a1 1 0 11-2 0 1 1 0 012 0z" />
      </svg>
    ),
  },
];

export function PurposeSelector({ value, onChange, disabled = false }: PurposeSelectorProps) {
  return (
    <div className="flex flex-col gap-2">
      <label className="text-sm font-medium text-slate-300">Purpose</label>
      <div className="flex flex-wrap gap-2">
        {purposes.map((purpose) => (
          <button
            key={purpose.value}
            type="button"
            onClick={() => !disabled && onChange(purpose.value)}
            disabled={disabled}
            className={`inline-flex items-center gap-2 px-3.5 py-2 rounded-xl text-sm font-medium transition-all duration-200 ${
              value === purpose.value
                ? "bg-primary-600/20 text-primary-400 border border-primary-500/30 shadow-sm shadow-primary-500/10"
                : "bg-slate-800/50 text-slate-400 border border-slate-700/50 hover:bg-slate-700/50 hover:text-white hover:border-slate-600/50"
            } disabled:opacity-50 disabled:cursor-not-allowed`}
          >
            {purpose.icon}
            {purpose.label}
          </button>
        ))}
      </div>
    </div>
  );
}
```

**Step 2: Update barrel export**

```typescript
// frontend/src/components/drafts/index.ts
export { EmptyDrafts } from "./EmptyDrafts";
export { DraftCard } from "./DraftCard";
export { StyleMatchIndicator } from "./StyleMatchIndicator";
export { RichTextEditor } from "./RichTextEditor";
export { ToneSelector } from "./ToneSelector";
export { PurposeSelector } from "./PurposeSelector";
```

**Step 3: Commit**

```bash
git add frontend/src/components/drafts/
git commit -m "feat(ui): add PurposeSelector with pill button styling

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```

---

## Task 10: Create Draft Compose Modal

**Files:**
- Create: `frontend/src/components/drafts/DraftComposeModal.tsx`
- Modify: `frontend/src/components/drafts/index.ts`

**Step 1: Create the compose modal with form fields**

```typescript
// frontend/src/components/drafts/DraftComposeModal.tsx
import { useState, useEffect, useCallback } from "react";
import type { EmailDraftTone, EmailDraftPurpose, CreateEmailDraftRequest } from "@/api/drafts";
import { ToneSelector } from "./ToneSelector";
import { PurposeSelector } from "./PurposeSelector";

interface DraftComposeModalProps {
  isOpen: boolean;
  onClose: () => void;
  onSubmit: (data: CreateEmailDraftRequest) => void;
  isLoading?: boolean;
}

export function DraftComposeModal({
  isOpen,
  onClose,
  onSubmit,
  isLoading = false,
}: DraftComposeModalProps) {
  const [recipientEmail, setRecipientEmail] = useState("");
  const [recipientName, setRecipientName] = useState("");
  const [subjectHint, setSubjectHint] = useState("");
  const [purpose, setPurpose] = useState<EmailDraftPurpose>("intro");
  const [tone, setTone] = useState<EmailDraftTone>("friendly");
  const [context, setContext] = useState("");

  // Reset form when modal opens
  useEffect(() => {
    if (isOpen) {
      setRecipientEmail("");
      setRecipientName("");
      setSubjectHint("");
      setPurpose("intro");
      setTone("friendly");
      setContext("");
    }
  }, [isOpen]);

  // Handle escape key
  const handleKeyDown = useCallback(
    (e: KeyboardEvent) => {
      if (e.key === "Escape" && !isLoading) {
        onClose();
      }
    },
    [onClose, isLoading]
  );

  useEffect(() => {
    if (isOpen) {
      document.addEventListener("keydown", handleKeyDown);
      return () => document.removeEventListener("keydown", handleKeyDown);
    }
  }, [isOpen, handleKeyDown]);

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!recipientEmail.trim()) return;

    onSubmit({
      recipient_email: recipientEmail.trim(),
      recipient_name: recipientName.trim() || undefined,
      subject_hint: subjectHint.trim() || undefined,
      purpose,
      tone,
      context: context.trim() || undefined,
    });
  };

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center">
      {/* Backdrop with blur */}
      <div
        className="absolute inset-0 bg-black/70 backdrop-blur-sm"
        onClick={isLoading ? undefined : onClose}
      />

      {/* Modal */}
      <div className="relative w-full max-w-xl max-h-[90vh] mx-4 bg-slate-800 border border-slate-700 rounded-2xl shadow-2xl flex flex-col overflow-hidden animate-in fade-in zoom-in-95 duration-200">
        {/* Header */}
        <div className="shrink-0 flex items-center justify-between px-6 py-4 border-b border-slate-700">
          <div>
            <h2 className="text-xl font-semibold text-white">Compose Email</h2>
            <p className="text-sm text-slate-400 mt-0.5">ARIA will draft an email based on your inputs</p>
          </div>
          <button
            onClick={onClose}
            disabled={isLoading}
            className="p-2 text-slate-400 hover:text-white hover:bg-slate-700 rounded-xl transition-colors disabled:opacity-50"
          >
            <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </div>

        {/* Form */}
        <form onSubmit={handleSubmit} className="flex-1 overflow-y-auto">
          <div className="px-6 py-5 space-y-5">
            {/* Recipient info */}
            <div className="grid sm:grid-cols-2 gap-4">
              <div>
                <label className="block text-sm font-medium text-slate-300 mb-1.5">
                  Recipient Email <span className="text-red-400">*</span>
                </label>
                <input
                  type="email"
                  value={recipientEmail}
                  onChange={(e) => setRecipientEmail(e.target.value)}
                  placeholder="john@example.com"
                  className="w-full px-4 py-2.5 bg-slate-900 border border-slate-700 rounded-xl text-white placeholder-slate-500 focus:outline-none focus:ring-2 focus:ring-primary-500 focus:border-transparent transition-all"
                  required
                  disabled={isLoading}
                />
              </div>
              <div>
                <label className="block text-sm font-medium text-slate-300 mb-1.5">
                  Recipient Name
                </label>
                <input
                  type="text"
                  value={recipientName}
                  onChange={(e) => setRecipientName(e.target.value)}
                  placeholder="John Smith"
                  className="w-full px-4 py-2.5 bg-slate-900 border border-slate-700 rounded-xl text-white placeholder-slate-500 focus:outline-none focus:ring-2 focus:ring-primary-500 focus:border-transparent transition-all"
                  disabled={isLoading}
                />
              </div>
            </div>

            {/* Subject hint */}
            <div>
              <label className="block text-sm font-medium text-slate-300 mb-1.5">
                Subject Hint
              </label>
              <input
                type="text"
                value={subjectHint}
                onChange={(e) => setSubjectHint(e.target.value)}
                placeholder="What should the email be about?"
                className="w-full px-4 py-2.5 bg-slate-900 border border-slate-700 rounded-xl text-white placeholder-slate-500 focus:outline-none focus:ring-2 focus:ring-primary-500 focus:border-transparent transition-all"
                disabled={isLoading}
              />
            </div>

            {/* Purpose selector */}
            <PurposeSelector value={purpose} onChange={setPurpose} disabled={isLoading} />

            {/* Tone selector */}
            <ToneSelector value={tone} onChange={setTone} disabled={isLoading} />

            {/* Additional context */}
            <div>
              <label className="block text-sm font-medium text-slate-300 mb-1.5">
                Additional Context
              </label>
              <textarea
                value={context}
                onChange={(e) => setContext(e.target.value)}
                placeholder="Any specific points to include, recent interactions, or relevant background..."
                rows={3}
                className="w-full px-4 py-2.5 bg-slate-900 border border-slate-700 rounded-xl text-white placeholder-slate-500 focus:outline-none focus:ring-2 focus:ring-primary-500 focus:border-transparent transition-all resize-none"
                disabled={isLoading}
              />
            </div>
          </div>

          {/* Footer */}
          <div className="shrink-0 flex items-center justify-end gap-3 px-6 py-4 border-t border-slate-700">
            <button
              type="button"
              onClick={onClose}
              disabled={isLoading}
              className="px-4 py-2.5 text-sm font-medium text-slate-400 hover:text-white hover:bg-slate-700 rounded-xl transition-colors disabled:opacity-50"
            >
              Cancel
            </button>
            <button
              type="submit"
              disabled={isLoading || !recipientEmail.trim()}
              className="inline-flex items-center gap-2 px-5 py-2.5 text-sm font-medium bg-gradient-to-r from-primary-600 to-primary-500 hover:from-primary-500 hover:to-primary-400 text-white rounded-xl transition-all duration-200 shadow-lg shadow-primary-600/25 disabled:opacity-50 disabled:cursor-not-allowed disabled:shadow-none"
            >
              {isLoading ? (
                <>
                  <svg className="animate-spin w-4 h-4" fill="none" viewBox="0 0 24 24">
                    <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                    <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z" />
                  </svg>
                  Generating...
                </>
              ) : (
                <>
                  <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 10V3L4 14h7v7l9-11h-7z" />
                  </svg>
                  Generate Draft
                </>
              )}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
```

**Step 2: Update barrel export**

```typescript
// frontend/src/components/drafts/index.ts
export { EmptyDrafts } from "./EmptyDrafts";
export { DraftCard } from "./DraftCard";
export { StyleMatchIndicator } from "./StyleMatchIndicator";
export { RichTextEditor } from "./RichTextEditor";
export { ToneSelector } from "./ToneSelector";
export { PurposeSelector } from "./PurposeSelector";
export { DraftComposeModal } from "./DraftComposeModal";
```

**Step 3: Commit**

```bash
git add frontend/src/components/drafts/
git commit -m "feat(ui): add DraftComposeModal for generating new email drafts

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```

---

## Task 11: Create Draft Detail/Edit Modal

**Files:**
- Create: `frontend/src/components/drafts/DraftDetailModal.tsx`
- Modify: `frontend/src/components/drafts/index.ts`

**Step 1: Create detail modal with edit capabilities**

```typescript
// frontend/src/components/drafts/DraftDetailModal.tsx
import { useState, useEffect, useCallback } from "react";
import type { EmailDraft, UpdateEmailDraftRequest, EmailDraftTone, RegenerateDraftRequest } from "@/api/drafts";
import { RichTextEditor } from "./RichTextEditor";
import { ToneSelector } from "./ToneSelector";
import { StyleMatchIndicator } from "./StyleMatchIndicator";

interface DraftDetailModalProps {
  draft: EmailDraft | null;
  isOpen: boolean;
  onClose: () => void;
  onSave: (draftId: string, data: UpdateEmailDraftRequest) => void;
  onRegenerate: (draftId: string, data?: RegenerateDraftRequest) => void;
  onSend: (draftId: string) => void;
  isSaving?: boolean;
  isRegenerating?: boolean;
  isSending?: boolean;
}

export function DraftDetailModal({
  draft,
  isOpen,
  onClose,
  onSave,
  onRegenerate,
  onSend,
  isSaving = false,
  isRegenerating = false,
  isSending = false,
}: DraftDetailModalProps) {
  const [subject, setSubject] = useState("");
  const [body, setBody] = useState("");
  const [tone, setTone] = useState<EmailDraftTone>("friendly");
  const [hasChanges, setHasChanges] = useState(false);
  const [showSendConfirm, setShowSendConfirm] = useState(false);

  const isLoading = isSaving || isRegenerating || isSending;
  const canEdit = draft?.status === "draft";

  // Initialize form when draft changes
  useEffect(() => {
    if (draft) {
      setSubject(draft.subject);
      setBody(draft.body);
      setTone(draft.tone);
      setHasChanges(false);
    }
  }, [draft]);

  // Track changes
  useEffect(() => {
    if (draft) {
      const changed = subject !== draft.subject || body !== draft.body || tone !== draft.tone;
      setHasChanges(changed);
    }
  }, [draft, subject, body, tone]);

  // Handle escape key
  const handleKeyDown = useCallback(
    (e: KeyboardEvent) => {
      if (e.key === "Escape" && !isLoading) {
        if (showSendConfirm) {
          setShowSendConfirm(false);
        } else {
          onClose();
        }
      }
    },
    [onClose, isLoading, showSendConfirm]
  );

  useEffect(() => {
    if (isOpen) {
      document.addEventListener("keydown", handleKeyDown);
      return () => document.removeEventListener("keydown", handleKeyDown);
    }
  }, [isOpen, handleKeyDown]);

  const handleSave = () => {
    if (!draft || !hasChanges) return;
    onSave(draft.id, {
      subject: subject.trim(),
      body: body.trim(),
      tone,
    });
  };

  const handleRegenerate = () => {
    if (!draft) return;
    onRegenerate(draft.id, { tone });
  };

  const handleSendClick = () => {
    setShowSendConfirm(true);
  };

  const handleConfirmSend = () => {
    if (!draft) return;
    setShowSendConfirm(false);
    onSend(draft.id);
  };

  if (!isOpen || !draft) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center">
      {/* Backdrop */}
      <div
        className="absolute inset-0 bg-black/70 backdrop-blur-sm"
        onClick={isLoading ? undefined : onClose}
      />

      {/* Modal */}
      <div className="relative w-full max-w-3xl max-h-[90vh] mx-4 bg-slate-800 border border-slate-700 rounded-2xl shadow-2xl flex flex-col overflow-hidden animate-in fade-in zoom-in-95 duration-200">
        {/* Header */}
        <div className="shrink-0 flex items-center justify-between px-6 py-4 border-b border-slate-700">
          <div className="flex items-center gap-4">
            <div>
              <h2 className="text-xl font-semibold text-white">
                {canEdit ? "Edit Draft" : "View Email"}
              </h2>
              <p className="text-sm text-slate-400 mt-0.5">
                To: {draft.recipient_name || draft.recipient_email}
              </p>
            </div>
            {draft.style_match_score !== undefined && (
              <StyleMatchIndicator score={draft.style_match_score} size="md" />
            )}
          </div>
          <button
            onClick={onClose}
            disabled={isLoading}
            className="p-2 text-slate-400 hover:text-white hover:bg-slate-700 rounded-xl transition-colors disabled:opacity-50"
          >
            <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </div>

        {/* Content */}
        <div className="flex-1 overflow-y-auto">
          <div className="px-6 py-5 space-y-5">
            {/* Status badge for sent/failed */}
            {draft.status !== "draft" && (
              <div className={`p-4 rounded-xl ${
                draft.status === "sent"
                  ? "bg-emerald-500/10 border border-emerald-500/30"
                  : "bg-red-500/10 border border-red-500/30"
              }`}>
                <div className="flex items-center gap-2">
                  {draft.status === "sent" ? (
                    <>
                      <svg className="w-5 h-5 text-emerald-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
                      </svg>
                      <span className="font-medium text-emerald-400">Email sent successfully</span>
                    </>
                  ) : (
                    <>
                      <svg className="w-5 h-5 text-red-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
                      </svg>
                      <span className="font-medium text-red-400">Failed to send</span>
                    </>
                  )}
                </div>
                {draft.sent_at && (
                  <p className="text-sm text-slate-400 mt-1">
                    {new Date(draft.sent_at).toLocaleString()}
                  </p>
                )}
                {draft.error_message && (
                  <p className="text-sm text-red-300 mt-1">{draft.error_message}</p>
                )}
              </div>
            )}

            {/* Subject */}
            <div>
              <label className="block text-sm font-medium text-slate-300 mb-1.5">Subject</label>
              <input
                type="text"
                value={subject}
                onChange={(e) => setSubject(e.target.value)}
                disabled={!canEdit || isLoading}
                className="w-full px-4 py-2.5 bg-slate-900 border border-slate-700 rounded-xl text-white placeholder-slate-500 focus:outline-none focus:ring-2 focus:ring-primary-500 focus:border-transparent transition-all disabled:opacity-60"
              />
            </div>

            {/* Tone selector - only show for editable drafts */}
            {canEdit && (
              <ToneSelector value={tone} onChange={setTone} disabled={isLoading} />
            )}

            {/* Body */}
            <div>
              <label className="block text-sm font-medium text-slate-300 mb-1.5">Body</label>
              <RichTextEditor
                content={body}
                onChange={setBody}
                placeholder="Email body..."
                disabled={!canEdit || isLoading}
              />
            </div>
          </div>
        </div>

        {/* Footer */}
        <div className="shrink-0 flex items-center justify-between px-6 py-4 border-t border-slate-700">
          <div className="flex items-center gap-2">
            {canEdit && (
              <button
                type="button"
                onClick={handleRegenerate}
                disabled={isLoading}
                className="inline-flex items-center gap-2 px-4 py-2.5 text-sm font-medium text-slate-300 hover:text-white bg-slate-700/50 hover:bg-slate-700 rounded-xl transition-colors disabled:opacity-50"
              >
                {isRegenerating ? (
                  <>
                    <svg className="animate-spin w-4 h-4" fill="none" viewBox="0 0 24 24">
                      <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                      <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z" />
                    </svg>
                    Regenerating...
                  </>
                ) : (
                  <>
                    <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
                    </svg>
                    Regenerate
                  </>
                )}
              </button>
            )}
          </div>

          <div className="flex items-center gap-3">
            <button
              type="button"
              onClick={onClose}
              disabled={isLoading}
              className="px-4 py-2.5 text-sm font-medium text-slate-400 hover:text-white hover:bg-slate-700 rounded-xl transition-colors disabled:opacity-50"
            >
              {canEdit ? "Cancel" : "Close"}
            </button>

            {canEdit && (
              <>
                <button
                  type="button"
                  onClick={handleSave}
                  disabled={isLoading || !hasChanges}
                  className="inline-flex items-center gap-2 px-4 py-2.5 text-sm font-medium text-primary-400 bg-primary-600/10 hover:bg-primary-600/20 border border-primary-500/30 rounded-xl transition-colors disabled:opacity-50"
                >
                  {isSaving ? (
                    <>
                      <svg className="animate-spin w-4 h-4" fill="none" viewBox="0 0 24 24">
                        <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                        <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z" />
                      </svg>
                      Saving...
                    </>
                  ) : (
                    "Save Changes"
                  )}
                </button>

                <button
                  type="button"
                  onClick={handleSendClick}
                  disabled={isLoading}
                  className="inline-flex items-center gap-2 px-5 py-2.5 text-sm font-medium bg-gradient-to-r from-emerald-600 to-emerald-500 hover:from-emerald-500 hover:to-emerald-400 text-white rounded-xl transition-all duration-200 shadow-lg shadow-emerald-600/25 disabled:opacity-50"
                >
                  <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 19l9 2-9-18-9 18 9-2zm0 0v-8" />
                  </svg>
                  Send Email
                </button>
              </>
            )}
          </div>
        </div>
      </div>

      {/* Send Confirmation Modal */}
      {showSendConfirm && (
        <div className="absolute inset-0 z-60 flex items-center justify-center">
          <div className="absolute inset-0 bg-black/50" onClick={() => setShowSendConfirm(false)} />
          <div className="relative bg-slate-800 border border-slate-700 rounded-2xl shadow-2xl p-6 max-w-md mx-4 animate-in fade-in zoom-in-95 duration-200">
            <div className="flex items-start gap-4">
              <div className="shrink-0 w-12 h-12 rounded-full bg-emerald-500/20 flex items-center justify-center">
                <svg className="w-6 h-6 text-emerald-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 19l9 2-9-18-9 18 9-2zm0 0v-8" />
                </svg>
              </div>
              <div className="flex-1">
                <h3 className="text-lg font-semibold text-white mb-2">Send this email?</h3>
                <p className="text-sm text-slate-400 mb-1">
                  This email will be sent to:
                </p>
                <p className="text-sm font-medium text-white mb-4">
                  {draft.recipient_name ? `${draft.recipient_name} <${draft.recipient_email}>` : draft.recipient_email}
                </p>
                <div className="flex items-center gap-3">
                  <button
                    onClick={() => setShowSendConfirm(false)}
                    className="flex-1 px-4 py-2.5 text-sm font-medium text-slate-400 hover:text-white bg-slate-700/50 hover:bg-slate-700 rounded-xl transition-colors"
                  >
                    Cancel
                  </button>
                  <button
                    onClick={handleConfirmSend}
                    disabled={isSending}
                    className="flex-1 inline-flex items-center justify-center gap-2 px-4 py-2.5 text-sm font-medium bg-emerald-600 hover:bg-emerald-500 text-white rounded-xl transition-colors disabled:opacity-50"
                  >
                    {isSending ? (
                      <>
                        <svg className="animate-spin w-4 h-4" fill="none" viewBox="0 0 24 24">
                          <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                          <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z" />
                        </svg>
                        Sending...
                      </>
                    ) : (
                      "Send Now"
                    )}
                  </button>
                </div>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
```

**Step 2: Update barrel export**

```typescript
// frontend/src/components/drafts/index.ts
export { EmptyDrafts } from "./EmptyDrafts";
export { DraftCard } from "./DraftCard";
export { StyleMatchIndicator } from "./StyleMatchIndicator";
export { RichTextEditor } from "./RichTextEditor";
export { ToneSelector } from "./ToneSelector";
export { PurposeSelector } from "./PurposeSelector";
export { DraftComposeModal } from "./DraftComposeModal";
export { DraftDetailModal } from "./DraftDetailModal";
```

**Step 3: Commit**

```bash
git add frontend/src/components/drafts/
git commit -m "feat(ui): add DraftDetailModal with edit, regenerate, and send capabilities

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```

---

## Task 12: Create Draft Skeleton Loader

**Files:**
- Create: `frontend/src/components/drafts/DraftSkeleton.tsx`
- Modify: `frontend/src/components/drafts/index.ts`

**Step 1: Create skeleton loader matching DraftCard layout**

```typescript
// frontend/src/components/drafts/DraftSkeleton.tsx
export function DraftSkeleton() {
  return (
    <div className="bg-slate-800/50 border border-slate-700/50 rounded-2xl p-5 animate-pulse">
      {/* Header row */}
      <div className="flex items-start justify-between gap-3 mb-3">
        <div className="flex-1">
          <div className="h-5 bg-slate-700 rounded-lg w-3/4 mb-2" />
          <div className="h-4 bg-slate-700/70 rounded-lg w-1/2" />
        </div>
        <div className="h-6 w-16 bg-slate-700 rounded-lg" />
      </div>

      {/* Tags row */}
      <div className="flex items-center gap-2 mb-4">
        <div className="h-7 w-24 bg-slate-700/70 rounded-lg" />
        <div className="h-7 w-20 bg-slate-700/70 rounded-lg" />
      </div>

      {/* Footer row */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <div className="w-8 h-8 bg-slate-700 rounded-full" />
          <div className="h-4 w-20 bg-slate-700/70 rounded-lg" />
        </div>
        <div className="h-4 w-24 bg-slate-700/70 rounded-lg" />
      </div>
    </div>
  );
}
```

**Step 2: Update barrel export**

```typescript
// frontend/src/components/drafts/index.ts
export { EmptyDrafts } from "./EmptyDrafts";
export { DraftCard } from "./DraftCard";
export { StyleMatchIndicator } from "./StyleMatchIndicator";
export { RichTextEditor } from "./RichTextEditor";
export { ToneSelector } from "./ToneSelector";
export { PurposeSelector } from "./PurposeSelector";
export { DraftComposeModal } from "./DraftComposeModal";
export { DraftDetailModal } from "./DraftDetailModal";
export { DraftSkeleton } from "./DraftSkeleton";
```

**Step 3: Commit**

```bash
git add frontend/src/components/drafts/
git commit -m "feat(ui): add DraftSkeleton loading component

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```

---

## Task 13: Create Email Drafts Page

**Files:**
- Create: `frontend/src/pages/EmailDrafts.tsx`
- Modify: `frontend/src/pages/index.ts`

**Step 1: Create the main page component**

```typescript
// frontend/src/pages/EmailDrafts.tsx
import { useState } from "react";
import type { EmailDraft, EmailDraftListItem, EmailDraftStatus, CreateEmailDraftRequest, UpdateEmailDraftRequest, RegenerateDraftRequest } from "@/api/drafts";
import { DashboardLayout } from "@/components/DashboardLayout";
import {
  EmptyDrafts,
  DraftCard,
  DraftComposeModal,
  DraftDetailModal,
  DraftSkeleton,
} from "@/components/drafts";
import {
  useDrafts,
  useDraft,
  useCreateDraft,
  useUpdateDraft,
  useDeleteDraft,
  useRegenerateDraft,
  useSendDraft,
} from "@/hooks/useDrafts";

type StatusFilter = EmailDraftStatus | "all";

const statusFilters: { value: StatusFilter; label: string }[] = [
  { value: "all", label: "All Drafts" },
  { value: "draft", label: "Pending" },
  { value: "sent", label: "Sent" },
  { value: "failed", label: "Failed" },
];

export function EmailDraftsPage() {
  const [statusFilter, setStatusFilter] = useState<StatusFilter>("all");
  const [isComposeOpen, setIsComposeOpen] = useState(false);
  const [selectedDraftId, setSelectedDraftId] = useState<string | null>(null);

  // Queries
  const { data: drafts, isLoading, error } = useDrafts(
    statusFilter === "all" ? undefined : statusFilter
  );

  // Get selected draft details when needed
  const { data: selectedDraft } = useDraft(selectedDraftId || "");

  // Mutations
  const createDraft = useCreateDraft();
  const updateDraft = useUpdateDraft();
  const deleteDraft = useDeleteDraft();
  const regenerateDraft = useRegenerateDraft();
  const sendDraft = useSendDraft();

  const handleCreate = (data: CreateEmailDraftRequest) => {
    createDraft.mutate(data, {
      onSuccess: (newDraft) => {
        setIsComposeOpen(false);
        setSelectedDraftId(newDraft.id);
      },
    });
  };

  const handleView = (draft: EmailDraftListItem) => {
    setSelectedDraftId(draft.id);
  };

  const handleDelete = (draftId: string) => {
    if (confirm("Are you sure you want to delete this draft?")) {
      deleteDraft.mutate(draftId, {
        onSuccess: () => {
          if (selectedDraftId === draftId) {
            setSelectedDraftId(null);
          }
        },
      });
    }
  };

  const handleSave = (draftId: string, data: UpdateEmailDraftRequest) => {
    updateDraft.mutate({ draftId, data });
  };

  const handleRegenerate = (draftId: string, data?: RegenerateDraftRequest) => {
    regenerateDraft.mutate({ draftId, data });
  };

  const handleSend = (draftId: string) => {
    sendDraft.mutate(draftId);
  };

  const handleCloseDetail = () => {
    setSelectedDraftId(null);
  };

  return (
    <DashboardLayout>
      <div className="relative">
        {/* Background pattern */}
        <div className="absolute inset-0 bg-[radial-gradient(ellipse_at_top,_var(--tw-gradient-stops))] from-slate-800 via-slate-900 to-slate-900 pointer-events-none" />

        <div className="relative max-w-6xl mx-auto px-4 py-8 lg:px-8">
          {/* Header */}
          <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4 mb-8">
            <div>
              <h1 className="text-3xl font-bold text-white">Email Drafts</h1>
              <p className="mt-1 text-slate-400">
                AI-powered emails crafted in your style
              </p>
            </div>

            <button
              onClick={() => setIsComposeOpen(true)}
              className="inline-flex items-center gap-2 px-5 py-2.5 bg-gradient-to-r from-primary-600 to-primary-500 hover:from-primary-500 hover:to-primary-400 text-white font-medium rounded-xl transition-all duration-200 shadow-lg shadow-primary-600/25 hover:shadow-primary-500/40"
            >
              <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 4v16m8-8H4" />
              </svg>
              Compose
            </button>
          </div>

          {/* Filter tabs */}
          <div className="flex items-center gap-2 mb-8 overflow-x-auto pb-2">
            {statusFilters.map((filter) => (
              <button
                key={filter.value}
                onClick={() => setStatusFilter(filter.value)}
                className={`px-4 py-2 text-sm font-medium rounded-xl whitespace-nowrap transition-all duration-200 ${
                  statusFilter === filter.value
                    ? "bg-primary-600/20 text-primary-400 border border-primary-500/30"
                    : "text-slate-400 hover:text-white hover:bg-slate-800/50"
                }`}
              >
                {filter.label}
              </button>
            ))}
          </div>

          {/* Error state */}
          {error && (
            <div className="bg-red-500/10 border border-red-500/30 rounded-xl p-4 mb-6">
              <p className="text-red-400">Failed to load drafts. Please try again.</p>
            </div>
          )}

          {/* Loading state */}
          {isLoading && (
            <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
              {[1, 2, 3, 4, 5, 6].map((i) => (
                <DraftSkeleton key={i} />
              ))}
            </div>
          )}

          {/* Empty state */}
          {!isLoading && drafts?.length === 0 && (
            <EmptyDrafts
              onCreateClick={() => setIsComposeOpen(true)}
              hasFilter={statusFilter !== "all"}
            />
          )}

          {/* Drafts grid */}
          {!isLoading && drafts && drafts.length > 0 && (
            <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
              {drafts.map((draft, index) => (
                <div
                  key={draft.id}
                  className="animate-in fade-in slide-in-from-bottom-4"
                  style={{
                    animationDelay: `${index * 50}ms`,
                    animationFillMode: "both",
                  }}
                >
                  <DraftCard
                    draft={draft}
                    onView={() => handleView(draft)}
                    onDelete={() => handleDelete(draft.id)}
                  />
                </div>
              ))}
            </div>
          )}
        </div>

        {/* Compose Modal */}
        <DraftComposeModal
          isOpen={isComposeOpen}
          onClose={() => setIsComposeOpen(false)}
          onSubmit={handleCreate}
          isLoading={createDraft.isPending}
        />

        {/* Detail Modal */}
        <DraftDetailModal
          draft={selectedDraft || null}
          isOpen={selectedDraftId !== null}
          onClose={handleCloseDetail}
          onSave={handleSave}
          onRegenerate={handleRegenerate}
          onSend={handleSend}
          isSaving={updateDraft.isPending}
          isRegenerating={regenerateDraft.isPending}
          isSending={sendDraft.isPending}
        />
      </div>
    </DashboardLayout>
  );
}
```

**Step 2: Update pages barrel export**

```typescript
// frontend/src/pages/index.ts
export { AriaChatPage } from "./AriaChat";
export { BattleCardsPage } from "./BattleCards";
export { DashboardPage } from "./Dashboard";
export { EmailDraftsPage } from "./EmailDrafts";
export { GoalsPage } from "./Goals";
export { IntegrationsCallbackPage } from "./IntegrationsCallback";
export { IntegrationsSettingsPage } from "./IntegrationsSettings";
export { LoginPage } from "./Login";
export { MeetingBriefPage } from "./MeetingBrief";
export { SignupPage } from "./Signup";
```

**Step 3: Commit**

```bash
git add frontend/src/pages/
git commit -m "feat(ui): add EmailDraftsPage with full CRUD functionality

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```

---

## Task 14: Add Route to App Router

**Files:**
- Modify: `frontend/src/App.tsx`

**Step 1: Add the drafts route**

Add the import and route for EmailDraftsPage:

```typescript
// In the imports section, add EmailDraftsPage:
import {
  AriaChatPage,
  BattleCardsPage,
  EmailDraftsPage,
  IntegrationsCallbackPage,
  IntegrationsSettingsPage,
  LoginPage,
  MeetingBriefPage,
  SignupPage,
  DashboardPage,
  GoalsPage,
} from "@/pages";

// Add the route inside <Routes> after /dashboard/battlecards:
<Route
  path="/dashboard/drafts"
  element={
    <ProtectedRoute>
      <EmailDraftsPage />
    </ProtectedRoute>
  }
/>
```

**Step 2: Commit**

```bash
git add frontend/src/App.tsx
git commit -m "feat(routing): add /dashboard/drafts route for email drafts

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```

---

## Task 15: Add Drafts to Sidebar Navigation

**Files:**
- Modify: `frontend/src/components/DashboardLayout.tsx`

**Step 1: Add drafts nav item and icon**

Add to navItems array (after Battle Cards):

```typescript
const navItems = [
  { name: "Dashboard", href: "/dashboard", icon: "home" },
  { name: "ARIA Chat", href: "/dashboard/aria", icon: "chat" },
  { name: "Goals", href: "/goals", icon: "target" },
  { name: "Battle Cards", href: "/dashboard/battlecards", icon: "swords" },
  { name: "Email Drafts", href: "/dashboard/drafts", icon: "mail" },
  { name: "Integrations", href: "/settings/integrations", icon: "integration" },
  { name: "Lead Memory", href: "/leads", icon: "users" },
  { name: "Daily Briefing", href: "/briefing", icon: "calendar" },
  { name: "Settings", href: "/settings", icon: "settings" },
];
```

Add the mail icon to NavIcon:

```typescript
mail: (
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
      d="M3 8l7.89 5.26a2 2 0 002.22 0L21 8M5 19h14a2 2 0 002-2V7a2 2 0 00-2-2H5a2 2 0 00-2 2v10a2 2 0 002 2z"
    />
  </svg>
),
```

**Step 2: Commit**

```bash
git add frontend/src/components/DashboardLayout.tsx
git commit -m "feat(nav): add Email Drafts to sidebar navigation

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```

---

## Task 16: Test the Complete Flow

**Step 1: Run the development server**

```bash
cd frontend && npm run dev
```

**Step 2: Manual testing checklist**

1. [ ] Navigate to `/dashboard/drafts`
2. [ ] Verify empty state displays correctly
3. [ ] Click "Compose" - verify modal opens
4. [ ] Fill in compose form and submit - verify loading state and draft creation
5. [ ] Verify new draft appears in grid
6. [ ] Click a draft card - verify detail modal opens
7. [ ] Edit subject/body - verify "Save Changes" enables
8. [ ] Save changes - verify update
9. [ ] Click "Regenerate" - verify loading and content update
10. [ ] Click "Send Email" - verify confirmation modal
11. [ ] Test status filter tabs
12. [ ] Test delete functionality
13. [ ] Verify sidebar navigation works

**Step 3: Run linting and type check**

```bash
cd frontend && npm run lint && npm run typecheck
```

**Step 4: Fix any issues and commit**

```bash
git add -A
git commit -m "fix: address lint and type issues in email drafts implementation

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```

---

## Task 17: Final Cleanup and Documentation

**Step 1: Verify all acceptance criteria from US-409**

- [ ] `/dashboard/drafts` route for email drafts management
- [ ] Draft composer with rich text editor
- [ ] Preview as recipient would see (detail modal)
- [ ] Edit subject, body, tone
- [ ] Regenerate button with different parameters
- [ ] Style match score displayed
- [ ] Send button (with confirmation modal)
- [ ] Save as template option (deferred - not in core requirements)
- [ ] List view of all drafts with status

**Step 2: Final commit**

```bash
git add -A
git commit -m "feat(US-409): complete Email Draft UI implementation

- Add /dashboard/drafts route with full CRUD
- Rich text editor with TipTap
- Style match score visualization
- Send confirmation modal
- Filter by draft status
- Apple-inspired luxury UI styling

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```

---

## Summary

This plan implements US-409 Email Draft UI with:

1. **API Layer** (Tasks 1-2): Type-safe API client and React Query hooks
2. **Rich Text Editing** (Tasks 3, 7): TipTap integration with toolbar
3. **UI Components** (Tasks 4-12): Apple-inspired styling with:
   - Elegant empty states
   - Card-based draft list with hover effects
   - Circular style match indicator
   - Segmented tone selector
   - Pill-style purpose buttons
   - Compose and detail modals
   - Skeleton loaders
4. **Page Assembly** (Tasks 13-15): Full page with routing and navigation
5. **Testing & Polish** (Tasks 16-17): Manual testing and final cleanup
