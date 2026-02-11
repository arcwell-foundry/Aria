interface TimeDividerProps {
  timestamp: string;
}

function formatDividerTime(timestamp: string): string {
  const date = new Date(timestamp);
  const now = new Date();
  const isToday =
    date.getFullYear() === now.getFullYear() &&
    date.getMonth() === now.getMonth() &&
    date.getDate() === now.getDate();

  const timeStr = date.toLocaleTimeString([], {
    hour: 'numeric',
    minute: '2-digit',
  });

  if (isToday) {
    return `Today, ${timeStr}`;
  }

  const monthStr = date.toLocaleDateString([], {
    month: 'short',
    day: 'numeric',
  });

  return `${monthStr}, ${timeStr}`;
}

export function TimeDivider({ timestamp }: TimeDividerProps) {
  return (
    <div className="flex items-center gap-3 py-2" data-aria-id="time-divider">
      <div className="flex-1 h-px bg-[#1A1A2E]" />
      <span className="font-sans text-xs text-[#555770] whitespace-nowrap select-none">
        {formatDividerTime(timestamp)}
      </span>
      <div className="flex-1 h-px bg-[#1A1A2E]" />
    </div>
  );
}
