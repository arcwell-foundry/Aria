export interface FrictionIndicatorProps {
  level: 'flag' | 'challenge' | 'refuse';
  reasoning?: string;
}

const LEVEL_STYLES: Record<
  FrictionIndicatorProps['level'],
  { bg: string; text: string; label: string }
> = {
  flag: {
    bg: 'bg-blue-500/10',
    text: 'text-blue-400',
    label: 'Flagged',
  },
  challenge: {
    bg: 'bg-amber-500/10',
    text: 'text-amber-400',
    label: 'Challenged',
  },
  refuse: {
    bg: 'bg-red-500/10',
    text: 'text-red-400',
    label: 'Refused',
  },
};

function SmallIcon({ level }: { level: FrictionIndicatorProps['level'] }) {
  const cls = 'h-3 w-3 shrink-0';
  switch (level) {
    case 'flag':
      return (
        <svg className={cls} viewBox="0 0 20 20" fill="currentColor">
          <path
            fillRule="evenodd"
            d="M18 10a8 8 0 11-16 0 8 8 0 0116 0zm-7-4a1 1 0 11-2 0 1 1 0 012 0zM9 9a.75.75 0 000 1.5h.253a.25.25 0 01.244.304l-.459 2.066A1.75 1.75 0 0010.747 15H11a.75.75 0 000-1.5h-.253a.25.25 0 01-.244-.304l.459-2.066A1.75 1.75 0 009.253 9H9z"
            clipRule="evenodd"
          />
        </svg>
      );
    case 'challenge':
      return (
        <svg className={cls} viewBox="0 0 20 20" fill="currentColor">
          <path
            fillRule="evenodd"
            d="M8.485 2.495c.673-1.167 2.357-1.167 3.03 0l6.28 10.875c.673 1.167-.17 2.625-1.516 2.625H3.72c-1.347 0-2.189-1.458-1.515-2.625L8.485 2.495zM10 5a.75.75 0 01.75.75v3.5a.75.75 0 01-1.5 0v-3.5A.75.75 0 0110 5zm0 9a1 1 0 100-2 1 1 0 000 2z"
            clipRule="evenodd"
          />
        </svg>
      );
    case 'refuse':
      return (
        <svg className={cls} viewBox="0 0 20 20" fill="currentColor">
          <path
            fillRule="evenodd"
            d="M10 18a8 8 0 100-16 8 8 0 000 16zM8.28 7.22a.75.75 0 00-1.06 1.06L8.94 10l-1.72 1.72a.75.75 0 101.06 1.06L10 11.06l1.72 1.72a.75.75 0 101.06-1.06L11.06 10l1.72-1.72a.75.75 0 00-1.06-1.06L10 8.94 8.28 7.22z"
            clipRule="evenodd"
          />
        </svg>
      );
  }
}

export function FrictionIndicator({ level, reasoning }: FrictionIndicatorProps) {
  const style = LEVEL_STYLES[level];

  return (
    <span
      className={`inline-flex items-center gap-1 rounded-full px-1.5 py-0.5 text-xs ${style.bg} ${style.text}`}
      title={reasoning}
    >
      <SmallIcon level={level} />
      {style.label}
    </span>
  );
}
