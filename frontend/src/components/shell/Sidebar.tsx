/**
 * Sidebar - Primary navigation for ARIA
 *
 * Always rendered in dark theme regardless of active page context.
 * 240px fixed width. Seven navigation items with ARIA as the default.
 * Supports badge counts and a live pulse indicator for ARIA status.
 *
 * Navigation is dual-controlled: the user clicks sidebar items, and ARIA
 * can navigate programmatically via ui_commands[]. Both paths converge
 * through the navigation store.
 */

import { useEffect, useMemo, useCallback } from 'react';
import { useNavigate, useLocation } from 'react-router-dom';
import {
  AudioLines,
  Calendar,
  Users,
  Shield,
  Mail,
  Zap,
  Settings,
} from 'lucide-react';
import {
  useNavigationStore,
  type SidebarItem,
  type NavigationState,
} from '@/stores/navigationStore';
import { useAuth } from '@/hooks/useAuth';
import { Avatar } from '@/components/primitives/Avatar';

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

interface NavEntry {
  key: SidebarItem;
  label: string;
  icon: React.ComponentType<{ className?: string }>;
  route: string;
}

export interface SidebarProps {
  /** Optional badge counts keyed by sidebar item */
  badges?: Partial<Record<SidebarItem, number>>;
  /** Whether the ARIA system is actively connected / processing */
  isARIAActive?: boolean;
}

// ---------------------------------------------------------------------------
// Navigation definitions
// ---------------------------------------------------------------------------

const PRIMARY_NAV: NavEntry[] = [
  { key: 'aria', label: 'ARIA', icon: AudioLines, route: '/' },
  { key: 'briefing', label: 'Briefing', icon: Calendar, route: '/briefing' },
  { key: 'pipeline', label: 'Pipeline', icon: Users, route: '/pipeline' },
  {
    key: 'intelligence',
    label: 'Intelligence',
    icon: Shield,
    route: '/intelligence',
  },
  {
    key: 'communications',
    label: 'Communications',
    icon: Mail,
    route: '/communications',
  },
  { key: 'actions', label: 'Actions', icon: Zap, route: '/actions' },
];

const SETTINGS_NAV: NavEntry = {
  key: 'settings',
  label: 'Settings',
  icon: Settings,
  route: '/settings',
};

// ---------------------------------------------------------------------------
// Route <-> SidebarItem resolution
// ---------------------------------------------------------------------------

function resolveItemFromPath(pathname: string): SidebarItem {
  // Exact match first, then prefix match for nested routes
  for (const entry of PRIMARY_NAV) {
    if (entry.route === pathname) return entry.key;
  }
  if (pathname === SETTINGS_NAV.route || pathname.startsWith('/settings')) {
    return 'settings';
  }
  for (const entry of [...PRIMARY_NAV].reverse()) {
    if (entry.route !== '/' && pathname.startsWith(entry.route)) {
      return entry.key;
    }
  }
  return 'aria';
}

// ---------------------------------------------------------------------------
// Sub-components
// ---------------------------------------------------------------------------

function NavItem({
  entry,
  isActive,
  badge,
  onClick,
}: {
  entry: NavEntry;
  isActive: boolean;
  badge?: number;
  onClick: () => void;
}) {
  const Icon = entry.icon;

  return (
    <button
      type="button"
      onClick={onClick}
      data-aria-id={`sidebar-${entry.key}`}
      className={`
        flex items-center gap-3 w-full px-3 py-2.5 rounded-lg text-sm font-medium
        transition-colors duration-150 relative group
        ${
          isActive
            ? 'bg-[#2E66FF] text-white'
            : 'text-[#8B92A5] hover:bg-[rgba(46,102,255,0.08)] hover:text-[#C4C9D9]'
        }
      `}
    >
      <Icon className="w-5 h-5 shrink-0" />
      <span className="truncate">{entry.label}</span>

      {badge !== undefined && badge > 0 && (
        <span
          className={`
            ml-auto bg-[#A66B6B] text-white text-[10px] font-mono
            min-w-[18px] h-[18px] rounded-full
            flex items-center justify-center px-1 leading-none
          `}
        >
          {badge > 99 ? '99+' : badge}
        </span>
      )}
    </button>
  );
}

