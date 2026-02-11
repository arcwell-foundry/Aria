import { useState, useEffect, useCallback } from "react";
import { ArrowRight, CheckCircle2, Circle, Loader2, Sparkles, Zap } from "lucide-react";
import {
  getSkillRecommendations,
  getOnboardingState,
  installRecommendedSkills,
  completeStep,
} from "@/api/onboarding";

interface SkillsConfigurationStepProps {
  onComplete: () => void;
  companyType?: string;
  userRole?: string;
}

interface SkillRecommendation {
  skill_id: string;
  trust_level: string;
}

interface SkillRecommendationsResponse {
  recommendations: SkillRecommendation[];
  message: string | null;
}

// Human-readable skill names and descriptions
const SKILL_INFO: Record<string, { name: string; description: string }> = {
  "clinical-trial-analysis": {
    name: "Clinical Trial Analysis",
    description: "Analyze clinical trial data and outcomes for research insights",
  },
  "regulatory-monitor-rmat": {
    name: "Regulatory Monitor (RMAT)",
    description: "Track RMAT designations and regulatory pathways for cell/gene therapies",
  },
  "pubmed-research": {
    name: "PubMed Research",
    description: "Search and analyze scientific literature from PubMed",
  },
  "patient-advocacy-tracking": {
    name: "Patient Advocacy Tracking",
    description: "Monitor patient advocacy groups and engagement opportunities",
  },
  "competitive-positioning": {
    name: "Competitive Positioning",
    description: "Analyze competitive landscape and market positioning",
  },
  "manufacturing-capacity-analysis": {
    name: "Manufacturing Capacity Analysis",
    description: "Track and analyze manufacturing capacity and utilization",
  },
  "quality-compliance-monitor": {
    name: "Quality Compliance Monitor",
    description: "Monitor quality metrics and regulatory compliance status",
  },
  "rfp-response-helper": {
    name: "RFP Response Helper",
    description: "Assist in drafting responses to Requests for Proposals",
  },
  "market-analysis": {
    name: "Market Analysis",
    description: "Analyze market trends, sizing, and opportunities",
  },
  "kol-mapping": {
    name: "KOL Mapping",
    description: "Identify and track Key Opinion Leaders in therapeutic areas",
  },
  "patent-monitor": {
    name: "Patent Monitor",
    description: "Track patent filings and intellectual property landscape",
  },
  "formulary-tracking": {
    name: "Formulary Tracking",
    description: "Monitor insurance formulary status and coverage decisions",
  },
  "investor-relations-monitor": {
    name: "Investor Relations Monitor",
    description: "Track investor communications and market sentiment",
  },
  "site-identification": {
    name: "Site Identification",
    description: "Identify and evaluate clinical trial sites",
  },
  "protocol-analysis": {
    name: "Protocol Analysis",
    description: "Analyze clinical trial protocols and requirements",
  },
  "regulatory-monitor": {
    name: "Regulatory Monitor",
    description: "Track regulatory submissions and approvals",
  },
  "competitive-pricing": {
    name: "Competitive Pricing",
    description: "Analyze pricing strategies and competitive benchmarks",
  },
  "regulatory-monitor-510k": {
    name: "Regulatory Monitor (510k)",
    description: "Track FDA 510(k) submissions and clearances",
  },
  "payer-landscape": {
    name: "Payer Landscape",
    description: "Analyze insurance payer coverage and reimbursement policies",
  },
};

