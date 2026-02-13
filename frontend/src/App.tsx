import { useState, useCallback, useEffect } from "react";
import { BrowserRouter, useNavigate } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { AuthProvider } from "@/contexts/AuthContext";
import { ThemeProvider } from "@/contexts/ThemeContext";
import { SessionProvider } from "@/contexts/SessionContext";
import { IntelPanelProvider } from "@/contexts/IntelPanelContext";
import { ErrorBoundary } from "@/components/ErrorBoundary";
import { OfflineBanner } from "@/components/OfflineBanner";
import { ErrorToaster } from "@/components/ErrorToaster";
import { CommandPalette } from "@/components/common/CommandPalette";
import { useKeyboardShortcuts } from "@/hooks/useKeyboardShortcuts";
import { useAuth } from "@/hooks/useAuth";
import { AppRoutes } from "@/app/routes";
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
  const [isCommandPaletteOpen, setIsCommandPaletteOpen] = useState(false);
  const [searchResults, setSearchResults] = useState<SearchResult[]>([]);
  const [recentItems, setRecentItems] = useState<RecentItem[]>([]);

  useEffect(() => {
    if (!isAuthenticated) return;
    getRecentItems().then(setRecentItems).catch(() => setRecentItems([]));
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
      <ThemeProvider>
        <SessionProvider isAuthenticated={isAuthenticated}>
          <IntelPanelProvider>
            <AppRoutes />
          </IntelPanelProvider>
        </SessionProvider>
      </ThemeProvider>

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
