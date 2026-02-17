/**
 * AriaPersonaSection - ARIA persona and communication preferences
 *
 * Includes name, communication style, and briefing delivery settings.
 */

import { useState, useEffect } from 'react';
import { Bot, MessageSquare, Loader2 } from 'lucide-react';
import { cn } from '@/utils/cn';
import { getPreferences, updatePreferences } from '@/api/preferences';
import type { DefaultTone, BriefingMode, BriefingDuration } from '@/api/preferences';
import { BriefingDeliverySection } from './BriefingDeliverySection';

const TONE_OPTIONS: { value: DefaultTone; label: string; description: string }[] = [
  { value: 'formal', label: 'Professional', description: 'Structured and precise communication' },
  { value: 'friendly', label: 'Conversational', description: 'Warm and approachable tone' },
  { value: 'urgent', label: 'Direct', description: 'Concise and action-oriented' },
];

interface PersonaState {
  name: string;
  tone: DefaultTone;
  briefingMode: BriefingMode;
  briefingTime: string;
  briefingDuration: BriefingDuration;
  timezone: string;
}

export function AriaPersonaSection() {
  const [isLoading, setIsLoading] = useState(true);
  const [isSaving, setIsSaving] = useState(false);
  const [state, setState] = useState<PersonaState>({
    name: '',
    tone: 'friendly',
    briefingMode: 'video',
    briefingTime: '08:00',
    briefingDuration: 5,
    timezone: 'America/New_York',
  });

  // Load preferences on mount
  useEffect(() => {
    let mounted = true;

    async function loadPreferences() {
      try {
        const prefs = await getPreferences();
        if (mounted) {
          setState({
            name: '', // Name comes from profile, not preferences
            tone: prefs.default_tone || 'friendly',
            briefingMode: prefs.briefing_mode || 'video',
            briefingTime: prefs.briefing_time || '08:00',
            briefingDuration: prefs.briefing_duration || 5,
            timezone: prefs.timezone || 'America/New_York',
          });
        }
      } catch (error) {
        console.error('Failed to load preferences:', error);
      } finally {
        if (mounted) {
          setIsLoading(false);
        }
      }
    }

    loadPreferences();

    return () => {
      mounted = false;
    };
  }, []);

  // Handle field changes
  const handleChange = async (field: string, value: string | number) => {
    setState((prev) => ({ ...prev, [field]: value }));

    // Persist immediately
    setIsSaving(true);
    try {
      await updatePreferences({
        [field]: value,
      });
    } catch (error) {
      console.error('Failed to save preference:', error);
    } finally {
      setIsSaving(false);
    }
  };

  // Handle tone change
  const handleToneChange = async (tone: DefaultTone) => {
    setState((prev) => ({ ...prev, tone }));
    setIsSaving(true);
    try {
      await updatePreferences({ default_tone: tone });
    } catch (error) {
      console.error('Failed to save tone:', error);
    } finally {
      setIsSaving(false);
    }
  };

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

  return (
    <div
      className="border rounded-lg p-6"
      style={{ borderColor: 'var(--border)', backgroundColor: 'var(--bg-elevated)' }}
    >
      <div className="flex items-center justify-between mb-6">
        <div className="flex items-center gap-2">
          <Bot className="w-4 h-4" style={{ color: 'var(--text-secondary)' }} />
          <h3
            className="font-medium"
            style={{ color: 'var(--text-primary)' }}
          >
            ARIA Persona
          </h3>
        </div>
        {isSaving && (
          <span className="text-xs" style={{ color: 'var(--text-secondary)' }}>
            Saving...
          </span>
        )}
      </div>

      <div className="space-y-6">
        {/* Name preference */}
        <div>
          <label
            className="block text-sm font-medium mb-1.5"
            style={{ color: 'var(--text-primary)' }}
          >
            How should ARIA address you?
          </label>
          <input
            type="text"
            placeholder="Your preferred name"
            value={state.name}
            onChange={(e) => setState((prev) => ({ ...prev, name: e.target.value }))}
            onBlur={() => handleChange('name', state.name)}
            className={cn(
              'w-full px-3 py-2 rounded-lg border text-sm',
              'border-[var(--border)] bg-[var(--bg-subtle)]',
              'focus:outline-none focus:ring-2 focus:ring-[var(--accent)]/30'
            )}
            style={{ color: 'var(--text-primary)' }}
          />
        </div>

        {/* Communication style */}
        <div>
          <label
            className="block text-sm font-medium mb-3"
            style={{ color: 'var(--text-primary)' }}
          >
            <MessageSquare className="w-4 h-4 inline-block mr-2" />
            Communication Style
          </label>
          <div className="space-y-2">
            {TONE_OPTIONS.map((option) => (
              <label
                key={option.value}
                className={cn(
                  'flex items-start gap-3 p-3 rounded-lg border cursor-pointer transition-colors',
                  state.tone === option.value
                    ? 'border-[var(--accent)] bg-[var(--accent)]/5'
                    : 'hover:border-[var(--accent)]/50'
                )}
                style={{ borderColor: state.tone === option.value ? undefined : 'var(--border)', backgroundColor: state.tone === option.value ? undefined : 'var(--bg-subtle)' }}
              >
                <input
                  type="radio"
                  name="tone"
                  value={option.value}
                  checked={state.tone === option.value}
                  onChange={() => handleToneChange(option.value)}
                  className="mt-1"
                />
                <div>
                  <p className="text-sm font-medium" style={{ color: 'var(--text-primary)' }}>
                    {option.label}
                  </p>
                  <p className="text-xs" style={{ color: 'var(--text-secondary)' }}>
                    {option.description}
                  </p>
                </div>
              </label>
            ))}
          </div>
        </div>

        {/* Briefing Delivery Section */}
        <BriefingDeliverySection
          briefingMode={state.briefingMode}
          briefingTime={state.briefingTime}
          briefingDuration={state.briefingDuration}
          timezone={state.timezone}
          onChange={handleChange}
        />
      </div>
    </div>
  );
}
