/**
 * ApolloSettingsCard - Apollo.io B2B contact enrichment settings
 *
 * Expandable card showing Apollo configuration with mode toggle,
 * BYOK key management, credit usage, and enrichment settings.
 */

import { useState, useEffect, useCallback } from 'react';
import {
  Users, Check, AlertTriangle, Loader2, Settings,
  ChevronDown, ChevronUp, Key, Eye, EyeOff,
  Phone, Mail, Zap, Clock, Save,
} from 'lucide-react';
import { apiClient } from '@/api/client';

type ApolloConfig = {
  is_configured: boolean;
  mode: 'byok' | 'luminone_provided' | 'unconfigured';
  monthly_credit_limit: number;
  credits_used: number;
  credits_remaining: number;
  billing_cycle_start: string | null;
  billing_cycle_end: string | null;
  has_byok_key: boolean;
  auto_enrich_on_approval: boolean;
  default_reveal_emails: boolean;
  default_reveal_phones: boolean;
};

type ApolloUsageEntry = {
  id: string;
  action: string;
  credits_consumed: number;
  cost_cents: number;
  target_company: string | null;
  target_person: string | null;
  mode: string;
  status: string;
  created_at: string;
};

type ApolloUsageResponse = {
  total_credits_used: number;
  total_cost_cents: number;
  billing_period_start: string | null;
  billing_period_end: string | null;
  breakdown: Array<{ action: string; count: number; credits: number }>;
  recent_transactions: ApolloUsageEntry[];
};

function formatAction(action: string): string {
  return action
    .replace(/_/g, ' ')
    .replace(/\b\w/g, (c) => c.toUpperCase());
}

function formatDate(dateStr: string): string {
  return new Date(dateStr).toLocaleDateString('en-US', {
    month: 'short',
    day: 'numeric',
    year: 'numeric',
  });
}

