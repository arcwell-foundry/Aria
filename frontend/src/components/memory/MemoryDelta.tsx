import {
  Brain,
  Check,
  ChevronDown,
  AlertTriangle,
  Pencil,
  Shield,
  Users,
  X,
} from "lucide-react";
import { useState, useRef, useEffect } from "react";
import type { MemoryDeltaGroup, MemoryDeltaFact } from "@/api/memory";
import { useCorrectMemory } from "@/hooks/useMemoryDelta";

// --- Domain config ---

interface DomainConfig {
  label: string;
  icon: typeof Brain;
  accentClass: string;
}

const DOMAIN_CONFIG: Record<string, DomainConfig> = {
  corporate_memory: {
    label: "Company Intelligence",
    icon: Brain,
    accentClass: "text-[#6B7FA3]",
  },
  competitive: {
    label: "Competitive Landscape",
    icon: Shield,
    accentClass: "text-[#B8956A]",
  },
  relationship: {
    label: "Relationships & Contacts",
    icon: Users,
    accentClass: "text-[#6B8F71]",
  },
  digital_twin: {
    label: "Communication Style",
    icon: Pencil,
    accentClass: "text-[#8B92A5]",
  },
};

function getDomainConfig(domain: string): DomainConfig {
  return (
    DOMAIN_CONFIG[domain] ?? {
      label: domain,
      icon: Brain,
      accentClass: "text-[#6B7FA3]",
    }
  );
}

// --- Confidence indicator ---

function confidenceTier(confidence: number): {
  label: string;
  opacity: string;
  fontWeight: string;
} {
  if (confidence >= 0.95)
    return { label: "High confidence", opacity: "opacity-100", fontWeight: "font-medium" };
  if (confidence >= 0.8)
    return { label: "Confident", opacity: "opacity-90", fontWeight: "font-normal" };
  if (confidence >= 0.6)
    return { label: "Moderate", opacity: "opacity-75", fontWeight: "font-normal" };
  if (confidence >= 0.4)
    return { label: "Uncertain", opacity: "opacity-60", fontWeight: "font-normal" };
  return { label: "Unconfirmed", opacity: "opacity-50", fontWeight: "font-normal" };
}

// --- Fact row ---

interface FactRowProps {
  fact: MemoryDeltaFact;
  surface: "dark" | "light";
}

