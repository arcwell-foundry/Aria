/**
 * BattleCardModal - Full competitive dossier modal
 *
 * Opens when clicking a BattleCardPreview. Shows all competitive intelligence
 * data for a single competitor in a rich modal overlay. Data sourced from
 * existing battle card API + V2 detail endpoint + filtered signals/insights.
 */

import { useState, useEffect, useCallback } from 'react';
import {
  X,
  ArrowUp,
  ArrowDown,
  ArrowRight,
  Activity,
  Shield,
  DollarSign,
  FlaskConical,
  FileText,
  UserCog,
  TrendingUp,
  Handshake,
  Scale,
  Package,
  Users,
  ChevronDown,
  ChevronUp,
  Copy,
  Check,
  Zap,
  ExternalLink,
} from 'lucide-react';
import { useBattleCard } from '@/hooks/useBattleCards';
import { useSignals } from '@/hooks/useIntelPanelData';
import { useIntelligenceInsights } from '@/hooks/useIntelPanelData';
import { sanitizeSignalText } from '@/utils/sanitizeSignalText';
import type { BattleCardObjectionHandler } from '@/api/battleCards';

interface BattleCardModalProps {
  competitorName: string;
  onClose: () => void;
}

// Signal type config for badges
const SIGNAL_TYPE_MAP: Record<string, { label: string; icon: React.ComponentType<{ className?: string; style?: React.CSSProperties }>; color: string }> = {
  funding: { label: 'Funding', icon: DollarSign, color: '#22c55e' },
  fda_approval: { label: 'FDA', icon: Shield, color: '#3b82f6' },
  clinical_trial: { label: 'Clinical Trial', icon: FlaskConical, color: '#a855f7' },
  patent: { label: 'Patent', icon: FileText, color: '#f59e0b' },
  leadership: { label: 'Leadership', icon: UserCog, color: '#64748b' },
  earnings: { label: 'Earnings', icon: TrendingUp, color: '#10b981' },
  partnership: { label: 'Partnership', icon: Handshake, color: '#6366f1' },
  regulatory: { label: 'Regulatory', icon: Scale, color: '#f97316' },
  product: { label: 'Product', icon: Package, color: '#06b6d4' },
  hiring: { label: 'Hiring', icon: Users, color: '#ec4899' },
};

const THREAT_COLORS = {
  high: '#EF4444',
  medium: '#F59E0B',
  low: '#22C55E',
} as const;

const MOMENTUM_CONFIG = {
  increasing: { icon: ArrowUp, color: '#22C55E', label: 'Increasing' },
  declining: { icon: ArrowDown, color: '#EF4444', label: 'Declining' },
  stable: { icon: ArrowRight, color: '#94A3B8', label: 'Stable' },
} as const;

function formatRelativeDate(dateStr: string): string {
  const date = new Date(dateStr);
  const now = new Date();
  const diffMs = now.getTime() - date.getTime();
  const diffDays = Math.floor(diffMs / (1000 * 60 * 60 * 24));
  if (diffDays === 0) return 'Today';
  if (diffDays === 1) return '1d ago';
  if (diffDays < 7) return `${diffDays}d ago`;
  if (diffDays < 30) return `${Math.floor(diffDays / 7)}w ago`;
  return date.toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
}

function SignalTypeBadge({ type }: { type: string }) {
  const config = SIGNAL_TYPE_MAP[type] ?? { label: type, icon: TrendingUp, color: '#94A3B8' };
  const Icon = config.icon;
  return (
    <span
      className="inline-flex items-center gap-1 px-1.5 py-0.5 rounded text-[10px] font-medium uppercase tracking-wide"
      style={{ backgroundColor: `${config.color}15`, color: config.color }}
    >
      <Icon className="w-3 h-3" />
      {config.label}
    </span>
  );
}

