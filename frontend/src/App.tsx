import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { AuthProvider } from "@/contexts/AuthContext";
import { ProtectedRoute } from "@/components/ProtectedRoute";
import {
  AriaChatPage,
  BattleCardsPage,
  EmailDraftsPage,
  IntegrationsCallbackPage,
  IntegrationsSettingsPage,
  LeadDetailPage,
  LeadsPage,
  LoginPage,
  MeetingBriefPage,
  NotificationsPage,
  PreferencesSettingsPage,
  SignupPage,
  DashboardPage,
  GoalsPage,
  SkillsPage,
} from "@/pages";

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 1000 * 60 * 5, // 5 minutes
      retry: 1,
    },
  },
});

function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <AuthProvider>
          <Routes>
            <Route path="/login" element={<LoginPage />} />
            <Route path="/signup" element={<SignupPage />} />
            <Route
              path="/dashboard"
              element={
                <ProtectedRoute>
                  <DashboardPage />
                </ProtectedRoute>
              }
            />
            <Route
              path="/dashboard/aria"
              element={
                <ProtectedRoute>
                  <AriaChatPage />
                </ProtectedRoute>
              }
            />
            <Route
              path="/goals"
              element={
                <ProtectedRoute>
                  <GoalsPage />
                </ProtectedRoute>
              }
            />
            <Route
              path="/dashboard/leads"
              element={
                <ProtectedRoute>
                  <LeadsPage />
                </ProtectedRoute>
              }
            />
            <Route
              path="/dashboard/leads/:id"
              element={
                <ProtectedRoute>
                  <LeadDetailPage />
                </ProtectedRoute>
              }
            />
            <Route
              path="/dashboard/meetings/:id/brief"
              element={
                <ProtectedRoute>
                  <MeetingBriefPage />
                </ProtectedRoute>
              }
            />
            <Route
              path="/dashboard/battlecards"
              element={
                <ProtectedRoute>
                  <BattleCardsPage />
                </ProtectedRoute>
              }
            />
            <Route
              path="/dashboard/drafts"
              element={
                <ProtectedRoute>
                  <EmailDraftsPage />
                </ProtectedRoute>
              }
            />
            <Route
              path="/dashboard/skills"
              element={
                <ProtectedRoute>
                  <SkillsPage />
                </ProtectedRoute>
              }
            />
            <Route
              path="/settings/integrations"
              element={
                <ProtectedRoute>
                  <IntegrationsSettingsPage />
                </ProtectedRoute>
              }
            />
            <Route
              path="/settings/integrations/callback"
              element={
                <ProtectedRoute>
                  <IntegrationsCallbackPage />
                </ProtectedRoute>
              }
            />
            <Route
              path="/settings/preferences"
              element={
                <ProtectedRoute>
                  <PreferencesSettingsPage />
                </ProtectedRoute>
              }
            />
            <Route
              path="/notifications"
              element={
                <ProtectedRoute>
                  <NotificationsPage />
                </ProtectedRoute>
              }
            />
            <Route path="/" element={<Navigate to="/dashboard" replace />} />
            <Route path="*" element={<Navigate to="/dashboard" replace />} />
          </Routes>
        </AuthProvider>
      </BrowserRouter>
    </QueryClientProvider>
  );
}

export default App;
