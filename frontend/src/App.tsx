import { useState, useCallback, useEffect } from "react";
import { BrowserRouter, Routes, Route, Navigate, useNavigate } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { AuthProvider } from "@/contexts/AuthContext";
import { ProtectedRoute } from "@/components/ProtectedRoute";
import { ErrorBoundary } from "@/components/ErrorBoundary";
import { OfflineBanner } from "@/components/OfflineBanner";
import { ErrorToaster } from "@/components/ErrorToaster";
import { CommandPalette } from "@/components/CommandPalette";
import { useKeyboardShortcuts } from "@/hooks/useKeyboardShortcuts";
import {
  AccountsPage,
  ActionQueuePage,
  AdminAuditLogPage,
  AdminTeamPage,
  AdminBillingPage,
  ARIAConfigPage,
  AriaChatPage,
  BattleCardsPage,
  ChangelogPage,
  EmailDraftsPage,
  HelpPage,
  IntegrationsCallbackPage,
  IntegrationsSettingsPage,
  LeadDetailPage,
  LeadGenPage,
  LeadsPage,
  LoginPage,
  MeetingBriefPage,
  NotificationsPage,
  OnboardingPage,
  PreferencesSettingsPage,
  ROIDashboardPage,
  SignupPage,
  DashboardPage,
  GoalsPage,
  SkillsPage,
  SettingsAccountPage,
  SettingsPrivacyPage,
  SettingsProfilePage,
} from "@/pages";
import { PostAuthRouter } from "@/components/PostAuthRouter";
import type { SearchResult, RecentItem } from "@/api/search";
import { globalSearch, getRecentItems } from "@/api/search";

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 1000 * 60 * 5, // 5 minutes
      retry: 1,
    },
  },
});

// Inner component with router context
function AppContent() {
  const navigate = useNavigate();
  const [isCommandPaletteOpen, setIsCommandPaletteOpen] = useState(false);
  const [searchResults, setSearchResults] = useState<SearchResult[]>([]);
  const [recentItems, setRecentItems] = useState<RecentItem[]>([]);

  // Fetch recent items on mount
  useEffect(() => {
    getRecentItems().then(setRecentItems).catch(() => setRecentItems([]));
  }, []);

  // Handle search
  const handleSearch = useCallback(async (query: string) => {
    if (query.trim()) {
      try {
        const results = await globalSearch({ query, limit: 10 });
        setSearchResults(results);
      } catch {
        setSearchResults([]);
      }
    } else {
      setSearchResults([]);
    }
  }, []);

  // Keyboard shortcuts
  useKeyboardShortcuts({
    onCommandPalette: () => setIsCommandPaletteOpen(true),
    onNavigate: (path) => navigate(path),
    onCloseOverlay: () => setIsCommandPaletteOpen(false),
    isEnabled: true,
  });

  return (
    <>
      <Routes>
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
        path="/accounts"
        element={
          <ProtectedRoute>
            <AccountsPage />
          </ProtectedRoute>
        }
      />
      <Route
        path="/actions"
        element={
          <ProtectedRoute>
            <ActionQueuePage />
          </ProtectedRoute>
        }
      />
      <Route
        path="/leads"
        element={
          <ProtectedRoute>
            <LeadGenPage />
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
        path="/dashboard/roi"
        element={
          <ProtectedRoute>
            <ROIDashboardPage />
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
        path="/settings/aria-config"
        element={
          <ProtectedRoute>
            <ARIAConfigPage />
          </ProtectedRoute>
        }
      />
      <Route
        path="/settings/profile"
        element={
          <ProtectedRoute>
            <SettingsProfilePage />
          </ProtectedRoute>
        }
      />
      <Route
        path="/settings/account"
        element={
          <ProtectedRoute>
            <SettingsAccountPage />
          </ProtectedRoute>
        }
      />
      <Route
        path="/settings/privacy"
        element={
          <ProtectedRoute>
            <SettingsPrivacyPage />
          </ProtectedRoute>
        }
      />
      <Route
        path="/admin/team"
        element={
          <ProtectedRoute>
            <AdminTeamPage />
          </ProtectedRoute>
        }
      />
      <Route
        path="/admin/billing"
        element={
          <ProtectedRoute>
            <AdminBillingPage />
          </ProtectedRoute>
        }
      />
      <Route
        path="/admin/audit-log"
        element={
          <ProtectedRoute>
            <AdminAuditLogPage />
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
      <Route
        path="/help"
        element={
          <ProtectedRoute>
            <HelpPage />
          </ProtectedRoute>
        }
      />
      <Route
        path="/changelog"
        element={
          <ProtectedRoute>
            <ChangelogPage />
          </ProtectedRoute>
        }
      />
      <Route
        path="/"
        element={
          <ProtectedRoute>
            <PostAuthRouter />
          </ProtectedRoute>
        }
      />
      <Route path="*" element={<Navigate to="/dashboard" replace />} />
      </Routes>

      <CommandPalette
        isOpen={isCommandPaletteOpen}
        onClose={() => setIsCommandPaletteOpen(false)}
        onSearch={handleSearch}
        recentItems={recentItems}
        searchResults={searchResults}
      />
    </>
  );
}

function App() {
  return (
    <ErrorBoundary>
      <OfflineBanner />
      <ErrorToaster />
      <QueryClientProvider client={queryClient}>
        <BrowserRouter>
          <AuthProvider>
            <AppContent />
          </AuthProvider>
        </BrowserRouter>
      </QueryClientProvider>
    </ErrorBoundary>
  );
}

export default App;
