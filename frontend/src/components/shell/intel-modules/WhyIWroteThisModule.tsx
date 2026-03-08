import { useState, useEffect } from 'react';
import DOMPurify from 'dompurify';
import { Brain, Mail, Clock, ChevronDown, ChevronUp, Loader2 } from 'lucide-react';
import { useIntelDraft, useIntelDrafts, useRouteContext, formatRelativeTime } from '@/hooks/useIntelPanelData';
import { getOriginalEmail } from '@/api/drafts';

function decodeHtmlEntities(text: string): string {
  const textarea = document.createElement('textarea');
  textarea.innerHTML = text;
  let decoded = textarea.value;
  // Strip zero-width characters
  decoded = decoded.replace(/[\u200B\uFEFF\u200C\u200D]/g, '');
  // Clean up excessive whitespace
  decoded = decoded.replace(/\s+/g, ' ').trim();
  return decoded;
}

function formatEmailThread(text: string): string {
  let formatted = decodeHtmlEntities(text);
  // Add line breaks before common email headers
  formatted = formatted.replace(/(From:|Date:|To:|Subject:|Sent from)/g, '\n$1');
  // Add line break before "On [date]... wrote:" pattern
  formatted = formatted.replace(/(On\s)/g, '\n\n$1');
  return formatted.trim();
}

interface OriginalEmail {
  from: string;
  sender_name?: string;
  sender_email: string;
  date: string;
  subject: string;
  snippet: string;
}

interface Reasoning {
  summary: string;
  factors: string[];
}

interface CompetitivePositioning {
  competitor?: string;
  differentiation?: string[];
  weaknesses?: string[];
  pricing?: {
    range?: string;
    notes?: string;
  };
}

interface DraftContext {
  signal_context?: string;
  user_context?: string;
}

function WhyIWroteThisSkeleton() {
  return (
    <div className="space-y-3">
      <div className="h-3 w-28 rounded bg-[var(--border)] animate-pulse" />
      <div className="h-20 rounded-lg bg-[var(--border)] animate-pulse" />
      <div className="space-y-1.5 pl-1">
        <div className="h-3 w-full rounded bg-[var(--border)] animate-pulse" />
        <div className="h-3 w-3/4 rounded bg-[var(--border)] animate-pulse" />
        <div className="h-3 w-5/6 rounded bg-[var(--border)] animate-pulse" />
      </div>
    </div>
  );
}

/**
 * Expandable block showing the original email being replied to.
 * Shows snippet by default, with a "Show full email" toggle that
 * fetches the complete body from the email provider on demand.
 *
 * Auto-fetches full email if snippet is null/empty on mount.
 */
