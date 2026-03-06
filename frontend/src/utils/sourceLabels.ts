/**
 * Source label mapping for displaying clean source names in the UI.
 * Maps internal system source identifiers to user-friendly labels.
 */

export const SOURCE_LABELS: Record<string, string> = {
  // Scout/monitoring sources
  exa_competitor_scan: 'Competitive Intel',
  scout_signal_scan: 'Market Monitor',
  signal_radar: 'Signal Radar',

  // Enrichment sources
  enrichment_news: 'News',
  enrichment_leadership: 'Leadership Intel',
  enrichment_website: 'Company Research',
  enrichment_clinical_trials: 'Clinical Trials',

  // Onboarding/inference sources
  inferred_during_onboarding: 'Onboarding Research',
  initial_seed: 'Initial Research',

  // Manual sources
  manual: 'Your Note',

  // General fallback
  auto: 'Auto-detected',
  demo_seed: 'Demo',
};

/**
 * Format an internal source name into a user-friendly label.
 *
 * @param source - The internal source identifier (e.g., "exa_competitor_scan")
 * @returns A user-friendly label (e.g., "Competitive Intel")
 */
export function formatSourceName(source: string | null | undefined): string {
  if (!source) return 'Intel';

  // Check for exact match in mapping
  if (SOURCE_LABELS[source]) {
    return SOURCE_LABELS[source];
  }

  // For unknown sources, convert snake_case to Title Case as fallback
  return source
    .replace(/_/g, ' ')
    .replace(/\b\w/g, (c) => c.toUpperCase());
}
