import { CheckSquare, AlertCircle, Clock } from "lucide-react";
import type { BriefingTask, BriefingTasks } from "@/api/briefings";
import { CollapsibleSection } from "@/components/ui/CollapsibleSection";

interface TasksSectionProps {
  tasks: BriefingTasks;
}

function TaskCard({
  task,
  variant,
}: {
  task: BriefingTask;
  variant: "overdue" | "today";
}) {
  const isOverdue = variant === "overdue";

  return (
    <div className="flex items-center gap-3 p-3 bg-slate-700/30 border border-slate-600/30 rounded-lg">
      <div
        className={`flex-shrink-0 p-2 rounded-lg ${
          isOverdue ? "bg-red-500/10" : "bg-slate-600/50"
        }`}
      >
        {isOverdue ? (
          <AlertCircle className="w-4 h-4 text-red-400" />
        ) : (
          <Clock className="w-4 h-4 text-slate-400" />
        )}
      </div>
      <div className="flex-1 min-w-0">
        <h4 className="text-white font-medium truncate">
          {task.title}
        </h4>
        {task.due_date && (
          <p className={`text-xs ${isOverdue ? "text-red-400" : "text-slate-400"}`}>
            {isOverdue ? "Overdue: " : "Due: "}
            {new Date(task.due_date).toLocaleDateString("en-US", {
              month: "short",
              day: "numeric",
            })}
          </p>
        )}
      </div>
      {task.priority && (
        <span
          className={`text-xs px-2 py-0.5 rounded-full ${
            task.priority === "high"
              ? "bg-red-500/20 text-red-400"
              : task.priority === "medium"
                ? "bg-amber-500/20 text-amber-400"
                : "bg-slate-600/50 text-slate-400"
          }`}
        >
          {task.priority}
        </span>
      )}
    </div>
  );
}

export function TasksSection({ tasks }: TasksSectionProps) {
  const { overdue, due_today } = tasks;
  const totalCount = overdue.length + due_today.length;
  const hasOverdue = overdue.length > 0;

  if (totalCount === 0) {
    return (
      <CollapsibleSection
        title="Tasks"
        icon={<CheckSquare className="w-5 h-5" />}
        badge={0}
        badgeColor="slate"
      >
        <div className="text-center py-6 text-slate-400">
          <CheckSquare className="w-8 h-8 mx-auto mb-2 opacity-50" />
          <p>No tasks for today</p>
        </div>
      </CollapsibleSection>
    );
  }

  return (
    <CollapsibleSection
      title="Tasks"
      icon={<CheckSquare className="w-5 h-5" />}
      badge={totalCount}
      badgeColor={hasOverdue ? "red" : "primary"}
    >
      <div className="space-y-4">
        {overdue.length > 0 && (
          <div>
            <h4 className="text-xs font-medium text-red-400 uppercase tracking-wider mb-2">
              Overdue
            </h4>
            <div className="space-y-2">
              {overdue.map((task) => (
                <TaskCard key={task.id} task={task} variant="overdue" />
              ))}
            </div>
          </div>
        )}

        {due_today.length > 0 && (
          <div>
            <h4 className="text-xs font-medium text-slate-400 uppercase tracking-wider mb-2">
              Due Today
            </h4>
            <div className="space-y-2">
              {due_today.map((task) => (
                <TaskCard key={task.id} task={task} variant="today" />
              ))}
            </div>
          </div>
        )}
      </div>
    </CollapsibleSection>
  );
}
