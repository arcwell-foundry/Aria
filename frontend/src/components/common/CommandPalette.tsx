/**
 * CommandPalette - Global command palette (Cmd+K / Ctrl+K).
 *
 * Provides:
 * - Full-screen overlay with backdrop blur
 * - DARK SURFACE styling
 * - Search input with auto-focus
 * - Recent items display when no search query
 * - Search results grouped by type
 * - Keyboard navigation (arrows + Enter)
 * - Esc to close
 *
 * Following ARIA Design System v1.0
 */

import { useEffect, useRef, useState, useCallback } from 'react';
import { Search, FileText, Target, MessageSquare, Building2, Briefcase } from 'lucide-react';
import { useNavigate } from 'react-router-dom';
import type { SearchResult, RecentItem } from '@/api/search';

export interface CommandPaletteProps {
  isOpen: boolean;
  onClose: () => void;
  onSearch: (query: string) => void;
  recentItems: RecentItem[];
  searchResults: SearchResult[];
}

// Type to icon mapping
const TYPE_ICONS: Record<string, React.ElementType> = {
  lead: Building2,
  goal: Target,
  conversation: MessageSquare,
  document: FileText,
  briefing: Briefcase,
  memory: FileText,
  signal: FileText,
};

// Type to display name mapping
const TYPE_LABELS: Record<string, string> = {
  lead: 'Leads',
  goals: 'Goals',
  conversation: 'Conversations',
  document: 'Documents',
  briefing: 'Briefings',
  memory: 'Memory',
  signals: 'Signals',
};

