import { ListChecks } from "lucide-react";
import { CollapsibleSection } from "@/components/ui/CollapsibleSection";

interface AgendaSectionProps {
  agenda: string[];
}

export function AgendaSection({ agenda }: AgendaSectionProps) {
  if (agenda.length === 0) {
    return null;
  }

  return (
    <CollapsibleSection
      title="Suggested Agenda"
      icon={<ListChecks className="w-5 h-5" />}
      badge={agenda.length}
      badgeColor="green"
    >
      <ol className="space-y-3">
        {agenda.map((item, i) => (
          <li key={i} className="flex items-start gap-4 p-3 bg-slate-700/30 border border-slate-600/30 rounded-lg">
            <span className="flex-shrink-0 w-7 h-7 bg-green-500/20 text-green-400 rounded-full flex items-center justify-center text-sm font-semibold">
              {i + 1}
            </span>
            <span className="text-slate-200 pt-0.5">{item}</span>
          </li>
        ))}
      </ol>
    </CollapsibleSection>
  );
}
