/**
 * EmailBootstrapProgress — Live email bootstrap progress display.
 *
 * Shows ARIA learning from the user's email history with live counters,
 * progress bar, and intelligence insights. The experience feels like
 * ARIA is genuinely thinking, not just a loading bar.
 *
 * Design Direction: Refined Intelligence
 * - Subtle depth through layered gradients and soft glows
 * - Typography-led with JetBrains Mono for data and Satoshi for narrative
 * - Count-up animations that feel precise and intentional
 * - Intelligence insights that surface as discoveries, not just data
 */

import { useState, useEffect, useRef, useMemo } from "react";
import { Mail, Users, Briefcase, PenLine, Sparkles, Check } from "lucide-react";
import ariaAvatarSrc from "@/assets/aria-avatar.png";
import type { BootstrapStatus } from "@/api/emailIntegration";

export interface EmailBootstrapProgressProps {
  /** Bootstrap status from the API */
  status: BootstrapStatus;
  /** Email provider name for display */
  provider: "google" | "microsoft";
  /** Called when bootstrap completes and user clicks Continue */
  onContinue: () => void;
  /** Called when user skips the bootstrap */
  onSkip: () => void;
}

// --- Count-Up Number Animation ---
function CountUpNumber({
  targetValue,
  duration = 600,
  className = "",
}: {
  targetValue: number;
  duration?: number;
  className?: string;
}) {
  const [displayValue, setDisplayValue] = useState(0);
  const startTimeRef = useRef<number | null>(null);
  const rafRef = useRef<number | null>(null);

  useEffect(() => {
    const animate = (timestamp: number) => {
      if (!startTimeRef.current) {
        startTimeRef.current = timestamp;
      }

      const elapsed = timestamp - startTimeRef.current;
      const progress = Math.min(elapsed / duration, 1);

      // Ease out cubic for smooth deceleration
      const eased = 1 - Math.pow(1 - progress, 3);
      const currentValue = Math.round(eased * targetValue);

      setDisplayValue(currentValue);

      if (progress < 1) {
        rafRef.current = requestAnimationFrame(animate);
      }
    };

    rafRef.current = requestAnimationFrame(animate);

    return () => {
      if (rafRef.current) {
        cancelAnimationFrame(rafRef.current);
      }
    };
  }, [targetValue, duration]);

  return (
    <span
      className={`font-mono tabular-nums ${className}`}
      style={{
        display: "inline-block",
        minWidth: `${String(targetValue).length + 1}ch`,
        fontVariantNumeric: "tabular-nums",
      }}
    >
      {displayValue.toLocaleString()}
    </span>
  );
}

// --- Progress Bar with Subtle Animation ---
function ProgressIndicator({
  current,
  total,
  animated = true,
}: {
  current: number;
  total: number;
  animated?: boolean;
}) {
  const percentage = total > 0 ? Math.round((current / total) * 100) : 0;

  return (
    <div className="w-full">
      <div className="flex items-center justify-between mb-2">
        <span className="text-xs font-medium text-[var(--text-secondary)]">
          Processing emails
        </span>
        <span className="text-xs font-mono text-[var(--text-tertiary)]">
          {current.toLocaleString()} of {total.toLocaleString()}
        </span>
      </div>
      <div
        className="h-1.5 w-full rounded-full overflow-hidden"
        style={{ backgroundColor: "rgba(46, 102, 255, 0.1)" }}
        role="progressbar"
        aria-valuenow={percentage}
        aria-valuemin={0}
        aria-valuemax={100}
      >
        <div
          className={`h-full rounded-full transition-all duration-500 ease-out ${
            animated ? "animate-pulse-subtle" : ""
          }`}
          style={{
            width: `${percentage}%`,
            background: "linear-gradient(90deg, #2E66FF 0%, #4A7AFF 100%)",
            boxShadow: "0 0 12px rgba(46, 102, 255, 0.4)",
          }}
        />
      </div>
    </div>
  );
}

// --- Stat Card ---
function StatCard({
  icon: Icon,
  label,
  value,
  subtext,
  delay = 0,
}: {
  icon: React.ElementType;
  label: string;
  value: number;
  subtext?: string;
  delay?: number;
}) {
  return (
    <div
      className="flex items-start gap-3 p-3 rounded-lg transition-all duration-300"
      style={{
        backgroundColor: "rgba(255, 255, 255, 0.02)",
        border: "1px solid rgba(255, 255, 255, 0.05)",
        animationDelay: `${delay}ms`,
        animation: "fadeSlideIn 0.4s ease-out forwards",
        opacity: 0,
      }}
    >
      <div
        className="flex-shrink-0 w-8 h-8 rounded-md flex items-center justify-center"
        style={{ backgroundColor: "rgba(46, 102, 255, 0.1)" }}
      >
        <Icon className="w-4 h-4 text-[var(--color-accent)]" />
      </div>
      <div className="flex-1 min-w-0">
        <p className="text-xs text-[var(--text-tertiary)] mb-0.5">{label}</p>
        <p className="text-lg font-semibold text-[var(--text-primary)] flex items-baseline gap-1.5">
          <CountUpNumber targetValue={value} duration={500} />
          {subtext && (
            <span className="text-xs font-normal text-[var(--text-secondary)]">
              {subtext}
            </span>
          )}
        </p>
      </div>
    </div>
  );
}