function ObjectionAccordion({ handler }: { handler: BattleCardObjectionHandler }) {
  const [open, setOpen] = useState(false);
  const [copied, setCopied] = useState(false);

  const handleCopy = (e: React.MouseEvent) => {
    e.stopPropagation();
    navigator.clipboard.writeText(handler.response);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  return (
    <div
      className="rounded-lg border"
      style={{ borderColor: '#E2E8F0', backgroundColor: '#FAFBFC' }}
    >
      <button
        onClick={() => setOpen(!open)}
        className="w-full flex items-center justify-between p-3 text-left"
      >
        <span className="text-sm font-medium" style={{ color: '#1E293B' }}>
          &ldquo;{handler.objection}&rdquo;
        </span>
        {open ? (
          <ChevronUp className="w-4 h-4 flex-shrink-0 ml-2" style={{ color: '#94A3B8' }} />
        ) : (
          <ChevronDown className="w-4 h-4 flex-shrink-0 ml-2" style={{ color: '#94A3B8' }} />
        )}
      </button>
      {open && (
        <div className="px-3 pb-3" style={{ borderTop: '1px solid #F1F5F9' }}>
          <p className="text-sm leading-relaxed mt-2" style={{ color: '#5B6E8A' }}>
            {handler.response}
          </p>
          <button
            onClick={handleCopy}
            className="inline-flex items-center gap-1 mt-2 text-[11px] font-medium px-2 py-1 rounded-md transition-colors"
            style={{
              color: copied ? '#16A34A' : 'var(--accent, #2E66FF)',
              backgroundColor: copied ? '#DCFCE710' : '#2E66FF10',
            }}
          >
            {copied ? <Check className="w-3 h-3" /> : <Copy className="w-3 h-3" />}
            {copied ? 'Copied' : 'Copy response'}
          </button>
        </div>
      )}
    </div>
  );
}

export function BattleCardModal({ competitorName, onClose }: BattleCardModalProps) {
  const { data: card, isLoading } = useBattleCard(competitorName);
  const { data: signals } = useSignals({ company: competitorName, limit: 20 });
  const { data: allInsights } = useIntelligenceInsights({ limit: 20 });

  // Filter insights to this competitor
  const competitorInsights = (allInsights ?? []).filter((insight) => {
    const content = (insight.content ?? '').toLowerCase();
    const trigger = (insight.trigger_event ?? '').toLowerCase();
    const name = competitorName.toLowerCase();
    return content.includes(name) || trigger.includes(name);
  });

  // Close on Escape
  const handleKeyDown = useCallback((e: KeyboardEvent) => {
    if (e.key === 'Escape') onClose();
  }, [onClose]);

  useEffect(() => {
    document.addEventListener('keydown', handleKeyDown);
    document.body.style.overflow = 'hidden';
    return () => {
      document.removeEventListener('keydown', handleKeyDown);
      document.body.style.overflow = '';
    };
  }, [handleKeyDown]);

  const analysis = card?.analysis;
  const threatLevel = analysis?.threat_level;
  const momentum = analysis?.momentum;
  const signalCount30d = analysis?.signal_count_30d;
  const lastSignalAt = analysis?.last_signal_at;
  const threatColor = threatLevel ? THREAT_COLORS[threatLevel] : '#94A3B8';
  const momentumConfig = momentum ? MOMENTUM_CONFIG[momentum] : null;

  const recentSignals = (card?.recent_signals ?? signals ?? [])
    .filter((s) => !(s as { dismissed_at?: string }).dismissed_at)
    .slice(0, 10);

  const howWeWin: string[] = card?.differentiation?.length
    ? card.differentiation.map((d) => {
        if (typeof d === 'string') return d;
        return d.our_advantage || '';
      }).filter(Boolean)
    : [];

  const productMatchups = analysis?.feature_gaps ?? [];

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center"
      style={{ backgroundColor: 'rgba(0, 0, 0, 0.5)', backdropFilter: 'blur(4px)' }}
      onClick={(e) => {
        if (e.target === e.currentTarget) onClose();
      }}
    >
      <div
        className="relative w-full max-w-3xl max-h-[90vh] overflow-hidden rounded-2xl border flex flex-col"
        style={{
          backgroundColor: '#FFFFFF',
          borderColor: '#E2E8F0',
          boxShadow: '0 25px 50px -12px rgba(0, 0, 0, 0.25)',
        }}
      >
        {/* Header */}
        <div
          className="flex items-start justify-between p-6 pb-4 flex-shrink-0"
          style={{ borderBottom: '1px solid #F1F5F9' }}
        >
          <div>
            <h2
              className="text-xl font-semibold"
              style={{ color: '#1E293B', fontFamily: 'var(--font-display, system-ui)' }}
            >
              {competitorName}
            </h2>
            {card?.overview && (
              <p className="text-sm mt-1" style={{ color: '#5B6E8A' }}>
                {card.overview}
              </p>
            )}
          </div>
          <button
            onClick={onClose}
            className="p-2 rounded-lg hover:bg-gray-100 transition-colors flex-shrink-0"
            aria-label="Close"
          >
            <X className="w-5 h-5" style={{ color: '#94A3B8' }} />
          </button>
        </div>

        {/* Scrollable content */}
        <div className="flex-1 overflow-y-auto p-6 space-y-6">
          {isLoading ? (
            <div className="space-y-4 animate-pulse">
              <div className="h-20 rounded-lg" style={{ backgroundColor: '#F1F5F9' }} />
              <div className="h-32 rounded-lg" style={{ backgroundColor: '#F1F5F9' }} />
              <div className="h-24 rounded-lg" style={{ backgroundColor: '#F1F5F9' }} />
            </div>
          ) : card ? (
            <>
              {/* Threat + Momentum bar */}
              <div
                className="flex items-center gap-4 p-4 rounded-xl"
                style={{ backgroundColor: '#F8FAFC', border: '1px solid #E2E8F0' }}
              >
                {/* Threat level */}
                <div className="flex items-center gap-2">
                  <span
                    className="w-3 h-3 rounded-full"
                    style={{ backgroundColor: threatColor, boxShadow: `0 0 8px ${threatColor}40` }}
                  />
                  <span className="text-sm font-semibold" style={{ color: '#1E293B' }}>
                    Threat Level: {threatLevel ? threatLevel.charAt(0).toUpperCase() + threatLevel.slice(1) : 'Unknown'}
                  </span>
                  {momentumConfig && (
                    <span
                      className="inline-flex items-center gap-1 text-xs font-medium ml-1"
                      style={{ color: momentumConfig.color }}
                    >
                      (<momentumConfig.icon className="w-3 h-3" />
                      {momentumConfig.label})
                    </span>
                  )}
                </div>
                <span className="text-sm" style={{ color: '#5B6E8A' }}>|</span>
                <span className="text-sm" style={{ color: '#5B6E8A' }}>
                  <Activity className="w-3.5 h-3.5 inline mr-1" />
                  {signalCount30d ?? 0} signals / 30d
                </span>
                {lastSignalAt && (
                  <>
                    <span className="text-sm" style={{ color: '#5B6E8A' }}>|</span>
                    <span className="text-sm" style={{ color: '#94A3B8' }}>
                      Last: {formatRelativeDate(lastSignalAt)}
                    </span>
                  </>
                )}
              </div>

              {/* Competitive Positioning */}
              <section>
                <h3
                  className="text-xs font-semibold uppercase tracking-widest mb-3 flex items-center gap-2"
                  style={{ color: '#94A3B8' }}
                >
                  <span className="h-px flex-1" style={{ backgroundColor: '#E2E8F0' }} />
                  Competitive Positioning
                  <span className="h-px flex-1" style={{ backgroundColor: '#E2E8F0' }} />
                </h3>

                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                  {/* How We Win */}
                  {howWeWin.length > 0 && (
                    <div className="rounded-lg p-4" style={{ backgroundColor: '#F0FDF4', border: '1px solid #BBF7D0' }}>
                      <h4 className="text-xs font-semibold uppercase tracking-wider mb-2" style={{ color: '#166534' }}>
                        How We Win
                      </h4>
                      <ul className="space-y-1.5">
                        {howWeWin.map((item, i) => (
                          <li key={i} className="text-sm" style={{ color: '#15803D' }}>
                            <span className="mr-1.5" style={{ color: '#22C55E' }}>&#9679;</span>
                            {item}
                          </li>
                        ))}
                      </ul>
                    </div>
                  )}

                  {/* Their Weaknesses */}
                  {card.weaknesses && card.weaknesses.length > 0 && (
                    <div className="rounded-lg p-4" style={{ backgroundColor: '#FEF2F2', border: '1px solid #FECACA' }}>
                      <h4 className="text-xs font-semibold uppercase tracking-wider mb-2" style={{ color: '#991B1B' }}>
                        Their Weaknesses
                      </h4>
                      <ul className="space-y-1.5">
                        {card.weaknesses.map((item, i) => (
                          <li key={i} className="text-sm" style={{ color: '#B91C1C' }}>
                            <span className="mr-1.5" style={{ color: '#EF4444' }}>&#9679;</span>
                            {item}
                          </li>
                        ))}
                      </ul>
                    </div>
                  )}
                </div>

                {/* Pricing */}
                {card.pricing && (card.pricing.range || card.pricing.strategy) && (
                  <div
                    className="mt-4 rounded-lg p-4 flex items-center gap-6"
                    style={{ backgroundColor: '#F8FAFC', border: '1px solid #E2E8F0' }}
                  >
                    <DollarSign className="w-5 h-5 flex-shrink-0" style={{ color: '#5B6E8A' }} />
                    <div>
                      {card.pricing.range && (
                        <span className="text-sm font-medium" style={{ color: '#1E293B' }}>
                          Their Pricing: {card.pricing.range}
                        </span>
                      )}
                      {card.pricing.strategy && (
                        <p className="text-xs mt-0.5" style={{ color: '#5B6E8A' }}>
                          Strategy: {card.pricing.strategy}
                        </p>
                      )}
                      {card.pricing.notes && (
                        <p className="text-xs mt-0.5" style={{ color: '#94A3B8' }}>
                          {card.pricing.notes}
                        </p>
                      )}
                    </div>
                  </div>
                )}
              </section>

              {/* Product Matchups */}
              {productMatchups.length > 0 && (
                <section>
                  <h3
                    className="text-xs font-semibold uppercase tracking-widest mb-3 flex items-center gap-2"
                    style={{ color: '#94A3B8' }}
                  >
                    <span className="h-px flex-1" style={{ backgroundColor: '#E2E8F0' }} />
                    Product Matchups
                    <span className="h-px flex-1" style={{ backgroundColor: '#E2E8F0' }} />
                  </h3>
                  <div className="space-y-2">
                    {productMatchups.map((gap, i) => (
                      <div
                        key={i}
                        className="flex items-center justify-between p-3 rounded-lg"
                        style={{ backgroundColor: '#F8FAFC', border: '1px solid #E2E8F0' }}
                      >
                        <span className="text-sm" style={{ color: '#1E293B' }}>{gap.feature}</span>
                        <div className="flex items-center gap-3">
                          <div className="flex items-center gap-1.5">
                            <span className="text-[10px] font-medium uppercase" style={{ color: '#5B6E8A' }}>Us</span>
                            <div className="w-16 h-1.5 rounded-full" style={{ backgroundColor: '#E2E8F0' }}>
                              <div
                                className="h-full rounded-full"
                                style={{ width: `${gap.aria_score * 10}%`, backgroundColor: '#22C55E' }}
                              />
                            </div>
                          </div>
                          <div className="flex items-center gap-1.5">
                            <span className="text-[10px] font-medium uppercase" style={{ color: '#5B6E8A' }}>Them</span>
                            <div className="w-16 h-1.5 rounded-full" style={{ backgroundColor: '#E2E8F0' }}>
                              <div
                                className="h-full rounded-full"
                                style={{ width: `${gap.competitor_score * 10}%`, backgroundColor: '#EF4444' }}
                              />
                            </div>
                          </div>
                        </div>
                      </div>
                    ))}
                  </div>
                </section>
              )}

              {/* Recent Signals */}
              {recentSignals.length > 0 && (
                <section>
                  <h3
                    className="text-xs font-semibold uppercase tracking-widest mb-3 flex items-center gap-2"
                    style={{ color: '#94A3B8' }}
                  >
                    <span className="h-px flex-1" style={{ backgroundColor: '#E2E8F0' }} />
                    Recent Signals
                    <span className="h-px flex-1" style={{ backgroundColor: '#E2E8F0' }} />
                  </h3>
                  <div className="space-y-2">
                    {recentSignals.map((signal) => {
                      const detected = 'detected_at' in signal ? signal.detected_at : (signal as { created_at?: string }).created_at;
                      return (
                        <div
                          key={signal.id}
                          className="flex items-start gap-3 p-3 rounded-lg"
                          style={{ backgroundColor: '#FAFBFC', border: '1px solid #F1F5F9' }}
                        >
                          <SignalTypeBadge type={signal.signal_type} />
                          <div className="flex-1 min-w-0">
                            <p className="text-sm" style={{ color: '#1E293B' }}>
                              {sanitizeSignalText('headline' in signal ? signal.headline : (signal.summary ?? signal.content), 200)}
                            </p>
                            {detected && (
                              <span className="text-[10px]" style={{ color: '#94A3B8' }}>
                                {formatRelativeDate(detected)}
                              </span>
                            )}
                          </div>
                          {signal.source_url && (
                            <a
                              href={signal.source_url}
                              target="_blank"
                              rel="noopener noreferrer"
                              onClick={(e) => e.stopPropagation()}
                              className="flex-shrink-0"
                            >
                              <ExternalLink className="w-3.5 h-3.5" style={{ color: '#94A3B8' }} />
                            </a>
                          )}
                        </div>
                      );
                    })}
                  </div>
                </section>
              )}

              {/* Objection Handlers */}
              {card.objection_handlers && card.objection_handlers.length > 0 && (
                <section>
                  <h3
                    className="text-xs font-semibold uppercase tracking-widest mb-3 flex items-center gap-2"
                    style={{ color: '#94A3B8' }}
                  >
                    <span className="h-px flex-1" style={{ backgroundColor: '#E2E8F0' }} />
                    Objection Handlers
                    <span className="h-px flex-1" style={{ backgroundColor: '#E2E8F0' }} />
                  </h3>
                  <div className="space-y-2">
                    {card.objection_handlers.map((handler, i) => (
                      <ObjectionAccordion key={i} handler={handler} />
                    ))}
                  </div>
                </section>
              )}

              {/* ARIA's Insights */}
              {competitorInsights.length > 0 && (
                <section>
                  <h3
                    className="text-xs font-semibold uppercase tracking-widest mb-3 flex items-center gap-2"
                    style={{ color: '#94A3B8' }}
                  >
                    <span className="h-px flex-1" style={{ backgroundColor: '#E2E8F0' }} />
                    ARIA&apos;s Insights
                    <span className="h-px flex-1" style={{ backgroundColor: '#E2E8F0' }} />
                  </h3>
                  <div className="space-y-2">
                    {competitorInsights.slice(0, 5).map((insight) => {
                      const isOpportunity = insight.classification === 'opportunity';
                      const isThreat = insight.classification === 'threat';
                      return (
                        <div
                          key={insight.id}
                          className="rounded-lg p-3"
                          style={{
                            backgroundColor: isThreat ? '#FEF2F210' : isOpportunity ? '#F0FDF410' : '#F8FAFC',
                            border: `1px solid ${isThreat ? '#FECACA' : isOpportunity ? '#BBF7D0' : '#E2E8F0'}`,
                            borderLeftWidth: '3px',
                            borderLeftColor: isThreat ? '#EF4444' : isOpportunity ? '#22C55E' : '#94A3B8',
                          }}
                        >
                          <span
                            className="text-[10px] font-semibold uppercase tracking-wider"
                            style={{ color: isThreat ? '#DC2626' : isOpportunity ? '#16A34A' : '#5B6E8A' }}
                          >
                            {insight.classification}
                          </span>
                          <p className="text-sm leading-relaxed mt-1" style={{ color: '#334155' }}>
                            {insight.content}
                          </p>
                          {insight.recommended_actions && insight.recommended_actions.length > 0 && (
                            <div className="mt-2">
                              <span className="text-[10px] font-medium uppercase tracking-wider" style={{ color: '#5B6E8A' }}>
                                Recommended:
                              </span>
                              <ul className="mt-1 space-y-0.5">
                                {insight.recommended_actions.slice(0, 2).map((action, i) => (
                                  <li key={i} className="text-xs" style={{ color: '#5B6E8A' }}>
                                    &bull; {action}
                                  </li>
                                ))}
                              </ul>
                            </div>
                          )}
                        </div>
                      );
                    })}
                  </div>
                </section>
              )}
            </>
          ) : (
            <div className="text-center py-12" style={{ color: '#94A3B8' }}>
              <p className="text-sm">No competitive data available for {competitorName}.</p>
            </div>
          )}
        </div>

        {/* Footer actions */}
        <div
          className="flex items-center justify-end gap-3 p-4 flex-shrink-0"
          style={{ borderTop: '1px solid #F1F5F9' }}
        >
          <button
            onClick={() => {
              window.location.href = `/?discuss=competitive&company=${encodeURIComponent(competitorName)}`;
            }}
            className="inline-flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-medium transition-colors"
            style={{
              backgroundColor: 'var(--accent, #2E66FF)',
              color: '#FFFFFF',
            }}
          >
            <Zap className="w-4 h-4" />
            Draft Outreach
          </button>
          <button
            onClick={onClose}
            className="px-4 py-2 rounded-lg text-sm font-medium transition-colors"
            style={{
              backgroundColor: '#F1F5F9',
              color: '#475569',
            }}
          >
            Close
          </button>
        </div>
      </div>
    </div>
  );
}