// ---------------------------------------------------------------------------
// Sidebar
// ---------------------------------------------------------------------------

export function Sidebar({ badges = {}, isARIAActive = true }: SidebarProps) {
  const navigate = useNavigate();
  const location = useLocation();
  const { user } = useAuth();

  const activeSidebarItem = useNavigationStore((s: NavigationState) => s.activeSidebarItem);
  const setActiveSidebarItem = useNavigationStore(
    (s: NavigationState) => s.setActiveSidebarItem,
  );
  const setCurrentRoute = useNavigationStore((s: NavigationState) => s.setCurrentRoute);

  // Keep store in sync with browser location
  useEffect(() => {
    const resolved = resolveItemFromPath(location.pathname);
    if (resolved !== activeSidebarItem) {
      setActiveSidebarItem(resolved);
    }
    setCurrentRoute(location.pathname);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [location.pathname]);

  const handleNav = useCallback(
    (entry: NavEntry) => {
      navigate(entry.route);
      setActiveSidebarItem(entry.key);
      setCurrentRoute(entry.route);
    },
    [navigate, setActiveSidebarItem, setCurrentRoute],
  );

  const displayName = user?.full_name ?? 'User';
  const displayEmail = user?.email ?? '';

  // Memoize the primary nav list to avoid re-renders
  const primaryNavItems = useMemo(
    () =>
      PRIMARY_NAV.map((entry) => (
        <NavItem
          key={entry.key}
          entry={entry}
          isActive={activeSidebarItem === entry.key}
          badge={badges[entry.key]}
          onClick={() => handleNav(entry)}
        />
      )),
    [activeSidebarItem, badges, handleNav],
  );

  return (
    <aside
      data-aria-id="sidebar"
      className="w-60 h-full flex flex-col shrink-0 select-none"
      style={{ backgroundColor: '#0F1117' }}
    >
      {/* ----------------------------------------------------------------- */}
      {/* Logo */}
      {/* ----------------------------------------------------------------- */}
      <div className="flex items-center gap-2 px-5 py-6">
        <span
          className={`text-xl tracking-tight text-[#E8E6E1] italic ${isARIAActive ? 'aria-logo-glow' : ''}`}
          style={{ fontFamily: "'Instrument Serif', Georgia, serif" }}
        >
          ARIA
        </span>
        {isARIAActive && (
          <span className="aria-pulse-dot w-2 h-2 rounded-full bg-[#2E66FF]" />
        )}
      </div>

      {/* ----------------------------------------------------------------- */}
      {/* Primary navigation */}
      {/* ----------------------------------------------------------------- */}
      <nav className="flex flex-col gap-1 px-3">{primaryNavItems}</nav>

      {/* Spacer */}
      <div className="flex-1 min-h-4" />

      {/* ----------------------------------------------------------------- */}
      {/* Settings */}
      {/* ----------------------------------------------------------------- */}
      <div className="px-3 pb-1">
        <div className="border-t border-[#1E2235] mx-1 mb-2" />
        <NavItem
          entry={SETTINGS_NAV}
          isActive={activeSidebarItem === 'settings'}
          badge={badges.settings}
          onClick={() => handleNav(SETTINGS_NAV)}
        />
      </div>

      {/* ----------------------------------------------------------------- */}
      {/* User section */}
      {/* ----------------------------------------------------------------- */}
      <div className="border-t border-[#1E2235]">
        <div className="flex items-center gap-3 px-4 py-4">
          <Avatar name={displayName} size="sm" className="shrink-0" />
          <div className="min-w-0 flex-1">
            <p className="text-sm font-medium text-[#E8E6E1] truncate">
              {displayName}
            </p>
            <p className="text-xs text-[#8B92A5] truncate">{displayEmail}</p>
          </div>
        </div>
      </div>
    </aside>
  );
}
