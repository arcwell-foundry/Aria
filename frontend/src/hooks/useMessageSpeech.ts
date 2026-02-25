/**
 * useMessageSpeech — Hook for speaking specific messages with global state
 *
 * Integrates useTextToSpeech with ttsStore for message-aware speech.
 * Tracks which message is currently being spoken across all components.
 */

import { useCallback, useEffect } from 'react';
import { useTextToSpeech } from './useTextToSpeech';
import { useTTSStore } from '@/stores/ttsStore';

interface UseMessageSpeechReturn {
  speakMessage: (messageId: string, text: string) => void;
  stopSpeaking: () => void;
  togglePause: () => void;
  isThisMessageSpeaking: (messageId: string) => boolean;
  isThisMessagePaused: (messageId: string) => boolean;
  isSupported: boolean;
}

export function useMessageSpeech(): UseMessageSpeechReturn {
  const { speak, stop, pause, resume, isSpeaking, isPaused, isSupported } = useTextToSpeech();

  const speakingMessageId = useTTSStore((s) => s.speakingMessageId);
  const storedIsPaused = useTTSStore((s) => s.isPaused);
  const setSpeakingMessageId = useTTSStore((s) => s.setSpeakingMessageId);
  const setIsPaused = useTTSStore((s) => s.setIsPaused);
  const stopStoreSpeaking = useTTSStore((s) => s.stopSpeaking);

  // Sync TTS state with store when speech ends naturally
  useEffect(() => {
    if (!isSpeaking && speakingMessageId) {
      setSpeakingMessageId(null);
    }
  }, [isSpeaking, speakingMessageId, setSpeakingMessageId]);

  const speakMessage = useCallback((messageId: string, text: string) => {
    // If clicking the same message that's speaking, stop it
    if (speakingMessageId === messageId && isSpeaking) {
      stop();
      stopStoreSpeaking();
      return;
    }

    // Otherwise, start speaking this message
    setSpeakingMessageId(messageId);
    speak(text, { rate: 1.0, pitch: 1.0 });
  }, [speakingMessageId, isSpeaking, setSpeakingMessageId, speak, stop, stopStoreSpeaking]);

  const stopSpeaking = useCallback(() => {
    stop();
    stopStoreSpeaking();
  }, [stop, stopStoreSpeaking]);

  const togglePause = useCallback(() => {
    if (isPaused) {
      resume();
      setIsPaused(false);
    } else {
      pause();
      setIsPaused(true);
    }
  }, [isPaused, pause, resume, setIsPaused]);

  const isThisMessageSpeaking = useCallback((messageId: string) => {
    return speakingMessageId === messageId && isSpeaking;
  }, [speakingMessageId, isSpeaking]);

  const isThisMessagePaused = useCallback((messageId: string) => {
    return speakingMessageId === messageId && storedIsPaused;
  }, [speakingMessageId, storedIsPaused]);

  return {
    speakMessage,
    stopSpeaking,
    togglePause,
    isThisMessageSpeaking,
    isThisMessagePaused,
    isSupported,
  };
}
