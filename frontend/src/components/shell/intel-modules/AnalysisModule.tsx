import { BarChart3 } from 'lucide-react'
import { useIntelDrafts } from '../../../hooks/useIntelPanelData'
import { isPlaceholderDraft } from '../../../utils/isPlaceholderDraft'
import { fetchCommunicationsAnalytics, type VolumeDay } from '../../../api/communications'
import { useQuery } from '@tanstack/react-query'
import type { EmailDraftListItem } from '../../../api/drafts'

const LEARNING_THRESHOLD = 5
const IMPROVING_THRESHOLD = 30

interface SparklineChartProps {
  data: VolumeDay[]
}

function SparklineChart({ data }: SparklineChartProps) {
  const maxValue = Math.max(
    ...data.map((d) => d.received),
    ...data.map((d) => d.drafted),
    ...data.map((d) => d.sent)
  )

  const height = 24
  const barWidth = 16
  const gap = 2

  const days = data.length
  const svgWidth = days * (barWidth + gap) + barWidth
  const svgHeight = height + 4

  const maxVal = maxValue || 1
  const scale = (svgHeight - 4) / maxVal

  return (
    <svg
      width={svgWidth}
      height={svgHeight}
      viewBox={`0 0 ${svgWidth} ${svgHeight}`}
    >
      {data.map((day, i) => {
        const x = i * (barWidth + gap) + barWidth / 2
        const receivedHeight = Math.max(1, (day.received / maxVal) * scale)
        const draftedHeight = Math.max(1, (day.drafted / maxVal) * scale)
        const sentHeight = Math.max(1, (day.sent / maxVal) * scale)
        return (
          <g key={day.date}>
            {/* Received bar */}
            <rect
              x={x}
              y={svgHeight - receivedHeight}
              width={barWidth}
              fill="var(--accent)"
              rx={2}
              ry={svgHeight}
            />
            {/* Drafted bar */}
            <rect
              x={x}
              y={svgHeight - draftedHeight}
              width={barWidth}
              fill="var(--success)"
              rx={2}
              ry={svgHeight}
            />
            {/* Sent bar */}
            <rect
              x={x}
              y={svgHeight - sentHeight}
              width={barWidth}
              fill="var(--info)"
              rx={2}
              ry={svgHeight}
            />
          </g>
        )
      })}
    </svg>
  )
}

interface AnalysisModuleProps {
  stats?: {
    openRate?: number
    replyRate?: number
    avgResponseTime?: string
    trend?: string
  }
}

function AnalysisSkeleton() {
  return (
    <div className="space-y-3">
      <h3
        className="font-sans text-[11px] font-medium uppercase tracking-wider"
        style={{ color: 'var(--text-secondary)' }}
      >
        Communication Analysis
      </h3>
      <div
        className="rounded-lg border p-3 animate-pulse"
        style={{ borderColor: 'var(--border)', backgroundColor: 'var(--bg-subtle)' }}
      >
        <div className="flex items-center gap-2">
          <BarChart3 size={14} style={{ color: 'var(--accent)' }} />
          <span className="font-sans text-[12px] font-medium" style={{ color: 'var(--text-primary)' }}>
            Loading...
          </span>
        </div>
      </div>
    </div>
  )
}

