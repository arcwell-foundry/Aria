import { motion, AnimatePresence } from 'framer-motion';
import { useConversationStore } from '@/stores/conversationStore';

interface SuggestionChipsProps {
  onSelect: (suggestion: string) => void;
}

export function SuggestionChips({ onSelect }: SuggestionChipsProps) {
  const suggestions = useConversationStore((s) => s.currentSuggestions);
  const isStreaming = useConversationStore((s) => s.isStreaming);

  if (suggestions.length === 0 || isStreaming) return null;

  return (
    <div className="px-6 pb-3" data-aria-id="suggestion-chips">
      <div className="flex items-center gap-2 mb-2">
        <div className="w-1.5 h-1.5 rounded-full bg-accent aria-pulse-dot" />
        <span className="font-mono text-[9px] tracking-widest uppercase text-[var(--text-secondary)]">
          ARIA is listening&nbsp;&nbsp;&bull;&nbsp;&nbsp;{suggestions.length} suggestion{suggestions.length !== 1 ? 's' : ''} available
        </span>
      </div>

      <div className="flex flex-wrap gap-2">
        <AnimatePresence>
          {suggestions.map((suggestion, i) => (
            <motion.button
              key={suggestion}
              initial={{ opacity: 0, y: 8 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -4 }}
              transition={{ delay: i * 0.05, duration: 0.2 }}
              onClick={() => onSelect(suggestion)}
              className="px-3 py-1.5 rounded-full border border-[var(--border)] text-xs text-[var(--text-secondary)] hover:text-[var(--text-primary)] hover:border-[var(--accent)] hover:bg-[var(--accent-muted)] transition-all"
            >
              {suggestion}
            </motion.button>
          ))}
        </AnimatePresence>
      </div>
    </div>
  );
}
