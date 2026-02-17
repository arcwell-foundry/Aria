import { lazy, Suspense } from 'react';
import { Routes, Route, Navigate } from 'react-router-dom';
import { AppShell } from '@/app/AppShell';
import { ProtectedRoute } from '@/components/common/ProtectedRoute';

// Eagerly loaded — critical path (default route, auth pages, shared modality component)
import { LoginPage } from '@/components/pages/LoginPage';
import { SignupPage } from '@/components/pages/SignupPage';
import { ARIAWorkspace } from '@/components/pages';
import { DialogueMode } from '@/components/avatar';

// Lazy loaded — route-level code splitting (named export wrapper pattern)
const PipelinePage = lazy(() =>
  import('@/components/pages/PipelinePage').then(m => ({ default: m.PipelinePage }))
);
const IntelligencePage = lazy(() =>
  import('@/components/pages/IntelligencePage').then(m => ({ default: m.IntelligencePage }))
);
const CommunicationsPage = lazy(() =>
  import('@/components/pages/CommunicationsPage').then(m => ({ default: m.CommunicationsPage }))
);
const ActionsPage = lazy(() =>
  import('@/components/pages/ActionsPage').then(m => ({ default: m.ActionsPage }))
);
const ActivityPage = lazy(() =>
  import('@/components/pages/ActivityPage').then(m => ({ default: m.ActivityPage }))
);
const AnalyticsPage = lazy(() =>
  import('@/components/pages/AnalyticsPage').then(m => ({ default: m.AnalyticsPage }))
);
const SettingsPage = lazy(() =>
  import('@/components/pages/SettingsPage').then(m => ({ default: m.SettingsPage }))
);
const OnboardingPage = lazy(() =>
  import('@/components/pages/OnboardingPage').then(m => ({ default: m.OnboardingPage }))
);
const VideoPage = lazy(() =>
  import('@/components/pages/VideoPage').then(m => ({ default: m.VideoPage }))
);
const DebriefPage = lazy(() =>
  import('@/components/pages/DebriefPage').then(m => ({ default: m.DebriefPage }))
);
const DebriefsListPage = lazy(() =>
  import('@/components/pages/DebriefsListPage').then(m => ({ default: m.DebriefsListPage }))
);

function PageLoadingSkeleton() {
  return (
    <div className="flex items-center justify-center h-full w-full min-h-[50vh]">
      <div className="flex flex-col items-center gap-3">
        <div className="h-8 w-8 animate-spin rounded-full border-2 border-[var(--accent-primary)] border-t-transparent" />
        <span className="text-sm text-[var(--text-secondary)]">Loading...</span>
      </div>
    </div>
  );
}

export function AppRoutes() {
  return (
    <Suspense fallback={<PageLoadingSkeleton />}>
      <Routes>
        {/* Shell-less routes (no sidebar) */}
        <Route path="/login" element={<LoginPage />} />
        <Route path="/signup" element={<SignupPage />} />
        <Route
          path="/onboarding"
          element={
            <ProtectedRoute>
              <OnboardingPage />
            </ProtectedRoute>
          }
        />

        {/* App shell routes */}
        <Route
          element={
            <ProtectedRoute>
              <AppShell />
            </ProtectedRoute>
          }
        >
          <Route index element={<ARIAWorkspace />} />
          <Route path="dialogue" element={<DialogueMode />} />
          <Route path="briefing" element={<DialogueMode sessionType="briefing" />} />
          <Route path="aria/video" element={<VideoPage />} />
          <Route path="pipeline" element={<PipelinePage />} />
          <Route path="pipeline/leads/:leadId" element={<PipelinePage />} />
          <Route path="intelligence" element={<IntelligencePage />} />
          <Route path="intelligence/battle-cards/:competitorId" element={<IntelligencePage />} />
          <Route path="communications" element={<CommunicationsPage />} />
          <Route path="communications/drafts/:draftId" element={<CommunicationsPage />} />
          <Route path="debriefs" element={<DebriefsListPage />} />
          <Route path="debriefs/new" element={<DebriefPage />} />
          <Route path="actions" element={<ActionsPage />} />
          <Route path="actions/goals/:goalId" element={<ActionsPage />} />
          <Route path="activity" element={<ActivityPage />} />
          <Route path="analytics" element={<AnalyticsPage />} />
          <Route path="settings" element={<SettingsPage />} />
          <Route path="settings/:section" element={<SettingsPage />} />
        </Route>

        {/* Fallback */}
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </Suspense>
  );
}
