import { useCallback, useEffect, useRef, useState } from "react";
import {
  Upload,
  FileText,
  FileSpreadsheet,
  Image,
  Trash2,
  CheckCircle2,
  AlertCircle,
  Loader2,
} from "lucide-react";
import {
  uploadDocument,
  getDocumentStatus,
  getDocuments,
  type CompanyDocument,
} from "@/api/documents";

interface DocumentUploadStepProps {
  onComplete: () => void;
  onSkip: () => void;
}

const ACCEPTED_EXTENSIONS =
  ".pdf,.docx,.pptx,.txt,.md,.csv,.xlsx,.png,.jpg,.jpeg,.webp";

const ACCEPTED_MIME_TYPES = new Set([
  "application/pdf",
  "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
  "application/vnd.openxmlformats-officedocument.presentationml.presentation",
  "text/plain",
  "text/markdown",
  "text/csv",
  "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
  "image/png",
  "image/jpeg",
  "image/webp",
]);

const MAX_FILE_SIZE = 50 * 1024 * 1024; // 50MB

function formatFileSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

function qualityLabel(score: number): { text: string; className: string } {
  if (score >= 80) return { text: "High value", className: "text-[#5A7D60] bg-[#5A7D60]/10" };
  if (score >= 50) return { text: "Good", className: "text-[#5B6E8A] bg-[#5B6E8A]/10" };
  return { text: "Standard", className: "text-[#6B7280] bg-[#6B7280]/10" };
}

function fileIcon(fileType: string) {
  switch (fileType) {
    case "pdf":
    case "docx":
    case "pptx":
    case "txt":
    case "md":
      return <FileText size={20} strokeWidth={1.5} className="text-[#5B6E8A] shrink-0" />;
    case "csv":
    case "xlsx":
      return <FileSpreadsheet size={20} strokeWidth={1.5} className="text-[#5B6E8A] shrink-0" />;
    case "image":
      return <Image size={20} strokeWidth={1.5} className="text-[#5B6E8A] shrink-0" />;
    default:
      return <FileText size={20} strokeWidth={1.5} className="text-[#5B6E8A] shrink-0" />;
  }
}

interface LocalDocument extends CompanyDocument {
  _uploading?: boolean;
  _error?: string;
}

