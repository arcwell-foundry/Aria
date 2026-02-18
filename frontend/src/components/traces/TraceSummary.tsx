import { CheckCircle, XCircle, RefreshCw, Users, DollarSign, Timer } from 'lucide-react';
import { cn } from '@/utils/cn';
import type { TraceSummary as TraceSummaryData } from '@/api/traces';

function formatDuration(ms: number): string {
  if (ms < 1000) return `${ms}ms`;
  const seconds = ms / 1000;
  if (seconds < 60) return `${seconds.toFixed(1)}s`;
  const mins = Math.floor(seconds / 60);
  const secs = Math.round(seconds % 60);
  return `${mins}m ${secs}s`;
}

function formatCost(usd: number): string {
  if (usd < 0.01) return '<$0.01';
  return `$${usd.toFixed(2)}`;
}

interface TraceSummaryProps {
  summary: TraceSummaryData;
  mode?: 'full' | 'compact';
}

export function TraceSummary({ summary, mode = 'full' }: TraceSummaryProps) {
  const verified = summary.verification_passes + summary.verification_failures;

  if (mode === 'compact') {
    return (
      <div
        className="flex items-center gap-3 text-xs font-mono"
        style={{ color: 'var(--text-secondary)' }}
      >
        <span className="flex items-center gap-1">
          <Users className="w-3 h-3" />
          {summary.agent_count} agent{summary.agent_count !== 1 ? 's' : ''}
        </span>
        <span className="opacity-40">·</span>
        {verified > 0 && (
          <>
            <span className="flex items-center gap-1">
              <CheckCircle className="w-3 h-3" style={{ color: 'var(--success)' }} />
              {summary.verification_passes} verified
            </span>
            <span className="opacity-40">·</span>
          </>
        )}
        <span>{formatCost(summary.total_cost_usd)}</span>
        <span className="opacity-40">·</span>
        <span>{formatDuration(summary.total_duration_ms)}</span>
      </div>
    );
  }

  return (
    <div
      className="grid grid-cols-2 sm:grid-cols-3 gap-3 text-xs"
      style={{ color: 'var(--text-secondary)' }}
    >
      {/* Agents */}
      <div
        className="flex items-center gap-2 px-3 py-2 rounded-lg"
        style={{ backgroundColor: 'var(--bg-subtle)' }}
      >
        <Users className="w-4 h-4 flex-shrink-0" style={{ color: 'var(--accent)' }} />
        <div>
          <p className="font-medium" style={{ color: 'var(--text-primary)' }}>
            {summary.agent_count} agent{summary.agent_count !== 1 ? 's' : ''}
          </p>
          <p className="font-mono truncate">
            {summary.unique_agents.join(', ')}
          </p>
        </div>
      </div>

      {/* Verification */}
      <div
        className="flex items-center gap-2 px-3 py-2 rounded-lg"
        style={{ backgroundColor: 'var(--bg-subtle)' }}
      >
        <CheckCircle className="w-4 h-4 flex-shrink-0" style={{ color: 'var(--success)' }} />
        <div>
          <p className="font-medium" style={{ color: 'var(--text-primary)' }}>
            {summary.verification_passes} passed
          </p>
          <div className="flex items-center gap-2">
            {summary.verification_failures > 0 && (
              <span className="flex items-center gap-1" style={{ color: 'var(--critical)' }}>
                <XCircle className="w-3 h-3" />
                {summary.verification_failures} failed
              </span>
            )}
            {summary.retries > 0 && (
              <span className={cn('flex items-center gap-1', summary.verification_failures > 0 && 'ml-1')}>
                <RefreshCw className="w-3 h-3" />
                {summary.retries} retr{summary.retries === 1 ? 'y' : 'ies'}
              </span>
            )}
          </div>
        </div>
      </div>

      {/* Cost & Duration */}
      <div
        className="flex items-center gap-2 px-3 py-2 rounded-lg"
        style={{ backgroundColor: 'var(--bg-subtle)' }}
      >
        <div className="flex flex-col gap-1">
          <p className="flex items-center gap-1.5 font-medium" style={{ color: 'var(--text-primary)' }}>
            <DollarSign className="w-3.5 h-3.5 flex-shrink-0" />
            {formatCost(summary.total_cost_usd)}
          </p>
          <p className="flex items-center gap-1.5 font-mono">
            <Timer className="w-3.5 h-3.5 flex-shrink-0" />
            {formatDuration(summary.total_duration_ms)}
          </p>
        </div>
      </div>
    </div>
  );
}
