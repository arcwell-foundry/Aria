/**
 * IntelPanel - ARIA Intelligence Panel (right column)
 *
 * The context-adaptive right panel in ARIA's three-column layout.
 * Renders route-specific modules with realistic intelligence data.
 * Supports ARIA-driven content overrides via update_intel_panel UICommand.
 * Width: 320px (w-80). Visibility controlled by parent (AppShell).
 *
 * Design System:
 * - Background: var(--bg-elevated)
 * - Left border: 1px solid var(--border)
 * - Title: Instrument Serif (font-display)
 * - Body: Satoshi/Inter (font-sans)
 * - Data labels: JetBrains Mono (font-mono)
 */

import { useMemo, type ReactNode } from 'react';
import { useLocation } from 'react-router-dom';
import { MoreHorizontal } from 'lucide-react';
import { useIntelPanel } from '@/hooks/useIntelPanel';
import {
  AlertsModule,
  BuyingSignalsModule,
  CompetitiveIntelModule,
  NewsAlertsModule,
  WhyIWroteThisModule,
  ToneModule,
  AnalysisModule,
  NextBestActionModule,
  StrategicAdviceModule,
  ObjectionsModule,
  NextStepsModule,
  AgentStatusModule,
  CRMSnapshotModule,
  ChatInputModule,
  SuggestedRefinementsModule,
  JarvisInsightsModule,
  TerritoryForecastModule,
  StakeholderMapModule,
  DocumentIntelModule,
  PendingApprovalsModule,
} from '@/components/shell/intel-modules';

interface IntelPanelProps {
  /** Additional CSS classes from parent for positioning */
  className?: string;
}

interface PanelConfig {
  title: string;
  modules: ReactNode[];
  chatContext?: string;
}

function getPanelConfig(pathname: string): PanelConfig {
  // Lead detail view (e.g., /pipeline/leads/abc-123)
  if (/^\/pipeline\/leads\/.+/.test(pathname)) {
    return {
      title: 'Lead Intelligence',
      modules: [
        <StrategicAdviceModule key="advice" />,
        <StakeholderMapModule key="stakeholders" />,
        <ObjectionsModule key="objections" />,
        <NextStepsModule key="steps" />,
        <CRMSnapshotModule key="crm" />,
      ],
      chatContext: 'lead-detail',
    };
  }

  // Draft detail view (e.g., /communications/drafts/abc-123)
  if (/^\/communications\/drafts\/.+/.test(pathname)) {
    return {
      title: 'ARIA Insights',
      modules: [
        <WhyIWroteThisModule key="why" />,
        <ToneModule key="tone" />,
        <AnalysisModule key="analysis" />,
        <NextBestActionModule key="action" />,
        <SuggestedRefinementsModule key="refinements" />,
      ],
      chatContext: 'draft-detail',
    };
  }

  if (pathname.startsWith('/pipeline')) {
    return {
      title: 'Pipeline Alerts',
      modules: [
        <TerritoryForecastModule key="forecast" />,
        <AlertsModule key="alerts" />,
        <BuyingSignalsModule key="signals" />,
        <StakeholderMapModule key="stakeholders" />,
        <CRMSnapshotModule key="crm" />,
      ],
      chatContext: 'pipeline',
    };
  }

  if (pathname.startsWith('/intelligence')) {
    return {
      title: 'ARIA Intel',
      modules: [
        <JarvisInsightsModule key="jarvis" />,
        <CompetitiveIntelModule key="competitive" />,
        <NewsAlertsModule key="news" />,
        <DocumentIntelModule key="documents" />,
        <NextBestActionModule key="action" />,
      ],
      chatContext: 'intelligence',
    };
  }

  if (pathname.startsWith('/communications')) {
    return {
      title: 'ARIA Insights',
      modules: [
        <WhyIWroteThisModule key="why" />,
        <ToneModule key="tone" />,
        <AnalysisModule key="analysis" />,
      ],
      chatContext: 'communications',
    };
  }

  if (pathname.startsWith('/actions')) {
    return {
      title: 'Agent Status',
      modules: [
        <PendingApprovalsModule key="pending" />,
        <AgentStatusModule key="agents" />,
        <NextBestActionModule key="action" />,
      ],
      chatContext: 'actions',
    };
  }

  if (pathname.startsWith('/activity')) {
    return {
      title: 'Agent Status',
      modules: [
        <PendingApprovalsModule key="pending" />,
        <AgentStatusModule key="agents" />,
        <NextBestActionModule key="action" />,
      ],
      chatContext: 'activity',
    };
  }

  if (pathname.startsWith('/analytics')) {
    return {
      title: 'ARIA Insights',
      modules: [
        <JarvisInsightsModule key="jarvis" />,
        <NextBestActionModule key="action" />,
      ],
      chatContext: 'analytics',
    };
  }

  // Default: briefing, settings, etc.
  return {
    title: 'ARIA Intelligence',
    modules: [
      <PendingApprovalsModule key="pending" />,
      <JarvisInsightsModule key="jarvis" />,
      <AlertsModule key="alerts" />,
      <DocumentIntelModule key="documents" />,
      <NextBestActionModule key="action" />,
    ],
    chatContext: 'general',
  };
}

export function IntelPanel({ className }: IntelPanelProps) {
  const location = useLocation();
  const { state: panelState } = useIntelPanel();

  const config = useMemo(
    () => getPanelConfig(location.pathname),
    [location.pathname],
  );

  const title = panelState.titleOverride || config.title;

  return (
    <aside
      className={`w-80 flex-shrink-0 flex flex-col h-full border-l ${className ?? ''}`}
      style={{
        borderColor: 'var(--border)',
        backgroundColor: 'var(--bg-elevated)',
      }}
      data-aria-id="intel-panel"
    >
      {/* Header */}
      <div
        className="h-14 flex items-center justify-between px-5 flex-shrink-0 border-b"
        style={{ borderColor: 'var(--border)' }}
      >
        <h2
          className="font-display text-[18px] leading-tight italic"
          style={{ color: 'var(--text-primary)' }}
        >
          {title}
        </h2>
        <button
          className="p-1.5 rounded-md transition-colors duration-150 cursor-pointer"
          style={{ color: 'var(--text-secondary)' }}
          onMouseEnter={(e) => {
            e.currentTarget.style.backgroundColor = 'var(--bg-subtle)';
          }}
          onMouseLeave={(e) => {
            e.currentTarget.style.backgroundColor = 'transparent';
          }}
          aria-label="Panel options"
        >
          <MoreHorizontal size={18} strokeWidth={1.5} />
        </button>
      </div>

      {/* Scrollable Content */}
      <div className="flex-1 overflow-y-auto px-5 py-4">
        {/* Route-based modules */}
        <div className="space-y-6">
          {config.modules}
        </div>

        {/* Timestamp */}
        <p
          className="font-mono text-[11px] mt-6"
          style={{ color: 'var(--text-secondary)' }}
        >
          Last updated: just now
        </p>

        {/* Contextual chat input */}
        <ChatInputModule context={config.chatContext} />
      </div>
    </aside>
  );
}
