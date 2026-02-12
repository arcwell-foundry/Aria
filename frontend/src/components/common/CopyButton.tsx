/**
 * CopyButton - Clipboard copy action button
 *
 * Follows ARIA Design System v1.0:
 * - Uses CSS variables for theming
 * - Shows Copy icon, changes to CheckCheck + "Copied" on success
 * - 2-second feedback duration
 *
 * @example
 * <CopyButton text="Text to copy" />
 * <CopyButton text={lead.email} className="ml-2" />
 */

import { useState, useCallback } from 'react';
import { Copy, CheckCheck } from 'lucide-react';

export interface CopyButtonProps {
  /** Text to copy to clipboard */
  text: string;
  /** Additional CSS classes */
  className?: string;
}

export function CopyButton({ text, className = '' }: CopyButtonProps) {
  const [copied, setCopied] = useState(false);

  const handleCopy = useCallback(async () => {
    try {
      await navigator.clipboard.writeText(text);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch (err) {
      console.error('Failed to copy text:', err);
    }
  }, [text]);

  return (
    <button
      onClick={handleCopy}
      className={`
        inline-flex items-center gap-1.5
        px-2 py-1 rounded-md
        text-xs font-medium
        transition-all duration-200
        hover:bg-[var(--bg-subtle)]
        ${className}
      `.trim()}
      style={{
        color: copied ? 'var(--success)' : 'var(--text-secondary)',
      }}
      title={copied ? 'Copied!' : 'Copy to clipboard'}
    >
      {copied ? (
        <>
          <CheckCheck className="w-3.5 h-3.5" />
          <span>Copied</span>
        </>
      ) : (
        <>
          <Copy className="w-3.5 h-3.5" />
        </>
      )}
    </button>
  );
}
