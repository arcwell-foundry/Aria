/**
 * Component Barrel File
 * Centralized exports for all components
 */

// Auth & Routing
export { ProtectedRoute } from './ProtectedRoute';
export { PostAuthRouter } from './PostAuthRouter';

// Layout
export { DashboardLayout } from './DashboardLayout';

// Error Handling
export { ErrorBoundary, withErrorBoundary } from './ErrorBoundary';
export {
  EmptyState,
  EmptyLeads,
  EmptyGoals,
  EmptyBriefings,
  EmptyBattleCards,
  EmptyMeetingBriefs,
  EmptyDrafts,
  EmptyActivity
} from './EmptyState';
export {
  SkeletonLoader,
  LeadsSkeleton,
  GoalsSkeleton,
  BriefingSkeleton,
  LeadsTableSkeleton,
  ContactsListSkeleton,
  TextSkeleton
} from './SkeletonLoader';
export { OfflineBanner } from './OfflineBanner';
export { ErrorToaster } from './ErrorToaster';

// Status Indicators
export { AgentActivationStatus } from './AgentActivationStatus';

// Help & Content
export { FeedbackWidget } from './FeedbackWidget';
export { HelpTooltip } from './HelpTooltip';
export type { HelpTooltipProps } from './HelpTooltip';
