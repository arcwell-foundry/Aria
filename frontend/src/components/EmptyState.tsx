import type { LucideIcon } from 'lucide-react';
import { Target, Mail, Shield, Calendar, FileText, Sparkles } from 'lucide-react';
import type { ReactNode } from 'react';

/**
 * EmptyState - Reusable empty state component with ARIA personality
 *
 * Follows ARIA Design System v1.0:
 * - Dark surface background: bg-[#0F1117]
 * - Instrument Serif for title (font-display text-[24px])
 * - Satoshi for description (font-sans text-[15px])
 * - Lucide icons (20x20, stroke 1.5)
 * - Icon container: w-16 h-16 rounded-full bg-[#1E2235]
 * - ARIA personality: optimistic, actionable messaging
 */

interface EmptyStateProps {
  /** Lucide icon component to display */
  icon: LucideIcon;
  /** Title text (displayed in Instrument Serif) */
  title: string;
  /** Description text (displayed in Satoshi) */
  description: string;
  /** Optional button label */
  actionLabel?: string;
  /** Optional button click handler */
  onAction?: () => void;
  /** Optional custom className for wrapper */
  className?: string;
}

export function EmptyState({
  icon: Icon,
  title,
  description,
  actionLabel,
  onAction,
  className = '',
}: EmptyStateProps): ReactNode {
  return (
    <div className={`flex flex-col items-center justify-center py-16 px-6 text-center ${className}`}>
      {/* Icon Container */}
      <div className="w-16 h-16 rounded-full bg-[#1E2235] flex items-center justify-center mb-6">
        <Icon size={20} strokeWidth={1.5} className="text-[#8B92A5]" aria-hidden="true" />
      </div>

      {/* Title - Instrument Serif */}
      <h3 className="font-display text-[24px] leading-[1.2] text-[#E8E6E1] mb-3">
        {title}
      </h3>

      {/* Description - Satoshi */}
      <p className="font-sans text-[15px] leading-[1.6] text-[#8B92A5] max-w-md mb-8">
        {description}
      </p>

      {/* Action Button */}
      {onAction && actionLabel && (
        <button
          onClick={onAction}
          className="inline-flex items-center justify-center gap-2 bg-[#5B6E8A] text-white rounded-lg px-5 py-2.5 font-sans font-medium text-[15px] hover:bg-[#4A5D79] active:bg-[#3D5070] transition-colors duration-150 cursor-pointer focus:outline-none focus:ring-2 focus:ring-[#7B8EAA] focus:ring-offset-2 focus:ring-offset-[#0F1117]"
        >
          {actionLabel}
        </button>
      )}
    </div>
  );
}

/**
 * Preset variants for common ARIA empty states
 * Each has ARIA personality: optimistic, actionable messaging
 */

export function EmptyLeads({ className, actionLabel, onAction }: Omit<EmptyStateProps, 'icon' | 'title' | 'description'> = {}) {
  return (
    <EmptyState
      icon={Target}
      title="No leads yet"
      description="ARIA can start finding prospects the moment you set a goal."
      actionLabel={actionLabel}
      onAction={onAction}
      className={className}
    />
  );
}

export function EmptyGoals({ className, actionLabel, onAction }: Omit<EmptyStateProps, 'icon' | 'title' | 'description'> = {}) {
  return (
    <EmptyState
      icon={Target}
      title="No goals yet"
      description="Set a goal and ARIA will start working on it immediately."
      actionLabel={actionLabel}
      onAction={onAction}
      className={className}
    />
  );
}

export function EmptyBriefings({ className, actionLabel, onAction }: Omit<EmptyStateProps, 'icon' | 'title' | 'description'> = {}) {
  return (
    <EmptyState
      icon={Mail}
      title="No briefings yet"
      description="Connect your email and CRM to get daily intelligence."
      actionLabel={actionLabel}
      onAction={onAction}
      className={className}
    />
  );
}

export function EmptyBattleCards({ className, actionLabel, onAction }: Omit<EmptyStateProps, 'icon' | 'title' | 'description'> = {}) {
  return (
    <EmptyState
      icon={Shield}
      title="No battle cards yet"
      description="ARIA will generate competitive battle cards as you research competitors."
      actionLabel={actionLabel}
      onAction={onAction}
      className={className}
    />
  );
}

export function EmptyMeetingBriefs({ className, actionLabel, onAction }: Omit<EmptyStateProps, 'icon' | 'title' | 'description'> = {}) {
  return (
    <EmptyState
      icon={Calendar}
      title="No upcoming meetings"
      description="ARIA prepares research briefs for your scheduled meetings."
      actionLabel={actionLabel}
      onAction={onAction}
      className={className}
    />
  );
}

export function EmptyDrafts({ className, actionLabel, onAction }: Omit<EmptyStateProps, 'icon' | 'title' | 'description'> = {}) {
  return (
    <EmptyState
      icon={FileText}
      title="No drafts yet"
      description="ARIA helps you write faster with personalized drafts based on your communication style."
      actionLabel={actionLabel}
      onAction={onAction}
      className={className}
    />
  );
}

export function EmptyActivity({ className, actionLabel, onAction }: Omit<EmptyStateProps, 'icon' | 'title' | 'description'> = {}) {
  return (
    <EmptyState
      icon={Sparkles}
      title="ARIA is getting started"
      description="Complete onboarding to unlock personalized intelligence and recommendations."
      actionLabel={actionLabel}
      onAction={onAction}
      className={className}
    />
  );
}
