/**
 * GoalPlanSidePanel - Slide-in panel for goal plans during avatar/video mode
 *
 * When ARIA's avatar triggers create_goal_from_video, this panel slides in
 * from the right to display the GoalPlanCard. The panel appears over the
 * avatar view without blocking interaction completely.
 *
 * Design:
 * - Slides in from right with smooth animation
 * - Width: 400px, responsive on smaller screens
 * - Z-index above avatar but below modals
 * - Semi-transparent backdrop (optional)
 * - Dismissible via X button or clicking outside
 */

import { useEffect, useCallback, useRef } from 'react';
import { X } from 'lucide-react';
import { GoalPlanCard } from '@/components/rich/GoalPlanCard';
import { useSidePanelStore } from '@/stores/sidePanelStore';
import type { GoalPlanData } from '@/components/rich/GoalPlanCard';

export function GoalPlanSidePanel() {
  const { pendingGoalPlan, isVisible, dismissSidePanel } = useSidePanelStore();
  const panelRef = useRef<HTMLDivElement>(null);

  // Handle escape key to dismiss
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape' && isVisible) {
        dismissSidePanel();
      }
    };

    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [isVisible, dismissSidePanel]);

  // Handle click outside to dismiss
  const handleBackdropClick = useCallback(
    (e: React.MouseEvent) => {
      if (e.target === e.currentTarget) {
        dismissSidePanel();
      }
    },
    [dismissSidePanel],
  );

  // Handle when goal plan is approved - dismiss panel after approval
  const handlePlanApproved = useCallback(() => {
    // The GoalPlanCard handles the approval internally
    // We dismiss the panel after a short delay to show the "approved" state
    setTimeout(() => {
      dismissSidePanel();
    }, 1500);
  }, [dismissSidePanel]);

  // Don't render if no pending goal plan
  if (!pendingGoalPlan) return null;

  return (
    <div
      className={`fixed inset-0 z-40 transition-opacity duration-300 ${
        isVisible ? 'opacity-100' : 'opacity-0 pointer-events-none'
      }`}
      onClick={handleBackdropClick}
      data-aria-id="goal-plan-side-panel-backdrop"
    >
      {/* Semi-transparent backdrop - subtle, doesn't fully block avatar */}
      <div
        className="absolute inset-0"
        style={{ backgroundColor: 'rgba(0, 0, 0, 0.3)' }}
      />

      {/* Slide-in panel */}
      <div
        ref={panelRef}
        className={`absolute right-0 top-0 bottom-0 w-[400px] max-w-[90vw] shadow-2xl transform transition-transform duration-300 ease-out ${
          isVisible ? 'translate-x-0' : 'translate-x-full'
        }`}
        style={{
          backgroundColor: 'var(--bg-elevated)',
          borderLeft: '1px solid var(--border)',
        }}
        data-aria-id="goal-plan-side-panel"
      >
        {/* Header */}
        <div
          className="flex items-center justify-between px-4 h-14 border-b shrink-0"
          style={{ borderColor: 'var(--border)' }}
        >
          <h2
            className="font-display text-lg italic"
            style={{ color: 'var(--text-primary)' }}
          >
            ARIA's Plan
          </h2>
          <button
            type="button"
            onClick={dismissSidePanel}
            className="p-1.5 rounded-md transition-colors cursor-pointer"
            style={{ color: 'var(--text-secondary)' }}
            onMouseEnter={(e) => {
              e.currentTarget.style.backgroundColor = 'var(--bg-subtle)';
            }}
            onMouseLeave={(e) => {
              e.currentTarget.style.backgroundColor = 'transparent';
            }}
            aria-label="Dismiss panel"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* Scrollable content */}
        <div className="flex-1 overflow-y-auto p-4">
          <GoalPlanCardWithDismiss
            data={pendingGoalPlan}
            onApproved={handlePlanApproved}
          />
        </div>
      </div>
    </div>
  );
}

/**
 * Wrapper around GoalPlanCard that provides dismiss callback on approval
 */
function GoalPlanCardWithDismiss({
  data,
  onApproved: _onApproved,
}: {
  data: GoalPlanData;
  onApproved: () => void;
}) {
  // We need to watch for approval state changes in the GoalPlanCard
  // Since GoalPlanCard manages its own status state, we use a custom wrapper
  // that triggers onApproved when the status becomes 'approved'

  // For now, we render the GoalPlanCard as-is. The card handles approval
  // internally and shows the "executing" state. The parent can dismiss
  // via the X button or escape key.
  //
  // Future enhancement: GoalPlanCard could accept an onStatusChange callback

  return <GoalPlanCard data={data} />;
}