function ReplyingToBlock({
  draftId,
  originalEmail,
}: {
  draftId: string;
  originalEmail: OriginalEmail | undefined;
}) {
  const [expanded, setExpanded] = useState(false);
  const [fullBody, setFullBody] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [fetchError, setFetchError] = useState(false);
  const [autoFetched, setAutoFetched] = useState(false);

  // Check if snippet is missing or empty
  const snippetMissing = !originalEmail?.snippet || originalEmail.snippet.trim() === '';

  // Auto-fetch full email when snippet is null/empty
  useEffect(() => {
    if (!snippetMissing || autoFetched || loading || !draftId) {
      return;
    }

    const autoFetchFullEmail = async () => {
      setLoading(true);
      setFetchError(false);
      try {
        const result = await getOriginalEmail(draftId, true);
        if (result.has_full_body && result.full_body) {
          setFullBody(result.full_body);
          setExpanded(true);
        } else {
          setFetchError(true);
        }
      } catch {
        setFetchError(true);
      } finally {
        setLoading(false);
        setAutoFetched(true);
      }
    };

    autoFetchFullEmail();
  }, [snippetMissing, autoFetched, loading, draftId]);

  const handleToggle = async () => {
    if (expanded) {
      setExpanded(false);
      return;
    }

    // If we already fetched the full body, just expand
    if (fullBody !== null) {
      setExpanded(true);
      return;
    }

    // Fetch from backend
    setLoading(true);
    setFetchError(false);
    try {
      const result = await getOriginalEmail(draftId, true);
      if (result.has_full_body && result.full_body) {
        setFullBody(result.full_body);
      } else {
        // No full body available — show snippet expanded (untruncated)
        setFullBody(null);
        setFetchError(true);
      }
      setExpanded(true);
    } catch {
      setFetchError(true);
      setExpanded(true);
    } finally {
      setLoading(false);
    }
  };

  if (!originalEmail) {
    return (
      <div
        className="rounded-lg border p-3"
        style={{ borderColor: 'var(--border)', backgroundColor: 'var(--bg-subtle)' }}
      >
        <div className="flex items-center gap-1.5 mb-1">
          <Mail size={12} style={{ color: 'var(--text-secondary)' }} />
          <span
            className="font-sans text-[10px] font-medium uppercase tracking-wider"
            style={{ color: 'var(--text-secondary)' }}
          >
            Replying To
          </span>
        </div>
        <p className="font-sans text-[12px] italic" style={{ color: 'var(--text-secondary)' }}>
          Original email not available
        </p>
      </div>
    );
  }

  const sanitizedBody = fullBody
    ? DOMPurify.sanitize(fullBody, {
        ALLOWED_TAGS: [
          'p', 'br', 'div', 'span', 'a', 'b', 'strong', 'i', 'em', 'u',
          'ul', 'ol', 'li', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6',
          'table', 'thead', 'tbody', 'tr', 'td', 'th', 'blockquote', 'hr', 'img',
        ],
        ALLOWED_ATTR: ['href', 'target', 'rel', 'src', 'alt', 'width', 'height', 'style'],
      })
    : '';

  return (
    <div
      className="rounded-lg border p-3"
      style={{ borderColor: 'var(--border)', backgroundColor: 'var(--bg-subtle)' }}
    >
      <div className="flex items-center gap-1.5 mb-2">
        <Mail size={12} style={{ color: 'var(--accent)' }} />
        <span
          className="font-sans text-[10px] font-medium uppercase tracking-wider"
          style={{ color: 'var(--accent)' }}
        >
          Replying To
        </span>
      </div>
      <div className="space-y-1.5">
        <div className="flex items-start gap-2">
          <span
            className="font-sans text-[11px] font-medium flex-shrink-0"
            style={{ color: 'var(--text-secondary)' }}
          >
            From:
          </span>
          <span
            className="font-sans text-[12px]"
            style={{ color: 'var(--text-primary)' }}
          >
            {originalEmail.from}
          </span>
        </div>
        {originalEmail.date && (
          <div className="flex items-start gap-2">
            <Clock size={10} className="mt-1 flex-shrink-0" style={{ color: 'var(--text-secondary)' }} />
            <span
              className="font-sans text-[11px]"
              style={{ color: 'var(--text-secondary)' }}
            >
              {formatRelativeTime(originalEmail.date)}
            </span>
          </div>
        )}
        {originalEmail.subject && (
          <div className="flex items-start gap-2">
            <span
              className="font-sans text-[11px] font-medium flex-shrink-0"
              style={{ color: 'var(--text-secondary)' }}
            >
              Subject:
            </span>
            <span
              className="font-sans text-[12px]"
              style={{ color: 'var(--text-primary)' }}
            >
              {originalEmail.subject}
            </span>
          </div>
        )}

        {/* Email body: snippet, full body, loading state, or error */}
        <div className="mt-2 pt-2 border-t" style={{ borderColor: 'var(--border)' }}>
          {/* Case 1: Snippet is null/empty - show loading or auto-fetched content */}
          {snippetMissing ? (
            <>
              {loading && (
                <p
                  className="font-sans text-[12px] italic flex items-center gap-1.5"
                  style={{ color: 'var(--text-secondary)' }}
                >
                  <Loader2 size={12} className="animate-spin" />
                  Loading original email...
                </p>
              )}
              {!loading && fullBody && (
                <div
                  className="font-sans text-[12px] leading-[1.5] max-h-[400px] overflow-y-auto prose prose-sm prose-slate"
                  style={{ color: 'var(--text-primary)' }}
                  dangerouslySetInnerHTML={{ __html: sanitizedBody }}
                />
              )}
              {!loading && fetchError && !fullBody && (
                <p
                  className="font-sans text-[12px] italic"
                  style={{ color: 'var(--text-secondary)' }}
                >
                  Original email content unavailable
                </p>
              )}
            </>
          ) : (
            <>
              {/* Case 2: Snippet exists - show snippet with expand/collapse */}
              {expanded && fullBody ? (
                <div
                  className="font-sans text-[12px] leading-[1.5] max-h-[400px] overflow-y-auto prose prose-sm prose-slate"
                  style={{ color: 'var(--text-primary)' }}
                  dangerouslySetInnerHTML={{ __html: sanitizedBody }}
                />
              ) : expanded ? (
                <p
                  className="font-sans text-[12px] leading-[1.5] whitespace-pre-wrap"
                  style={{ color: 'var(--text-primary)' }}
                >
                  {formatEmailThread(originalEmail.snippet)}
                </p>
              ) : (
                <p
                  className="font-sans text-[12px] leading-[1.5] line-clamp-3"
                  style={{ color: 'var(--text-primary)' }}
                >
                  {decodeHtmlEntities(originalEmail.snippet)}
                </p>
              )}

              {/* Toggle link */}
              <button
                type="button"
                onClick={handleToggle}
                disabled={loading}
                className="mt-2 flex items-center gap-1 font-sans text-[11px] font-medium hover:underline disabled:opacity-50"
                style={{ color: 'var(--accent)' }}
              >
                {loading ? (
                  <>
                    <Loader2 size={10} className="animate-spin" />
                    Loading full email...
                  </>
                ) : expanded ? (
                  <>
                    <ChevronUp size={10} />
                    Collapse
                  </>
                ) : (
                  <>
                    <ChevronDown size={10} />
                    Show full email
                  </>
                )}
              </button>

              {expanded && fetchError && !fullBody && (
                <p
                  className="mt-1 font-sans text-[11px] italic"
                  style={{ color: 'var(--text-secondary)' }}
                >
                  Full email content is not available. Showing snippet only.
                </p>
              )}
            </>
          )}
        </div>
      </div>
    </div>
  );
}


