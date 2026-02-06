import { useCallback, useEffect, useRef, useState } from "react";
import {
  Plus,
  Trash2,
  Upload,
  FileText,
  Loader2,
  ThumbsUp,
  ThumbsDown,
  PenLine,
} from "lucide-react";
import {
  analyzeWriting,
  getFingerprint,
  isFingerprint,
  type WritingStyleFingerprint,
} from "@/api/writingAnalysis";

interface WritingSampleStepProps {
  onComplete: () => void;
  onSkip: () => void;
}

type InputMethod = "paste" | "upload";

const UPLOAD_ACCEPT = ".txt,.md,.docx,.pdf";
const UPLOAD_MIME_TYPES = new Set([
  "text/plain",
  "text/markdown",
  "application/pdf",
  "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
]);
const MAX_FILE_SIZE = 10 * 1024 * 1024; // 10MB

function deriveTraits(fp: WritingStyleFingerprint): string[] {
  const traits: string[] = [];

  if (fp.directness >= 0.7) traits.push("Direct");
  else if (fp.directness <= 0.3) traits.push("Diplomatic");

  if (fp.data_driven) traits.push("Data-driven");

  if (fp.formality_index >= 0.7) {
    if (fp.warmth >= 0.5) traits.push("Formal with warmth");
    else traits.push("Formal");
  } else if (fp.formality_index <= 0.3) {
    traits.push("Conversational");
  }

  if (fp.assertiveness >= 0.7) traits.push("Assertive");
  if (fp.warmth >= 0.7 && fp.formality_index < 0.7) traits.push("Warm");

  const styleLabels: Record<string, string> = {
    analytical: "Analytical",
    narrative: "Storyteller",
    persuasive: "Persuasive",
  };
  if (fp.rhetorical_style in styleLabels) {
    traits.push(styleLabels[fp.rhetorical_style]);
  }

  if (fp.vocabulary_sophistication === "advanced") traits.push("Sophisticated vocabulary");

  // Cap at 4 traits for visual cleanliness
  return traits.slice(0, 4);
}