export function DocumentUploadStep({ onComplete, onSkip }: DocumentUploadStepProps) {
  const [documents, setDocuments] = useState<LocalDocument[]>([]);
  const [isDragOver, setIsDragOver] = useState(false);
  const [uploadError, setUploadError] = useState<string | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const pollTimersRef = useRef<Map<string, ReturnType<typeof setInterval>>>(new Map());

  // Load existing documents on mount
  useEffect(() => {
    getDocuments()
      .then((docs) => setDocuments(docs))
      .catch(() => {
        // Silently handle — user may not have a company yet
      });
  }, []);

  // Clean up polling timers
  useEffect(() => {
    const timers = pollTimersRef.current;
    return () => {
      timers.forEach((timer) => clearInterval(timer));
      timers.clear();
    };
  }, []);

  const pollDocumentStatus = useCallback((docId: string) => {
    const timer = setInterval(async () => {
      try {
        const status = await getDocumentStatus(docId);
        setDocuments((prev) =>
          prev.map((doc) =>
            doc.id === docId
              ? {
                  ...doc,
                  processing_status: status.processing_status,
                  processing_progress: status.processing_progress,
                  chunk_count: status.chunk_count,
                  entity_count: status.entity_count,
                  quality_score: status.quality_score,
                }
              : doc
          )
        );

        if (status.processing_status === "complete" || status.processing_status === "failed") {
          clearInterval(timer);
          pollTimersRef.current.delete(docId);
        }
      } catch {
        // Silently retry on next interval
      }
    }, 2000);
    pollTimersRef.current.set(docId, timer);
  }, []);

  const handleFiles = useCallback(
    async (files: FileList | File[]) => {
      setUploadError(null);
      const fileArray = Array.from(files);

      for (const file of fileArray) {
        // Client-side validation
        if (!ACCEPTED_MIME_TYPES.has(file.type)) {
          setUploadError(`"${file.name}" is not a supported file type.`);
          continue;
        }
        if (file.size > MAX_FILE_SIZE) {
          setUploadError(`"${file.name}" exceeds the 50MB file size limit.`);
          continue;
        }

        // Optimistic placeholder
        const placeholderId = `uploading-${Date.now()}-${file.name}`;
        const placeholder: LocalDocument = {
          id: placeholderId,
          company_id: "",
          uploaded_by: "",
          filename: file.name,
          file_type: file.name.split(".").pop() || "unknown",
          file_size_bytes: file.size,
          storage_path: "",
          processing_status: "uploaded",
          processing_progress: 0,
          chunk_count: 0,
          entity_count: 0,
          quality_score: 0,
          extracted_metadata: {},
          created_at: new Date().toISOString(),
          updated_at: new Date().toISOString(),
          _uploading: true,
        };
        setDocuments((prev) => [placeholder, ...prev]);

        try {
          const doc = await uploadDocument(file);
          // Replace placeholder with real document
          setDocuments((prev) =>
            prev.map((d) => (d.id === placeholderId ? doc : d))
          );
          // Start polling for processing status
          if (doc.processing_status === "processing") {
            pollDocumentStatus(doc.id);
          }
        } catch (err) {
          // Mark placeholder as failed
          const message =
            err instanceof Error ? err.message : "Upload failed";
          setDocuments((prev) =>
            prev.map((d) =>
              d.id === placeholderId
                ? { ...d, _uploading: false, _error: message }
                : d
            )
          );
        }
      }
    },
    [pollDocumentStatus]
  );

  const handleDrop = useCallback(
    (e: React.DragEvent) => {
      e.preventDefault();
      setIsDragOver(false);
      if (e.dataTransfer.files.length > 0) {
        handleFiles(e.dataTransfer.files);
      }
    },
    [handleFiles]
  );

  const handleDragOver = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    setIsDragOver(true);
  }, []);

  const handleDragLeave = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    setIsDragOver(false);
  }, []);

  const handleRemove = (docId: string) => {
    // Clear any polling timer
    const timer = pollTimersRef.current.get(docId);
    if (timer) {
      clearInterval(timer);
      pollTimersRef.current.delete(docId);
    }
    setDocuments((prev) => prev.filter((d) => d.id !== docId));
  };

  const handleBrowseClick = () => {
    fileInputRef.current?.click();
  };

  const handleFileInputChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files && e.target.files.length > 0) {
      handleFiles(e.target.files);
      // Reset input so same file can be re-selected
      e.target.value = "";
    }
  };

  const uploadedCount = documents.filter(
    (d) => !d._uploading && !d._error
  ).length;

  return (
    <div className="flex flex-col gap-8 max-w-lg animate-in fade-in slide-in-from-bottom-4 duration-400">
      {/* Header */}
      <div className="flex flex-col gap-3">
        <h1 className="text-[32px] leading-[1.2] text-[#1A1D27] font-display">
          Share your company's knowledge
        </h1>
        <p className="font-sans text-[15px] leading-relaxed text-[#6B7280]">
          Upload capabilities decks, org charts, product sheets — anything that
          helps ARIA understand your business.
        </p>
      </div>

      {/* Upload zone */}
      <div
        role="button"
        tabIndex={0}
        onClick={handleBrowseClick}
        onKeyDown={(e) => {
          if (e.key === "Enter" || e.key === " ") {
            e.preventDefault();
            handleBrowseClick();
          }
        }}
        onDrop={handleDrop}
        onDragOver={handleDragOver}
        onDragLeave={handleDragLeave}
        className={`
          flex flex-col items-center justify-center gap-3
          rounded-xl border-2 border-dashed px-6 py-10
          transition-colors duration-150 cursor-pointer
          focus:outline-none focus:ring-2 focus:ring-[#7B8EAA] focus:ring-offset-2
          ${
            isDragOver
              ? "border-[#5B6E8A] bg-[#5B6E8A]/5"
              : "border-[#E2E0DC] bg-[#FAFAF9] hover:border-[#5B6E8A]"
          }
        `}
        aria-label="Upload documents. Drop files here or click to browse."
      >
        <Upload
          size={24}
          strokeWidth={1.5}
          className={`transition-colors duration-150 ${
            isDragOver ? "text-[#5B6E8A]" : "text-[#6B7280]"
          }`}
        />
        <p className="font-sans text-[15px] text-[#1A1D27]">
          Drop files here or click to browse
        </p>
        <p className="font-sans text-[13px] text-[#6B7280]">
          PDF, DOCX, PPTX, TXT, MD, CSV, XLSX, PNG, JPG, WebP — up to 50MB
        </p>
      </div>

      <input
        ref={fileInputRef}
        type="file"
        accept={ACCEPTED_EXTENSIONS}
        multiple
        onChange={handleFileInputChange}
        className="sr-only"
        aria-hidden="true"
        tabIndex={-1}
      />

      {/* Upload error */}
      {uploadError && (
        <div
          className="flex items-center gap-2 font-sans text-[13px] text-[#945A5A]"
          role="alert"
          aria-live="polite"
        >
          <AlertCircle size={16} strokeWidth={1.5} className="shrink-0" />
          <span>{uploadError}</span>
        </div>
      )}

      {/* File list */}
      {documents.length > 0 && (
        <div className="flex flex-col gap-2" role="list" aria-label="Uploaded documents">
          {documents.map((doc) => (
            <DocumentRow
              key={doc.id}
              doc={doc}
              onRemove={() => handleRemove(doc.id)}
            />
          ))}
        </div>
      )}

      {/* ARIA presence */}
      <div className="rounded-xl bg-[#F5F5F0] border border-[#E2E0DC] px-5 py-4">
        <p className="font-sans text-[13px] leading-relaxed text-[#6B7280] italic">
          Each document makes me significantly smarter about your business.
          Capabilities decks and product sheets are especially valuable.
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
          {uploadedCount > 0
            ? `Continue with ${uploadedCount} document${uploadedCount !== 1 ? "s" : ""}`
            : "Continue"}
        </button>

        {/* Skip affordance */}
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
          Skip for now — you can upload documents later from your profile
        </button>
      </div>
    </div>
  );
}

