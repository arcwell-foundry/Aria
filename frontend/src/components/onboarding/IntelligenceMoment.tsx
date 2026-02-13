/**
 * IntelligenceMoment — ARIA's "thinking" processing state during onboarding.
 *
 * Shows a centered ARIA avatar with a pulsing blue glow ring,
 * and status lines that fade in one by one with real data from API responses.
 *
 * This is the signature experience that makes ARIA feel intelligent.
 */

import { useState, useEffect, useRef, useMemo } from "react";
import ariaAvatarSrc from "@/assets/aria-avatar.png";
import type { WritingStyleFingerprint } from "@/api/onboarding";

export type IntelligenceStep =
  | "company_discovery"
  | "user_profile"
  | "writing_samples"
  | "email_integration";

export interface IntelligenceMomentProps {
  /** Which onboarding step is being processed */
  step: IntelligenceStep;
  /** Data from the API response to populate status lines */
  responseData?: {
    // Company discovery
    companyName?: string;
    productCount?: number;
    competitorCount?: number;
    classification?: {
      company_type?: string;
      therapeutic_areas?: string[];
    } | null;
    // User profile
    linkedinFound?: boolean;
    roleType?: string;
    // Writing samples
    writingFingerprint?: WritingStyleFingerprint | null;
    sampleCount?: number;
    // Email integration
    emailProvider?: string;
    contactCount?: number;
    priorityContacts?: number;
  };
  /** Whether the API call is still in progress */
  isLoading: boolean;
  /** Called when the intelligence moment animation is complete */
  onComplete?: () => void;
  /** Minimum time to show the processing state (ms) */
  minDuration?: number;
}

interface StatusLine {
  id: string;
  text: string;
  delay: number;
  /** Whether this line should pulse with ellipsis while loading */
  pulse?: boolean;
}

// Step-specific status line configurations
function getStatusLines(
  step: IntelligenceStep,
  data: IntelligenceMomentProps["responseData"],
  isLoading: boolean
): StatusLine[] {
  switch (step) {
    case "company_discovery": {
      const name = data?.companyName || "your company";
      const products = data?.productCount;
      const competitors = data?.competitorCount;
      const classification = data?.classification;

      const lines: StatusLine[] = [
        {
          id: "researching",
          text: `Researching ${name}...`,
          delay: 0,
          pulse: isLoading && !products,
        },
      ];

      // These lines appear when we have data
      if (products !== undefined || !isLoading) {
        lines.push({
          id: "products",
          text: products !== undefined
            ? `Found ${products} key products...`
            : "Identifying product portfolio...",
          delay: 300,
          pulse: isLoading && !competitors,
        });
      }

      if (competitors !== undefined || (!isLoading && products !== undefined)) {
        lines.push({
          id: "competitors",
          text: competitors !== undefined
            ? `Identified ${competitors} competitors...`
            : "Mapping competitive landscape...",
          delay: 600,
          pulse: isLoading && !classification,
        });
      }

      if (classification || (!isLoading && competitors !== undefined)) {
        lines.push({
          id: "memory",
          text: classification?.company_type
            ? `Classified as ${classification.company_type}...`
            : "Corporate memory initialized.",
          delay: 900,
          pulse: false,
        });
      }

      return lines;
    }

    case "user_profile": {
      const linkedin = data?.linkedinFound;
      const role = data?.roleType;

      const lines: StatusLine[] = [
        {
          id: "profile",
          text: linkedin !== false ? "Analyzing your professional profile..." : "Building your profile...",
          delay: 0,
          pulse: isLoading,
        },
      ];

      if (linkedin === true || !isLoading) {
        lines.push({
          id: "linkedin",
          text: linkedin === true
            ? "Found your LinkedIn profile..."
            : "Profile data captured...",
          delay: 300,
          pulse: isLoading && !role,
        });
      }

      if (role || (!isLoading && linkedin !== undefined)) {
        lines.push({
          id: "calibrate",
          text: role
            ? `Calibrating for ${role.replace("_", " ")} role...`
            : "Communication style calibrated.",
          delay: 600,
          pulse: false,
        });
      }

      return lines;
    }

    case "writing_samples": {
      const fingerprint = data?.writingFingerprint;
      const count = data?.sampleCount;

      const lines: StatusLine[] = [
        {
          id: "analyzing",
          text: count
            ? `Analyzing ${count} writing sample${count !== 1 ? "s" : ""}...`
            : "Analyzing writing patterns...",
          delay: 0,
          pulse: isLoading,
        },
      ];

      if (fingerprint || !isLoading) {
        lines.push({
          id: "style",
          text: fingerprint?.style_summary
            ? `Style: ${fingerprint.style_summary.toLowerCase()}...`
            : "Style patterns identified...",
          delay: 300,
          pulse: isLoading && !fingerprint?.rhetorical_style,
        });
      }

      if (fingerprint?.rhetorical_style || (!isLoading && fingerprint)) {
        lines.push({
          id: "tone",
          text: fingerprint?.rhetorical_style
            ? `Tone: ${fingerprint.rhetorical_style.toLowerCase()}`
            : "Writing fingerprint saved.",
          delay: 600,
          pulse: false,
        });
      }

      return lines;
    }

    case "email_integration": {
      const provider = data?.emailProvider;
      const contacts = data?.contactCount;
      const priority = data?.priorityContacts;

      const providerName = provider === "google" ? "Gmail" : "Outlook";

      const lines: StatusLine[] = [
        {
          id: "scanning",
          text: `Scanning ${providerName} patterns...`,
          delay: 0,
          pulse: isLoading,
        },
      ];

      if (contacts !== undefined || !isLoading) {
        lines.push({
          id: "relationships",
          text: contacts !== undefined
            ? `Found ${contacts} contacts...`
            : "Building relationship graph...",
          delay: 300,
          pulse: isLoading && !priority,
        });
      }

      if (priority !== undefined || (!isLoading && contacts !== undefined)) {
        lines.push({
          id: "priority",
          text: priority !== undefined
            ? `Identified ${priority} priority contacts.`
            : "Priority contacts identified.",
          delay: 600,
          pulse: false,
        });
      }

      return lines;
    }

    default:
      return [];
  }
}