export function SkillsConfigurationStep({
  onComplete,
  companyType = "",
  userRole = "",
}: SkillsConfigurationStepProps) {
  const [recommendations, setRecommendations] = useState<SkillRecommendationsResponse | null>(null);
  const [selectedSkills, setSelectedSkills] = useState<Set<string>>(new Set());
  const [isLoading, setIsLoading] = useState(true);
  const [isInstalling, setIsInstalling] = useState(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  useEffect(() => {
    loadRecommendations();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [companyType, userRole]);

  const loadRecommendations = useCallback(async () => {
    setIsLoading(true);
    setErrorMessage(null);
    try {
      // Load recommendations and check for previously saved selections in parallel
      const [response, onboardingState] = await Promise.all([
        getSkillRecommendations({
          company_type: companyType,
          role: userRole,
        }),
        getOnboardingState().catch(() => null),
      ]);
      setRecommendations(response);

      // Restore previously configured skills on revisit
      const stepData = onboardingState?.state?.step_data as Record<string, unknown> | undefined;
      const firstGoalData = stepData?.first_goal as Record<string, unknown> | undefined;
      const savedSkills = firstGoalData?.skills_configured as string[] | undefined;

      if (savedSkills && savedSkills.length > 0) {
        setSelectedSkills(new Set(savedSkills));
      } else {
        // Pre-select all recommended skills for first visit
        setSelectedSkills(new Set(response.recommendations.map((r) => r.skill_id)));
      }
    } catch {
      setErrorMessage("Failed to load skill recommendations. Please try again.");
    } finally {
      setIsLoading(false);
    }
  }, [companyType, userRole]);

  const toggleSkill = (skillId: string) => {
    const newSelection = new Set(selectedSkills);
    if (newSelection.has(skillId)) {
      newSelection.delete(skillId);
    } else {
      newSelection.add(skillId);
    }
    setSelectedSkills(newSelection);
  };

  const handleConfirm = async () => {
    setIsInstalling(true);
    setErrorMessage(null);
    try {
      const skillIds = Array.from(selectedSkills);
      await installRecommendedSkills({ skill_ids: skillIds });
      await completeStep("first_goal", {
        skills_configured: skillIds,
      });
      onComplete();
    } catch {
      setErrorMessage("Failed to install skills. Please try again.");
    } finally {
      setIsInstalling(false);
    }
  };

  const handleSkip = async () => {
    try {
      await completeStep("first_goal", { skills_configured: [] });
      onComplete();
    } catch {
      setErrorMessage("Failed to proceed. Please try again.");
    }
  };

  if (isLoading) {
    return (
      <div className="flex items-center justify-center py-12">
        <Loader2 className="w-8 h-8 animate-spin text-secondary" />
      </div>
    );
  }

  if (!recommendations) {
    return (
      <div className="text-center py-12">
        <p className="text-secondary mb-4">
          Unable to load skill recommendations.
        </p>
        <button
          onClick={loadRecommendations}
          className="text-interactive hover:text-interactive-hover font-medium cursor-pointer"
        >
          Try again
        </button>
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-6">
      {/* Header */}
      <div className="flex flex-col gap-3">
        <div className="flex items-center gap-2">
          <Sparkles className="w-6 h-6 text-interactive" />
          <h1 className="text-[32px] leading-[1.2] text-content font-display">
            Skills Configuration
          </h1>
        </div>
        <p className="font-sans text-[15px] leading-relaxed text-secondary">
          {recommendations.message ||
            `Based on your role in ${companyType}, I've equipped myself with these capabilities.`}
        </p>
        <p className="font-sans text-[13px] text-secondary">
          You can add or remove any skills before confirming, or skip this step.
        </p>
      </div>

      {/* Trust Level Badge */}
      <div className="flex items-center gap-2 font-sans text-[13px]">
        <Zap className="w-4 h-4 text-info" />
        <span className="text-secondary">Starting at</span>
        <span className="px-2 py-1 bg-interactive/10 text-interactive rounded-full font-medium">
          COMMUNITY Trust Level
        </span>
        <span className="text-secondary">— Skills will earn trust through usage</span>
      </div>

      {/* Skills List */}
      <div className="flex flex-col gap-3 max-h-96 overflow-y-auto">
        {recommendations.recommendations.map((skill) => {
          const info = SKILL_INFO[skill.skill_id] || {
            name: skill.skill_id,
            description: "AI-powered capability",
          };
          const isSelected = selectedSkills.has(skill.skill_id);

          return (
            <button
              key={skill.skill_id}
              type="button"
              onClick={() => toggleSkill(skill.skill_id)}
              className={`w-full text-left p-4 rounded-lg border-2 transition-colors duration-150 cursor-pointer ${
                isSelected
                  ? "border-interactive bg-interactive/10"
                  : "border-border hover:border-interactive/50"
              }`}
            >
              <div className="flex items-start">
                <div className="flex-shrink-0 mt-0.5">
                  {isSelected ? (
                    <CheckCircle2 className="w-5 h-5 text-interactive" />
                  ) : (
                    <Circle className="w-5 h-5 text-border" />
                  )}
                </div>
                <div className="ml-3 flex-1">
                  <h3 className="font-sans font-medium text-[15px] text-content">{info.name}</h3>
                  <p className="font-sans text-[13px] text-secondary mt-1">{info.description}</p>
                </div>
              </div>
            </button>
          );
        })}
      </div>

      {/* Error Message */}
      {errorMessage && (
        <div className="p-4 bg-critical/10 border border-critical/30 rounded-lg">
          <p className="font-sans text-[13px] text-critical">{errorMessage}</p>
        </div>
      )}

      {/* Action Buttons */}
      <div className="flex flex-col gap-3">
        <button
          type="button"
          onClick={handleConfirm}
          disabled={isInstalling || selectedSkills.size === 0}
          className="
            bg-interactive text-white rounded-lg px-5 py-2.5
            font-sans font-medium text-[15px]
            hover:bg-interactive-hover active:bg-interactive-hover
            transition-colors duration-150
            focus:outline-none focus:ring-2 focus:ring-interactive focus:ring-offset-2
            disabled:opacity-50 disabled:cursor-not-allowed
            cursor-pointer flex items-center justify-center gap-2
            min-h-[44px]
          "
        >
          {isInstalling ? (
            <>
              <Loader2 className="w-4 h-4 animate-spin" />
              Installing...
            </>
          ) : (
            <>
              Confirm & Continue
              <ArrowRight className="w-4 h-4" />
            </>
          )}
        </button>

        <button
          type="button"
          onClick={handleSkip}
          disabled={isInstalling}
          className="
            bg-transparent text-secondary rounded-lg px-4 py-2.5
            font-sans text-[13px]
            hover:bg-subtle
            transition-colors duration-150
            focus:outline-none focus:ring-2 focus:ring-interactive focus:ring-offset-2
            disabled:opacity-50 disabled:cursor-not-allowed
            cursor-pointer text-center
            min-h-[44px]
          "
        >
          Skip for now
        </button>
      </div>

      {/* Selected Count */}
      {selectedSkills.size > 0 && (
        <p className="text-center font-sans text-[13px] text-secondary">
          {selectedSkills.size} skill{selectedSkills.size !== 1 ? "s" : ""} selected
        </p>
      )}
    </div>
  );
}
