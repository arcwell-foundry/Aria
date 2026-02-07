/**
 * Global keyboard shortcuts hook.
 *
 * Provides:
 * - Cmd+K: Open command palette
 * - Cmd+/: Show shortcuts modal
 * - G then D: Go to dashboard
 * - G then L: Go to leads
 * - G then G: Go to goals
 * - G then S: Go to settings
 * - Esc: Close any overlay
 */

import { useEffect, useRef, useCallback, useMemo } from 'react';

interface ShortcutConfig {
  key: string;
  ctrlKey?: boolean;
  metaKey?: boolean;
  shiftKey?: boolean;
  altKey?: boolean;
  handler: () => void;
  description: string;
}

interface KeyboardShortcutsOptions {
  onCommandPalette?: () => void;
  onShowShortcuts?: () => void;
  onNavigate?: (path: string) => void;
  onCloseOverlay?: () => void;
  isEnabled?: boolean;
}

export function useKeyboardShortcuts(options: KeyboardShortcutsOptions = {}) {
  const {
    onCommandPalette,
    onShowShortcuts,
    onNavigate,
    onCloseOverlay,
    isEnabled = true,
  } = options;

  // Track pending key sequences (like G then D)
  const pendingKeyRef = useRef<string | null>(null);
  const pendingKeyTimeoutRef = useRef<NodeJS.Timeout | null>(null);

  // Clear pending key after delay
  const clearPendingKey = useCallback(() => {
    pendingKeyRef.current = null;
    if (pendingKeyTimeoutRef.current) {
      clearTimeout(pendingKeyTimeoutRef.current);
      pendingKeyTimeoutRef.current = null;
    }
  }, []);

  // Define shortcuts
  const shortcuts: ShortcutConfig[] = useMemo(
    () => [
      {
        key: 'k',
        metaKey: true,
        ctrlKey: true,
        handler: () => onCommandPalette?.(),
        description: 'Open command palette',
      },
      {
        key: '/',
        shiftKey: true,
        metaKey: true,
        ctrlKey: true,
        handler: () => onShowShortcuts?.(),
        description: 'Show keyboard shortcuts',
      },
      {
        key: 'Escape',
        handler: () => onCloseOverlay?.(),
        description: 'Close overlay',
      },
    ],
    [onCommandPalette, onShowShortcuts, onCloseOverlay]
  );

  // Handle single key shortcuts
  const handleKeyDown = useCallback(
    (e: KeyboardEvent) => {
      if (!isEnabled) return;

      // Ignore if user is typing in an input
      if (
        e.target instanceof HTMLInputElement ||
        e.target instanceof HTMLTextAreaElement ||
        (e.target as HTMLElement).isContentEditable
      ) {
        return;
      }

      // Check for sequence shortcuts (G then X)
      if (pendingKeyRef.current === 'g') {
        clearPendingKey();

        const keyMap: Record<string, () => void> = {
          d: () => onNavigate?.('/dashboard'),
          l: () => onNavigate?.('/leads'),
          g: () => onNavigate?.('/goals'),
          s: () => onNavigate?.('/settings'),
        };

        const handler = keyMap[e.key.toLowerCase()];
        if (handler) {
          e.preventDefault();
          handler();
        }
        return;
      }

      // Check if 'G' is pressed (start of sequence)
      if (e.key.toLowerCase() === 'g') {
        pendingKeyRef.current = 'g';
        pendingKeyTimeoutRef.current = setTimeout(clearPendingKey, 1000);
        return;
      }

      // Check regular shortcuts
      for (const shortcut of shortcuts) {
        if (
          shortcut.key.toLowerCase() === e.key.toLowerCase() &&
          (shortcut.ctrlKey === undefined || shortcut.ctrlKey === e.ctrlKey) &&
          (shortcut.metaKey === undefined || shortcut.metaKey === e.metaKey) &&
          (shortcut.shiftKey === undefined || shortcut.shiftKey === e.shiftKey) &&
          (shortcut.altKey === undefined || shortcut.altKey === e.altKey)
        ) {
          e.preventDefault();
          shortcut.handler();
          return;
        }
      }
    },
    [isEnabled, onCommandPalette, onShowShortcuts, onNavigate, onCloseOverlay, clearPendingKey, shortcuts]
  );

  useEffect(() => {
    document.addEventListener('keydown', handleKeyDown);
    return () => {
      document.removeEventListener('keydown', handleKeyDown);
      clearPendingKey();
    };
  }, [handleKeyDown, clearPendingKey]);
}
