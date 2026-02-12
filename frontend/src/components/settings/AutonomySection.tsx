/**
 * AutonomySection - ARIA autonomy level settings
 */

import { Shield, Zap } from 'lucide-react';
import { ComingSoonIndicator } from './ComingSoonIndicator';

const AUTONOMY_LEVELS = [
  {
    id: 'guided',
    name: 'Guided',
    description: 'ARIA suggests actions, you approve everything',
    recommended: true,
  },
  {
    id: 'assisted',
    name: 'Assisted',
    description: 'ARIA executes low-risk actions automatically',
    recommended: false,
  },
  {
    id: 'autonomous',
    name: 'Autonomous',
    description: 'ARIA manages most tasks independently',
    recommended: false,
  },
];

export function AutonomySection() {
  return (
    <div
      className="border rounded-lg p-6"
      style={{ borderColor: 'var(--border)', backgroundColor: 'var(--bg-elevated)' }}
    >
      <div className="flex items-center gap-2 mb-6">
        <Shield className="w-4 h-4" style={{ color: 'var(--text-secondary)' }} />
        <h3
          className="font-medium"
          style={{ color: 'var(--text-primary)' }}
        >
          Autonomy Level
        </h3>
      </div>

      <div className="space-y-6">
        {/* Current level display */}
        <div
          className="p-4 rounded-lg border"
          style={{
            borderColor: 'var(--accent)',
            backgroundColor: 'var(--accent)/10',
          }}
        >
          <div className="flex items-center gap-2 mb-2">
            <Zap className="w-4 h-4" style={{ color: 'var(--accent)' }} />
            <span className="text-sm font-medium" style={{ color: 'var(--text-primary)' }}>
              Current Level: Guided
            </span>
          </div>
          <p className="text-xs" style={{ color: 'var(--text-secondary)' }}>
            ARIA will suggest actions and wait for your approval before executing. This is the safest mode for getting started.
          </p>
        </div>

        {/* Level options (read-only for now) */}
        <div className="space-y-2">
          {AUTONOMY_LEVELS.map((level) => (
            <div
              key={level.id}
              className="flex items-center justify-between p-3 rounded-lg border"
              style={{
                borderColor: level.id === 'guided' ? 'var(--accent)' : 'var(--border)',
                backgroundColor: level.id === 'guided' ? 'var(--accent)/5' : 'var(--bg-subtle)',
              }}
            >
              <div>
                <div className="flex items-center gap-2">
                  <p className="text-sm font-medium" style={{ color: 'var(--text-primary)' }}>
                    {level.name}
                  </p>
                  {level.recommended && (
                    <span
                      className="px-1.5 py-0.5 rounded text-xs"
                      style={{
                        backgroundColor: 'var(--accent)',
                        color: 'white',
                      }}
                    >
                      Current
                    </span>
                  )}
                </div>
                <p className="text-xs" style={{ color: 'var(--text-secondary)' }}>
                  {level.description}
                </p>
              </div>
            </div>
          ))}
        </div>

        {/* Coming Soon: Full Autonomy */}
        <ComingSoonIndicator
          title="Full Autonomy"
          description="Let ARIA operate independently, managing your entire workflow without approval."
          availableDate="Q3 2026"
        />
      </div>
    </div>
  );
}