// Intelligence draft types that have competitive positioning data
const INTELLIGENCE_DRAFT_TYPES = [
  'competitive_displacement',
  'conference_outreach',
  'clinical_trial_outreach',
];

export interface WhyIWroteThisModuleProps {
  reasoning?: Reasoning;
}

export function WhyIWroteThisModule({ reasoning: propReasoning }: WhyIWroteThisModuleProps) {
  const { draftId, isDraftDetail } = useRouteContext();
  const { data: draft, isLoading: draftLoading } = useIntelDraft(draftId);
  const { data: drafts, isLoading: draftsLoading } = useIntelDrafts();

  const isLoading = isDraftDetail ? draftLoading : draftsLoading;

  if (isLoading && !propReasoning) return <WhyIWroteThisSkeleton />;

  // Check if this is an intelligence-generated draft with competitive positioning
  const isIntelligenceDraft =
    isDraftDetail &&
    draft &&
    draft.draft_type &&
    INTELLIGENCE_DRAFT_TYPES.includes(draft.draft_type);

  // Render full ARIA reasoning chain for intelligence drafts
  if (isIntelligenceDraft && draft) {
    // If aria_reasoning exists (LLM-generated narrative), show it as primary
    if (draft.aria_reasoning) {
      return (
        <div data-aria-id="intel-why-wrote" className="space-y-3">
          <h3
            className="font-sans text-[11px] font-medium uppercase tracking-wider"
            style={{ color: 'var(--text-secondary)' }}
          >
            Why I Wrote This
          </h3>
          <div className="text-sm leading-relaxed">
            {draft.aria_reasoning.split('\n').map((line, i) => {
              if (line.startsWith('## ')) {
                return (
                  <h4
                    key={i}
                    className="text-xs font-semibold uppercase tracking-wide text-blue-600 mt-3 mb-1"
                  >
                    {line.replace('## ', '')}
                  </h4>
                );
              }
              if (line.startsWith('• ') || line.startsWith('- ')) {
                return (
                  <div key={i} className="flex gap-2 pl-1" style={{ color: 'var(--text-primary)' }}>
                    <span className="text-slate-400">•</span>
                    <span>{line.replace(/^[•\-]\s*/, '')}</span>
                  </div>
                );
              }
              if (line.trim() === '') {
                return <div key={i} className="h-2" />;
              }
              return (
                <p key={i} className="mb-1" style={{ color: 'var(--text-primary)' }}>
                  {line}
                </p>
              );
            })}
          </div>
          {draft.style_match_score !== undefined && (
            <div className="flex items-center gap-2 text-xs pt-1 border-t"
              style={{ color: 'var(--text-secondary)', borderColor: 'var(--border)' }}
            >
              <span>Written in your voice</span>
              <span className="font-medium">{Math.round(draft.style_match_score * 100)}% style match</span>
            </div>
          )}
        </div>
      );
    }

    const competitivePositioning = draft.competitive_positioning as CompetitivePositioning | undefined;
    const contextData = draft.context as DraftContext | undefined;
    const competitor = competitivePositioning?.competitor || 'this competitor';
    const differentiation = competitivePositioning?.differentiation || [];
    const weaknesses = competitivePositioning?.weaknesses || [];
    const pricing = competitivePositioning?.pricing;
    const signalContext = contextData?.signal_context || '';
    const ariaNotes = draft.aria_notes || '';

    return (
      <div data-aria-id="intel-why-wrote" className="space-y-3">
        <h3
          className="font-sans text-[11px] font-medium uppercase tracking-wider"
          style={{ color: 'var(--text-secondary)' }}
        >
          Why I Wrote This
        </h3>

        {/* Signal that triggered this */}
        {signalContext && (
          <div>
            <div className="text-xs font-medium text-amber-600 uppercase tracking-wide mb-1">
              Signal Detected
            </div>
            <p className="text-sm text-slate-700">
              {signalContext}
            </p>
          </div>
        )}

        {/* Why ARIA acted */}
        <div>
          <div className="text-xs font-medium text-blue-600 uppercase tracking-wide mb-1">
            Why ARIA Acted
          </div>
          <p className="text-sm text-slate-700">
            {competitor} is a tracked competitor. This signal indicates a supply chain vulnerability that creates a displacement window for your accounts.
          </p>
        </div>

        {/* Competitive positioning used */}
        {(differentiation.length > 0 || weaknesses.length > 0 || pricing) && (
          <div>
            <div className="text-xs font-medium text-green-600 uppercase tracking-wide mb-1">
              Competitive Positioning Used
            </div>
            <div className="text-sm text-slate-700 space-y-1">
              {differentiation.length > 0 && (
                <p>
                  <span className="font-medium">Your advantages:</span>{' '}
                  {differentiation.slice(0, 3).join('; ')}
                </p>
              )}
              {weaknesses.length > 0 && (
                <p>
                  <span className="font-medium">Their vulnerabilities:</span>{' '}
                  {weaknesses.slice(0, 2).join('; ')}
                </p>
              )}
              {pricing?.range && (
                <p>
                  <span className="font-medium">Their pricing:</span>{' '}
                  {pricing.range}
                  {pricing.notes ? ` — ${pricing.notes.substring(0, 100)}` : ''}
                </p>
              )}
            </div>
          </div>
        )}

        {/* Email strategy */}
        <div>
          <div className="text-xs font-medium text-purple-600 uppercase tracking-wide mb-1">
            Email Strategy
          </div>
          <p className="text-sm text-slate-700">
            {ariaNotes || 'Positioned around supply chain reliability and proactive diversification. Led with value, not competitor problems.'}
          </p>
        </div>

        {/* Style match */}
        {draft.style_match_score !== undefined && (
          <div className="flex items-center gap-2 text-xs text-slate-500 pt-1 border-t border-slate-200">
            <span>Written in your voice</span>
            <span className="font-medium">{Math.round(draft.style_match_score * 100)}% style match</span>
          </div>
        )}
      </div>
    );
  }

  // Reply draft handling - show the original email being replied to
  if (isDraftDetail && draft && draft.purpose === 'reply') {
    const originalEmail = draft.original_email as OriginalEmail | undefined;
    const ctx = draft.context as Record<string, string> | undefined;

    return (
      <div data-aria-id="intel-why-wrote" className="space-y-3">
        <h3
          className="font-sans text-[11px] font-medium uppercase tracking-wider"
          style={{ color: 'var(--text-secondary)' }}
        >
          Why I Wrote This
        </h3>

        {/* REPLYING TO block - show the original incoming email */}
        <ReplyingToBlock draftId={draftId} originalEmail={originalEmail} />

        {/* ARIA's reasoning for this reply */}
        <div
          className="rounded-lg border p-3"
          style={{ borderColor: 'var(--border)', backgroundColor: 'var(--bg-subtle)' }}
        >
          <div className="flex items-start gap-2">
            <Brain size={14} className="mt-0.5 flex-shrink-0" style={{ color: 'var(--accent)' }} />
            <div className="space-y-1">
              <p className="font-sans text-[13px] leading-[1.6]" style={{ color: 'var(--text-primary)' }}>
                {ctx?.user_context ?? `This reply to ${draft.recipient_name ?? draft.recipient_email} was crafted based on your communication history and relationship context.`}
              </p>
            </div>
          </div>
        </div>

        {/* Context factors */}
        <div className="space-y-1.5 pl-1">
          <div className="flex items-start gap-2">
            <div
              className="w-1 h-1 rounded-full mt-2 flex-shrink-0"
              style={{ backgroundColor: 'var(--accent)' }}
            />
            <p className="font-sans text-[12px] leading-[1.5]" style={{ color: 'var(--text-secondary)' }}>
              Purpose: {draft.purpose}
            </p>
          </div>
          <div className="flex items-start gap-2">
            <div
              className="w-1 h-1 rounded-full mt-2 flex-shrink-0"
              style={{ backgroundColor: 'var(--accent)' }}
            />
            <p className="font-sans text-[12px] leading-[1.5]" style={{ color: 'var(--text-secondary)' }}>
              Tone: {draft.tone}
            </p>
          </div>
          {draft.style_match_score && (
            <div className="flex items-start gap-2">
              <div
                className="w-1 h-1 rounded-full mt-2 flex-shrink-0"
                style={{ backgroundColor: 'var(--accent)' }}
              />
              <p className="font-sans text-[12px] leading-[1.5]" style={{ color: 'var(--text-secondary)' }}>
                Style match: {Math.round(draft.style_match_score * 100)}%
              </p>
            </div>
          )}
          {draft.lead_memory_id && (
            <div className="flex items-start gap-2">
              <div
                className="w-1 h-1 rounded-full mt-2 flex-shrink-0"
                style={{ backgroundColor: 'var(--accent)' }}
              />
              <p className="font-sans text-[12px] leading-[1.5]" style={{ color: 'var(--text-secondary)' }}>
                Linked to pipeline lead
              </p>
            </div>
          )}
        </div>

        {/* Style match footer */}
        {draft.style_match_score !== undefined && (
          <div
            className="flex items-center gap-2 text-xs pt-1 border-t"
            style={{ color: 'var(--text-secondary)', borderColor: 'var(--border)' }}
          >
            <span>Written in your voice</span>
            <span className="font-medium">{Math.round(draft.style_match_score * 100)}% style match</span>
          </div>
        )}
      </div>
    );
  }

  // Standard draft handling
  let reasoning: Reasoning;
  if (propReasoning) {
    reasoning = propReasoning;
  } else if (isDraftDetail && draft) {
    const ctx = draft.context as Record<string, string> | undefined;
    reasoning = {
      summary: ctx?.user_context ?? `This ${draft.purpose} email to ${draft.recipient_name ?? draft.recipient_email} was crafted based on your communication history and relationship context.`,
      factors: [
        `Purpose: ${draft.purpose}`,
        `Tone: ${draft.tone}`,
        `Recipient: ${draft.recipient_name ?? draft.recipient_email}`,
        ...(draft.style_match_score ? [`Style match: ${Math.round(draft.style_match_score * 100)}%`] : []),
        ...(draft.lead_memory_id ? ['Linked to pipeline lead'] : []),
      ],
    };
  } else if (drafts && drafts.length > 0) {
    const latest = drafts[0];
    reasoning = {
      summary: `Most recent draft: ${latest.purpose} email to ${latest.recipient_name ?? latest.recipient_email}.`,
      factors: [
        `Purpose: ${latest.purpose}`,
        `Tone: ${latest.tone}`,
        `Status: ${latest.status}`,
      ],
    };
  } else {
    return (
      <div data-aria-id="intel-why-wrote" className="space-y-3">
        <h3
          className="font-sans text-[11px] font-medium uppercase tracking-wider"
          style={{ color: 'var(--text-secondary)' }}
        >
          Why I Wrote This
        </h3>
        <div
          className="rounded-lg border p-4"
          style={{ borderColor: 'var(--border)', backgroundColor: 'var(--bg-subtle)' }}
        >
          <p className="font-sans text-[12px]" style={{ color: 'var(--text-secondary)' }}>
            No draft context available. ARIA will explain her reasoning when composing emails.
          </p>
        </div>
      </div>
    );
  }

  return (
    <div data-aria-id="intel-why-wrote" className="space-y-3">
      <h3
        className="font-sans text-[11px] font-medium uppercase tracking-wider"
        style={{ color: 'var(--text-secondary)' }}
      >
        Why I Wrote This
      </h3>
      <div
        className="rounded-lg border p-3"
        style={{ borderColor: 'var(--border)', backgroundColor: 'var(--bg-subtle)' }}
      >
        <div className="flex items-start gap-2">
          <Brain size={14} className="mt-0.5 flex-shrink-0" style={{ color: 'var(--accent)' }} />
          <p className="font-sans text-[13px] leading-[1.6]" style={{ color: 'var(--text-primary)' }}>
            {reasoning.summary}
          </p>
        </div>
      </div>
      <div className="space-y-1.5 pl-1">
        {reasoning.factors.map((factor, i) => (
          <div key={i} className="flex items-start gap-2">
            <div
              className="w-1 h-1 rounded-full mt-2 flex-shrink-0"
              style={{ backgroundColor: 'var(--accent)' }}
            />
            <p className="font-sans text-[12px] leading-[1.5]" style={{ color: 'var(--text-secondary)' }}>
              {factor}
            </p>
          </div>
        ))}
      </div>
    </div>
  );
}
