/**
 * ActivityPage - Agent Activity Feed
 *
 * Wraps the reusable ActivityFeed component in a full-page layout.
 * Light theme content page per ARIA Design System v1.0.
 */

import { ActivityFeed } from '@/components/activity/ActivityFeed';

export function ActivityPage() {
  return (
    <div
      className="flex-1 flex flex-col h-full"
      style={{ backgroundColor: 'var(--bg-primary)' }}
      data-aria-id="activity-page"
    >
      <div className="flex-1 overflow-y-auto p-8">
        <ActivityFeed />
      </div>
    </div>
  );
}