// --- Intelligence Insight ---
function IntelligenceInsight({
  text,
  delay = 0,
}: {
  text: string;
  delay?: number;
}) {
  return (
    <div
      className="flex items-center gap-2 py-2 px-3 rounded-lg"
      style={{
        backgroundColor: "rgba(107, 143, 113, 0.08)",
        borderLeft: "2px solid var(--success)",
        animationDelay: `${delay}ms`,
        animation: "fadeSlideIn 0.4s ease-out forwards",
        opacity: 0,
      }}
    >
      <Sparkles className="w-3.5 h-3.5 text-[var(--success)] flex-shrink-0" />
      <p className="text-sm text-[var(--text-secondary)]">{text}</p>
    </div>
  );
}

// --- Main Component ---
export function EmailBootstrapProgress({
  status,
  provider,
  onContinue,
  onSkip,
}: EmailBootstrapProgressProps) {
  const [showInsights, setShowInsights] = useState(false);
  const isComplete = status.status === "complete";
  const isProcessing = status.status === "processing" || status.status === "not_started";
  const hasError = status.status === "error";

  const providerName = provider === "google" ? "Gmail" : "Outlook";

  // Generate intelligence insights from the data
  const insights = useMemo(() => {
    if (!isComplete || !status.communication_patterns) return [];

    const patterns = status.communication_patterns;
    const result: string[] = [];

    // Peak hours insight
    if (patterns.peak_send_hours.length > 0) {
      const hours = patterns.peak_send_hours
        .map((h) => `${h}:00`)
        .slice(0, 2)
        .join("-");
      result.push(`Peak email hours: ${hours}`);
    }

    // Response time insight
    if (patterns.avg_response_time_hours > 0) {
      const hours = patterns.avg_response_time_hours;
      const timeStr =
        hours < 1
          ? `${Math.round(hours * 60)} minutes`
          : `${hours.toFixed(1)} hours`;
      result.push(`Average response time: ${timeStr}`);
    }

    // Top recipient insight
    if (patterns.top_recipients.length > 0) {
      const topRecipient = patterns.top_recipients[0];
      const name = topRecipient.split("@")[0];
      result.push(`Most frequent contact: ${name}`);
    }

    return result;
  }, [isComplete, status]);

  // Show insights after a delay when complete
  useEffect(() => {
    if (isComplete) {
      const timer = setTimeout(() => setShowInsights(true), 800);
      return () => clearTimeout(timer);
    }
    return () => setShowInsights(false);
  }, [isComplete]);

  // Error state
  if (hasError) {
    return (
      <div className="w-full max-w-xl mx-auto space-y-6">
        <div className="text-center py-8">
          <div
            className="w-16 h-16 mx-auto mb-4 rounded-full flex items-center justify-center"
            style={{ backgroundColor: "rgba(166, 107, 107, 0.1)" }}
          >
            <Mail className="w-8 h-8 text-[var(--critical)]" />
          </div>
          <h3 className="text-lg font-medium text-[var(--text-primary)] mb-2">
            Something went wrong
          </h3>
          <p className="text-sm text-[var(--text-secondary)] mb-6">
            {status.error_message ||
              "I couldn't analyze your emails. You can continue anyway."}
          </p>
          <div className="flex items-center justify-center gap-3">
            <button
              onClick={onContinue}
              className="px-4 py-2.5 rounded-lg bg-[var(--color-accent)] text-white text-sm font-medium transition hover:bg-[var(--color-accent-hover)]"
            >
              Continue
            </button>
            <button
              onClick={onSkip}
              className="text-sm text-[var(--text-tertiary)] hover:text-[var(--text-secondary)] transition"
            >
              Skip for now
            </button>
          </div>
        </div>
      </div>
    );
  }

  // Complete state
  if (isComplete) {
    return (
      <div className="w-full max-w-xl mx-auto space-y-6">
        {/* ARIA Avatar with Success State */}
        <div className="flex flex-col items-center py-6">
          <div className="relative mb-4">
            <div
              className="absolute inset-0 rounded-full animate-pulse"
              style={{
                background:
                  "radial-gradient(circle, rgba(107, 143, 113, 0.3) 0%, transparent 70%)",
                transform: "scale(1.5)",
              }}
            />
            <div
              className="relative z-10 w-20 h-20 rounded-full overflow-hidden border-2"
              style={{
                borderColor: "var(--success)",
                boxShadow: "0 0 30px rgba(107, 143, 113, 0.3)",
              }}
            >
              <img
                src={ariaAvatarSrc}
                alt="ARIA"
                className="w-full h-full object-cover"
              />
            </div>
            <div
              className="absolute -bottom-1 -right-1 w-7 h-7 rounded-full flex items-center justify-center z-20"
              style={{ backgroundColor: "var(--success)" }}
            >
              <Check className="w-4 h-4 text-white" />
            </div>
          </div>

          <h3
            className="text-xl font-medium text-center mb-2"
            style={{ fontFamily: "var(--font-display, Georgia, serif)" }}
          >
            I've learned your communication world.
          </h3>
          <p className="text-sm text-[var(--text-secondary)] text-center max-w-md">
            I know who matters to you, how you write, and what deals you're
            working on.
          </p>
        </div>

        {/* Stats Grid */}
        <div className="grid grid-cols-2 gap-3">
          <StatCard
            icon={Users}
            label="Contacts discovered"
            value={status.contacts_discovered}
            delay={0}
          />
          <StatCard
            icon={Briefcase}
            label="Active deal threads"
            value={status.active_threads}
            delay={100}
          />
          <StatCard
            icon={PenLine}
            label="Writing samples analyzed"
            value={status.writing_samples_extracted}
            delay={200}
          />
          <StatCard
            icon={Mail}
            label="Emails processed"
            value={status.emails_processed}
            subtext="in 60 days"
            delay={300}
          />
        </div>

        {/* Intelligence Insights */}
        {showInsights && insights.length > 0 && (
          <div className="space-y-2 mt-4">
            {insights.map((insight, idx) => (
              <IntelligenceInsight
                key={idx}
                text={insight}
                delay={idx * 150}
              />
            ))}
          </div>
        )}

        {/* Actions */}
        <div className="flex items-center justify-center gap-3 pt-4">
          <button
            onClick={onContinue}
            className="px-6 py-2.5 rounded-lg bg-[var(--color-accent)] text-white text-sm font-medium transition hover:bg-[var(--color-accent-hover)]"
          >
            Continue
          </button>
          <button
            onClick={onSkip}
            className="text-sm text-[var(--text-tertiary)] hover:text-[var(--text-secondary)] transition"
          >
            Skip for now
          </button>
        </div>

        {/* CSS for animations */}
        <style>{`
          @keyframes fadeSlideIn {
            from {
              opacity: 0;
              transform: translateY(8px);
            }
            to {
              opacity: 1;
              transform: translateY(0);
            }
          }
        `}</style>
      </div>
    );
  }

  // Processing state
  return (
    <div className="w-full max-w-xl mx-auto space-y-6">
      {/* ARIA Avatar with Processing State */}
      <div className="flex flex-col items-center py-6">
        <div className="relative mb-4">
          {/* Pulsing glow ring */}
          <div
            className="absolute inset-0 rounded-full"
            style={{
              background:
                "radial-gradient(circle, rgba(46, 102, 255, 0.25) 0%, transparent 70%)",
              transform: "scale(1.6)",
              animation: "pulse 2s ease-in-out infinite",
            }}
          />
          <div
            className="relative z-10 w-20 h-20 rounded-full overflow-hidden border-2 border-[var(--color-accent)]"
            style={{
              boxShadow: "0 0 40px rgba(46, 102, 255, 0.25)",
            }}
          >
            <img
              src={ariaAvatarSrc}
              alt="ARIA"
              className="w-full h-full object-cover"
            />
          </div>
        </div>

        <p className="text-sm text-[var(--text-secondary)] text-center">
          Reading your {providerName} history...
        </p>
      </div>

      {/* Progress Bar */}
      <div className="px-4">
        <ProgressIndicator
          current={status.emails_processed}
          total={Math.max(status.emails_processed * 2, 100)} // Estimate total if not known
          animated={isProcessing}
        />
      </div>

      {/* Live Stats Grid */}
      <div className="grid grid-cols-2 gap-3 px-4">
        <StatCard
          icon={Users}
          label="Contacts discovered"
          value={status.contacts_discovered}
          delay={0}
        />
        <StatCard
          icon={Briefcase}
          label="Deal threads detected"
          value={status.active_threads}
          delay={100}
        />
        <StatCard
          icon={PenLine}
          label="Writing samples"
          value={status.writing_samples_extracted}
          delay={200}
        />
        <StatCard
          icon={Mail}
          label="Commitments found"
          value={status.commitments_detected}
          delay={300}
        />
      </div>

      {/* Skip option while processing */}
      <div className="flex justify-center pt-2">
        <button
          onClick={onSkip}
          className="text-xs text-[var(--text-tertiary)] hover:text-[var(--text-secondary)] transition"
        >
          Skip for now (analysis continues in background)
        </button>
      </div>

      {/* CSS for animations */}
      <style>{`
        @keyframes fadeSlideIn {
          from {
            opacity: 0;
            transform: translateY(8px);
          }
          to {
            opacity: 1;
            transform: translateY(0);
          }
        }
        @keyframes pulse {
          0%, 100% {
            opacity: 0.5;
            transform: scale(1.5);
          }
          50% {
            opacity: 0.8;
            transform: scale(1.7);
          }
        }
      `}</style>
    </div>
  );
}
