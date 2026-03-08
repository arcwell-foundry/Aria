/**
 * Utility function to detect placeholder drafts
 *
 * A draft is considered a placeholder if any of these conditions are true:
 * - status === 'pending_review'
 * - recipient_email contains 'placeholder'
 * - recipient_name contains '[' (template variable marker)
 */

import type { EmailDraft, EmailDraftListItem } from "@/api/drafts";

/**
 * Checks if a draft is a placeholder draft that should be filtered
 * from the drafts list or handled specially.
 *
 * @param draft - The draft to check (can be EmailDraft or EmailDraftListItem)
 * @returns true if the draft is a placeholder, false otherwise
 */
export function isPlaceholderDraft(
  draft: EmailDraft | EmailDraftListItem | null | undefined
): boolean {
  // Handle null/undefined gracefully
  if (!draft) {
    return false;
  }

  // Check for pending_review status
  if (draft.status === "pending_review") {
    return true;
  }

  // Check if recipient_email contains 'placeholder' (case-insensitive)
  if (
    draft.recipient_email &&
    draft.recipient_email.toLowerCase().includes("placeholder")
  ) {
    return true;
  }

  // Check if recipient_name contains '[' (template variable marker)
  if (draft.recipient_name && draft.recipient_name.includes("[")) {
    return true;
  }

  return false;
}
