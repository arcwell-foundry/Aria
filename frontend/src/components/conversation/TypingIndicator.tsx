import ariaAvatarSrc from '@/assets/aria-avatar-transparent.png';

export function TypingIndicator() {
  return (
    <div
      className="flex items-start gap-3"
      data-aria-id="typing-indicator"
    >
      <img
        src={ariaAvatarSrc}
        alt="ARIA"
        className="w-8 h-8 rounded-full object-cover shrink-0"
      />
      <div className="border-l-2 border-accent pl-4 py-3">
        <div className="flex items-center gap-1.5">
          <div
            className="w-2 h-2 rounded-full bg-accent"
            style={{ animation: 'typing-bounce 1.4s infinite 0s' }}
          />
          <div
            className="w-2 h-2 rounded-full bg-accent"
            style={{ animation: 'typing-bounce 1.4s infinite 0.16s' }}
          />
          <div
            className="w-2 h-2 rounded-full bg-accent"
            style={{ animation: 'typing-bounce 1.4s infinite 0.32s' }}
          />
        </div>
      </div>
    </div>
  );
}
