/**
 * SettingsPage - Multi-section settings with Coming Soon indicators
 *
 * Follows ARIA Design System v1.0:
 * - LIGHT THEME (content pages use light background)
 * - Header: "Settings" with status dot
 * - NO IntelPanel - full-width layout
 * - Sections: Profile, Integrations, ARIA Persona, Autonomy, Perception, Billing
 */

import { useParams, useNavigate } from 'react-router-dom';
import { cn } from '@/utils/cn';
import {
  ProfileSection,
  IntegrationsSection,
  AriaPersonaSection,
  AutonomySettings,
  PerceptionSection,
  BillingSection,
  PrivacySection,
  EmailSettingsSection,
} from '@/components/settings';

type SettingsSection = 'profile' | 'integrations' | 'aria' | 'email' | 'autonomy' | 'perception' | 'privacy' | 'billing';

const SECTIONS: { id: SettingsSection; label: string }[] = [
  { id: 'profile', label: 'Profile' },
  { id: 'integrations', label: 'Integrations' },
  { id: 'aria', label: 'ARIA Persona' },
  { id: 'email', label: 'Email Intelligence' },
  { id: 'autonomy', label: 'Autonomy' },
  { id: 'perception', label: 'Perception' },
  { id: 'privacy', label: 'Privacy' },
  { id: 'billing', label: 'Billing' },
];

function SectionContent({ section }: { section: SettingsSection }) {
  switch (section) {
    case 'profile':
      return <ProfileSection />;
    case 'integrations':
      return <IntegrationsSection />;
    case 'aria':
      return <AriaPersonaSection />;
    case 'email':
      return <EmailSettingsSection />;
    case 'autonomy':
      return <AutonomySettings />;
    case 'perception':
      return <PerceptionSection />;
    case 'privacy':
      return <PrivacySection />;
    case 'billing':
      return <BillingSection />;
    default:
      return <ProfileSection />;
  }
}

export function SettingsPage() {
  const { section } = useParams<{ section: string }>();
  const navigate = useNavigate();

  const activeSection = (section as SettingsSection) || 'profile';

  const handleSectionChange = (newSection: SettingsSection) => {
    navigate(`/settings/${newSection}`);
  };

  return (
    <div
      className="flex-1 flex flex-col h-full"
      style={{ backgroundColor: 'var(--bg-primary)' }}
    >
      <div className="flex-1 overflow-y-auto p-8">
        {/* Header */}
        <div className="mb-6">
          <div className="flex items-center gap-3 mb-1">
            <div
              className="w-2 h-2 rounded-full"
              style={{ backgroundColor: 'var(--success)' }}
            />
            <h1
              className="font-display text-2xl italic"
              style={{ color: 'var(--text-primary)' }}
            >
              Settings
            </h1>
          </div>
          <p
            className="text-sm ml-5"
            style={{ color: 'var(--text-secondary)' }}
          >
            Manage your account, preferences, and integrations.
          </p>
        </div>

        {/* Section Navigation */}
        <div className="mb-6">
          <nav className="flex flex-wrap gap-2">
            {SECTIONS.map((s) => (
              <button
                key={s.id}
                onClick={() => handleSectionChange(s.id)}
                className={cn(
                  'px-4 py-2 rounded-lg text-sm font-medium transition-colors',
                  activeSection === s.id
                    ? 'bg-[var(--accent)] text-white'
                    : 'border border-[var(--border)] hover:bg-[var(--bg-subtle)]'
                )}
                style={{
                  color: activeSection === s.id ? 'white' : 'var(--text-primary)',
                }}
              >
                {s.label}
              </button>
            ))}
          </nav>
        </div>

        {/* Section Content */}
        <div className="max-w-2xl">
          <SectionContent section={activeSection} />
        </div>

        {/* Enterprise Network Teaser */}
        <div
          className="mt-8 p-4 rounded-lg border border-dashed"
          style={{ borderColor: 'var(--border)', backgroundColor: 'var(--bg-subtle)' }}
        >
          <p
            className="text-sm font-medium mb-1"
            style={{ color: 'var(--text-primary)' }}
          >
            Enterprise Network
          </p>
          <p className="text-xs" style={{ color: 'var(--text-secondary)' }}>
            Connect your ARIA with your team's ARIAs for coordinated intelligence and shared workflows.
            <span
              className="ml-2 px-1.5 py-0.5 rounded text-xs"
              style={{
                backgroundColor: 'var(--bg-elevated)',
                color: 'var(--text-secondary)',
              }}
            >
              Coming 2027
            </span>
          </p>
        </div>
      </div>
    </div>
  );
}
