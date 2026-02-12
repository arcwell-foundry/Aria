import { useState, useCallback, useRef, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { Loader2 } from 'lucide-react';
import { MessageBubble } from '@/components/conversation/MessageBubble';
import type { Message } from '@/types/chat';
import {
  completeStep,
  getOnboardingState,
  type OnboardingStep,
} from '@/api/onboarding';

type OnboardingPhase =
  | 'GREETING'
  | 'COMPANY'
  | 'ROLE'
  | 'COMPETITORS'
  | 'INTEGRATIONS'
  | 'ENRICHING'
  | 'COMPLETE';

const PHASE_PROMPTS: Record<OnboardingPhase, string> = {
  GREETING:
    "Welcome! I'm ARIA, your AI Department Director. I'll be working alongside you to transform how your team operates. Let's get to know each other — what company are you with?",
  COMPANY:
    "Great. Now tell me about your role — what's your title and what does a typical day look like for you?",
  ROLE:
    "That helps me calibrate how I support you. Who are the main competitors you go up against? List a few names and I'll start building your competitive intelligence.",
  COMPETITORS:
    "I'll start tracking those. Last step — would you like to connect any integrations now? You can type 'skip' to do this later, or tell me which tools you use (Salesforce, HubSpot, Google Calendar, Slack, etc.).",
  INTEGRATIONS:
    "Excellent. Give me a moment while I enrich your company data and set up your workspace...",
  ENRICHING: '',
  COMPLETE: "Everything's set up. Let's get to work.",
};

function createMessage(
  role: 'aria' | 'user',
  content: string,
  id?: string,
): Message {
  return {
    id: id ?? crypto.randomUUID(),
    role,
    content,
    rich_content: [],
    ui_commands: [],
    suggestions: [],
    timestamp: new Date().toISOString(),
  };
}

export function OnboardingPage() {
  const navigate = useNavigate();
  const [messages, setMessages] = useState<Message[]>([
    createMessage('aria', PHASE_PROMPTS.GREETING, 'greeting'),
  ]);
  const [phase, setPhase] = useState<OnboardingPhase>('GREETING');
  const [inputValue, setInputValue] = useState('');
  const [isProcessing, setIsProcessing] = useState(false);
  const bottomRef = useRef<HTMLDivElement>(null);

  // Auto-scroll on new messages
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  // Check if already onboarded
  useEffect(() => {
    getOnboardingState()
      .then((state) => {
        if (state.is_complete) {
          navigate('/', { replace: true });
        }
      })
      .catch(() => {
        // If state fetch fails, let them continue onboarding
      });
  }, [navigate]);

  const advancePhase = useCallback(
    (nextPhase: OnboardingPhase) => {
      setPhase(nextPhase);
      const prompt = PHASE_PROMPTS[nextPhase];
      if (prompt) {
        setMessages((prev) => [...prev, createMessage('aria', prompt)]);
      }

      if (nextPhase === 'ENRICHING') {
        // Auto-advance to complete after a delay
        setTimeout(() => {
          setMessages((prev) => [
            ...prev,
            createMessage('aria', PHASE_PROMPTS.COMPLETE),
          ]);
          setPhase('COMPLETE');

          // Redirect after showing completion message
          setTimeout(() => {
            navigate('/', { replace: true });
          }, 2000);
        }, 3000);
      }
    },
    [navigate],
  );

  const handleSend = useCallback(async () => {
    const text = inputValue.trim();
    if (!text || isProcessing) return;

    setInputValue('');
    setMessages((prev) => [...prev, createMessage('user', text)]);
    setIsProcessing(true);

    try {
      // Map current phase to the backend step to complete
      const stepForPhase: Record<string, OnboardingStep | null> = {
        GREETING: 'company_discovery',
        COMPANY: 'user_profile',
        ROLE: 'writing_samples',
        COMPETITORS: 'integration_wizard',
        INTEGRATIONS: 'activation',
      };

      const step = stepForPhase[phase];
      if (step) {
        await completeStep(step, { user_input: text });
      }

      // Determine next phase
      const phaseOrder: OnboardingPhase[] = [
        'GREETING',
        'COMPANY',
        'ROLE',
        'COMPETITORS',
        'INTEGRATIONS',
        'ENRICHING',
      ];
      const currentIndex = phaseOrder.indexOf(phase);
      const nextPhase = phaseOrder[currentIndex + 1] ?? 'ENRICHING';
      advancePhase(nextPhase);
    } catch {
      setMessages((prev) => [
        ...prev,
        createMessage(
          'aria',
          "I had trouble saving that. Let's try again — could you repeat what you said?",
        ),
      ]);
    } finally {
      setIsProcessing(false);
    }
  }, [inputValue, isProcessing, phase, advancePhase]);

  const handleKeyDown = useCallback(
    (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
      if (e.key === 'Enter' && !e.shiftKey) {
        e.preventDefault();
        void handleSend();
      }
    },
    [handleSend],
  );

  const isInputDisabled =
    isProcessing || phase === 'ENRICHING' || phase === 'COMPLETE';

  return (
    <div className="flex h-screen flex-col bg-[var(--bg-primary,#0A0A0B)] text-[var(--text-primary,#F1F1F1)]">
      {/* Header */}
      <header className="flex items-center justify-center border-b border-white/5 px-6 py-4">
        <h1 className="font-display text-xl italic text-[var(--text-primary,#F1F1F1)]">
          Welcome to ARIA
        </h1>
      </header>

      {/* Conversation area */}
      <div className="flex-1 overflow-y-auto px-4 py-6">
        <div className="mx-auto flex max-w-2xl flex-col gap-4">
          {messages.map((msg, idx) => (
            <MessageBubble
              key={msg.id}
              message={msg}
              isFirstInGroup={
                idx === 0 || messages[idx - 1].role !== msg.role
              }
            />
          ))}

          {isProcessing && (
            <div className="flex items-center gap-2 px-4 py-2 text-sm text-[var(--text-tertiary,#6B7280)]">
              <Loader2 className="h-4 w-4 animate-spin" />
              <span>ARIA is thinking...</span>
            </div>
          )}

          {phase === 'ENRICHING' && (
            <div className="flex items-center gap-3 rounded-lg border border-white/5 bg-white/[0.02] px-4 py-3">
              <Loader2 className="h-5 w-5 animate-spin text-[var(--color-accent,#2E66FF)]" />
              <span className="text-sm text-[var(--text-secondary,#A1A1AA)]">
                Enriching company data and setting up your workspace...
              </span>
            </div>
          )}

          <div ref={bottomRef} />
        </div>
      </div>

      {/* Input bar */}
      <div className="border-t border-white/5 px-4 py-4">
        <div className="mx-auto max-w-2xl">
          <form
            onSubmit={(e) => {
              e.preventDefault();
              void handleSend();
            }}
            className="flex items-end gap-3"
          >
            <textarea
              value={inputValue}
              onChange={(e) => setInputValue(e.target.value)}
              onKeyDown={handleKeyDown}
              disabled={isInputDisabled}
              placeholder={
                isInputDisabled
                  ? 'Setting things up...'
                  : 'Type your response...'
              }
              rows={1}
              className="flex-1 resize-none rounded-lg border border-white/10 bg-white/[0.03] px-4 py-3 text-sm text-[var(--text-primary,#F1F1F1)] placeholder-[var(--text-tertiary,#6B7280)] outline-none transition focus:border-[var(--color-accent,#2E66FF)] disabled:opacity-50"
            />
            <button
              type="submit"
              disabled={!inputValue.trim() || isInputDisabled}
              className="rounded-lg bg-[var(--color-accent,#2E66FF)] px-4 py-3 text-sm font-medium text-white transition hover:bg-[var(--color-accent,#2E66FF)]/90 disabled:opacity-40"
            >
              Send
            </button>
          </form>
        </div>
      </div>
    </div>
  );
}
