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
    <div className="flex items-center gap-4 my-6">
      <div className="flex-1 h-px bg-[#2A2F42]" />
      <span className="font-mono text-[11px] font-medium text-[#8B9DC3] tracking-wide">
        {formatDividerTime(timestamp)}
      </span>
      <div className="flex-1 h-px bg-[#2A2F42]" />
    </div>
  );
}
