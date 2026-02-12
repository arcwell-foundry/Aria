/**
 * useVoiceInput — Space-to-talk and mic-click voice input
 *
 * Uses the Web SpeechRecognition API. Space key activates when textarea
 * is NOT focused (so typing works). Mic click toggles listen on/off.
 */

import { useEffect, useRef, useCallback } from 'react';
import { useModalityStore } from '@/stores/modalityStore';
import { useConversationStore } from '@/stores/conversationStore';

// SpeechRecognition type shim for browsers
interface SpeechRecognitionInstance {
  continuous: boolean;
  interimResults: boolean;
  lang: string;
  start(): void;
  stop(): void;
  onresult: ((event: { results: { length: number; [index: number]: { [index: number]: { transcript: string; confidence: number }; isFinal: boolean } } }) => void) | null;
  onerror: ((event: { error: string }) => void) | null;
  onend: (() => void) | null;
}

function getSpeechRecognitionCtor(): (new () => SpeechRecognitionInstance) | null {
  const w = window as unknown as Record<string, unknown>;
  return (w.SpeechRecognition ?? w.webkitSpeechRecognition ?? null) as (new () => SpeechRecognitionInstance) | null;
}

interface UseVoiceInputOptions {
  onTranscript: (text: string) => void;
}

export function useVoiceInput({ onTranscript }: UseVoiceInputOptions) {
  const isListening = useModalityStore((s) => s.isListening);
  const setIsListening = useModalityStore((s) => s.setIsListening);

  const recognitionRef = useRef<SpeechRecognitionInstance | null>(null);
  const isSpaceHeldRef = useRef(false);
  const transcriptRef = useRef('');

  const isSupported = typeof window !== 'undefined' && getSpeechRecognitionCtor() !== null;

  const startListening = useCallback(() => {
    if (!isSupported || useConversationStore.getState().isStreaming || useModalityStore.getState().isListening) return;

    const Ctor = getSpeechRecognitionCtor()!;
    const recognition = new Ctor();
    recognition.continuous = true;
    recognition.interimResults = true;
    recognition.lang = 'en-US';

    transcriptRef.current = '';

    recognition.onresult = (event) => {
      let transcript = '';
      for (let i = 0; i < event.results.length; i++) {
        transcript += event.results[i][0].transcript;
      }
      transcriptRef.current = transcript;
    };

    recognition.onerror = (event) => {
      if (event.error !== 'aborted') {
        console.warn('SpeechRecognition error:', event.error);
      }
      setIsListening(false);
    };

    recognition.onend = () => {
      if (useModalityStore.getState().isListening) {
        setIsListening(false);
      }
    };

    recognitionRef.current = recognition;

    try {
      recognition.start();
      setIsListening(true);
    } catch {
      setIsListening(false);
    }
  }, [isSupported, setIsListening]);

  const stopListening = useCallback(() => {
    if (recognitionRef.current) {
      try {
        recognitionRef.current.stop();
      } catch {
        // Already stopped
      }
      recognitionRef.current = null;
    }

    setIsListening(false);

    const transcript = transcriptRef.current.trim();
    if (transcript) {
      onTranscript(transcript);
    }
    transcriptRef.current = '';
  }, [onTranscript, setIsListening]);

  const toggleListening = useCallback(() => {
    if (isListening) {
      stopListening();
    } else {
      startListening();
    }
  }, [isListening, startListening, stopListening]);

  // Global Space key listener (push-to-talk)
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.code !== 'Space') return;
      if (isSpaceHeldRef.current) return;

      const tag = (e.target as HTMLElement)?.tagName;
      if (tag === 'INPUT' || tag === 'TEXTAREA' || tag === 'SELECT') return;
      if ((e.target as HTMLElement)?.contentEditable === 'true') return;

      e.preventDefault();
      isSpaceHeldRef.current = true;
      startListening();
    };

    const handleKeyUp = (e: KeyboardEvent) => {
      if (e.code !== 'Space') return;
      if (!isSpaceHeldRef.current) return;

      isSpaceHeldRef.current = false;
      stopListening();
    };

    window.addEventListener('keydown', handleKeyDown);
    window.addEventListener('keyup', handleKeyUp);

    return () => {
      window.removeEventListener('keydown', handleKeyDown);
      window.removeEventListener('keyup', handleKeyUp);
    };
  }, [startListening, stopListening]);

  // Cleanup on unmount
  useEffect(() => {
    return () => {
      if (recognitionRef.current) {
        try { recognitionRef.current.stop(); } catch { /* noop */ }
      }
    };
  }, []);

  return {
    isListening,
    isSupported,
    toggleListening,
    startListening,
    stopListening,
  };
}
