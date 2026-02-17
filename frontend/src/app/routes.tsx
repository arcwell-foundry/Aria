import { Routes, Route, Navigate } from 'react-router-dom';
import { AppShell } from '@/app/AppShell';
import { ProtectedRoute } from '@/components/common/ProtectedRoute';
import { LoginPage } from '@/components/pages/LoginPage';
import { SignupPage } from '@/components/pages/SignupPage';
import {
  ARIAWorkspace,
  PipelinePage,
  IntelligencePage,
  CommunicationsPage,
  ActionsPage,
  ActivityPage,
  AnalyticsPage,
  SettingsPage,
  OnboardingPage,
  VideoPage,
  DebriefPage,
} from '@/components/pages';
import { DialogueMode } from '@/components/avatar';

export function AppRoutes() {
  return (
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
  );
}
