import { useState, useEffect, useCallback } from "react";
import { ArrowRight, CheckCircle2, Circle, Loader2, Sparkles, Zap } from "lucide-react";
import {
  getSkillRecommendations,
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
      const response = await getSkillRecommendations({
        company_type: companyType,
        role: userRole,
      });
      setRecommendations(response);
      // Pre-select all recommended skills
      setSelectedSkills(new Set(response.recommendations.map((r) => r.skill_id)));
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
        <Loader2 className="w-8 h-8 animate-spin text-gray-400" />
      </div>
    );
  }

  if (!recommendations) {
    return (
      <div className="text-center py-12">
        <p className="text-gray-500 mb-4">
          Unable to load skill recommendations.
        </p>
        <button
          onClick={loadRecommendations}
          className="text-blue-600 hover:text-blue-700"
        >
          Try again
        </button>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="text-center">
        <div className="flex items-center justify-center mb-4">
          <Sparkles className="w-8 h-8 text-purple-500 mr-2" />
          <h2 className="text-2xl font-semibold text-gray-900">
            Skills Configuration
          </h2>
        </div>
        <p className="text-gray-600">
          {recommendations.message ||
            `Based on your role in ${companyType}, I've equipped myself with these capabilities.`}
        </p>
        <p className="text-sm text-gray-500 mt-2">
          You can add or remove any skills before confirming, or skip this step.
        </p>
      </div>

      {/* Trust Level Badge */}
      <div className="flex items-center justify-center space-x-2 text-sm">
        <Zap className="w-4 h-4 text-blue-500" />
        <span className="text-gray-600">Starting at</span>
        <span className="px-2 py-1 bg-blue-100 text-blue-700 rounded-full font-medium">
          COMMUNITY Trust Level
        </span>
        <span className="text-gray-500">— Skills will earn trust through usage</span>
      </div>

      {/* Skills List */}
      <div className="space-y-3 max-h-96 overflow-y-auto">
        {recommendations.recommendations.map((skill) => {
          const info = SKILL_INFO[skill.skill_id] || {
            name: skill.skill_id,
            description: "AI-powered capability",
          };
          const isSelected = selectedSkills.has(skill.skill_id);

          return (
            <button
              key={skill.skill_id}
              onClick={() => toggleSkill(skill.skill_id)}
              className={`w-full text-left p-4 rounded-lg border-2 transition-all ${
                isSelected
                  ? "border-blue-500 bg-blue-50"
                  : "border-gray-200 hover:border-gray-300"
              }`}
            >
              <div className="flex items-start">
                <div className="flex-shrink-0 mt-0.5">
                  {isSelected ? (
                    <CheckCircle2 className="w-5 h-5 text-blue-500" />
                  ) : (
                    <Circle className="w-5 h-5 text-gray-300" />
                  )}
                </div>
                <div className="ml-3 flex-1">
                  <h3 className="font-medium text-gray-900">{info.name}</h3>
                  <p className="text-sm text-gray-600 mt-1">{info.description}</p>
                </div>
              </div>
            </button>
          );
        })}
      </div>

      {/* Error Message */}
      {errorMessage && (
        <div className="p-4 bg-red-50 border border-red-200 rounded-lg">
          <p className="text-sm text-red-600">{errorMessage}</p>
        </div>
      )}

      {/* Action Buttons */}
      <div className="flex items-center justify-between pt-4 border-t">
        <button
          onClick={handleSkip}
          disabled={isInstalling}
          className="text-gray-600 hover:text-gray-700 font-medium disabled:opacity-50"
        >
          Skip for now
        </button>
        <button
          onClick={handleConfirm}
          disabled={isInstalling || selectedSkills.size === 0}
          className="flex items-center px-6 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed"
        >
          {isInstalling ? (
            <>
              <Loader2 className="w-4 h-4 mr-2 animate-spin" />
              Installing...
            </>
          ) : (
            <>
              Confirm & Continue
              <ArrowRight className="w-4 h-4 ml-2" />
            </>
          )}
        </button>
      </div>

      {/* Selected Count */}
      {selectedSkills.size > 0 && (
        <p className="text-center text-sm text-gray-500">
          {selectedSkills.size} skill{selectedSkills.size !== 1 ? "s" : ""} selected
        </p>
      )}
    </div>
  );
}
