import { AlertTriangle, Lightbulb } from "lucide-react";
import { CollapsibleSection } from "@/components/ui/CollapsibleSection";

interface RisksOpportunitiesSectionProps {
  items: string[];
}

export function RisksOpportunitiesSection({ items }: RisksOpportunitiesSectionProps) {
  if (items.length === 0) {
    return null;
  }

  // Simple heuristic: items with warning keywords are risks, others are opportunities
  const riskKeywords = ["risk", "concern", "challenge", "issue", "problem", "caution", "careful", "avoid", "don't", "not"];

  const categorized = items.map((item) => {
    const lowerItem = item.toLowerCase();
    const isRisk = riskKeywords.some((keyword) => lowerItem.includes(keyword));
    return { text: item, isRisk };
  });

  return (
    <CollapsibleSection
      title="Risks & Opportunities"
      icon={<Lightbulb className="w-5 h-5" />}
      badge={items.length}
      badgeColor="amber"
    >
      <div className="space-y-3">
        {categorized.map((item, i) => (
          <div
            key={i}
            className={`flex items-start gap-3 p-3 rounded-lg border ${
              item.isRisk
                ? "bg-critical/10 border-critical/20"
                : "bg-success/10 border-success/20"
            }`}
          >
            {item.isRisk ? (
              <AlertTriangle className="w-5 h-5 text-critical flex-shrink-0 mt-0.5" />
            ) : (
              <Lightbulb className="w-5 h-5 text-success flex-shrink-0 mt-0.5" />
            )}
            <span className={item.isRisk ? "text-red-200" : "text-emerald-200"}>
              {item.text}
            </span>
          </div>
        ))}
      </div>
    </CollapsibleSection>
  );
}