export function CommandPalette({
  isOpen,
  onClose,
  onSearch,
  recentItems,
  searchResults,
}: CommandPaletteProps) {
  const navigate = useNavigate();
  const searchInputRef = useRef<HTMLInputElement>(null);
  const [query, setQuery] = useState('');
  const [selectedIndex, setSelectedIndex] = useState(0);

  /* eslint-disable react-hooks/set-state-in-effect */
  // Focus input when opened, reset state when closing
  useEffect(() => {
    if (isOpen) {
      setTimeout(() => searchInputRef.current?.focus(), 100);
    } else {
      // Reset state when closing to ensure clean state on next open
      // This is intentional - we want synchronous reset when palette closes
      setQuery('');
      setSelectedIndex(0);
    }
  }, [isOpen]);
  /* eslint-enable react-hooks/set-state-in-effect */

  // Handle keyboard navigation
  const handleKeyDown = useCallback(
    (e: React.KeyboardEvent<HTMLInputElement>) => {
      if (e.key === 'Escape') {
        onClose();
        return;
      }

      if (e.key === 'ArrowDown') {
        e.preventDefault();
        const items = query ? searchResults : recentItems;
        setSelectedIndex((prev) => (prev + 1) % items.length);
      }

      if (e.key === 'ArrowUp') {
        e.preventDefault();
        const items = query ? searchResults : recentItems;
        setSelectedIndex((prev) => (prev - 1 + items.length) % items.length);
      }

      if (e.key === 'Enter') {
        e.preventDefault();
        const items = query ? searchResults : recentItems;
        const selected = items[selectedIndex];
        if (selected) {
          navigate(selected.url);
          onClose();
        }
      }
    },
    [query, searchResults, recentItems, selectedIndex, onClose, navigate]
  );

  // Handle search input change
  const handleSearchChange = useCallback(
    (e: React.ChangeEvent<HTMLInputElement>) => {
      const value = e.target.value;
      setQuery(value);
      setSelectedIndex(0);
      onSearch(value);
    },
    [onSearch]
  );

  // Get icon for type
  const getTypeIcon = (type: string) => TYPE_ICONS[type] || FileText;

  // Group results by type
  const groupResults = (results: SearchResult[] | RecentItem[]) => {
    const groups: Record<string, (SearchResult | RecentItem)[]> = {};
    results.forEach((item) => {
      if (!groups[item.type]) {
        groups[item.type] = [];
      }
      groups[item.type].push(item);
    });
    return groups;
  };

  // Render item
  const renderItem = (item: SearchResult | RecentItem, index: number) => {
    const Icon = getTypeIcon(item.type);
    const isSelected = index === selectedIndex;
    const snippet = 'snippet' in item ? item.snippet : '';

    return (
      <button
        key={`${item.type}-${item.id}`}
        onClick={() => {
          navigate(item.url);
          onClose();
        }}
        className={`
          w-full text-left px-4 py-3 flex items-center gap-3 transition-colors duration-150
          ${isSelected ? 'bg-surface-hover' : 'hover:bg-surface-hover'}
          focus:outline-none focus:bg-surface-hover
        `}
      >
        <div className="text-secondary shrink-0">
          <Icon size={20} strokeWidth={1.5} />
        </div>
        <div className="flex-1 min-w-0">
          <div className="text-primary font-medium truncate">{item.title}</div>
          {snippet && (
            <div className="text-secondary text-caption truncate">{snippet}</div>
          )}
        </div>
      </button>
    );
  };

  // Render result section
  const renderSection = (type: string, sectionItems: (SearchResult | RecentItem)[]) => {
    const label = TYPE_LABELS[type] || type.charAt(0).toUpperCase() + type.slice(1);
    const Icon = getTypeIcon(type);

    return (
      <div key={type} className="mb-4">
        <div className="flex items-center gap-2 px-4 py-2 text-secondary text-caption uppercase tracking-wide">
          <Icon size={14} strokeWidth={1.5} />
          {label}
        </div>
        <div>{sectionItems.map((item, index) => renderItem(item, index))}</div>
      </div>
    );
  };

  if (!isOpen) return null;

  const items = query ? searchResults : recentItems;
  const groupedItems = groupResults(items);
  const hasResults = items.length > 0;

  return (
    <div
      className="fixed inset-0 z-50 flex items-start justify-center pt-[20vh]"
      onClick={onClose}
    >
      {/* Backdrop */}
      <div className="absolute inset-0 bg-black/50 backdrop-blur-sm" />

      {/* Command Palette */}
      <div
        className="relative w-full max-w-2xl mx-4 bg-elevated rounded-lg shadow-2xl border border-border"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Search Input */}
        <div className="flex items-center gap-3 px-4 py-4 border-b border-border">
          <Search size={20} className="text-secondary shrink-0" strokeWidth={1.5} />
          <input
            ref={searchInputRef}
            type="text"
            value={query}
            onChange={handleSearchChange}
            onKeyDown={handleKeyDown}
            placeholder="Search leads, goals, documents..."
            className="flex-1 bg-transparent border-none outline-none text-primary placeholder:text-secondary text-body"
            role="combobox"
            aria-autocomplete="list"
            tabIndex={0}
          />
          <div className="text-secondary text-caption">ESC</div>
        </div>

        {/* Results */}
        <div className="max-h-[50vh] overflow-y-auto py-2">
          {hasResults ? (
            Object.entries(groupedItems).map(([type, groupItems]) =>
              renderSection(type, groupItems)
            )
          ) : (
            <div className="px-4 py-8 text-center">
              {query ? (
                <>
                  <p className="text-secondary text-body mb-2">No results found</p>
                  <p className="text-secondary text-caption">
                    Try different keywords or ask ARIA directly
                  </p>
                </>
              ) : (
                <div className="text-secondary text-body">
                  No recent items
                </div>
              )}
            </div>
          )}
        </div>

        {/* Footer hint */}
        <div className="px-4 py-2 border-t border-border flex items-center justify-between text-secondary text-caption">
          <div className="flex items-center gap-4">
            <span className="flex items-center gap-1">
              <kbd className="px-1.5 py-0.5 bg-subtle rounded text-xs">&#8593;&#8595;</kbd>
              <span>Navigate</span>
            </span>
            <span className="flex items-center gap-1">
              <kbd className="px-1.5 py-0.5 bg-subtle rounded text-xs">&#8629;</kbd>
              <span>Select</span>
            </span>
          </div>
          <span className="flex items-center gap-1">
            <kbd className="px-1.5 py-0.5 bg-subtle rounded text-xs">ESC</kbd>
            <span>Close</span>
          </span>
        </div>
      </div>
    </div>
  );
}