export function ApolloSettingsCard() {
  const [config, setConfig] = useState<ApolloConfig | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [isExpanded, setIsExpanded] = useState(false);
  const [isSaving, setIsSaving] = useState(false);
  const [saveMessage, setSaveMessage] = useState<{ type: 'success' | 'error'; text: string } | null>(null);

  // Form state
  const [selectedMode, setSelectedMode] = useState<'luminone_provided' | 'byok'>('luminone_provided');
  const [apiKey, setApiKey] = useState('');
  const [showApiKey, setShowApiKey] = useState(false);
  const [autoEnrich, setAutoEnrich] = useState(false);
  const [revealEmails, setRevealEmails] = useState(true);
  const [revealPhones, setRevealPhones] = useState(false);

  // Usage details
  const [usageData, setUsageData] = useState<ApolloUsageResponse | null>(null);
  const [showUsageDetails, setShowUsageDetails] = useState(false);
  const [usageLoading, setUsageLoading] = useState(false);

  const fetchConfig = useCallback(async () => {
    try {
      const { data } = await apiClient.get<ApolloConfig>('/apollo/config');
      setConfig(data);
      setSelectedMode(data.mode === 'byok' ? 'byok' : 'luminone_provided');
      setAutoEnrich(data.auto_enrich_on_approval);
      setRevealEmails(data.default_reveal_emails);
      setRevealPhones(data.default_reveal_phones);
      setError(null);
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : 'Failed to load';
      setError(message);
    } finally {
      setIsLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchConfig();
  }, [fetchConfig]);

  const fetchUsageDetails = async () => {
    if (usageData) {
      setShowUsageDetails(!showUsageDetails);
      return;
    }
    setUsageLoading(true);
    try {
      const { data } = await apiClient.get<ApolloUsageResponse>('/apollo/usage');
      setUsageData(data);
      setShowUsageDetails(true);
    } catch {
      setSaveMessage({ type: 'error', text: 'Failed to load usage details' });
    } finally {
      setUsageLoading(false);
    }
  };

  const handleSave = async () => {
    setIsSaving(true);
    setSaveMessage(null);
    try {
      const payload: Record<string, unknown> = {
        auto_enrich_on_approval: autoEnrich,
        default_reveal_emails: revealEmails,
        default_reveal_phones: revealPhones,
      };

      // Include mode if changed
      if (config && selectedMode !== config.mode) {
        payload.mode = selectedMode;
      }

      // Include API key for BYOK
      if (selectedMode === 'byok' && apiKey) {
        payload.mode = 'byok';
        payload.api_key = apiKey;
      }

      await apiClient.put('/apollo/config', payload);
      setSaveMessage({ type: 'success', text: 'Settings saved' });
      setApiKey('');
      await fetchConfig();
    } catch {
      setSaveMessage({ type: 'error', text: 'Failed to save settings' });
    } finally {
      setIsSaving(false);
      setTimeout(() => setSaveMessage(null), 3000);
    }
  };

  // Check if form has unsaved changes
  const hasChanges = config && (
    selectedMode !== (config.mode === 'byok' ? 'byok' : 'luminone_provided') ||
    autoEnrich !== config.auto_enrich_on_approval ||
    revealEmails !== config.default_reveal_emails ||
    revealPhones !== config.default_reveal_phones ||
    apiKey.length > 0
  );

  if (isLoading) {
    return (
      <div
        className="p-3 rounded-lg border"
        style={{ borderColor: 'var(--border)', backgroundColor: 'var(--bg-subtle)' }}
      >
        <div className="flex items-center gap-3">
          <div
            className="w-10 h-10 rounded-lg flex items-center justify-center"
            style={{ backgroundColor: 'var(--bg-elevated)' }}
          >
            <Loader2 className="w-5 h-5 animate-spin" style={{ color: 'var(--text-secondary)' }} />
          </div>
          <div>
            <p className="text-sm font-medium" style={{ color: 'var(--text-primary)' }}>Apollo.io</p>
            <p className="text-xs" style={{ color: 'var(--text-secondary)' }}>Loading...</p>
          </div>
        </div>
      </div>
    );
  }

  if (error || !config) {
    return (
      <div
        className="p-3 rounded-lg border"
        style={{ borderColor: 'var(--border)', backgroundColor: 'var(--bg-subtle)' }}
      >
        <div className="flex items-center gap-3">
          <div
            className="w-10 h-10 rounded-lg flex items-center justify-center"
            style={{ backgroundColor: 'var(--bg-elevated)' }}
          >
            <AlertTriangle className="w-5 h-5" style={{ color: 'var(--error, #ef4444)' }} />
          </div>
          <div>
            <p className="text-sm font-medium" style={{ color: 'var(--text-primary)' }}>Apollo.io</p>
            <p className="text-xs" style={{ color: 'var(--text-secondary)' }}>Failed to load configuration</p>
          </div>
        </div>
      </div>
    );
  }

  const isConfigured = config.is_configured && config.mode !== 'unconfigured';
  const usagePercent = config.monthly_credit_limit > 0
    ? Math.min(100, (config.credits_used / config.monthly_credit_limit) * 100)
    : 0;
  const isLowCredits = usagePercent >= 80;

  // Calculate reset date display
  const resetDateStr = config.billing_cycle_start
    ? formatDate(config.billing_cycle_start)
    : null;

  return (
    <div
      className="rounded-lg border overflow-hidden"
      style={{ borderColor: 'var(--border)', backgroundColor: 'var(--bg-subtle)' }}
    >
      {/* Summary Row — always visible */}
      <div className="flex items-center justify-between p-3">
        <div className="flex items-center gap-3">
          <div
            className="w-10 h-10 rounded-lg flex items-center justify-center font-medium text-sm"
            style={{ backgroundColor: 'var(--bg-elevated)', color: 'var(--text-primary)' }}
          >
            <Users className="w-5 h-5" />
          </div>
          <div className="flex flex-col gap-1">
            <div className="flex items-center gap-2">
              <p className="text-sm font-medium" style={{ color: 'var(--text-primary)' }}>Apollo.io</p>
              <span
                className="text-xs px-1.5 py-0.5 rounded"
                style={{
                  backgroundColor: config.mode === 'byok' ? 'var(--accent)' : 'var(--bg-elevated)',
                  color: config.mode === 'byok' ? 'white' : 'var(--text-secondary)',
                }}
              >
                {config.mode === 'byok' ? 'BYOK' : 'LuminOne'}
              </span>
            </div>
            <p className="text-xs" style={{ color: 'var(--text-secondary)' }}>
              B2B contact enrichment for lead discovery
            </p>
            {isConfigured && (
              <div className="flex items-center gap-2 mt-1">
                <div
                  className="flex-1 h-1.5 rounded-full overflow-hidden"
                  style={{ backgroundColor: 'var(--bg-elevated)', maxWidth: '120px' }}
                >
                  <div
                    className="h-full rounded-full transition-all duration-300"
                    style={{
                      width: `${usagePercent}%`,
                      backgroundColor: isLowCredits ? 'var(--warning, #f59e0b)' : 'var(--success)',
                    }}
                  />
                </div>
                <span
                  className="text-xs"
                  style={{ color: isLowCredits ? 'var(--warning, #f59e0b)' : 'var(--text-secondary)' }}
                >
                  {config.credits_used}/{config.monthly_credit_limit} credits
                </span>
              </div>
            )}
          </div>
        </div>

        <div className="flex items-center gap-2">
          {isConfigured && (
            <span className="flex items-center gap-1 text-xs" style={{ color: 'var(--success)' }}>
              <Check className="w-3.5 h-3.5" />
              {config.has_byok_key ? 'Connected' : 'Active'}
            </span>
          )}
          <button
            onClick={() => setIsExpanded(!isExpanded)}
            className="flex items-center gap-1 text-xs px-2 py-1 rounded border"
            style={{ borderColor: 'var(--border)', color: 'var(--text-secondary)' }}
          >
            <Settings className="w-3 h-3" />
            Settings
            {isExpanded ? <ChevronUp className="w-3 h-3" /> : <ChevronDown className="w-3 h-3" />}
          </button>
        </div>
      </div>

      {/* Expanded Settings Panel */}
      {isExpanded && (
        <div
          className="px-3 pb-3 space-y-4"
          style={{ borderTop: '1px solid var(--border)' }}
        >
          {/* Save feedback */}
          {saveMessage && (
            <div
              className="text-xs px-3 py-2 rounded mt-3"
              style={{
                backgroundColor: saveMessage.type === 'success'
                  ? 'rgba(34, 197, 94, 0.1)'
                  : 'rgba(239, 68, 68, 0.1)',
                color: saveMessage.type === 'success'
                  ? 'var(--success)'
                  : 'var(--error, #ef4444)',
              }}
            >
              {saveMessage.text}
            </div>
          )}

          {/* Mode Selection */}
          <div className="mt-3">
            <p className="text-xs font-medium mb-2" style={{ color: 'var(--text-primary)' }}>
              Mode
            </p>
            <div className="space-y-2">
              <label
                className="flex items-start gap-2 p-2 rounded-lg border cursor-pointer"
                style={{
                  borderColor: selectedMode === 'luminone_provided' ? 'var(--accent)' : 'var(--border)',
                  backgroundColor: selectedMode === 'luminone_provided' ? 'rgba(99, 102, 241, 0.05)' : 'transparent',
                }}
              >
                <input
                  type="radio"
                  name="apollo-mode"
                  checked={selectedMode === 'luminone_provided'}
                  onChange={() => setSelectedMode('luminone_provided')}
                  className="mt-0.5"
                  style={{ accentColor: 'var(--accent)' }}
                />
                <div>
                  <p className="text-xs font-medium" style={{ color: 'var(--text-primary)' }}>
                    Use ARIA's Apollo (credits included)
                  </p>
                  <p className="text-xs mt-0.5" style={{ color: 'var(--text-secondary)' }}>
                    {config.monthly_credit_limit} credits/month included with your plan
                  </p>
                </div>
              </label>
              <label
                className="flex items-start gap-2 p-2 rounded-lg border cursor-pointer"
                style={{
                  borderColor: selectedMode === 'byok' ? 'var(--accent)' : 'var(--border)',
                  backgroundColor: selectedMode === 'byok' ? 'rgba(99, 102, 241, 0.05)' : 'transparent',
                }}
              >
                <input
                  type="radio"
                  name="apollo-mode"
                  checked={selectedMode === 'byok'}
                  onChange={() => setSelectedMode('byok')}
                  className="mt-0.5"
                  style={{ accentColor: 'var(--accent)' }}
                />
                <div>
                  <p className="text-xs font-medium" style={{ color: 'var(--text-primary)' }}>
                    Use your own Apollo subscription
                  </p>
                  <p className="text-xs mt-0.5" style={{ color: 'var(--text-secondary)' }}>
                    Bring your own API key — unlimited usage
                  </p>
                </div>
              </label>
            </div>
          </div>

          {/* BYOK Key Input */}
          {selectedMode === 'byok' && (
            <div>
              <p className="text-xs font-medium mb-1.5" style={{ color: 'var(--text-primary)' }}>
                <Key className="w-3 h-3 inline mr-1" />
                API Key
              </p>
              <div className="flex gap-2">
                <div className="relative flex-1">
                  <input
                    type={showApiKey ? 'text' : 'password'}
                    value={apiKey}
                    onChange={(e) => setApiKey(e.target.value)}
                    placeholder={config.has_byok_key ? '••••••••••••••••' : 'Enter your Apollo API key'}
                    className="w-full text-xs px-3 py-1.5 rounded border pr-8"
                    style={{
                      borderColor: 'var(--border)',
                      backgroundColor: 'var(--bg-elevated)',
                      color: 'var(--text-primary)',
                    }}
                  />
                  <button
                    onClick={() => setShowApiKey(!showApiKey)}
                    className="absolute right-2 top-1/2 -translate-y-1/2"
                    style={{ color: 'var(--text-secondary)' }}
                  >
                    {showApiKey ? <EyeOff className="w-3.5 h-3.5" /> : <Eye className="w-3.5 h-3.5" />}
                  </button>
                </div>
              </div>
              <p className="text-xs mt-1" style={{ color: 'var(--text-secondary)' }}>
                Your API key is encrypted and stored securely.
              </p>
            </div>
          )}

          {/* Credit Usage Detail (LuminOne mode) */}
          {selectedMode === 'luminone_provided' && isConfigured && (
            <div>
              <p className="text-xs font-medium mb-1.5" style={{ color: 'var(--text-primary)' }}>
                Credit Usage
              </p>
              <div
                className="p-2.5 rounded-lg"
                style={{ backgroundColor: 'var(--bg-elevated)' }}
              >
                <div className="flex items-center justify-between mb-2">
                  <span className="text-xs" style={{ color: 'var(--text-secondary)' }}>
                    {config.credits_used} / {config.monthly_credit_limit} credits used
                  </span>
                  <span
                    className="text-xs font-medium"
                    style={{ color: isLowCredits ? 'var(--warning, #f59e0b)' : 'var(--success)' }}
                  >
                    {config.credits_remaining} remaining
                  </span>
                </div>
                <div
                  className="h-2 rounded-full overflow-hidden"
                  style={{ backgroundColor: 'var(--bg-subtle)' }}
                >
                  <div
                    className="h-full rounded-full transition-all duration-300"
                    style={{
                      width: `${usagePercent}%`,
                      backgroundColor: isLowCredits ? 'var(--warning, #f59e0b)' : 'var(--success)',
                    }}
                  />
                </div>
                {resetDateStr && (
                  <p className="text-xs mt-1.5 flex items-center gap-1" style={{ color: 'var(--text-secondary)' }}>
                    <Clock className="w-3 h-3" />
                    Resets {resetDateStr}
                  </p>
                )}
                <p className="text-xs mt-1" style={{ color: 'var(--text-secondary)' }}>
                  Credits are consumed when ARIA enriches contacts with verified emails.
                </p>
              </div>
            </div>
          )}

          {/* Enrichment Settings */}
          <div>
            <p className="text-xs font-medium mb-2" style={{ color: 'var(--text-primary)' }}>
              Enrichment Settings
            </p>
            <div className="space-y-2">
              <label className="flex items-start gap-2 cursor-pointer">
                <input
                  type="checkbox"
                  checked={autoEnrich}
                  onChange={(e) => setAutoEnrich(e.target.checked)}
                  className="mt-0.5"
                  style={{ accentColor: 'var(--accent)' }}
                />
                <div>
                  <p className="text-xs" style={{ color: 'var(--text-primary)' }}>
                    <Zap className="w-3 h-3 inline mr-1" />
                    Auto-enrich contacts when leads are approved
                  </p>
                </div>
              </label>
              <label className="flex items-start gap-2 cursor-pointer">
                <input
                  type="checkbox"
                  checked={revealEmails}
                  onChange={(e) => setRevealEmails(e.target.checked)}
                  className="mt-0.5"
                  style={{ accentColor: 'var(--accent)' }}
                />
                <div>
                  <p className="text-xs" style={{ color: 'var(--text-primary)' }}>
                    <Mail className="w-3 h-3 inline mr-1" />
                    Reveal email addresses
                  </p>
                </div>
              </label>
              <label className="flex items-start gap-2 cursor-pointer">
                <input
                  type="checkbox"
                  checked={revealPhones}
                  onChange={(e) => setRevealPhones(e.target.checked)}
                  className="mt-0.5"
                  style={{ accentColor: 'var(--accent)' }}
                />
                <div>
                  <p className="text-xs" style={{ color: 'var(--text-primary)' }}>
                    <Phone className="w-3 h-3 inline mr-1" />
                    Reveal phone numbers (costs 8x credits)
                  </p>
                </div>
              </label>
            </div>
          </div>

          {/* Usage Details */}
          <div>
            <button
              onClick={fetchUsageDetails}
              className="flex items-center gap-1 text-xs"
              style={{ color: 'var(--accent)' }}
              disabled={usageLoading}
            >
              {usageLoading ? (
                <Loader2 className="w-3 h-3 animate-spin" />
              ) : showUsageDetails ? (
                <ChevronUp className="w-3 h-3" />
              ) : (
                <ChevronDown className="w-3 h-3" />
              )}
              View usage details
            </button>
            {showUsageDetails && usageData && (
              <div
                className="mt-2 rounded-lg overflow-hidden"
                style={{ border: '1px solid var(--border)' }}
              >
                <table className="w-full text-xs">
                  <thead>
                    <tr style={{ backgroundColor: 'var(--bg-elevated)' }}>
                      <th className="text-left px-2.5 py-1.5 font-medium" style={{ color: 'var(--text-secondary)' }}>Date</th>
                      <th className="text-left px-2.5 py-1.5 font-medium" style={{ color: 'var(--text-secondary)' }}>Action</th>
                      <th className="text-left px-2.5 py-1.5 font-medium" style={{ color: 'var(--text-secondary)' }}>Target</th>
                      <th className="text-right px-2.5 py-1.5 font-medium" style={{ color: 'var(--text-secondary)' }}>Credits</th>
                    </tr>
                  </thead>
                  <tbody>
                    {usageData.recent_transactions.length === 0 ? (
                      <tr>
                        <td colSpan={4} className="px-2.5 py-3 text-center" style={{ color: 'var(--text-secondary)' }}>
                          No usage recorded this billing cycle
                        </td>
                      </tr>
                    ) : (
                      usageData.recent_transactions.map((tx) => (
                        <tr
                          key={tx.id}
                          style={{ borderTop: '1px solid var(--border)' }}
                        >
                          <td className="px-2.5 py-1.5" style={{ color: 'var(--text-secondary)' }}>
                            {formatDate(tx.created_at)}
                          </td>
                          <td className="px-2.5 py-1.5" style={{ color: 'var(--text-primary)' }}>
                            {formatAction(tx.action)}
                          </td>
                          <td className="px-2.5 py-1.5" style={{ color: 'var(--text-secondary)' }}>
                            {tx.target_person || tx.target_company || '-'}
                          </td>
                          <td className="px-2.5 py-1.5 text-right font-medium" style={{ color: 'var(--text-primary)' }}>
                            {tx.credits_consumed}
                          </td>
                        </tr>
                      ))
                    )}
                  </tbody>
                </table>
              </div>
            )}
          </div>

          {/* Save Button */}
          <div className="flex justify-end pt-1">
            <button
              onClick={handleSave}
              disabled={isSaving || !hasChanges}
              className="flex items-center gap-1.5 text-xs px-3 py-1.5 rounded-lg transition-opacity"
              style={{
                backgroundColor: hasChanges ? 'var(--accent)' : 'var(--bg-elevated)',
                color: hasChanges ? 'white' : 'var(--text-secondary)',
                opacity: isSaving ? 0.6 : 1,
                cursor: hasChanges ? 'pointer' : 'default',
              }}
            >
              {isSaving ? <Loader2 className="w-3 h-3 animate-spin" /> : <Save className="w-3 h-3" />}
              {isSaving ? 'Saving...' : 'Save Settings'}
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
