import { useState } from "react";
import { ThumbsUp, ThumbsDown } from "lucide-react";
import { useSubmitFeedback } from "@/hooks/useSkills";

interface SkillSatisfactionButtonsProps {
  executionId: string;
  initialFeedback?: "positive" | "negative" | null;
}

export function SkillSatisfactionButtons({
  executionId,
  initialFeedback = null,
}: SkillSatisfactionButtonsProps) {
  const [selected, setSelected] = useState<"positive" | "negative" | null>(
    initialFeedback
  );
  const submitFeedback = useSubmitFeedback();

  const handleFeedback = (feedback: "positive" | "negative") => {
    const newValue = selected === feedback ? null : feedback;
    setSelected(newValue);
    if (newValue) {
      submitFeedback.mutate({ executionId, feedback: newValue });
    }
  };

  return (
    <span className="inline-flex items-center gap-1 ml-2">
      <button
        onClick={() => handleFeedback("positive")}
        className={`p-1 rounded transition-colors ${
          selected === "positive"
            ? "text-success bg-success/10"
            : "text-slate-500 hover:text-success hover:bg-success/10"
        }`}
        title="Helpful"
      >
        <ThumbsUp className="w-3 h-3" />
      </button>
      <button
        onClick={() => handleFeedback("negative")}
        className={`p-1 rounded transition-colors ${
          selected === "negative"
            ? "text-critical bg-critical/10"
            : "text-slate-500 hover:text-critical hover:bg-critical/10"
        }`}
        title="Not helpful"
      >
        <ThumbsDown className="w-3 h-3" />
      </button>
    </span>
  );
}
