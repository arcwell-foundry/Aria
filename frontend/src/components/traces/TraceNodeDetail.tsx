import { useState } from 'react';
import { Light as SyntaxHighlighter } from 'react-syntax-highlighter';
import json from 'react-syntax-highlighter/dist/esm/languages/hljs/json';
import atomOneDark from 'react-syntax-highlighter/dist/esm/styles/hljs/atom-one-dark';
import {
  ChevronDown,
  CheckCircle,
  XCircle,
  Shield,
  Brain,
  FileJson,
  FileOutput,
} from 'lucide-react';
import { cn } from '@/utils/cn';
import type { DelegationTrace } from '@/api/traces';

SyntaxHighlighter.registerLanguage('json', json);

// ---------------------------------------------------------------------------
// Collapsible sub-section
// ---------------------------------------------------------------------------

function DetailSection({
  title,
  icon,
  defaultOpen = false,
  children,
}: {
  title: string;
  icon: React.ReactNode;
  defaultOpen?: boolean;
  children: React.ReactNode;
}) {
  const [open, setOpen] = useState(defaultOpen);

  return (
    <div
      className="border rounded-lg overflow-hidden"
      style={{ borderColor: 'var(--border)' }}
    >
      <button
        onClick={() => setOpen(!open)}
        className="w-full flex items-center gap-2 px-3 py-2 text-xs font-medium hover:bg-[var(--bg-subtle)] transition-colors"
        style={{ color: 'var(--text-primary)' }}
      >
        <span style={{ color: 'var(--text-secondary)' }}>{icon}</span>
        {title}
        <ChevronDown
          className={cn(
            'w-3.5 h-3.5 ml-auto transition-transform duration-200',
            open && 'rotate-180'
          )}
          style={{ color: 'var(--text-secondary)' }}
        />
      </button>
      {open && (
        <div className="px-3 pb-3 text-xs" style={{ color: 'var(--text-secondary)' }}>
          {children}
        </div>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// JSON viewer
// ---------------------------------------------------------------------------

function JsonBlock({ data }: { data: Record<string, unknown> }) {
  const jsonStr = JSON.stringify(data, null, 2);
  return (
    <SyntaxHighlighter
      language="json"
      style={atomOneDark}
      customStyle={{
        borderRadius: '6px',
        fontSize: '11px',
        padding: '10px',
        maxHeight: '200px',
        overflow: 'auto',
      }}
    >
      {jsonStr}
    </SyntaxHighlighter>
  );
}

// ---------------------------------------------------------------------------
// Risk bar
// ---------------------------------------------------------------------------

function RiskBar({ label, value }: { label: string; value: number }) {
  const pct = Math.round(value * 100);
  const barColor =
    value > 0.7 ? 'var(--critical)' : value > 0.4 ? 'var(--warning)' : 'var(--success)';

  return (
    <div className="flex items-center gap-2">
      <span className="w-24 font-mono text-[11px] capitalize">{label}</span>
      <div
        className="flex-1 h-1.5 rounded-full overflow-hidden"
        style={{ backgroundColor: 'var(--bg-subtle)' }}
      >
        <div
          className="h-full rounded-full transition-all"
          style={{ width: `${pct}%`, backgroundColor: barColor }}
        />
      </div>
      <span className="w-8 text-right font-mono text-[11px]">{pct}%</span>
    </div>
  );
}

// ---------------------------------------------------------------------------
// TraceNodeDetail
// ---------------------------------------------------------------------------

interface TraceNodeDetailProps {
  trace: DelegationTrace;
}

export function TraceNodeDetail({ trace }: TraceNodeDetailProps) {
  const hasInputs = trace.inputs && Object.keys(trace.inputs).length > 0;
  const hasOutputs = trace.outputs && Object.keys(trace.outputs).length > 0;
  const hasDCT = trace.capability_token;
  const hasVerification = trace.verification_result;
  const hasThinking = !!trace.thinking_trace;
  const hasCharacteristics = trace.task_characteristics;

  return (
    <div className="space-y-2">
      {/* Inputs */}
      {hasInputs && (
        <DetailSection title="Inputs" icon={<FileJson className="w-3.5 h-3.5" />}>
          <JsonBlock data={trace.inputs} />
        </DetailSection>
      )}

      {/* Outputs */}
      {hasOutputs && (
        <DetailSection title="Outputs" icon={<FileOutput className="w-3.5 h-3.5" />}>
          <JsonBlock data={trace.outputs!} />
        </DetailSection>
      )}

      {/* Thinking trace */}
      {hasThinking && (
        <DetailSection title="Thinking Trace" icon={<Brain className="w-3.5 h-3.5" />}>
          <pre
            className="whitespace-pre-wrap font-mono text-[11px] p-2.5 rounded-md max-h-48 overflow-auto"
            style={{
              backgroundColor: 'var(--bg-subtle)',
              color: 'var(--text-secondary)',
            }}
          >
            {trace.thinking_trace}
          </pre>
        </DetailSection>
      )}

      {/* DCT scope */}
      {hasDCT && (
        <DetailSection title="Capability Token" icon={<Shield className="w-3.5 h-3.5" />}>
          <div className="grid grid-cols-2 gap-3 mt-1">
            <div>
              <p className="font-medium mb-1" style={{ color: 'var(--text-primary)' }}>
                Allowed
              </p>
              <div className="flex flex-wrap gap-1">
                {trace.capability_token!.allowed_actions.map((action) => (
                  <span
                    key={action}
                    className="px-1.5 py-0.5 rounded text-[10px] font-mono"
                    style={{
                      backgroundColor: 'rgba(16, 185, 129, 0.15)',
                      color: 'var(--success)',
                    }}
                  >
                    {action}
                  </span>
                ))}
                {trace.capability_token!.allowed_actions.length === 0 && (
                  <span className="italic">None</span>
                )}
              </div>
            </div>
            <div>
              <p className="font-medium mb-1" style={{ color: 'var(--text-primary)' }}>
                Denied
              </p>
              <div className="flex flex-wrap gap-1">
                {trace.capability_token!.denied_actions.map((action) => (
                  <span
                    key={action}
                    className="px-1.5 py-0.5 rounded text-[10px] font-mono"
                    style={{
                      backgroundColor: 'rgba(239, 68, 68, 0.15)',
                      color: 'var(--critical)',
                    }}
                  >
                    {action}
                  </span>
                ))}
                {trace.capability_token!.denied_actions.length === 0 && (
                  <span className="italic">None</span>
                )}
              </div>
            </div>
          </div>
        </DetailSection>
      )}

      {/* Verification */}
      {hasVerification && (
        <DetailSection
          title="Verification"
          icon={
            trace.verification_result!.passed ? (
              <CheckCircle className="w-3.5 h-3.5" style={{ color: 'var(--success)' }} />
            ) : (
              <XCircle className="w-3.5 h-3.5" style={{ color: 'var(--critical)' }} />
            )
          }
          defaultOpen={!trace.verification_result!.passed}
        >
          <div className="space-y-2 mt-1">
            <div className="flex items-center gap-2">
              <span
                className="px-2 py-0.5 rounded-full text-[10px] font-medium"
                style={{
                  backgroundColor: trace.verification_result!.passed
                    ? 'rgba(16, 185, 129, 0.15)'
                    : 'rgba(239, 68, 68, 0.15)',
                  color: trace.verification_result!.passed
                    ? 'var(--success)'
                    : 'var(--critical)',
                }}
              >
                {trace.verification_result!.passed ? 'PASSED' : 'FAILED'}
              </span>
              <span className="font-mono">
                {Math.round(trace.verification_result!.confidence * 100)}% confidence
              </span>
            </div>

            {trace.verification_result!.issues.length > 0 && (
              <div>
                <p className="font-medium mb-0.5" style={{ color: 'var(--text-primary)' }}>
                  Issues
                </p>
                <ul className="list-disc list-inside space-y-0.5">
                  {trace.verification_result!.issues.map((issue, i) => (
                    <li key={i}>{issue}</li>
                  ))}
                </ul>
              </div>
            )}

            {trace.verification_result!.suggestions.length > 0 && (
              <div>
                <p className="font-medium mb-0.5" style={{ color: 'var(--text-primary)' }}>
                  Suggestions
                </p>
                <ul className="list-disc list-inside space-y-0.5">
                  {trace.verification_result!.suggestions.map((s, i) => (
                    <li key={i}>{s}</li>
                  ))}
                </ul>
              </div>
            )}
          </div>
        </DetailSection>
      )}

      {/* Task characteristics */}
      {hasCharacteristics && (
        <DetailSection title="Task Characteristics" icon={<Brain className="w-3.5 h-3.5" />}>
          <div className="space-y-1.5 mt-1">
            {(
              Object.entries(trace.task_characteristics!) as [string, number][]
            ).map(([key, value]) => (
              <RiskBar key={key} label={key} value={value} />
            ))}
          </div>
        </DetailSection>
      )}
    </div>
  );
}
