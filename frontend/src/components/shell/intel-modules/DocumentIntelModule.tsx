/**
 * DocumentIntelModule - Document intelligence in Intel Panel
 *
 * Shows processed document summary with status badges:
 * - Complete (green), Processing (amber animated), Failed (red), Uploaded (gray)
 * - Quality score mini-bar, entity + chunk counts
 * - Up to 5 most recent documents
 *
 * Follows JarvisInsightsModule pattern:
 * - Skeleton loading, empty state, data-aria-id
 * - Dark theme (Intel Panel context)
 */

import { FileText } from 'lucide-react';
import { useDocuments } from '@/hooks/useDocuments';
import type { CompanyDocument } from '@/api/documents';

const STATUS_STYLES: Record<string, { label: string; color: string; animated?: boolean }> = {
  complete: { label: 'Complete', color: 'var(--success)' },
  processing: { label: 'Processing', color: 'var(--warning)', animated: true },
  failed: { label: 'Failed', color: 'var(--critical)' },
  uploaded: { label: 'Uploaded', color: 'var(--text-secondary)' },
};

function DocumentIntelSkeleton() {
  return (
    <div className="space-y-2">
      <div className="h-3 w-36 rounded bg-[var(--border)] animate-pulse" />
      <div className="space-y-2">
        {Array.from({ length: 3 }).map((_, i) => (
          <div key={i} className="h-16 rounded-lg bg-[var(--border)] animate-pulse" />
        ))}
      </div>
    </div>
  );
}

function DocumentRow({ doc }: { doc: CompanyDocument }) {
  const status = STATUS_STYLES[doc.processing_status] ?? STATUS_STYLES.uploaded;

  return (
    <div
      className="rounded-lg border p-2.5"
      style={{ borderColor: 'var(--border)', backgroundColor: 'var(--bg-subtle)' }}
    >
      <div className="flex items-start gap-2">
        <FileText size={14} className="mt-0.5 flex-shrink-0" style={{ color: 'var(--text-secondary)' }} />
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2 mb-1">
            <span
              className="font-sans text-[12px] truncate flex-1"
              style={{ color: 'var(--text-primary)' }}
              title={doc.filename}
            >
              {doc.filename}
            </span>
            <span
              className={`inline-flex items-center px-1.5 py-0.5 rounded text-[9px] font-medium uppercase tracking-wide ${status.animated ? 'animate-pulse' : ''}`}
              style={{
                backgroundColor: `color-mix(in srgb, ${status.color} 15%, transparent)`,
                color: status.color,
              }}
            >
              {status.label}
            </span>
          </div>

          {/* Quality score mini-bar */}
          {doc.processing_status === 'complete' && (
            <div className="flex items-center gap-2 mb-1">
              <div
                className="flex-1 h-[3px] rounded-full"
                style={{ backgroundColor: 'var(--border)' }}
              >
                <div
                  className="h-full rounded-full"
                  style={{
                    width: `${doc.quality_score * 100}%`,
                    backgroundColor: 'var(--accent)',
                    opacity: 0.7,
                  }}
                />
              </div>
              <span
                className="font-mono text-[10px]"
                style={{ color: 'var(--text-secondary)' }}
              >
                {(doc.quality_score * 100).toFixed(0)}%
              </span>
            </div>
          )}

          {/* Counts */}
          <div className="flex items-center gap-3">
            <span className="font-mono text-[10px]" style={{ color: 'var(--text-secondary)' }}>
              {doc.entity_count} entities
            </span>
            <span className="font-mono text-[10px]" style={{ color: 'var(--text-secondary)' }}>
              {doc.chunk_count} chunks
            </span>
          </div>
        </div>
      </div>
    </div>
  );
}

export function DocumentIntelModule() {
  const { data: documents, isLoading } = useDocuments();

  if (isLoading) return <DocumentIntelSkeleton />;

  if (!documents || documents.length === 0) {
    return (
      <div data-aria-id="intel-document-intel" className="space-y-2">
        <h3
          className="font-sans text-[11px] font-medium uppercase tracking-wider mb-3"
          style={{ color: 'var(--text-secondary)' }}
        >
          Document Intelligence
        </h3>
        <div
          className="rounded-lg border p-4"
          style={{ borderColor: 'var(--border)', backgroundColor: 'var(--bg-subtle)' }}
        >
          <p className="font-sans text-[12px]" style={{ color: 'var(--text-secondary)' }}>
            No documents uploaded yet. Share files with ARIA to build your knowledge base.
          </p>
        </div>
      </div>
    );
  }

  const sorted = [...documents].sort(
    (a, b) => new Date(b.updated_at).getTime() - new Date(a.updated_at).getTime(),
  );
  const recent = sorted.slice(0, 5);
  const totalEntities = documents.reduce((sum, d) => sum + d.entity_count, 0);

  return (
    <div data-aria-id="intel-document-intel" className="space-y-2">
      <h3
        className="font-sans text-[11px] font-medium uppercase tracking-wider mb-3"
        style={{ color: 'var(--text-secondary)' }}
      >
        Document Intelligence
      </h3>

      {/* Summary */}
      <div className="flex items-center gap-2 mb-2">
        <span className="font-mono text-[11px]" style={{ color: 'var(--text-secondary)' }}>
          {documents.length} document{documents.length !== 1 ? 's' : ''} processed
        </span>
        <span
          className="w-1 h-1 rounded-full"
          style={{ backgroundColor: 'var(--text-secondary)' }}
        />
        <span className="font-mono text-[11px]" style={{ color: 'var(--text-secondary)' }}>
          {totalEntities} entities
        </span>
      </div>

      {/* Document list */}
      <div className="space-y-2">
        {recent.map((doc) => (
          <DocumentRow key={doc.id} doc={doc} />
        ))}
      </div>
    </div>
  );
}
