import type { EmailDraftTone } from "@/api/drafts";

interface ToneSelectorProps {
  value: EmailDraftTone;
  onChange: (tone: EmailDraftTone) => void;
  disabled?: boolean;
}

const tones: { value: EmailDraftTone; label: string; description: string }[] = [
  { value: "formal", label: "Formal", description: "Professional & polished" },
  { value: "friendly", label: "Friendly", description: "Warm & approachable" },
  { value: "urgent", label: "Urgent", description: "Direct & action-oriented" },
];

export function ToneSelector({ value, onChange, disabled = false }: ToneSelectorProps) {
  return (
    <div className="flex flex-col gap-2">
      <label className="text-sm font-medium text-slate-300">Tone</label>
      <div className="relative flex bg-slate-800/50 rounded-xl p-1 border border-slate-700/50">
        {/* Sliding background indicator */}
        <div
          className="absolute top-1 bottom-1 bg-primary-600/20 border border-primary-500/30 rounded-lg transition-all duration-300 ease-out"
          style={{
            left: `${(tones.findIndex((t) => t.value === value) * 100) / 3 + 0.5}%`,
            width: `${100 / 3 - 1}%`,
          }}
        />

        {tones.map((tone) => (
          <button
            key={tone.value}
            type="button"
            onClick={() => !disabled && onChange(tone.value)}
            disabled={disabled}
            className={`relative flex-1 px-4 py-2.5 rounded-lg text-sm font-medium transition-colors z-10 ${
              value === tone.value
                ? "text-primary-400"
                : "text-slate-400 hover:text-white"
            } disabled:opacity-50 disabled:cursor-not-allowed`}
          >
            {tone.label}
          </button>
        ))}
      </div>
      <p className="text-xs text-slate-500">
        {tones.find((t) => t.value === value)?.description}
      </p>
    </div>
  );
}
