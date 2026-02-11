import { Routes, Route, Navigate } from 'react-router-dom';
import { AppShell } from '@/app/AppShell';
import { ProtectedRoute } from '@/_deprecated/components/ProtectedRoute';
import { LoginPage } from '@/_deprecated/pages/Login';
import { SignupPage } from '@/_deprecated/pages/Signup';
import {
  ARIAWorkspace,
  BriefingPage,
  PipelinePage,
  IntelligencePage,
  CommunicationsPage,
  ActionsPage,
  SettingsPage,
} from '@/components/pages';

export function AppRoutes() {
  return (
    <Routes>
      {/* Shell-less routes (no sidebar) */}
      <Route path="/login" element={<LoginPage />} />
      <Route path="/signup" element={<SignupPage />} />

      {/* App shell routes */}
      <Route
        element={
          <ProtectedRoute>
            <AppShell />
          </ProtectedRoute>
        }
      >
        <Route index element={<ARIAWorkspace />} />
        <Route path="briefing" element={<BriefingPage />} />
        <Route path="pipeline" element={<PipelinePage />} />
        <Route path="pipeline/leads/:leadId" element={<PipelinePage />} />
        <Route path="intelligence" element={<IntelligencePage />} />
        <Route path="intelligence/battle-cards/:competitorId" element={<IntelligencePage />} />
        <Route path="communications" element={<CommunicationsPage />} />
        <Route path="communications/drafts/:draftId" element={<CommunicationsPage />} />
        <Route path="actions" element={<ActionsPage />} />
        <Route path="actions/goals/:goalId" element={<ActionsPage />} />
        <Route path="settings" element={<SettingsPage />} />
        <Route path="settings/:section" element={<SettingsPage />} />
      </Route>

      {/* Fallback */}
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}
