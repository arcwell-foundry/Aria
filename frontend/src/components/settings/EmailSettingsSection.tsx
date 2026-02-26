/**
 * EmailSettingsSection - Email intelligence configuration
 *
 * Controls for auto-draft behavior, draft timing, VIP contacts,
 * excluded senders, email provider status, and learning mode.
 */

import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  Mail,
  Clock,
  Star,
  Ban,
  Wifi,
  GraduationCap,
  Loader2,
  Plus,
  X,
  AlertCircle,
  AlertTriangle,
} from 'lucide-react';
import { cn } from '@/utils/cn';
import {
  useEmailIntelligenceSettings,
  useUpdateEmailIntelligenceSettings,
} from '@/hooks/useEmailIntelligenceSettings';
import type { DraftTiming } from '@/api/emailIntelligenceSettings';

function EmailListEditor({
  label,
  description,
  icon: Icon,
  items,
  onAdd,
  onRemove,
  placeholder,
  addLabel,
}: {
  label: string;
  description: string;
  icon: React.ElementType;
  items: string[];
  onAdd: (value: string) => void;
  onRemove: (index: number) => void;
  placeholder: string;
  addLabel: string;
}) {
  const [inputValue, setInputValue] = useState('');
  const [isAdding, setIsAdding] = useState(false);

  const handleAdd = () => {
    const trimmed = inputValue.trim().toLowerCase();
    if (trimmed && !items.includes(trimmed)) {
      onAdd(trimmed);
      setInputValue('');
      setIsAdding(false);
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter') {
      e.preventDefault();
      handleAdd();
    } else if (e.key === 'Escape') {
      setIsAdding(false);
      setInputValue('');
    }
  };

  return (
    <div>
      <label
        className="flex items-center gap-2 text-sm font-medium mb-2"
        style={{ color: 'var(--text-primary)' }}
      >
        <Icon className="w-4 h-4" style={{ color: 'var(--text-secondary)' }} />
        {label}
      </label>
      <p className="text-xs mb-3 ml-6" style={{ color: 'var(--text-secondary)' }}>
        {description}
      </p>

      {/* Existing items */}
      {items.length > 0 && (
        <div className="flex flex-wrap gap-2 mb-3 ml-6">
          {items.map((item, index) => (
            <span
              key={item}
              className="inline-flex items-center gap-1 px-2.5 py-1 rounded-full text-xs border"
              style={{
                borderColor: 'var(--border)',
                backgroundColor: 'var(--bg-subtle)',
                color: 'var(--text-primary)',
              }}
            >
              {item}
              <button
                type="button"
                onClick={() => onRemove(index)}
                className="ml-0.5 rounded-full p-0.5 hover:bg-[var(--bg-elevated)] transition-colors"
                aria-label={`Remove ${item}`}
              >
                <X className="w-3 h-3" style={{ color: 'var(--text-secondary)' }} />
              </button>
            </span>
          ))}
        </div>
      )}

      {/* Add input */}
      {isAdding ? (
        <div className="flex gap-2 ml-6">
          <input
            type="text"
            value={inputValue}
            onChange={(e) => setInputValue(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder={placeholder}
            autoFocus
            className={cn(
              'flex-1 px-3 py-1.5 rounded-lg border text-sm',
              'border-[var(--border)] bg-[var(--bg-subtle)]',
              'focus:outline-none focus:ring-2 focus:ring-[var(--accent)]/30'
            )}
            style={{ color: 'var(--text-primary)' }}
          />
          <button
            type="button"
            onClick={handleAdd}
            className="px-3 py-1.5 rounded-lg text-xs font-medium bg-[var(--accent)] text-white hover:opacity-90 transition-opacity"
          >
            Add
          </button>
          <button
            type="button"
            onClick={() => {
              setIsAdding(false);
              setInputValue('');
            }}
            className="px-3 py-1.5 rounded-lg text-xs border border-[var(--border)] hover:bg-[var(--bg-subtle)] transition-colors"
            style={{ color: 'var(--text-secondary)' }}
          >
            Cancel
          </button>
        </div>
      ) : (
        <button
          type="button"
          onClick={() => setIsAdding(true)}
          className="flex items-center gap-1.5 ml-6 text-xs font-medium hover:opacity-80 transition-opacity"
          style={{ color: 'var(--accent)' }}
        >
          <Plus className="w-3.5 h-3.5" />
          {addLabel}
        </button>
      )}
    </div>
  );
}

export function EmailSettingsSection() {
  const navigate = useNavigate();
  const { data: settings, isLoading, error } = useEmailIntelligenceSettings();
  const updateMutation = useUpdateEmailIntelligenceSettings();

  const isSaving = updateMutation.isPending;

  if (isLoading) {
    return (
      <div
        className="border rounded-lg p-6"
        style={{ borderColor: 'var(--border)', backgroundColor: 'var(--bg-elevated)' }}
      >
        <div className="flex items-center justify-center py-8">
          <Loader2 className="w-5 h-5 animate-spin" style={{ color: 'var(--text-secondary)' }} />
        </div>
      </div>
    );
  }

  if (error || !settings) {
    return (
      <div
        className="border rounded-lg p-6"
        style={{ borderColor: 'var(--border)', backgroundColor: 'var(--bg-elevated)' }}
      >
        <div className="flex items-center gap-2 py-4">
          <AlertCircle className="w-4 h-4" style={{ color: 'var(--error, #ef4444)' }} />
          <p className="text-sm" style={{ color: 'var(--text-secondary)' }}>
            Failed to load email settings. Please try again later.
          </p>
        </div>
      </div>
    );
  }

  const handleToggleAutoDraft = () => {
    updateMutation.mutate({
      auto_draft_enabled: !settings.auto_draft_enabled,
    });
  };

  const handleTimingChange = (timing: DraftTiming) => {
    updateMutation.mutate({ draft_timing: timing });
  };

  const handleAddVip = (email: string) => {
    updateMutation.mutate({
      vip_contacts: [...settings.vip_contacts, email],
    });
  };

  const handleRemoveVip = (index: number) => {
    const updated = settings.vip_contacts.filter((_, i) => i !== index);
    updateMutation.mutate({ vip_contacts: updated });
  };

  const handleAddExclusion = (pattern: string) => {
    updateMutation.mutate({
      excluded_senders: [...settings.excluded_senders, pattern],
    });
  };

  const handleRemoveExclusion = (index: number) => {
    const updated = settings.excluded_senders.filter((_, i) => i !== index);
    updateMutation.mutate({ excluded_senders: updated });
  };

  return (
    <div
      className="border rounded-lg p-6"
      style={{ borderColor: 'var(--border)', backgroundColor: 'var(--bg-elevated)' }}
    >
      {/* Header */}
      <div className="flex items-center justify-between mb-6">
        <div className="flex items-center gap-2">
          <Mail className="w-4 h-4" style={{ color: 'var(--text-secondary)' }} />
          <h3
            className="font-medium"
            style={{ color: 'var(--text-primary)' }}
          >
            Email Intelligence
          </h3>
        </div>
        {isSaving && (
          <span className="text-xs" style={{ color: 'var(--text-secondary)' }}>
            Saving...
          </span>
        )}
      </div>

      <div className="space-y-6">
        {/* Auto-Draft Behavior */}
        <div>
          <label className="flex items-center justify-between cursor-pointer">
            <div className="flex items-center gap-2">
              <Mail className="w-4 h-4" style={{ color: settings.auto_draft_enabled ? 'var(--accent)' : 'var(--text-secondary)' }} />
              <span className="text-sm" style={{ color: 'var(--text-primary)' }}>
                Auto-draft replies for business emails
              </span>
            </div>
            <button
              type="button"
              role="switch"
              aria-checked={settings.auto_draft_enabled}
              onClick={handleToggleAutoDraft}
              className={cn(
                'relative inline-flex h-5 w-9 items-center rounded-full transition-colors',
                settings.auto_draft_enabled ? 'bg-[var(--accent)]' : 'bg-[var(--border)]'
              )}
            >
              <span
                className={cn(
                  'inline-block h-4 w-4 transform rounded-full bg-white transition-transform',
                  settings.auto_draft_enabled ? 'translate-x-4' : 'translate-x-0.5'
                )}
              />
            </button>
          </label>
          <p className="text-xs mt-1 ml-6" style={{ color: 'var(--text-secondary)' }}>
            {settings.auto_draft_enabled
              ? 'ARIA will automatically draft replies for incoming business emails'
              : 'ARIA will only draft replies when you explicitly request them'}
          </p>
        </div>

        {/* Draft Timing */}
        {settings.auto_draft_enabled && (
          <div>
            <label
              className="flex items-center gap-2 text-sm font-medium mb-2"
              style={{ color: 'var(--text-primary)' }}
            >
              <Clock className="w-4 h-4" style={{ color: 'var(--text-secondary)' }} />
              Draft Timing
            </label>
            <div className="flex gap-2 ml-6">
              <button
                type="button"
                onClick={() => handleTimingChange('overnight')}
                className={cn(
                  'flex-1 py-2 px-3 rounded-lg border text-sm transition-colors text-left',
                  settings.draft_timing === 'overnight'
                    ? 'border-[var(--accent)] bg-[var(--accent)]/10 text-[var(--accent)]'
                    : 'border-[var(--border)] bg-[var(--bg-subtle)] text-[var(--text-primary)] hover:border-[var(--accent)]/50'
                )}
              >
                <div className="font-medium">Overnight</div>
                <div className="text-xs opacity-70">Ready for morning briefing</div>
              </button>
              <button
                type="button"
                onClick={() => handleTimingChange('realtime')}
                className={cn(
                  'flex-1 py-2 px-3 rounded-lg border text-sm transition-colors text-left',
                  settings.draft_timing === 'realtime'
                    ? 'border-[var(--accent)] bg-[var(--accent)]/10 text-[var(--accent)]'
                    : 'border-[var(--border)] bg-[var(--bg-subtle)] text-[var(--text-primary)] hover:border-[var(--accent)]/50'
                )}
              >
                <div className="font-medium">Real-time</div>
                <div className="text-xs opacity-70">Draft immediately on arrival</div>
              </button>
            </div>
          </div>
        )}

        {/* Divider */}
        <div className="border-t" style={{ borderColor: 'var(--border)' }} />

        {/* VIP Contacts */}
        <EmailListEditor
          label="VIP Contacts"
          description="VIP contacts always get immediate drafts and priority alerts, regardless of timing settings."
          icon={Star}
          items={settings.vip_contacts}
          onAdd={handleAddVip}
          onRemove={handleRemoveVip}
          placeholder="email@example.com"
          addLabel="Add VIP Contact"
        />

        {/* Excluded Senders */}
        <EmailListEditor
          label="Excluded Senders"
          description="Emails from these addresses or domains will never get auto-drafted. Supports wildcards (e.g., *@newsletter.com)."
          icon={Ban}
          items={settings.excluded_senders}
          onAdd={handleAddExclusion}
          onRemove={handleRemoveExclusion}
          placeholder="noreply@example.com or *@newsletter.com"
          addLabel="Add Exclusion"
        />

        {/* Divider */}
        <div className="border-t" style={{ borderColor: 'var(--border)' }} />

        {/* Email Provider */}
        <div>
          <label
            className="flex items-center gap-2 text-sm font-medium mb-2"
            style={{ color: 'var(--text-primary)' }}
          >
            <Wifi className="w-4 h-4" style={{ color: 'var(--text-secondary)' }} />
            Email Provider
          </label>
          <div
            className="ml-6 p-3 rounded-lg border"
            style={{ borderColor: 'var(--border)', backgroundColor: 'var(--bg-subtle)' }}
          >
            {settings.email_connected ? (
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <div
                    className="w-2 h-2 rounded-full"
                    style={{ backgroundColor: 'var(--success)' }}
                  />
                  <span className="text-sm" style={{ color: 'var(--text-primary)' }}>
                    {settings.email_provider === 'gmail' ? 'Gmail' : 'Outlook'} connected
                  </span>
                </div>
              </div>
            ) : settings.email_status && settings.email_provider ? (
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <AlertTriangle
                    className="w-3.5 h-3.5"
                    style={{ color: 'var(--warning, #f59e0b)' }}
                  />
                  <span className="text-sm" style={{ color: 'var(--text-primary)' }}>
                    {settings.email_provider === 'gmail' ? 'Gmail' : 'Outlook'} disconnected
                  </span>
                </div>
                <button
                  type="button"
                  onClick={() => navigate('/settings/integrations')}
                  className="text-xs font-medium hover:opacity-80 transition-opacity"
                  style={{ color: 'var(--accent)' }}
                >
                  Reconnect in Integrations &rarr;
                </button>
              </div>
            ) : (
              <div className="flex items-center gap-2">
                <div
                  className="w-2 h-2 rounded-full"
                  style={{ backgroundColor: 'var(--text-secondary)' }}
                />
                <span className="text-sm" style={{ color: 'var(--text-secondary)' }}>
                  No email provider connected
                </span>
              </div>
            )}
          </div>
        </div>

        {/* Learning Mode Status */}
        <div>
          <label
            className="flex items-center gap-2 text-sm font-medium mb-2"
            style={{ color: 'var(--text-primary)' }}
          >
            <GraduationCap className="w-4 h-4" style={{ color: 'var(--text-secondary)' }} />
            Learning Status
          </label>
          <div
            className="ml-6 p-3 rounded-lg border"
            style={{ borderColor: 'var(--border)', backgroundColor: 'var(--bg-subtle)' }}
          >
            {settings.learning_mode_active ? (
              <div>
                <div className="flex items-center gap-2 mb-1">
                  <div
                    className="w-2 h-2 rounded-full animate-pulse"
                    style={{ backgroundColor: 'var(--accent)' }}
                  />
                  <span className="text-sm font-medium" style={{ color: 'var(--text-primary)' }}>
                    Learning mode active
                  </span>
                </div>
                <p className="text-xs" style={{ color: 'var(--text-secondary)' }}>
                  ARIA is learning your writing style
                  {settings.learning_mode_day != null
                    ? ` (Day ${settings.learning_mode_day} of 7)`
                    : ''}
                </p>
              </div>
            ) : settings.email_connected ? (
              <div>
                <div className="flex items-center gap-2 mb-1">
                  <div
                    className="w-2 h-2 rounded-full"
                    style={{ backgroundColor: 'var(--success)' }}
                  />
                  <span className="text-sm font-medium" style={{ color: 'var(--text-primary)' }}>
                    Learning complete
                  </span>
                </div>
                <p className="text-xs" style={{ color: 'var(--text-secondary)' }}>
                  Full inbox drafting active
                </p>
              </div>
            ) : (
              <p className="text-xs" style={{ color: 'var(--text-secondary)' }}>
                Connect an email provider to begin learning your writing style.
              </p>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