export function IntelligenceMoment({
  step,
  responseData,
  isLoading,
  onComplete,
  minDuration = 2000,
}: IntelligenceMomentProps) {
  const [visibleLines, setVisibleLines] = useState<StatusLine[]>([]);
  const startTimeRef = useRef<number>(0);
  const hasCompletedRef = useRef(false);
  const prevStepRef = useRef<IntelligenceStep | null>(null);

  // Get status lines based on step and current data
  const statusLines = useMemo(
    () => getStatusLines(step, responseData, isLoading),
    [step, responseData, isLoading]
  );

  // Initialize and reset on step change
  useEffect(() => {
    if (prevStepRef.current !== step) {
      prevStepRef.current = step;
      startTimeRef.current = Date.now();
      hasCompletedRef.current = false;
      // eslint-disable-next-line react-hooks/set-state-in-effect -- Valid pattern for resetting state when step prop changes
      setVisibleLines(statusLines.slice(0, 1));
    }
  }, [step, statusLines]);

  // Gradually reveal lines
  useEffect(() => {
    // Skip if we've already shown all lines or haven't started
    if (visibleLines.length === 0 || visibleLines.length >= statusLines.length) {
      return;
    }

    // Add remaining lines with delays
    const timers: NodeJS.Timeout[] = [];
    statusLines.slice(visibleLines.length).forEach((_, idx) => {
      const timer = setTimeout(() => {
        setVisibleLines((prev) => {
          const nextLine = statusLines[prev.length];
          if (!nextLine || prev.find((v) => v.id === nextLine.id)) {
            return prev;
          }
          return [...prev, nextLine];
        });
      }, (idx + 1) * 300);
      timers.push(timer);
    });

    return () => {
      timers.forEach(clearTimeout);
    };
  }, [statusLines, visibleLines.length]);

  // Handle completion
  useEffect(() => {
    if (!isLoading && !hasCompletedRef.current) {
      const elapsed = Date.now() - startTimeRef.current;
      const remaining = Math.max(0, minDuration - elapsed);

      // Ensure minimum duration, then complete
      const timer = setTimeout(() => {
        hasCompletedRef.current = true;
        onComplete?.();
      }, remaining + 500); // Extra 500ms for last line to settle

      return () => clearTimeout(timer);
    }
  }, [isLoading, minDuration, onComplete]);

  return (
    <div className="flex flex-col items-center justify-center py-8">
      {/* Avatar with pulsing glow ring */}
      <div className="relative mb-8">
        <div className="intelligence-glow-ring" />
        <div
          className="relative z-10 h-24 w-24 overflow-hidden rounded-full border-2 border-[var(--color-accent,#2E66FF)]"
          style={{
            boxShadow: "0 0 40px rgba(46,102,255,0.2), 0 0 80px rgba(46,102,255,0.1)",
          }}
        >
          <img
            src={ariaAvatarSrc}
            alt="ARIA"
            className="h-full w-full object-cover"
          />
        </div>
      </div>

      {/* Status lines */}
      <div className="flex flex-col items-center gap-3 min-h-[80px]">
        {visibleLines.map((line, idx) => (
          <div
            key={line.id}
            className={`intelligence-line intelligence-line-delay-${Math.min(idx, 5)}`}
          >
            <p className="text-sm text-[var(--text-secondary,#A1A1AA)] font-medium">
              {line.text}
              {line.pulse && (
                <span className="intelligence-ellipsis ml-1">
                  <span>.</span>
                  <span>.</span>
                  <span>.</span>
                </span>
              )}
            </p>
          </div>
        ))}
      </div>
    </div>
  );
}

/**
 * Wrapper component to add intelligence moment to any panel.
 * Fades out the form, shows the intelligence moment, then proceeds.
 */
export function IntelligenceMomentWrapper({
  children,
  showMoment,
  step,
  responseData,
  isLoading,
  onComplete,
}: {
  children: React.ReactNode;
  showMoment: boolean;
  step: IntelligenceStep;
  responseData?: IntelligenceMomentProps["responseData"];
  isLoading: boolean;
  onComplete?: () => void;
}) {
  if (!showMoment) {
    return <>{children}</>;
  }

  return (
    <IntelligenceMoment
      step={step}
      responseData={responseData}
      isLoading={isLoading}
      onComplete={onComplete}
    />
  );
}
