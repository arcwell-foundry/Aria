import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import {
  CheckCircle,
  AlertCircle,
  ChevronDown,
  ChevronUp,
  Loader2,
  Building2,
} from "lucide-react";
import {
  confirmCompanyData,
  type CrossUserAccelerationResponse,
} from "@/api/onboarding";

interface CompanyMemoryDeltaConfirmationProps {
  data: CrossUserAccelerationResponse;
  showGaps?: boolean;
}

export function CompanyMemoryDeltaConfirmation({
  data,
  showGaps = false,
}: CompanyMemoryDeltaConfirmationProps) {
  const [isExpanded, setIsExpanded] = useState(false);
  const [corrections] = useState<Record<string, string>>({});
  const navigate = useNavigate();
  const queryClient = useQueryClient();

  const confirmMutation = useMutation({
    mutationFn: () =>
      confirmCompanyData({
        company_id: data.company_id ?? "",
        corrections,
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["onboarding"] });
      navigate("/dashboard");
    },
  });

  const handleConfirm = () => {
    confirmMutation.mutate();
  };

  const handleSomethingChanged = () => {
    // Navigate to company discovery step to make corrections
    navigate("/onboarding?step=company_discovery", {
      state: { editMode: true, companyId: data.company_id },
    });
  };

  // Get richness badge color and text
  const getRichnessBadge = () => {
    if (data.richness_score >= 70) {
      return {
        color: "text-[#5A7D60]",
        bgColor: "bg-[#5A7D60]/10",
        borderColor: "border-[#5A7D60]/20",
        text: "Rich company knowledge",
      };
    }
    if (data.richness_score >= 30) {
      return {
        color: "text-[#B8956A]",
        bgColor: "bg-[#B8956A]/10",
        borderColor: "border-[#B8956A]/20",
        text: "Moderate company knowledge",
      };
    }
    return {
      color: "text-[#6B7280]",
      bgColor: "bg-[#E2E0DC]/30",
      borderColor: "border-[#E2E0DC]/50",
      text: "Basic company knowledge",
    };
  };

  // Get high confidence facts (confidence >= 0.80)
  const highConfidenceFacts = data.facts
    .filter((fact) => fact.confidence >= 0.8)
    .sort((a, b) => b.confidence - a.confidence)
    .slice(0, 5);

  // Group remaining facts by domain
  const remainingFacts = data.facts.filter(
    (fact) => fact.confidence < 0.8 || !highConfidenceFacts.includes(fact)
  );

  const domainGroups = remainingFacts.reduce((acc, fact) => {
    if (!acc[fact.domain]) {
      acc[fact.domain] = [];
    }
    acc[fact.domain].push(fact);
    return acc;
  }, {} as Record<string, typeof data.facts>);

  const badge = getRichnessBadge();

  return (
    <div className="flex flex-col gap-6 max-w-2xl animate-in fade-in slide-in-from-bottom-4 duration-400">
      {/* Header */}
      <div className="flex flex-col gap-3">
        <h1 className="text-[32px] leading-[1.2] text-[#1A1D27] font-display">
          I already know quite a bit about {data.company_name || "your company"}
        </h1>
        <p className="font-sans text-[15px] leading-relaxed text-[#6B7280]">
          I've learned from your colleagues. Please confirm this information is still
          accurate.
        </p>
      </div>

      {/* Richness Badge */}
      <div
        className={`inline-flex items-center gap-2 px-4 py-2 rounded-lg border ${badge.bgColor} ${badge.borderColor} ${badge.color} w-fit`}
      >
        <Building2 size={16} strokeWidth={1.5} />
        <span className="font-sans text-[13px] font-medium">{badge.text}</span>
        <span className="font-sans text-[13px]">({data.richness_score}% rich)</span>
      </div>

      {/* High Confidence Facts */}
      {highConfidenceFacts.length > 0 && (
        <div className="bg-white border border-[#E2E0DC] rounded-xl p-6">
          <h2 className="font-sans text-[15px] font-medium text-[#1A1D27] mb-4">
            What I know about {data.company_name || "your company"}
          </h2>
          <div className="flex flex-col gap-3">
            {highConfidenceFacts.map((fact) => (
              <div
                key={fact.id}
                className="flex items-start gap-3 p-3 bg-[#FAFAF9] rounded-lg"
              >
                <CheckCircle
                  size={18}
                  strokeWidth={1.5}
                  className="text-[#5A7D60] shrink-0 mt-0.5"
                />
                <div className="flex flex-col gap-1 flex-1">
                  <p className="font-sans text-[14px] text-[#1A1D27] leading-relaxed">
                    {fact.fact}
                  </p>
                  <div className="flex items-center gap-2">
                    <span className="font-sans text-[11px] text-[#6B7280] uppercase tracking-wide">
                      {fact.domain}
                    </span>
                    <span className="text-[#E2E0DC]">•</span>
                    <span className="font-sans text-[11px] text-[#6B7280]">
                      {Math.round(fact.confidence * 100)}% confident
                    </span>
                  </div>
                </div>
              </div>
            ))}
          </div>

          {/* Expand/Collapse for remaining facts */}
          {Object.keys(domainGroups).length > 0 && (
            <button
              type="button"
              onClick={() => setIsExpanded(!isExpanded)}
              className="mt-4 font-sans text-[13px] text-[#5B6E8A] hover:text-[#4A5D79] transition-colors cursor-pointer flex items-center gap-2 focus:outline-none focus:ring-2 focus:ring-[#7B8EAA] focus:ring-offset-2 rounded px-2 py-1"
            >
              {isExpanded ? (
                <>
                  <ChevronUp size={16} strokeWidth={1.5} />
                  <span>Show less</span>
                </>
              ) : (
                <>
                  <ChevronDown size={16} strokeWidth={1.5} />
                  <span>Show {data.facts.length - highConfidenceFacts.length} more facts</span>
                </>
              )}
            </button>
          )}

          {/* Expanded Domain Groups */}
          {isExpanded &&
            Object.entries(domainGroups).map(([domain, facts]) => (
              <div key={domain} className="mt-4 pt-4 border-t border-[#E2E0DC]">
                <h3 className="font-sans text-[13px] font-medium text-[#6B7280] mb-3 capitalize">
                  {domain.replace(/_/g, " ")}
                </h3>
                <div className="flex flex-col gap-2">
                  {facts.map((fact) => (
                    <div
                      key={fact.id}
                      className="flex items-start gap-3 p-3 bg-[#FAFAF9] rounded-lg"
                    >
                      <CheckCircle
                        size={16}
                        strokeWidth={1.5}
                        className={`shrink-0 mt-0.5 ${
                          fact.confidence >= 0.8
                            ? "text-[#5A7D60]"
                            : fact.confidence >= 0.6
                            ? "text-[#B8956A]"
                            : "text-[#6B7280]"
                        }`}
                      />
                      <div className="flex flex-col gap-1 flex-1">
                        <p className="font-sans text-[13px] text-[#1A1D27] leading-relaxed">
                          {fact.fact}
                        </p>
                        <span className="font-sans text-[11px] text-[#6B7280]">
                          {Math.round(fact.confidence * 100)}% confident
                        </span>
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            ))}
        </div>
      )}

      {/* Gap Highlights (shown for partial skip case) */}
      {showGaps && data.recommendation === "partial" && (
        <div className="bg-[#FAFAF9] border border-[#B8956A]/30 rounded-xl p-5">
          <div className="flex items-start gap-3">
            <AlertCircle
              size={20}
              strokeWidth={1.5}
              className="text-[#B8956A] shrink-0 mt-0.5"
            />
            <div className="flex flex-col gap-2">
              <h3 className="font-sans text-[14px] font-medium text-[#1A1D27]">
                Some information may be outdated
              </h3>
              <p className="font-sans text-[13px] text-[#6B7280] leading-relaxed">
                Company knowledge is {data.richness_score}% complete. I'll learn more
                about your specific role and priorities as we continue.
              </p>
            </div>
          </div>
        </div>
      )}

      {/* ARIA Presence */}
      <div className="flex flex-col gap-2 bg-[#FAFAF9] border border-[#E2E0DC] rounded-xl p-5">
        <p className="font-sans text-[13px] text-[#1A1D27]">
          I'll use this company knowledge to help you from day one. If anything has
          changed, you can let me know.
        </p>
      </div>

      {/* Action Buttons */}
      <div className="flex flex-col sm:flex-row gap-3">
        <button
          type="button"
          onClick={handleConfirm}
          disabled={confirmMutation.isPending}
          className="flex-1 bg-[#5B6E8A] text-white rounded-xl px-6 py-3.5 font-sans font-medium text-[15px] hover:bg-[#4A5D79] active:bg-[#3D5070] transition-colors duration-150 focus:outline-none focus:ring-2 focus:ring-[#7B8EAA] focus:ring-offset-2 disabled:opacity-50 disabled:cursor-not-allowed cursor-pointer flex items-center justify-center gap-2 min-h-[52px]"
        >
          {confirmMutation.isPending ? (
            <>
              <Loader2 size={18} strokeWidth={1.5} className="animate-spin" />
              <span>Confirming...</span>
            </>
          ) : (
            "This looks correct"
          )}
        </button>
        <button
          type="button"
          onClick={handleSomethingChanged}
          disabled={confirmMutation.isPending}
          className="flex-1 bg-white text-[#1A1D27] border border-[#E2E0DC] rounded-xl px-6 py-3.5 font-sans font-medium text-[15px] hover:bg-[#FAFAF9] hover:border-[#5B6E8A] active:bg-[#E2E0DC] transition-colors duration-150 focus:outline-none focus:ring-2 focus:ring-[#7B8EAA] focus:ring-offset-2 disabled:opacity-50 disabled:cursor-not-allowed cursor-pointer flex items-center justify-center gap-2 min-h-[52px]"
        >
          Something's changed
        </button>
      </div>

      {/* Error Display */}
      {confirmMutation.error && (
        <div
          className="rounded-xl bg-[#FAFAF9] border border-[#945A5A]/30 px-5 py-4"
          role="alert"
          aria-live="polite"
        >
          <p className="font-sans text-[13px] text-[#945A5A]">
            Failed to confirm company data. Please try again.
          </p>
        </div>
      )}
    </div>
  );
}