// --- Document row ---

interface DocumentRowProps {
  doc: LocalDocument;
  onRemove: () => void;
}

function DocumentRow({ doc, onRemove }: DocumentRowProps) {
  const isUploading = doc._uploading;
  const hasError = !!doc._error;
  const isProcessing = doc.processing_status === "processing";
  const isComplete = doc.processing_status === "complete";
  const isFailed = doc.processing_status === "failed";

  return (
    <div
      role="listitem"
      className="flex items-center gap-3 rounded-lg bg-white border border-[#E2E0DC] px-4 py-3 transition-colors duration-150"
    >
      {/* Icon */}
      {fileIcon(doc.file_type)}

      {/* Info */}
      <div className="flex-1 min-w-0">
        <p className="font-sans text-[15px] text-[#1A1D27] truncate">
          {doc.filename}
        </p>
        <div className="flex items-center gap-2">
          <span className="font-mono text-[13px] text-[#6B7280]">
            {formatFileSize(doc.file_size_bytes)}
          </span>

          {isUploading && (
            <span className="flex items-center gap-1 font-sans text-[13px] text-[#5B6E8A]">
              <Loader2 size={12} strokeWidth={1.5} className="animate-spin" />
              Uploading
            </span>
          )}

          {hasError && (
            <span className="font-sans text-[13px] text-[#945A5A]">
              {doc._error}
            </span>
          )}

          {isProcessing && (
            <span className="flex items-center gap-1 font-sans text-[13px] text-[#5B6E8A]">
              <Loader2 size={12} strokeWidth={1.5} className="animate-spin" />
              Processing
              <span className="font-mono text-[13px]">
                {Math.round(doc.processing_progress)}%
              </span>
            </span>
          )}

          {isComplete && (
            <span className="flex items-center gap-1 font-sans text-[13px] text-[#5A7D60]">
              <CheckCircle2 size={12} strokeWidth={1.5} />
              Complete
            </span>
          )}

          {isFailed && (
            <span className="flex items-center gap-1 font-sans text-[13px] text-[#945A5A]">
              <AlertCircle size={12} strokeWidth={1.5} />
              Processing failed
            </span>
          )}
        </div>
      </div>

      {/* Quality badge */}
      {isComplete && doc.quality_score > 0 && (
        <span
          className={`shrink-0 rounded-md px-2 py-0.5 font-sans text-[11px] font-medium ${
            qualityLabel(doc.quality_score).className
          }`}
        >
          {qualityLabel(doc.quality_score).text}
        </span>
      )}

      {/* Remove */}
      <button
        type="button"
        onClick={(e) => {
          e.stopPropagation();
          onRemove();
        }}
        className="
          shrink-0 rounded p-1.5
          text-[#6B7280] hover:text-[#945A5A] hover:bg-[#F5F5F0]
          transition-colors duration-150
          focus:outline-none focus:ring-2 focus:ring-[#7B8EAA] focus:ring-offset-2
          cursor-pointer
        "
        aria-label={`Remove ${doc.filename}`}
      >
        <Trash2 size={16} strokeWidth={1.5} />
      </button>
    </div>
  );
}