export function AnalysisModule(_props: AnalysisModuleProps) {
  const { data: drafts, isLoading: draftsLoading } = useIntelDrafts()
  const { data: analytics, isLoading: analyticsLoading } = useQuery({
    queryKey: ['communicationsAnalytics'],
    queryFn: () => fetchCommunicationsAnalytics(),
    staleTime: 5 * 60 * 1000,
    refetchOnMount: true,
  })

  if (draftsLoading || analyticsLoading) return <AnalysisSkeleton />

  if (!analytics) {
    // Fall back to legacy metrics if no analytics data
    const realDrafts = (drafts || []).filter((d: EmailDraftListItem) => !isPlaceholderDraft(d))
    const realTotal = realDrafts.length
    const sent = realDrafts.filter((d) => d.status === 'sent').length
    const sentRate = realTotal > 0 ? Math.round((sent / realTotal) * 100) : 0
    const scoredDrafts = realDrafts.filter(
      (d: EmailDraftListItem) => d.style_match_score != null && d.style_match_score > 0
    )
    const avgMatch =
      scoredDrafts.length > 0
        ? Math.round(
            scoredDrafts.reduce((sum: number, d: EmailDraftListItem) => sum + (d.style_match_score ?? 1), 0) / scoredDrafts.length
          )
        : 0
    const isLearning = sent < LEARNING_THRESHOLD
    let styleMatchDisplay: string
    let styleMatchSubtitle: string
    if (isLearning) {
      styleMatchDisplay = 'Learning'
      styleMatchSubtitle = 'Send more emails to calibrate'
    } else if (avgMatch < IMPROVING_THRESHOLD) {
      styleMatchDisplay = `${avgMatch}%`
      styleMatchSubtitle = 'Improving'
    } else {
      styleMatchDisplay = `${avgMatch}%`
      styleMatchSubtitle = 'Style Match'
    }
    const trend = sent > 0
      ? `${sent} of ${realTotal} drafts sent. ${isLearning ? 'Style match calibrating.' : `Average style match: ${avgMatch}%.`}`
      : `${realTotal} draft${realTotal === 1 ? '' : 's'} created. None sent yet.`
    return (
      <div className="space-y-3">
        <h3
          className="font-sans text-[11px] font-medium uppercase tracking-wider"
          style={{ color: 'var(--text-secondary)' }}
        >
          Communication Analysis
        </h3>
        <div
          className="rounded-lg border p-3"
          style={{ borderColor: 'var(--border)', backgroundColor: 'var(--bg-subtle)' }}
        >
          <div className="flex items-center gap-2">
            <BarChart3 size={14} style={{ color: 'var(--accent)' }} />
            <span className="font-sans text-[12px] font-medium" style={{ color: 'var(--text-primary)' }}>
              Communication Analysis
            </span>
          </div>
          <div className="grid grid-cols-3 gap-3 mt-2">
            <div>
              <p className="font-mono text-[18px] font-medium" style={{ color: 'var(--text-primary)' }}>
                {sentRate}%
              </p>
              <p className="font-mono text-[9px] uppercase" style={{ color: 'var(--text-secondary)' }}>
                Sent Rate
              </p>
            </div>
            <div>
              <p
                className={`font-mono font-medium ${isLearning ? 'text-[14px]' : 'text-[18px]'}`}
                style={{ color: isLearning ? 'var(--text-secondary)' : 'var(--text-primary)' }}
              >
                {styleMatchDisplay}
              </p>
              <p className="font-mono text-[9px] uppercase" style={{ color: 'var(--text-secondary)' }}>
                {styleMatchSubtitle}
              </p>
            </div>
            <div>
              <p className="font-mono text-[18px] font-medium" style={{ color: 'var(--text-primary)' }}>
                {realTotal} drafts
              </p>
              <p className="font-mono text-[9px] uppercase" style={{ color: 'var(--text-secondary)' }}>
                Total
              </p>
            </div>
          </div>
          <p className="font-sans text-[11px] mt-3 leading-[1.5]" style={{ color: 'var(--success)' }}>
            {trend}
          </p>
        </div>
      </div>
    )
  }

  // We have analytics from backend
  const hasData = analytics?.has_data ?? false
  const avgResponseHours = analytics?.avg_response_hours
  const draftCoveragePct = analytics?.draft_coverage_pct
  const volume = analytics?.volume_7d ?? []
  const needsReplyCount = analytics?.classification?.NEEDS_REPLY ?? 0
  const fyiCount = analytics?.classification?.FYI ?? 0
  const skipCount = analytics?.classification?.SKIP ?? 0
  const receivedTotal = volume.reduce((sum: number, v: VolumeDay) => sum + v.received, 0)
  const draftedTotal = volume.reduce((sum: number, v: VolumeDay) => sum + v.drafted, 0)

  // Calculate trend direction
  const prevWeekSent = volume.slice(0, 3).reduce((sum: number, v: VolumeDay) => sum + v.sent, 0)
  const thisWeekSent = volume.slice(-3).reduce((sum: number, v: VolumeDay) => sum + v.sent, 0)
  const trendDir = thisWeekSent > prevWeekSent ? 'up' : thisWeekSent < prevWeekSent ? 'down' : 'stable'
  const trend = trendDir === 'up' ? 'Growing' : trendDir === 'down' ? 'Declining' : 'Stable'

  if (!hasData) {
    return (
      <div className="space-y-3">
        <h3
          className="font-sans text-[11px] font-medium uppercase tracking-wider"
          style={{ color: 'var(--text-secondary)' }}
        >
          Communication Analysis
        </h3>
        <div
          className="rounded-lg border p-3"
          style={{ borderColor: 'var(--border)', backgroundColor: 'var(--bg-subtle)' }}
        >
          <div className="flex items-center gap-2">
            <BarChart3 size={14} style={{ color: 'var(--accent)' }} />
            <span className="font-sans text-[12px] font-medium" style={{ color: 'var(--text-primary)' }}>
              Your Outreach Performance
            </span>
          </div>
          <div className="grid grid-cols-3 gap-3 mt-2">
            <div>
              <p className="font-mono text-[18px] font-medium" style={{ color: 'var(--text-primary)' }}>
                0%
              </p>
              <p className="font-mono text-[9px] uppercase" style={{ color: 'var(--text-secondary)' }}>
                Sent Rate
              </p>
            </div>
            <div>
              <p className="font-mono text-[14px] font-medium" style={{ color: 'var(--text-secondary)' }}>
                Learning
              </p>
              <p className="font-mono text-[9px] uppercase" style={{ color: 'var(--text-secondary)' }}>
                Not enough data
              </p>
            </div>
            <div>
              <p className="font-mono text-[18px] font-medium" style={{ color: 'var(--text-primary)' }}>
                {draftedTotal} drafts
              </p>
              <p className="font-mono text-[9px] uppercase" style={{ color: 'var(--text-secondary)' }}>
                Total
              </p>
            </div>
          </div>
          <p className="font-sans text-[11px] mt-3 leading-[1.5]" style={{ color: 'var(--text-secondary)' }}>
            No data yet. Metrics will appear as ARIA processes more emails.
          </p>
        </div>
      </div>
    )
  }

  // Show analytics data
  const sortedVolume = [...volume].sort(
    (a, b) => new Date(b.date).getTime() - new Date(a.date).getTime()
  )

  return (
    <div className="space-y-3">
      <h3
        className="font-sans text-[11px] font-medium uppercase tracking-wider"
        style={{ color: 'var(--text-secondary)' }}
      >
        Communication Analysis
      </h3>
      <div
        className="rounded-lg border p-3"
        style={{ borderColor: 'var(--border)', backgroundColor: 'var(--bg-subtle)' }}
      >
        <div className="flex items-center gap-2">
          <BarChart3 size={14} style={{ color: 'var(--accent)' }} />
          <span className="font-sans text-[12px] font-medium" style={{ color: 'var(--text-primary)' }}>
            Your Outreach Performance
          </span>
        </div>
        <div className="grid grid-cols-3 gap-3 mt-2">
          <div>
            <p className="font-mono text-[18px] font-medium" style={{ color: 'var(--text-primary)' }}>
              {avgResponseHours !== null ? `${avgResponseHours}h` : '--'}
            </p>
            <p className="font-mono text-[9px] uppercase" style={{ color: 'var(--text-secondary)' }}>
              Avg response
            </p>
          </div>
          <div>
            <p className="font-mono text-[18px] font-medium" style={{ color: 'var(--text-primary)' }}>
              {draftCoveragePct !== null ? `${draftCoveragePct}%` : '--'}
            </p>
            <p className="font-mono text-[9px] uppercase" style={{ color: 'var(--text-secondary)' }}>
              Draft coverage
            </p>
          </div>
          <div>
            <p className="font-mono text-[18px] font-medium" style={{ color: 'var(--text-primary)' }}>
              {receivedTotal} received
            </p>
            <p className="font-mono text-[9px] uppercase" style={{ color: 'var(--text-secondary)' }}>
              This week
            </p>
          </div>
        </div>
        {/* 7-day volume sparkline */}
        {sortedVolume.length > 0 && (
          <div className="mt-3">
            <SparklineChart data={sortedVolume} />
          </div>
        )}
        {/* Trend indicator */}
        <p
          className="font-sans text-[11px] mt-2"
          style={{
            color:
              trendDir === 'up'
                ? 'var(--success)'
                : trendDir === 'down'
                  ? 'var(--error)'
                  : 'var(--text-secondary)',
          }}
        >
          {trend} activity
        </p>
        {/* Classification breakdown */}
        <div className="mt-2 pt-2 border-t" style={{ borderColor: 'var(--border)' }}>
          <p className="font-mono text-[10px] font-medium" style={{ color: 'var(--text-primary)' }}>
            Classification
          </p>
          <div className="flex justify-between text-[11px] mt-1" style={{ color: 'var(--text-secondary)' }}>
            <span>NEEDS_REPLY: {needsReplyCount}</span>
            <span>FYI: {fyiCount}</span>
            <span>SKIP: {skipCount}</span>
          </div>
        </div>
      </div>
    </div>
  )
}
