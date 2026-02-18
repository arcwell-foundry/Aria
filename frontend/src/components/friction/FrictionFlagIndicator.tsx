/**
 * FrictionFlagIndicator - Inline amber badge for "flag" level concerns
 *
 * Non-blocking informational indicator rendered within an ARIA message
 * when the Cognitive Friction Engine flags a minor concern.
 */

import { AlertTriangle } from 'lucide-react';

export interface FrictionFlagData {
  flag_message: string;
}

export function FrictionFlagIndicator({ data }: { data: FrictionFlagData }) {
  return (
    <div
      className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-md text-xs"
      style={{
        backgroundColor: 'rgba(184,149,106,0.1)',
        border: '1px solid rgba(184,149,106,0.3)',
        color: 'rgb(184,149,106)',
      }}
      data-aria-id="friction-flag-indicator"
    >
      <AlertTriangle className="w-3 h-3 shrink-0" />
      <span>{data.flag_message}</span>
    </div>
  );
}
