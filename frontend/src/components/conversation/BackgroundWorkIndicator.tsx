import { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { wsManager } from '@/core/WebSocketManager';

interface ActiveTask {
  id: string;
  description: string;
}

const MAX_VISIBLE = 2;

export function BackgroundWorkIndicator() {
  const [tasks, setTasks] = useState<ActiveTask[]>([]);
  const navigate = useNavigate();

  useEffect(() => {
    const handleStarted = (payload: unknown) => {
      const data = payload as { id: string; description?: string };
      setTasks((prev) => {
        if (prev.some((t) => t.id === data.id)) return prev;
        return [
          ...prev,
          {
            id: data.id,
            description: data.description || 'Working on task...',
          },
        ];
      });
    };

    const handleCompleted = (payload: unknown) => {
      const data = payload as { id: string };
      setTasks((prev) => prev.filter((t) => t.id !== data.id));
    };

    wsManager.on('agent.started', handleStarted);
    wsManager.on('agent.completed', handleCompleted);

    return () => {
      wsManager.off('agent.started', handleStarted as (payload: unknown) => void);
      wsManager.off('agent.completed', handleCompleted as (payload: unknown) => void);
    };
  }, []);

  if (tasks.length === 0) return null;

  const visible = tasks.slice(0, MAX_VISIBLE);
  const remaining = tasks.length - MAX_VISIBLE;

  return (
    <button
      type="button"
      onClick={() => navigate('/actions')}
      className="w-full px-6 py-2 bg-[#111318] border-t border-[#1A1A2E] text-left transition-colors hover:bg-[#161B2E] cursor-pointer"
      data-aria-id="background-work-indicator"
    >
      <div className="space-y-1">
        {visible.map((task) => (
          <div key={task.id} className="flex items-center gap-2">
            <span className="text-accent text-xs shrink-0">&#10022;</span>
            <span className="text-xs text-[#8B8FA3] truncate">
              {task.description}
            </span>
          </div>
        ))}
        {remaining > 0 && (
          <div className="text-xs text-[#8B8FA3] pl-5">
            +{remaining} more task{remaining !== 1 ? 's' : ''}
          </div>
        )}
      </div>
    </button>
  );
}
