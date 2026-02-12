/**
 * Avatar - User/entity representation following ARIA Design System v1.0
 *
 * Design System Colors:
 * - Background: bg-subtle
 * - Text: text-secondary
 * - Status indicators: success, warning, critical
 *
 * @example
 * <Avatar name="John Doe" src="/avatar.jpg" />
 * <Avatar name="Jane" size="lg" status="online" />
 */

import { useState } from "react";

export interface AvatarProps {
  /** Image source URL */
  src?: string;
  /** Alt text for image, also used for initials fallback */
  name?: string;
  /** Size of the avatar */
  size?: "xs" | "sm" | "md" | "lg" | "xl";
  /** Status indicator */
  status?: "online" | "offline" | "busy" | "away";
  /** Show status indicator */
  showStatus?: boolean;
  /** Additional CSS classes */
  className?: string;
}

const sizeStyles = {
  xs: "w-6 h-6 text-xs",
  sm: "w-8 h-8 text-sm",
  md: "w-10 h-10 text-sm",
  lg: "w-12 h-12 text-base",
  xl: "w-16 h-16 text-lg",
};

const statusSizeStyles = {
  xs: "w-1.5 h-1.5",
  sm: "w-2 h-2",
  md: "w-2.5 h-2.5",
  lg: "w-3 h-3",
  xl: "w-4 h-4",
};

const statusStyles = {
  online: "bg-success",
  offline: "bg-secondary",
  busy: "bg-critical",
  away: "bg-warning",
};

function getInitials(name: string): string {
  const words = name.trim().split(/\s+/);
  if (words.length === 1) {
    return words[0].charAt(0).toUpperCase();
  }
  return (words[0].charAt(0) + words[words.length - 1].charAt(0)).toUpperCase();
}

function stringToColor(str: string): string {
  let hash = 0;
  for (let i = 0; i < str.length; i++) {
    hash = str.charCodeAt(i) + ((hash << 5) - hash);
  }
  const hue = hash % 360;
  return `hsl(${hue}, 40%, 50%)`;
}

export function Avatar({
  src,
  name = "",
  size = "md",
  status,
  showStatus = false,
  className = "",
}: AvatarProps) {
  const [imageState, setImageState] = useState({ src, error: false, loaded: false });

  // Reset state when src changes (React-recommended derived state pattern)
  if (imageState.src !== src) {
    setImageState({ src, error: false, loaded: false });
  }

  const imageError = imageState.error;
  const imageLoaded = imageState.loaded;
  const setImageError = (error: boolean) => setImageState((s) => ({ ...s, error }));
  const setImageLoaded = (loaded: boolean) => setImageState((s) => ({ ...s, loaded }));

  const showImage = src && !imageError;
  const showFallback = !showImage || !imageLoaded;
  const initials = name ? getInitials(name) : "?";
  const bgColor = name ? stringToColor(name) : "var(--bg-subtle)";

  return (
    <div className={`relative inline-flex ${className}`}>
      <div
        className={`
          relative rounded-full overflow-hidden
          flex items-center justify-center
          ${sizeStyles[size]}
        `.trim()}
        style={showFallback ? { backgroundColor: bgColor } : undefined}
      >
        {showImage && (
          <img
            src={src}
            alt={name}
            className="w-full h-full object-cover"
            onLoad={() => setImageLoaded(true)}
            onError={() => setImageError(true)}
          />
        )}
        {showFallback && (
          <span className="text-white font-medium select-none">
            {initials}
          </span>
        )}
      </div>
      {showStatus && status && (
        <span
          className={`
            absolute bottom-0 right-0 rounded-full ring-2 ring-elevated
            ${statusSizeStyles[size]}
            ${statusStyles[status]}
          `.trim()}
        />
      )}
    </div>
  );
}
