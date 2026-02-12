/**
 * BillingSection - Subscription and billing information
 */

import { CreditCard, Calendar, Users, ArrowUpRight } from 'lucide-react';

export function BillingSection() {
  return (
    <div
      className="border rounded-lg p-6"
      style={{ borderColor: 'var(--border)', backgroundColor: 'var(--bg-elevated)' }}
    >
      <div className="flex items-center gap-2 mb-6">
        <CreditCard className="w-4 h-4" style={{ color: 'var(--text-secondary)' }} />
        <h3
          className="font-medium"
          style={{ color: 'var(--text-primary)' }}
        >
          Billing
        </h3>
      </div>

      <div className="space-y-6">
        {/* Current plan */}
        <div
          className="p-4 rounded-lg border"
          style={{
            borderColor: 'var(--accent)',
            backgroundColor: 'var(--accent)/5',
          }}
        >
          <div className="flex items-center justify-between mb-3">
            <div>
              <p className="text-lg font-medium" style={{ color: 'var(--text-primary)' }}>
                Professional
              </p>
              <p className="text-sm" style={{ color: 'var(--text-secondary)' }}>
                $1,500/month per seat
              </p>
            </div>
            <span
              className="px-2 py-1 rounded-full text-xs font-medium"
              style={{
                backgroundColor: 'var(--success)',
                color: 'white',
              }}
            >
              Active
            </span>
          </div>

          <div className="flex items-center gap-4 text-xs" style={{ color: 'var(--text-secondary)' }}>
            <div className="flex items-center gap-1">
              <Users className="w-3.5 h-3.5" />
              1 seat
            </div>
            <div className="flex items-center gap-1">
              <Calendar className="w-3.5 h-3.5" />
              Renews Feb 1, 2026
            </div>
          </div>
        </div>

        {/* Plan details */}
        <div className="space-y-2">
          <p
            className="text-xs font-medium uppercase tracking-wider"
            style={{ color: 'var(--text-secondary)' }}
          >
            Plan Features
          </p>
          <ul className="space-y-2">
            {[
              'Unlimited goals and agents',
              'Full lead intelligence pipeline',
              'AI-drafted communications',
              'Competitive battle cards',
              'Meeting briefings',
              'Email integration',
            ].map((feature, i) => (
              <li
                key={i}
                className="flex items-center gap-2 text-sm"
                style={{ color: 'var(--text-primary)' }}
              >
                <div
                  className="w-1.5 h-1.5 rounded-full"
                  style={{ backgroundColor: 'var(--accent)' }}
                />
                {feature}
              </li>
            ))}
          </ul>
        </div>

        {/* Upgrade button */}
        <div className="pt-4 border-t" style={{ borderColor: 'var(--border)' }}>
          <button
            className="w-full flex items-center justify-center gap-2 px-4 py-2.5 rounded-lg text-sm font-medium transition-colors"
            style={{
              backgroundColor: 'var(--bg-subtle)',
              color: 'var(--text-primary)',
              border: '1px solid var(--border)',
            }}
          >
            <ArrowUpRight className="w-4 h-4" />
            Manage Subscription
          </button>
        </div>
      </div>
    </div>
  );
}
