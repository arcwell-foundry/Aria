/**
 * FrictionChallengeCard - Amber-bordered card for "challenge" level pushback
 *
 * Rendered when ARIA's Cognitive Friction Engine determines the user's
 * request warrants pushback. Shows ARIA's concern and lets the user
 * proceed anyway or defer to ARIA's recommendation.
 */

import { useState } from 'react';
import { AlertTriangle, Check, Loader2 } from 'lucide-react';
import { wsManager } from '@/core/WebSocketManager';
import { WS_EVENTS } from '@/types/chat';

export interface FrictionChallengeData {
  challenge_id: string;
  user_message: string;
  original_request: string;
  proceed_if_confirmed: boolean;
  conversation_id?: string;
}

type ChallengeStatus = 'pending' | 'confirming' | 'confirmed' | 'deferring' | 'deferred';

const AMBER = 'rgb(184,149,106)';
const AMBER_BG = 'rgba(184,149,106,0.05)';
const AMBER_BORDER = 'rgba(184,149,106,0.5)';

export function FrictionChallengeCard({ data }: { data: FrictionChallengeData }) {
  const [status, setStatus] = useState<ChallengeStatus>('pending');

  const isResolved = status === 'confirmed' || status === 'deferred';

  const sendDecision = (action: 'proceed' | 'defer') => {
    wsManager.send(WS_EVENTS.USER_CONFIRM_FRICTION, {
      challenge_id: data.challenge_id,
      action,
      conversation_id: data.conversation_id,
    });
  };

  const handleProceed = () => {
    setStatus('confirming');
    sendDecision('proceed');
    setStatus('confirmed');
  };

  const handleDefer = () => {
    setStatus('deferring');
    sendDecision('defer');
    setStatus('deferred');
  };

  return (
    <div
      className="rounded-lg border overflow-hidden"
      style={{
        borderColor: isResolved ? 'var(--border)' : AMBER_BORDER,
        backgroundColor: 'var(--bg-elevated)',
      }}
      data-aria-id="friction-challenge-card"
      data-challenge-id={data.challenge_id}
    >
      {/* Header */}
      <div
        className="flex items-center gap-2 px-4 py-2.5"
        style={{
          backgroundColor: isResolved ? 'var(--bg-subtle)' : AMBER_BG,
          borderBottom: '1px solid var(--border)',
        }}
      >
        <AlertTriangle
          className="w-3.5 h-3.5"
          style={{ color: isResolved ? 'var(--text-secondary)' : AMBER }}
        />
        <span
          className="text-xs font-medium"
          style={{ color: 'var(--text-primary)' }}
        >
          ARIA has a concern
        </span>
      </div>

      {/* Body */}
      <div className="px-4 py-3">
        <blockquote
          className="text-sm italic mb-3 pl-3"
          style={{
            borderLeft: `2px solid ${isResolved ? 'var(--border)' : AMBER}`,
            color: 'var(--text-primary)',
          }}
        >
          {data.user_message}
        </blockquote>

        {/* Resolved state */}
        {status === 'confirmed' && (
          <div
            className="flex items-center gap-2 text-xs"
            style={{ color: 'var(--text-secondary)' }}
          >
            <Check className="w-3.5 h-3.5" />
            Proceeding as requested
          </div>
        )}

        {status === 'deferred' && (
          <div
            className="flex items-center gap-2 text-xs"
            style={{ color: AMBER }}
          >
            <Check className="w-3.5 h-3.5" />
            ARIA&rsquo;s recommendation followed
          </div>
        )}

        {/* Pending state — buttons */}
        {!isResolved && (
          <div className="flex items-center gap-2">
            <button
              type="button"
              disabled={status === 'confirming' || status === 'deferring'}
              onClick={handleDefer}
              className="flex items-center gap-1.5 px-3 py-1.5 rounded text-xs font-medium text-white transition-opacity hover:opacity-90 disabled:opacity-50"
              style={{ backgroundColor: 'var(--accent)' }}
            >
              {status === 'deferring' ? (
                <Loader2 className="w-3 h-3 animate-spin" />
              ) : null}
              Let ARIA Handle It
            </button>
            <button
              type="button"
              disabled={status === 'confirming' || status === 'deferring'}
              onClick={handleProceed}
              className="flex items-center gap-1.5 px-3 py-1.5 rounded text-xs font-medium border transition-opacity hover:opacity-90 disabled:opacity-50"
              style={{
                borderColor: 'var(--border)',
                color: 'var(--text-secondary)',
                backgroundColor: 'transparent',
              }}
            >
              {status === 'confirming' ? (
                <Loader2 className="w-3 h-3 animate-spin" />
              ) : null}
              Proceed Anyway
            </button>
          </div>
        )}
      </div>
    </div>
  );
}
