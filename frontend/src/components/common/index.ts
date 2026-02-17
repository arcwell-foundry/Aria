/**
 * Common - Shared UI components following ARIA Design System v1.0
 *
 * These components are used across Layer 2 content pages:
 * - EmptyState: Placeholder for empty content areas
 * - CopyButton: Clipboard copy action
 * - SortableHeader: Table column sorting
 *
 * @example
 * import { EmptyState, CopyButton, SortableHeader } from '@/components/common';
 */

export { EmptyState, type EmptyStateProps } from './EmptyState';
export { CopyButton, type CopyButtonProps } from './CopyButton';
export { SortableHeader, type SortableHeaderProps, type SortDirection } from './SortableHeader';
export { AgentAvatar, type AgentAvatarProps } from './AgentAvatar';
export { ProtectedRoute, type ProtectedRouteProps } from './ProtectedRoute';
export { CommandPalette, type CommandPaletteProps } from './CommandPalette';
export { ErrorBoundary, withErrorBoundary } from '../ErrorBoundary';
