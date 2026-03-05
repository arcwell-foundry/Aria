import { motion, AnimatePresence } from 'framer-motion';
import { useConversationStore } from '@/stores/conversationStore';
import { useSuggestions } from '@/hooks/useSuggestions';

interface SuggestionChipsProps {
  onSelect: (suggestion: string) => void;
}

// Unified chip type for rendering
interface Chip {
  text: string;
  action: string;
}

export function SuggestionChips({ onSelect }: SuggestionChipsProps) {
  // Context-aware suggestions from API (prioritized)
  const { suggestions: contextSuggestions, isLoading } = useSuggestions();

  // Response-based suggestions from ARIA (fallback)
  const responseSuggestions = useConversationStore((s) => s.currentSuggestions);
  const isStreaming = useConversationStore((s) => s.isStreaming);

  // Normalize to unified Chip format
  const contextChips: Chip[] = contextSuggestions.slice(0, 4);
  const responseChips: Chip[] = responseSuggestions.slice(0, 4).map((s) => ({ text: s, action: s }));

  // Use context-aware suggestions if available, otherwise fall back to response suggestions
  const chips = contextChips.length > 0 ? contextChips : responseChips;

  // Hide while ARIA is streaming a response
  if (isStreaming) return null;

  // Don't show if no suggestions and not loading
  if (chips.length === 0 && !isLoading) return null;

  return (
    <div className="px-6 pb-3" data-aria-id="suggestion-chips">
      {/* Header label */}
      <div className="flex items-center gap-2 mb-2">
        <div
          className="w-1.5 h-1.5 rounded-full bg-[#22C55E]"
          style={{
            animation: 'pulse 2s cubic-bezier(0.4, 0, 0.6, 1) infinite',
            boxShadow: '0 0 6px rgba(34, 197, 94, 0.5)',
          }}
        />
        <span
          className="text-xs text-[#666] tracking-wider uppercase"
          style={{ fontFamily: 'var(--font-mono)' }}
        >
          ARIA IS LISTENING · {chips.length || '...'} SUGGESTIONS
        </span>
      </div>

      {/* Chips container with horizontal scroll */}
      <div className="flex gap-2 overflow-x-auto py-1">
        <AnimatePresence mode="popLayout">
          {isLoading && chips.length === 0 ? (
            // Loading skeleton
            [...Array(3)].map((_, i) => (
              <motion.div
                key={`skeleton-${i}`}
                initial={{ opacity: 0, y: 8 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0, y: -4 }}
                transition={{ delay: i * 0.05, duration: 0.2 }}
                className="px-3 py-1.5 rounded-full bg-[#1E2436] border border-[#2A2F42]"
              >
                <div className="w-20 h-4 bg-[#2A2F42] rounded animate-pulse" />
              </motion.div>
            ))
          ) : (
            // Actual chips
            chips.map((chip, i) => (
              <motion.button
                key={chip.text}
                initial={{ opacity: 0, y: 8 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0, y: -4 }}
                transition={{ delay: i * 0.05, duration: 0.2 }}
                onClick={() => onSelect(chip.action)}
                className="flex-shrink-0 px-3 py-1.5 rounded-full text-sm cursor-pointer bg-[#1E2436] border border-[#2A2F42] text-[#A0AEC0] hover:bg-[#2E66FF] hover:text-white hover:border-transparent transition-all duration-150"
              >
                {chip.text}
              </motion.button>
            ))
          )}
        </AnimatePresence>
      </div>
    </div>
  );
}