function FactRow({ fact, surface }: FactRowProps) {
  const [editing, setEditing] = useState(false);
  const [correctedValue, setCorrectedValue] = useState(fact.fact);
  const inputRef = useRef<HTMLInputElement>(null);
  const correctMutation = useCorrectMemory();
  const tier = confidenceTier(fact.confidence);

  useEffect(() => {
    if (editing && inputRef.current) {
      inputRef.current.focus();
      inputRef.current.select();
    }
  }, [editing]);

  const handleSubmit = () => {
    if (correctedValue.trim() && correctedValue !== fact.fact) {
      correctMutation.mutate({
        fact_id: fact.id,
        corrected_value: correctedValue.trim(),
        correction_type: "factual",
      });
    }
    setEditing(false);
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Enter") handleSubmit();
    if (e.key === "Escape") {
      setCorrectedValue(fact.fact);
      setEditing(false);
    }
  };

  const isDark = surface === "dark";

  if (editing) {
    return (
      <div
        className={`flex items-center gap-2 px-3 py-2.5 rounded-lg border ${
          isDark
            ? "bg-[#1E2235] border-[#7B8EAA]"
            : "bg-white border-[#5B6E8A]"
        }`}
      >
        <input
          ref={inputRef}
          type="text"
          value={correctedValue}
          onChange={(e) => setCorrectedValue(e.target.value)}
          onKeyDown={handleKeyDown}
          className={`flex-1 bg-transparent text-[15px] font-sans outline-none ${
            isDark ? "text-[#E8E6E1]" : "text-[#1A1D27]"
          }`}
          aria-label="Correct this fact"
        />
        <button
          onClick={handleSubmit}
          disabled={correctMutation.isPending}
          className={`p-1.5 rounded-md transition-colors duration-150 cursor-pointer ${
            isDark
              ? "hover:bg-[#6B8F71]/20 text-[#6B8F71]"
              : "hover:bg-[#5A7D60]/10 text-[#5A7D60]"
          }`}
          aria-label="Save correction"
        >
          <Check className="w-4 h-4" />
        </button>
        <button
          onClick={() => {
            setCorrectedValue(fact.fact);
            setEditing(false);
          }}
          className={`p-1.5 rounded-md transition-colors duration-150 cursor-pointer ${
            isDark
              ? "hover:bg-[#A66B6B]/20 text-[#8B92A5]"
              : "hover:bg-[#945A5A]/10 text-[#6B7280]"
          }`}
          aria-label="Cancel editing"
        >
          <X className="w-4 h-4" />
        </button>
      </div>
    );
  }

  return (
    <button
      onClick={() => setEditing(true)}
      className={`w-full text-left group flex items-start gap-3 px-3 py-2.5 rounded-lg transition-colors duration-150 cursor-pointer ${
        isDark
          ? "hover:bg-[#1E2235]/60"
          : "hover:bg-[#F5F5F0]"
      }`}
      aria-label={`Edit fact: ${fact.fact}`}
    >
      {/* Confidence bar */}
      <div className="flex-shrink-0 mt-1.5 w-1 h-4 rounded-full overflow-hidden">
        <div
          className={`w-full rounded-full ${
            isDark ? "bg-[#7B8EAA]" : "bg-[#5B6E8A]"
          }`}
          style={{ height: `${Math.max(fact.confidence * 100, 15)}%` }}
          title={tier.label}
        />
      </div>

      {/* Fact text */}
      <span
        className={`flex-1 text-[15px] font-sans leading-relaxed ${tier.opacity} ${tier.fontWeight} ${
          isDark ? "text-[#E8E6E1]" : "text-[#1A1D27]"
        }`}
      >
        {fact.language || fact.fact}
      </span>

      {/* Source tag */}
      <span
        className={`flex-shrink-0 mt-0.5 text-[11px] font-mono ${
          isDark ? "text-[#8B92A5]/60" : "text-[#6B7280]/60"
        } opacity-0 group-hover:opacity-100 transition-opacity duration-150`}
      >
        {fact.source}
      </span>
    </button>
  );
}

// --- Domain section ---

interface DomainSectionProps {
  group: MemoryDeltaGroup;
  surface: "dark" | "light";
  onConfirm?: (domain: string) => void;
  onFlag?: (domain: string) => void;
}

