/**
 * TerritoryForecastModule - Pipeline forecast in Intel Panel
 *
 * Shows per-stage rows with deal count, proportional bars, and
 * weighted pipeline summary. Optional quota attainment bar.
 *
 * Follows JarvisInsightsModule pattern:
 * - Skeleton loading state
 * - Empty state messaging
 * - data-aria-id attributes
 * - Dark theme (Intel Panel context)
 */

import { useForecast, useQuotas } from '@/hooks/useAccounts';

function TerritoryForecastSkeleton() {
  return (
    <div className="space-y-2">
      <div className="h-3 w-32 rounded bg-[var(--border)] animate-pulse" />
      <div className="space-y-2">
        {Array.from({ length: 3 }).map((_, i) => (
          <div key={i} className="h-10 rounded-lg bg-[var(--border)] animate-pulse" />
        ))}
      </div>
    </div>
  );
}

export function TerritoryForecastModule() {
  const { data: forecast, isLoading: forecastLoading } = useForecast();
  const { data: quotas, isLoading: quotasLoading } = useQuotas();

  if (forecastLoading || quotasLoading) return <TerritoryForecastSkeleton />;

  if (!forecast || forecast.stages.length === 0) {
    return (
      <div data-aria-id="intel-territory-forecast" className="space-y-2">
        <h3
          className="font-sans text-[11px] font-medium uppercase tracking-wider mb-3"
          style={{ color: 'var(--text-secondary)' }}
        >
          Pipeline Forecast
        </h3>
        <div
          className="rounded-lg border p-4"
          style={{ borderColor: 'var(--border)', backgroundColor: 'var(--bg-subtle)' }}
        >
          <p className="font-sans text-[12px]" style={{ color: 'var(--text-secondary)' }}>
            No forecast data yet. ARIA is analyzing your pipeline.
          </p>
        </div>
      </div>
    );
  }

  const maxValue = Math.max(...forecast.stages.map((s) => s.weighted_value), 1);
  const currentQuota = quotas?.[0];

  return (
    <div data-aria-id="intel-territory-forecast" className="space-y-2">
      <h3
        className="font-sans text-[11px] font-medium uppercase tracking-wider mb-3"
        style={{ color: 'var(--text-secondary)' }}
      >
        Pipeline Forecast
      </h3>

      <div className="space-y-2">
        {forecast.stages.map((stage) => {
          const barWidth = Math.max(4, (stage.weighted_value / maxValue) * 100);
          return (
            <div
              key={stage.stage}
              className="rounded-lg border p-2.5"
              style={{ borderColor: 'var(--border)', backgroundColor: 'var(--bg-subtle)' }}
            >
              <div className="flex items-center justify-between mb-1">
                <span
                  className="font-sans text-[12px] font-medium capitalize"
                  style={{ color: 'var(--text-primary)' }}
                >
                  {stage.stage}
                </span>
                <span
                  className="font-mono text-[11px]"
                  style={{ color: 'var(--text-secondary)' }}
                >
                  {stage.count} deal{stage.count !== 1 ? 's' : ''}
                </span>
              </div>
              <div
                className="h-[4px] rounded-full"
                style={{ backgroundColor: 'var(--border)' }}
              >
                <div
                  className="h-full rounded-full transition-all duration-300"
                  style={{
                    width: `${barWidth}%`,
                    backgroundColor: 'var(--accent)',
                    opacity: 0.8,
                  }}
                />
              </div>
            </div>
          );
        })}
      </div>

      {/* Summary */}
      <div
        className="rounded-lg border p-2.5 mt-2"
        style={{ borderColor: 'var(--accent)', backgroundColor: 'var(--bg-subtle)', borderLeftWidth: '3px' }}
      >
        <div className="flex items-center justify-between">
          <span
            className="font-sans text-[11px] font-medium"
            style={{ color: 'var(--text-secondary)' }}
          >
            Weighted Pipeline
          </span>
          <span
            className="font-mono text-[13px] font-semibold"
            style={{ color: 'var(--accent)' }}
          >
            ${forecast.weighted_pipeline >= 1_000_000
              ? `${(forecast.weighted_pipeline / 1_000_000).toFixed(1)}M`
              : forecast.weighted_pipeline >= 1_000
                ? `${(forecast.weighted_pipeline / 1_000).toFixed(0)}K`
                : forecast.weighted_pipeline.toFixed(0)}
          </span>
        </div>
      </div>

      {/* Quota attainment */}
      {currentQuota && currentQuota.target_value > 0 && (
        <div className="mt-2">
          <div className="flex items-center justify-between mb-1">
            <span
              className="font-sans text-[10px] uppercase tracking-wider"
              style={{ color: 'var(--text-secondary)' }}
            >
              Quota Attainment
            </span>
            <span
              className="font-mono text-[10px]"
              style={{ color: 'var(--text-secondary)' }}
            >
              {((currentQuota.actual_value / currentQuota.target_value) * 100).toFixed(0)}%
            </span>
          </div>
          <div
            className="h-[4px] rounded-full"
            style={{ backgroundColor: 'var(--border)' }}
          >
            <div
              className="h-full rounded-full transition-all duration-300"
              style={{
                width: `${Math.min(100, (currentQuota.actual_value / currentQuota.target_value) * 100)}%`,
                backgroundColor: currentQuota.actual_value >= currentQuota.target_value
                  ? 'var(--success)'
                  : 'var(--warning)',
              }}
            />
          </div>
        </div>
      )}
    </div>
  );
}
