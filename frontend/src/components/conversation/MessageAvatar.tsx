import { useState } from 'react';
import ariaAvatarSrc from '@/assets/aria-avatar-transparent.png';
import { useAuth } from '@/hooks/useAuth';

interface MessageAvatarProps {
  role: 'aria' | 'user' | 'system';
  visible: boolean;
}

function getInitials(fullName: string | null): string {
  if (!fullName) return '?';
  const parts = fullName.trim().split(/\s+/);
  if (parts.length >= 2) {
    return (parts[0][0] + parts[parts.length - 1][0]).toUpperCase();
  }
  return parts[0][0].toUpperCase();
}

export function MessageAvatar({ role, visible }: MessageAvatarProps) {
  if (!visible) {
    return <div className="w-12 h-12 shrink-0" aria-hidden="true" />;
  }

  if (role === 'aria' || role === 'system') {
    return <AriaAvatar />;
  }

  return <UserAvatar />;
}

function AriaAvatar() {
  const [imageError, setImageError] = useState(false);

  if (imageError) {
    // Gradient fallback with "A" in Instrument Serif
    return (
      <div
        className="w-12 h-12 rounded-full shrink-0 flex items-center justify-center border border-white/10 animate-aria-breathing"
        style={{
          background: 'linear-gradient(135deg, #0F172A 0%, #2E66FF 100%)',
        }}
      >
        <span className="font-display italic text-white text-lg select-none">
          A
        </span>
      </div>
    );
  }

  return (
    <img
      src={ariaAvatarSrc}
      alt="ARIA"
      onError={() => setImageError(true)}
      className="w-12 h-12 rounded-full object-cover shrink-0 border border-white/10 animate-aria-breathing"
    />
  );
}

function UserAvatar() {
  const { user } = useAuth();

  if (user?.avatar_url) {
    return (
      <img
        src={user.avatar_url}
        alt={user.full_name || 'User'}
        className="w-12 h-12 rounded-full object-cover shrink-0 border border-white/10"
      />
    );
  }

  const initials = getInitials(user?.full_name ?? null);

  return (
    <div className="w-12 h-12 rounded-full bg-[#1C1C1E] flex items-center justify-center shrink-0 border border-white/10">
      <span className="text-[#A1A1AA] text-sm font-medium select-none">
        {initials}
      </span>
    </div>
  );
}
