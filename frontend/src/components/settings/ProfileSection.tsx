/**
 * ProfileSection - User profile settings
 */

import { User, Camera } from 'lucide-react';
import { cn } from '@/utils/cn';

export function ProfileSection() {
  return (
    <div
      className="border rounded-lg p-6"
      style={{ borderColor: 'var(--border)', backgroundColor: 'var(--bg-elevated)' }}
    >
      <div className="flex items-center gap-2 mb-6">
        <User className="w-4 h-4" style={{ color: 'var(--text-secondary)' }} />
        <h3
          className="font-medium"
          style={{ color: 'var(--text-primary)' }}
        >
          Profile
        </h3>
      </div>

      <div className="space-y-4">
        {/* Avatar */}
        <div className="flex items-center gap-4">
          <div
            className="w-16 h-16 rounded-full flex items-center justify-center relative"
            style={{ backgroundColor: 'var(--bg-subtle)' }}
          >
            <User className="w-8 h-8" style={{ color: 'var(--text-secondary)' }} />
            <button
              className="absolute bottom-0 right-0 w-6 h-6 rounded-full flex items-center justify-center border"
              style={{
                backgroundColor: 'var(--bg-elevated)',
                borderColor: 'var(--border)',
              }}
              title="Upload photo"
            >
              <Camera className="w-3 h-3" style={{ color: 'var(--text-secondary)' }} />
            </button>
          </div>
          <div>
            <p className="text-sm font-medium" style={{ color: 'var(--text-primary)' }}>
              Profile Photo
            </p>
            <p className="text-xs" style={{ color: 'var(--text-secondary)' }}>
              JPG, PNG or GIF. Max 2MB.
            </p>
          </div>
        </div>

        {/* Name */}
        <div>
          <label
            className="block text-sm font-medium mb-1.5"
            style={{ color: 'var(--text-primary)' }}
          >
            Full Name
          </label>
          <input
            type="text"
            placeholder="Your name"
            className={cn(
              'w-full px-3 py-2 rounded-lg border text-sm',
              'border-[var(--border)] bg-[var(--bg-subtle)]',
              'focus:outline-none focus:ring-2 focus:ring-[var(--accent)]/30'
            )}
            style={{ color: 'var(--text-primary)' }}
          />
        </div>

        {/* Role */}
        <div>
          <label
            className="block text-sm font-medium mb-1.5"
            style={{ color: 'var(--text-primary)' }}
          >
            Role
          </label>
          <input
            type="text"
            placeholder="e.g., Sales Director"
            className={cn(
              'w-full px-3 py-2 rounded-lg border text-sm',
              'border-[var(--border)] bg-[var(--bg-subtle)]',
              'focus:outline-none focus:ring-2 focus:ring-[var(--accent)]/30'
            )}
            style={{ color: 'var(--text-primary)' }}
          />
        </div>

        {/* Company */}
        <div>
          <label
            className="block text-sm font-medium mb-1.5"
            style={{ color: 'var(--text-primary)' }}
          >
            Company
          </label>
          <input
            type="text"
            placeholder="Your company"
            className={cn(
              'w-full px-3 py-2 rounded-lg border text-sm',
              'border-[var(--border)] bg-[var(--bg-subtle)]',
              'focus:outline-none focus:ring-2 focus:ring-[var(--accent)]/30'
            )}
            style={{ color: 'var(--text-primary)' }}
          />
        </div>
      </div>
    </div>
  );
}
