/**
 * useTextToSpeech — Browser speechSynthesis wrapper for ARIA voice output
 *
 * Features:
 * - Speaks text with ARIA-like voice (female English preferred)
 * - Stop/pause/resume controls
 * - Speaking state tracking
 * - Voice mode integration (auto-speak in voice mode)
 */

import { useCallback, useEffect, useState, useRef } from 'react';
import { useModalityStore } from '@/stores/modalityStore';

interface SpeechOptions {
  rate?: number;    // 0.1 - 10, default 1
  pitch?: number;   // 0 - 2, default 1
  volume?: number;  // 0 - 1, default 1
}

interface UseTextToSpeechReturn {
  speak: (text: string, options?: SpeechOptions) => void;
  stop: () => void;
  pause: () => void;
  resume: () => void;
  isSpeaking: boolean;
  isPaused: boolean;
  isSupported: boolean;
  voices: SpeechSynthesisVoice[];
  selectedVoice: SpeechSynthesisVoice | null;
  setSelectedVoice: (voice: SpeechSynthesisVoice) => void;
}

// Clean text for speech - remove markdown formatting, etc.
function cleanTextForSpeech(text: string): string {
  return text
    // Remove markdown headers
    .replace(/^#+\s+/gm, '')
    // Remove bold/italic markers
    .replace(/[*_]{1,3}([^*_]+)[*_]{1,3}/g, '$1')
    // Remove code block markers
    .replace(/```[\s\S]*?```/g, 'code block')
    // Remove inline code
    .replace(/`([^`]+)`/g, '$1')
    // Remove links but keep text
    .replace(/\[([^\]]+)\]\([^)]+\)/g, '$1')
    // Remove images
    .replace(/!\[([^\]]*)\]\([^)]+\)/g, '')
    // Clean up whitespace
    .replace(/\s+/g, ' ')
    .trim();
}

// Find the best ARIA-like voice (prefer female English)
function findBestVoice(voices: SpeechSynthesisVoice[]): SpeechSynthesisVoice | null {
  // Priority: Female English voices
  const femaleEnglishKeywords = ['female', 'woman', 'samantha', 'victoria', 'karen', 'moira', 'fiona', 'veena', 'tessa'];

  // First try to find explicitly female English voices
  for (const keyword of femaleEnglishKeywords) {
    const match = voices.find(
      v => v.lang.startsWith('en') && v.name.toLowerCase().includes(keyword)
    );
    if (match) return match;
  }

  // Then try any English female-sounding names
  const englishFemalePatterns = [
    /samantha/i, /victoria/i, /karen/i, /moira/i, /fiona/i, /veena/i,
    /tessa/i, /serena/i, /amelie/i, /kate/i, /zira/i, /hazel/i, /susan/i
  ];

  for (const pattern of englishFemalePatterns) {
    const match = voices.find(v => v.lang.startsWith('en') && pattern.test(v.name));
    if (match) return match;
  }

  // Fall back to any English voice
  const englishVoice = voices.find(v => v.lang.startsWith('en'));
  if (englishVoice) return englishVoice;

  // Last resort: first available voice
  return voices[0] || null;
}

export function useTextToSpeech(): UseTextToSpeechReturn {
  const [isSpeaking, setIsSpeaking] = useState(false);
  const [isPaused, setIsPaused] = useState(false);
  const [voices, setVoices] = useState<SpeechSynthesisVoice[]>([]);
  const [selectedVoice, setSelectedVoice] = useState<SpeechSynthesisVoice | null>(null);

  const utteranceRef = useRef<SpeechSynthesisUtterance | null>(null);
  const setIsStoreSpeaking = useModalityStore((s) => s.setIsSpeaking);

  const isSupported = typeof window !== 'undefined' && 'speechSynthesis' in window;

  // Load voices on mount and when they change
  useEffect(() => {
    if (!isSupported) return;

    const loadVoices = () => {
      const availableVoices = window.speechSynthesis.getVoices();
      if (availableVoices.length > 0) {
        setVoices(availableVoices);
        if (!selectedVoice) {
          const bestVoice = findBestVoice(availableVoices);
          setSelectedVoice(bestVoice);
        }
      }
    };

    loadVoices();

    // Chrome loads voices asynchronously
    window.speechSynthesis.onvoiceschanged = loadVoices;

    return () => {
      window.speechSynthesis.onvoiceschanged = null;
    };
  }, [isSupported, selectedVoice]);

  // Cleanup on unmount
  useEffect(() => {
    return () => {
      if (isSupported) {
        window.speechSynthesis.cancel();
      }
    };
  }, [isSupported]);

  const speak = useCallback((text: string, options: SpeechOptions = {}) => {
    if (!isSupported) return;

    // Stop any current speech
    window.speechSynthesis.cancel();

    const cleanedText = cleanTextForSpeech(text);
    if (!cleanedText) return;

    const utterance = new SpeechSynthesisUtterance(cleanedText);

    // Apply voice settings
    if (selectedVoice) {
      utterance.voice = selectedVoice;
    }
    utterance.rate = options.rate ?? 1.0;
    utterance.pitch = options.pitch ?? 1.0;
    utterance.volume = options.volume ?? 1.0;

    utterance.onstart = () => {
      setIsSpeaking(true);
      setIsPaused(false);
      setIsStoreSpeaking(true);
    };

    utterance.onend = () => {
      setIsSpeaking(false);
      setIsPaused(false);
      setIsStoreSpeaking(false);
      utteranceRef.current = null;
    };

    utterance.onerror = (event) => {
      // Don't log 'interrupted' or 'canceled' as errors - these are normal
      if (event.error !== 'interrupted' && event.error !== 'canceled') {
        console.warn('Speech synthesis error:', event.error);
      }
      setIsSpeaking(false);
      setIsPaused(false);
      setIsStoreSpeaking(false);
      utteranceRef.current = null;
    };

    utterance.onpause = () => {
      setIsPaused(true);
    };

    utterance.onresume = () => {
      setIsPaused(false);
    };

    utteranceRef.current = utterance;
    window.speechSynthesis.speak(utterance);
  }, [isSupported, selectedVoice, setIsStoreSpeaking]);

  const stop = useCallback(() => {
    if (!isSupported) return;
    window.speechSynthesis.cancel();
    setIsSpeaking(false);
    setIsPaused(false);
    setIsStoreSpeaking(false);
    utteranceRef.current = null;
  }, [isSupported, setIsStoreSpeaking]);

  const pause = useCallback(() => {
    if (!isSupported || !isSpeaking) return;
    window.speechSynthesis.pause();
  }, [isSupported, isSpeaking]);

  const resume = useCallback(() => {
    if (!isSupported || !isPaused) return;
    window.speechSynthesis.resume();
  }, [isSupported, isPaused]);

  return {
    speak,
    stop,
    pause,
    resume,
    isSpeaking,
    isPaused,
    isSupported,
    voices,
    selectedVoice,
    setSelectedVoice,
  };
}