export function WritingSampleStep({ onComplete, onSkip }: WritingSampleStepProps) {
  const [inputMethod, setInputMethod] = useState<InputMethod>("paste");
  const [samples, setSamples] = useState<string[]>(["", ""]);
  const [uploadedFiles, setUploadedFiles] = useState<{ name: string; text: string }[]>([]);
  const [isAnalyzing, setIsAnalyzing] = useState(false);
  const [fingerprint, setFingerprint] = useState<WritingStyleFingerprint | null>(null);
  const [feedback, setFeedback] = useState<"up" | "down" | null>(null);
  const [error, setError] = useState<string | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  // Check for existing fingerprint on mount
  useEffect(() => {
    getFingerprint()
      .then((r) => {
        if (isFingerprint(r)) setFingerprint(r);
      })
      .catch(() => {
        // No fingerprint yet
      });
  }, []);

  const updateSample = (index: number, value: string) => {
    setSamples((prev) => prev.map((s, i) => (i === index ? value : s)));
  };

  const addSample = () => {
    setSamples((prev) => [...prev, ""]);
  };

  const removeSample = (index: number) => {
    if (samples.length <= 1) return;
    setSamples((prev) => prev.filter((_, i) => i !== index));
  };

  const handleFileUpload = useCallback(
    async (files: FileList | File[]) => {
      setError(null);
      const fileArray = Array.from(files);

      for (const file of fileArray) {
        if (!UPLOAD_MIME_TYPES.has(file.type)) {
          setError(`"${file.name}" is not a supported file type. Use TXT, MD, DOCX, or PDF.`);
          continue;
        }
        if (file.size > MAX_FILE_SIZE) {
          setError(`"${file.name}" exceeds the 10MB limit.`);
          continue;
        }

        try {
          // For text files, read directly
          if (file.type === "text/plain" || file.type === "text/markdown") {
            const text = await file.text();
            setUploadedFiles((prev) => [...prev, { name: file.name, text }]);
          } else {
            // For DOCX/PDF, we pass the filename and note that server will extract
            // For now, read as text if possible, otherwise note file
            const text = await file.text().catch(() => "");
            if (text.trim()) {
              setUploadedFiles((prev) => [...prev, { name: file.name, text }]);
            } else {
              setError(
                `Could not extract text from "${file.name}". Try pasting the content instead.`
              );
            }
          }
        } catch {
          setError(`Failed to read "${file.name}".`);
        }
      }
    },
    []
  );

  const removeUploadedFile = (index: number) => {
    setUploadedFiles((prev) => prev.filter((_, i) => i !== index));
  };

  const handleAnalyze = async () => {
    setError(null);

    // Gather all samples
    const allSamples: string[] = [];

    if (inputMethod === "paste") {
      const nonEmpty = samples.filter((s) => s.trim().length > 0);
      allSamples.push(...nonEmpty);
    } else {
      const fileTexts = uploadedFiles.map((f) => f.text).filter((t) => t.trim().length > 0);
      allSamples.push(...fileTexts);
    }

    if (allSamples.length === 0) {
      setError("Please add at least one writing sample to analyze.");
      return;
    }

    setIsAnalyzing(true);
    setFeedback(null);

    try {
      const result = await analyzeWriting(allSamples);
      setFingerprint(result);
    } catch {
      setError("Analysis failed. Please try again.");
    } finally {
      setIsAnalyzing(false);
    }
  };

  const sampleCount =
    inputMethod === "paste"
      ? samples.filter((s) => s.trim().length > 0).length
      : uploadedFiles.length;

  return (
    <div className="flex flex-col gap-8 max-w-lg animate-in fade-in slide-in-from-bottom-4 duration-400">
      {/* Header */}
      <div className="flex flex-col gap-3">
        <h1 className="text-[32px] leading-[1.2] text-[#1A1D27] font-display">
          Teach ARIA your voice
        </h1>
        <p className="font-sans text-[15px] leading-relaxed text-[#6B7280]">
          Share examples of your writing so ARIA drafts content that sounds like you, not a robot.
        </p>
      </div>

      {/* Input method tabs */}
      <div className="flex gap-1 rounded-lg bg-[#F5F5F0] p-1" role="tablist">
        <button
          type="button"
          role="tab"
          aria-selected={inputMethod === "paste"}
          onClick={() => setInputMethod("paste")}
          className={`
            flex-1 flex items-center justify-center gap-2
            rounded-md px-4 py-2 font-sans text-[13px] font-medium
            transition-colors duration-150 cursor-pointer
            min-h-[44px]
            focus:outline-none focus:ring-2 focus:ring-[#7B8EAA] focus:ring-offset-2
            ${
              inputMethod === "paste"
                ? "bg-white text-[#1A1D27] shadow-sm"
                : "text-[#6B7280] hover:text-[#1A1D27]"
            }
          `}
        >
          <PenLine size={16} strokeWidth={1.5} />
          Paste samples
        </button>
        <button
          type="button"
          role="tab"
          aria-selected={inputMethod === "upload"}
          onClick={() => setInputMethod("upload")}
          className={`
            flex-1 flex items-center justify-center gap-2
            rounded-md px-4 py-2 font-sans text-[13px] font-medium
            transition-colors duration-150 cursor-pointer
            min-h-[44px]
            focus:outline-none focus:ring-2 focus:ring-[#7B8EAA] focus:ring-offset-2
            ${
              inputMethod === "upload"
                ? "bg-white text-[#1A1D27] shadow-sm"
                : "text-[#6B7280] hover:text-[#1A1D27]"
            }
          `}
        >
          <Upload size={16} strokeWidth={1.5} />
          Upload files
        </button>
      </div>

      {/* Paste samples tab */}
      {inputMethod === "paste" && (
        <div className="flex flex-col gap-3" role="tabpanel" aria-label="Paste writing samples">
          {samples.map((sample, index) => (
            <div key={index} className="relative">
              <textarea
                value={sample}
                onChange={(e) => updateSample(index, e.target.value)}
                placeholder="Paste a recent email, proposal, or message you wrote..."
                rows={4}
                className="
                  w-full bg-white border border-[#E2E0DC] rounded-lg px-4 py-3
                  font-sans text-[15px] text-[#1A1D27]
                  placeholder:text-[#6B7280]/50
                  focus:border-[#5B6E8A] focus:ring-1 focus:ring-[#5B6E8A]
                  focus:outline-none resize-y
                  transition-colors duration-150
                "
                aria-label={`Writing sample ${index + 1}`}
              />
              {samples.length > 1 && (
                <button
                  type="button"
                  onClick={() => removeSample(index)}
                  className="
                    absolute top-2 right-2 p-1.5 rounded
                    text-[#6B7280] hover:text-[#945A5A] hover:bg-[#F5F5F0]
                    transition-colors duration-150
                    focus:outline-none focus:ring-2 focus:ring-[#7B8EAA] focus:ring-offset-2
                    cursor-pointer
                  "
                  aria-label={`Remove sample ${index + 1}`}
                >
                  <Trash2 size={14} strokeWidth={1.5} />
                </button>
              )}
            </div>
          ))}

          <button
            type="button"
            onClick={addSample}
            className="
              flex items-center gap-2 self-start
              text-[#5B6E8A] font-sans text-[13px] font-medium
              hover:text-[#4A5D79]
              transition-colors duration-150
              cursor-pointer rounded px-1 py-1
              focus:outline-none focus:ring-2 focus:ring-[#7B8EAA] focus:ring-offset-2
            "
          >
            <Plus size={16} strokeWidth={1.5} />
            Add another sample
          </button>
        </div>
      )}

      {/* Upload files tab */}
      {inputMethod === "upload" && (
        <div className="flex flex-col gap-3" role="tabpanel" aria-label="Upload writing samples">
          <div
            role="button"
            tabIndex={0}
            onClick={() => fileInputRef.current?.click()}
            onKeyDown={(e) => {
              if (e.key === "Enter" || e.key === " ") {
                e.preventDefault();
                fileInputRef.current?.click();
              }
            }}
            onDrop={(e) => {
              e.preventDefault();
              if (e.dataTransfer.files.length > 0) {
                handleFileUpload(e.dataTransfer.files);
              }
            }}
            onDragOver={(e) => e.preventDefault()}
            className="
              flex flex-col items-center justify-center gap-3
              rounded-xl border-2 border-dashed border-[#E2E0DC] bg-[#FAFAF9]
              px-6 py-10 cursor-pointer
              hover:border-[#5B6E8A]
              transition-colors duration-150
              focus:outline-none focus:ring-2 focus:ring-[#7B8EAA] focus:ring-offset-2
            "
            aria-label="Upload files. Drop files here or click to browse."
          >
            <Upload size={24} strokeWidth={1.5} className="text-[#6B7280]" />
            <p className="font-sans text-[15px] text-[#1A1D27]">
              Drop files here or click to browse
            </p>
            <p className="font-sans text-[13px] text-[#6B7280]">
              TXT, MD, DOCX, PDF — up to 10MB
            </p>
          </div>

          <input
            ref={fileInputRef}
            type="file"
            accept={UPLOAD_ACCEPT}
            multiple
            onChange={(e) => {
              if (e.target.files && e.target.files.length > 0) {
                handleFileUpload(e.target.files);
                e.target.value = "";
              }
            }}
            className="sr-only"
            aria-hidden="true"
            tabIndex={-1}
          />

          {/* Uploaded file list */}
          {uploadedFiles.length > 0 && (
            <div className="flex flex-col gap-2" role="list" aria-label="Uploaded writing samples">
              {uploadedFiles.map((file, index) => (
                <div
                  key={`${file.name}-${index}`}
                  role="listitem"
                  className="flex items-center gap-3 rounded-lg bg-white border border-[#E2E0DC] px-4 py-3"
                >
                  <FileText size={20} strokeWidth={1.5} className="text-[#5B6E8A] shrink-0" />
                  <span className="flex-1 font-sans text-[15px] text-[#1A1D27] truncate">
                    {file.name}
                  </span>
                  <button
                    type="button"
                    onClick={() => removeUploadedFile(index)}
                    className="
                      shrink-0 rounded p-1.5
                      text-[#6B7280] hover:text-[#945A5A] hover:bg-[#F5F5F0]
                      transition-colors duration-150
                      focus:outline-none focus:ring-2 focus:ring-[#7B8EAA] focus:ring-offset-2
                      cursor-pointer
                    "
                    aria-label={`Remove ${file.name}`}
                  >
                    <Trash2 size={16} strokeWidth={1.5} />
                  </button>
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {/* Error */}
      {error && (
        <p className="font-sans text-[13px] text-[#945A5A]" role="alert" aria-live="polite">
          {error}
        </p>
      )}

      {/* Analyze button */}
      {!fingerprint && (
        <button
          type="button"
          onClick={handleAnalyze}
          disabled={isAnalyzing || sampleCount === 0}
          className="
            bg-[#5B6E8A] text-white rounded-lg px-5 py-2.5
            font-sans font-medium text-[15px]
            hover:bg-[#4A5D79] active:bg-[#3D5070]
            disabled:opacity-50 disabled:cursor-not-allowed
            transition-colors duration-150
            focus:outline-none focus:ring-2 focus:ring-[#7B8EAA] focus:ring-offset-2
            cursor-pointer flex items-center justify-center gap-2
            min-h-[44px]
          "
        >
          {isAnalyzing ? (
            <>
              <Loader2 size={16} strokeWidth={1.5} className="animate-spin" />
              ARIA is studying your writing patterns...
            </>
          ) : (
            "Analyze my writing"
          )}
        </button>
      )}

      {/* Style preview card */}
      {fingerprint && (
        <div className="rounded-xl bg-white border border-[#E2E0DC] p-6 flex flex-col gap-4 animate-in fade-in duration-400">
          <p className="font-sans text-[15px] font-medium text-[#1A1D27]">
            Here&apos;s how I&apos;d describe your style:
          </p>

          <blockquote className="font-display italic text-[18px] leading-[1.4] text-[#1A1D27] border-l-2 border-[#E2E0DC] pl-4">
            &ldquo;{fingerprint.style_summary}&rdquo;
          </blockquote>

          {/* Trait badges */}
          <div className="flex flex-wrap gap-2">
            {deriveTraits(fingerprint).map((trait) => (
              <span
                key={trait}
                className="rounded-md bg-[#F5F5F0] border border-[#E2E0DC] px-2.5 py-1 font-sans text-[11px] font-medium text-[#5B6E8A]"
              >
                {trait}
              </span>
            ))}
          </div>

          {/* Confidence indicator */}
          <p className="font-sans text-[13px] text-[#6B7280]">
            Based on {sampleCount} sample{sampleCount !== 1 ? "s" : ""} — more samples = more
            accuracy
          </p>

          {/* Feedback */}
          <div className="flex items-center gap-3">
            <span className="font-sans text-[13px] text-[#6B7280]">Sound right?</span>
            <button
              type="button"
              onClick={() => setFeedback("up")}
              className={`
                rounded p-1.5 transition-colors duration-150 cursor-pointer
                focus:outline-none focus:ring-2 focus:ring-[#7B8EAA] focus:ring-offset-2
                ${
                  feedback === "up"
                    ? "text-[#5A7D60] bg-[#5A7D60]/10"
                    : "text-[#6B7280] hover:text-[#5A7D60] hover:bg-[#F5F5F0]"
                }
              `}
              aria-label="Yes, this sounds right"
              aria-pressed={feedback === "up"}
            >
              <ThumbsUp size={16} strokeWidth={1.5} />
            </button>
            <button
              type="button"
              onClick={() => setFeedback("down")}
              className={`
                rounded p-1.5 transition-colors duration-150 cursor-pointer
                focus:outline-none focus:ring-2 focus:ring-[#7B8EAA] focus:ring-offset-2
                ${
                  feedback === "down"
                    ? "text-[#945A5A] bg-[#945A5A]/10"
                    : "text-[#6B7280] hover:text-[#945A5A] hover:bg-[#F5F5F0]"
                }
              `}
              aria-label="No, this doesn't sound right"
              aria-pressed={feedback === "down"}
            >
              <ThumbsDown size={16} strokeWidth={1.5} />
            </button>
          </div>

          {/* Re-analyze option if feedback is negative */}
          {feedback === "down" && (
            <p className="font-sans text-[13px] text-[#6B7280]">
              Try adding more samples — different types of writing (emails, proposals, LinkedIn
              posts) give ARIA a more complete picture.
            </p>
          )}
        </div>
      )}

      {/* ARIA presence */}
      <div className="rounded-xl bg-[#F5F5F0] border border-[#E2E0DC] px-5 py-4">
        <p className="font-sans text-[13px] leading-relaxed text-[#6B7280] italic">
          The more samples you share, the more I&apos;ll sound like you. Even 3-4 emails give me a
          strong foundation.
        </p>
      </div>

      {/* Actions */}
      <div className="flex flex-col gap-3">
        <button
          type="button"
          onClick={onComplete}
          className="
            bg-[#5B6E8A] text-white rounded-lg px-5 py-2.5
            font-sans font-medium text-[15px]
            hover:bg-[#4A5D79] active:bg-[#3D5070]
            transition-colors duration-150
            focus:outline-none focus:ring-2 focus:ring-[#7B8EAA] focus:ring-offset-2
            cursor-pointer flex items-center justify-center gap-2
            min-h-[44px]
          "
        >
          Continue
        </button>

        <button
          type="button"
          onClick={onSkip}
          className="
            bg-transparent text-[#6B7280] rounded-lg px-4 py-2.5
            font-sans text-[13px]
            hover:bg-[#F5F5F0]
            transition-colors duration-150
            focus:outline-none focus:ring-2 focus:ring-[#7B8EAA] focus:ring-offset-2
            cursor-pointer text-center
            min-h-[44px]
          "
        >
          Skip for now — I&apos;ll learn your style from your emails once connected
        </button>
      </div>
    </div>
  );
}