function DomainSection({ group, surface, onConfirm, onFlag }: DomainSectionProps) {
  const [expanded, setExpanded] = useState(true);
  const config = getDomainConfig(group.domain);
  const Icon = config.icon;
  const isDark = surface === "dark";

  return (
    <div
      className={`rounded-xl border overflow-hidden ${
        isDark
          ? "bg-[#161B2E] border-[#2A2F42]"
          : "bg-white border-[#E2E0DC] shadow-sm"
      }`}
    >
      {/* Header */}
      <button
        onClick={() => setExpanded(!expanded)}
        className={`w-full flex items-center justify-between px-5 py-4 transition-colors duration-150 cursor-pointer ${
          isDark ? "hover:bg-[#1E2235]/40" : "hover:bg-[#F5F5F0]/60"
        }`}
        aria-expanded={expanded}
      >
        <div className="flex items-center gap-3">
          <Icon className={`w-5 h-5 ${config.accentClass}`} strokeWidth={1.5} />
          <h3
            className={`text-[15px] font-sans font-medium ${
              isDark ? "text-[#E8E6E1]" : "text-[#1A1D27]"
            }`}
          >
            {config.label}
          </h3>
          <span
            className={`text-[11px] font-mono px-2 py-0.5 rounded-full ${
              isDark
                ? "bg-[#1E2235] text-[#8B92A5]"
                : "bg-[#F5F5F0] text-[#6B7280]"
            }`}
          >
            {group.facts.length}
          </span>
        </div>
        <ChevronDown
          className={`w-4 h-4 transition-transform duration-200 ${
            expanded ? "rotate-180" : ""
          } ${isDark ? "text-[#8B92A5]" : "text-[#6B7280]"}`}
          strokeWidth={1.5}
        />
      </button>

      {/* Fact list */}
      <div
        className={`transition-all duration-200 ease-in-out overflow-hidden ${
          expanded ? "max-h-[2000px] opacity-100" : "max-h-0 opacity-0"
        }`}
      >
        <div className="px-3 pb-3 space-y-0.5">
          {group.facts.map((fact) => (
            <FactRow key={fact.id} fact={fact} surface={surface} />
          ))}
        </div>

        {/* Domain actions */}
        <div
          className={`flex items-center gap-2 px-5 py-3 border-t ${
            isDark ? "border-[#2A2F42]" : "border-[#E2E0DC]"
          }`}
        >
          <button
            onClick={() => onConfirm?.(group.domain)}
            className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-[13px] font-sans font-medium transition-colors duration-150 cursor-pointer ${
              isDark
                ? "text-[#6B8F71] hover:bg-[#6B8F71]/10"
                : "text-[#5A7D60] hover:bg-[#5A7D60]/10"
            }`}
          >
            <Check className="w-3.5 h-3.5" strokeWidth={2} />
            Looks right
          </button>
          <button
            onClick={() => onFlag?.(group.domain)}
            className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-[13px] font-sans font-medium transition-colors duration-150 cursor-pointer ${
              isDark
                ? "text-[#B8956A] hover:bg-[#B8956A]/10"
                : "text-[#A6845A] hover:bg-[#A6845A]/10"
            }`}
          >
            <AlertTriangle className="w-3.5 h-3.5" strokeWidth={2} />
            Something&apos;s off
          </button>
        </div>
      </div>
    </div>
  );
}

// --- Main component ---

interface MemoryDeltaProps {
  deltas: MemoryDeltaGroup[];
  surface?: "dark" | "light";
  title?: string;
  onConfirmDomain?: (domain: string) => void;
  onFlagDomain?: (domain: string) => void;
}

export function MemoryDelta({
  deltas,
  surface = "dark",
  title = "Here\u2019s what I learned",
  onConfirmDomain,
  onFlagDomain,
}: MemoryDeltaProps) {
  const isDark = surface === "dark";

  if (deltas.length === 0) {
    return (
      <div
        className={`rounded-xl border px-6 py-8 text-center ${
          isDark
            ? "bg-[#161B2E] border-[#2A2F42]"
            : "bg-white border-[#E2E0DC] shadow-sm"
        }`}
      >
        <Brain
          className={`w-8 h-8 mx-auto mb-3 ${
            isDark ? "text-[#8B92A5]/40" : "text-[#6B7280]/40"
          }`}
          strokeWidth={1.5}
        />
        <p
          className={`text-[15px] font-sans ${
            isDark ? "text-[#8B92A5]" : "text-[#6B7280]"
          }`}
        >
          ARIA is building her understanding. New intelligence will appear here.
        </p>
      </div>
    );
  }

  return (
    <div className="space-y-4">
      {title && (
        <h2
          className={`text-lg font-display ${
            isDark ? "text-[#E8E6E1]" : "text-[#1A1D27]"
          }`}
        >
          {title}
        </h2>
      )}

      {deltas.map((group) => (
        <DomainSection
          key={group.domain}
          group={group}
          surface={surface}
          onConfirm={onConfirmDomain}
          onFlag={onFlagDomain}
        />
      ))}
    </div>
  );
}
