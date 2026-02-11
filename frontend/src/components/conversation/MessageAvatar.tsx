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
    return <div className="w-8 h-8 shrink-0" aria-hidden="true" />;
  }

  if (role === 'aria' || role === 'system') {
    return (
      <img
        src={ariaAvatarSrc}
        alt="ARIA"
        className="w-8 h-8 rounded-full object-cover shrink-0"
      />
    );
  }

  return <UserAvatar />;
}

function UserAvatar() {
  const { user } = useAuth();

  if (user?.avatar_url) {
    return (
      <img
        src={user.avatar_url}
        alt={user.full_name || 'User'}
        className="w-8 h-8 rounded-full object-cover shrink-0"
      />
    );
  }

  const initials = getInitials(user?.full_name ?? null);

  return (
    <div className="w-8 h-8 rounded-full bg-[#1C1C1E] flex items-center justify-center shrink-0">
      <span className="text-[#A1A1AA] text-xs font-medium select-none">
        {initials}
      </span>
    </div>
  );
}
