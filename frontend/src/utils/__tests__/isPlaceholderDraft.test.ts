/**
 * Tests for isPlaceholderDraft utility function
 * @see /Users/dhruv/aria/frontend/src/utils/isPlaceholderDraft.ts
 */

import { describe, it, expect } from "vitest";
import { isPlaceholderDraft } from "../isPlaceholderDraft";
import type { EmailDraft, EmailDraftListItem } from "@/api/drafts";

// Helper to create a minimal valid EmailDraft for testing
function createMockDraft(
  overrides: Partial<EmailDraft> = {}
): EmailDraft {
  return {
    id: "test-draft-id",
    user_id: "test-user-id",
    recipient_email: "john@example.com",
    recipient_name: "John Doe",
    subject: "Test Subject",
    body: "Test body",
    purpose: "follow_up",
    tone: "friendly",
    status: "draft",
    created_at: "2024-01-01T00:00:00Z",
    updated_at: "2024-01-01T00:00:00Z",
    ...overrides,
  };
}

// Helper to create a minimal valid EmailDraftListItem for testing
function createMockDraftListItem(
  overrides: Partial<EmailDraftListItem> = {}
): EmailDraftListItem {
  return {
    id: "test-draft-id",
    recipient_email: "john@example.com",
    recipient_name: "John Doe",
    subject: "Test Subject",
    purpose: "follow_up",
    tone: "friendly",
    status: "draft",
    created_at: "2024-01-01T00:00:00Z",
    ...overrides,
  };
}

describe("isPlaceholderDraft", () => {
  describe("placeholder email detection", () => {
    it("should detect placeholder email with 'placeholder' in recipient_email", () => {
      const draft = createMockDraft({
        recipient_email: "pending@placeholder.com",
      });
      expect(isPlaceholderDraft(draft)).toBe(true);
    });

    it("should detect placeholder email case-insensitively", () => {
      const draft = createMockDraft({
        recipient_email: "test@PLACEHOLDER.com",
      });
      expect(isPlaceholderDraft(draft)).toBe(true);
    });

    it("should detect placeholder email with mixed case", () => {
      const draft = createMockDraft({
        recipient_email: "test@PlaceHolder.org",
      });
      expect(isPlaceholderDraft(draft)).toBe(true);
    });

    it("should work with EmailDraftListItem type", () => {
      const draftItem = createMockDraftListItem({
        recipient_email: "someone@placeholder.io",
      });
      expect(isPlaceholderDraft(draftItem)).toBe(true);
    });
  });

  describe("pending_review status detection", () => {
    it("should detect pending_review status as placeholder", () => {
      const draft = createMockDraft({
        status: "pending_review",
      });
      expect(isPlaceholderDraft(draft)).toBe(true);
    });

    it("should detect pending_review even with valid email", () => {
      const draft = createMockDraft({
        status: "pending_review",
        recipient_email: "valid@company.com",
        recipient_name: "Valid Name",
      });
      expect(isPlaceholderDraft(draft)).toBe(true);
    });

    it("should work with EmailDraftListItem type", () => {
      const draftItem = createMockDraftListItem({
        status: "pending_review",
      });
      expect(isPlaceholderDraft(draftItem)).toBe(true);
    });
  });

  describe("bracket placeholder in name detection", () => {
    it("should detect bracket placeholder in recipient_name", () => {
      const draft = createMockDraft({
        recipient_name: "[Contact Name]",
      });
      expect(isPlaceholderDraft(draft)).toBe(true);
    });

    it("should detect single bracket at start", () => {
      const draft = createMockDraft({
        recipient_name: "[Some Template Variable",
      });
      expect(isPlaceholderDraft(draft)).toBe(true);
    });

    it("should detect bracket anywhere in name", () => {
      const draft = createMockDraft({
        recipient_name: "Dear [Name],",
      });
      expect(isPlaceholderDraft(draft)).toBe(true);
    });

    it("should work with EmailDraftListItem type", () => {
      const draftItem = createMockDraftListItem({
        recipient_name: "[Recipient]",
      });
      expect(isPlaceholderDraft(draftItem)).toBe(true);
    });
  });

  describe("returns false for regular drafts", () => {
    it("should return false for a regular draft with all valid fields", () => {
      const draft = createMockDraft({
        recipient_email: "john.smith@company.com",
        recipient_name: "John Smith",
        status: "draft",
      });
      expect(isPlaceholderDraft(draft)).toBe(false);
    });

    it("should return false for 'sent' status drafts", () => {
      const draft = createMockDraft({
        status: "sent",
      });
      expect(isPlaceholderDraft(draft)).toBe(false);
    });

    it("should return false for 'approved' status drafts", () => {
      const draft = createMockDraft({
        status: "approved",
      });
      expect(isPlaceholderDraft(draft)).toBe(false);
    });

    it("should return false for 'failed' status drafts", () => {
      const draft = createMockDraft({
        status: "failed",
      });
      expect(isPlaceholderDraft(draft)).toBe(false);
    });

    it("should return false for 'dismissed' status drafts", () => {
      const draft = createMockDraft({
        status: "dismissed",
      });
      expect(isPlaceholderDraft(draft)).toBe(false);
    });

    it("should return false for 'saved_to_client' status drafts", () => {
      const draft = createMockDraft({
        status: "saved_to_client",
      });
      expect(isPlaceholderDraft(draft)).toBe(false);
    });

    it("should work with EmailDraftListItem type for regular drafts", () => {
      const draftItem = createMockDraftListItem({
        recipient_email: "jane@valid.org",
        recipient_name: "Jane Doe",
        status: "draft",
      });
      expect(isPlaceholderDraft(draftItem)).toBe(false);
    });
  });

  describe("handles undefined/null fields gracefully", () => {
    it("should return false for null draft", () => {
      expect(isPlaceholderDraft(null)).toBe(false);
    });

    it("should return false for undefined draft", () => {
      expect(isPlaceholderDraft(undefined)).toBe(false);
    });

    it("should handle undefined recipient_name", () => {
      const draft = createMockDraft({
        recipient_name: undefined,
        recipient_email: "valid@email.com",
        status: "draft",
      });
      expect(isPlaceholderDraft(draft)).toBe(false);
    });

    it("should handle undefined recipient_email", () => {
      const draft = createMockDraft({
        recipient_email: undefined as unknown as string,
        recipient_name: "Valid Name",
        status: "draft",
      });
      expect(isPlaceholderDraft(draft)).toBe(false);
    });

    it("should handle empty string recipient_name", () => {
      const draft = createMockDraft({
        recipient_name: "",
        recipient_email: "valid@email.com",
        status: "draft",
      });
      expect(isPlaceholderDraft(draft)).toBe(false);
    });

    it("should handle empty string recipient_email", () => {
      const draft = createMockDraft({
        recipient_email: "",
        recipient_name: "Valid Name",
        status: "draft",
      });
      expect(isPlaceholderDraft(draft)).toBe(false);
    });

    it("should detect placeholder in email even with undefined name", () => {
      const draft = createMockDraft({
        recipient_email: "test@placeholder.com",
        recipient_name: undefined,
        status: "draft",
      });
      expect(isPlaceholderDraft(draft)).toBe(true);
    });

    it("should detect bracket in name even with undefined email", () => {
      const draft = createMockDraft({
        recipient_email: undefined as unknown as string,
        recipient_name: "[Contact]",
        status: "draft",
      });
      expect(isPlaceholderDraft(draft)).toBe(true);
    });
  });
});
