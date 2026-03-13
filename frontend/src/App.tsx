import { useState, useCallback, useEffect } from "react";
import { BrowserRouter, useNavigate } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { AuthProvider } from "@/contexts/AuthContext";
import { ThemeProvider } from "@/contexts/ThemeContext";
import { SessionProvider } from "@/contexts/SessionContext";
import { IntelPanelProvider } from "@/contexts/IntelPanelContext";
import { ErrorBoundary } from "@/components/ErrorBoundary";
import { OfflineBanner } from "@/components/OfflineBanner";
import { ServiceHealthBanner } from "@/components/ServiceHealthBanner";
import { IntegrationReconnectBanner } from "@/components/IntegrationReconnectBanner";
import { ErrorToaster } from "@/components/ErrorToaster";
import { Toaster } from "sonner";
import { useServiceHealth } from "@/hooks/useServiceHealth";
import { CommandPalette } from "@/components/common/CommandPalette";
import { useKeyboardShortcuts } from "@/hooks/useKeyboardShortcuts";
import { useAuth } from "@/hooks/useAuth";
import { AppRoutes } from "@/app/routes";
import { ThesysProvider } from "@/contexts/ThesysContext";
import { useThesysStore } from "@/stores/thesysStore";
import { apiClient } from "@/api/client";
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

function AppContent() {
  const navigate = useNavigate();
  const { isAuthenticated } = useAuth();
  const serviceHealth = useServiceHealth(isAuthenticated);
  const thesysEnabled = useThesysStore((s) => s.enabled);
  const [isCommandPaletteOpen, setIsCommandPaletteOpen] = useState(false);
  const [searchResults, setSearchResults] = useState<SearchResult[]>([]);
  const [recentItems, setRecentItems] = useState<RecentItem[]>([]);

  // Warm backend connection pool on first load (no auth needed)
  useEffect(() => {
    const apiUrl = import.meta.env.VITE_API_URL || 'http://localhost:8000';
    fetch(`${apiUrl}/api/v1/briefings/ping`).catch(() => {});
  }, []);

  useEffect(() => {
    if (!isAuthenticated) return;
    getRecentItems().then(setRecentItems).catch(() => setRecentItems([]));
  }, [isAuthenticated]);

  // Fetch Thesys feature flag after authentication
  useEffect(() => {
    if (!isAuthenticated) return;
    apiClient.get('/config/features')
      .then((res) => useThesysStore.getState().setEnabled(res.data.thesys_enabled))
      .catch(() => {}); // Default: disabled
  }, [isAuthenticated]);

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

  useKeyboardShortcuts({
    onCommandPalette: () => setIsCommandPaletteOpen(true),
    onNavigate: (path) => navigate(path),
    onCloseOverlay: () => setIsCommandPaletteOpen(false),
    isEnabled: true,
  });

  return (
    <>
      <ServiceHealthBanner health={serviceHealth} />
      <IntegrationReconnectBanner isAuthenticated={isAuthenticated} />
      <ThesysProvider enabled={thesysEnabled}>
        <ThemeProvider>
          <SessionProvider isAuthenticated={isAuthenticated}>
            <IntelPanelProvider>
              <AppRoutes />
            </IntelPanelProvider>
          </SessionProvider>
        </ThemeProvider>
      </ThesysProvider>

      <CommandPalette
        isOpen={isCommandPaletteOpen}
        onClose={() => setIsCommandPaletteOpen(false)}
        onSearch={handleSearch}
        recentItems={recentItems}
        searchResults={searchResults}
      />
      <Toaster position="top-right" richColors />
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
