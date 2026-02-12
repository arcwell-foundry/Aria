/**
 * Pipeline - Pipeline-specific UI components following ARIA Design System v1.0
 *
 * These components are used in PipelinePage and LeadDetailPage:
 * - HealthBar: Lead health score indicator
 * - LeadTable: Sortable table with pagination for leads
 *
 * @example
 * import { HealthBar, LeadTable } from '@/components/pipeline';
 */

export { HealthBar, type HealthBarProps } from './HealthBar';
export { LeadTable, LeadRowSkeleton, type LeadTableProps } from './LeadTable';
