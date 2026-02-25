/**
 * useVoiceMode — Orchestrates continuous voice conversation mode
 *
 * When voice mode is enabled:
 * - ARIA's responses auto-speak
 * - After ARIA finishes speaking, auto-start listening
 * - User can interrupt by speaking during playback
 */

import { useEffect, useRef, useCallback } from 'react';
import { useModalityStore } from '@/stores/modalityStore';
import { useTTSStore } from '@/stores/ttsStore';
import { useConversationStore } from '@/stores/conversationStore';
import { useTextToSpeech } from './useTextToSpeech';

interface UseVoiceModeReturn {
  voiceModeEnabled: boolean;
  toggleVoiceMode: () => void;
  setVoiceModeEnabled: (enabled: boolean) => void;
  startListeningAfterSpeech: () => void;
}

// Global callback to trigger listening - set by useVoiceInput
let listeningTriggerCallback: (() => void) | null = null;

export function setListeningTrigger(callback: (() => void) | null) {
  listeningTriggerCallback = callback;
}

export function useVoiceMode(): UseVoiceModeReturn {
  const voiceModeEnabled = useModalityStore((s) => s.voiceModeEnabled);
  const toggleVoiceMode = useModalityStore((s) => s.toggleVoiceMode);
  const setVoiceModeEnabled = useModalityStore((s) => s.setVoiceModeEnabled);
  const isListening = useModalityStore((s) => s.isListening);

  const { isSpeaking, stop } = useTextToSpeech();

  const lastSpokenIdRef = useRef<string | null>(null);

  // Auto-speak new ARIA messages when voice mode is enabled
  useEffect(() => {
    if (!voiceModeEnabled) return;

    const messages = useConversationStore.getState().messages;
    const lastMessage = messages[messages.length - 1];

    // Only speak new ARIA messages that haven't been spoken yet
    if (
      lastMessage &&
      lastMessage.role === 'aria' &&
      lastMessage.id !== lastSpokenIdRef.current &&
      !lastMessage.isStreaming
    ) {
      lastSpokenIdRef.current = lastMessage.id;

      // Small delay to ensure message is rendered
      setTimeout(() => {
        const ttsStore = useTTSStore.getState();
        ttsStore.setSpeakingMessageId(lastMessage.id);

        // Use speech synthesis directly
        const text = lastMessage.content
          .replace(/^#+\s+/gm, '')
          .replace(/[*_]{1,3}([^*_]+)[*_]{1,3}/g, '$1')
          .replace(/```[\s\S]*?```/g, 'code block')
          .replace(/`([^`]+)`/g, '$1')
          .replace(/\[([^\]]+)\]\([^)]+\)/g, '$1')
          .replace(/\s+/g, ' ')
          .trim();

        if (text && 'speechSynthesis' in window) {
          const utterance = new SpeechSynthesisUtterance(text);
          utterance.rate = 1.0;
          utterance.pitch = 1.0;

          utterance.onend = () => {
            ttsStore.setSpeakingMessageId(null);
            // Auto-start listening after ARIA finishes speaking
            if (useModalityStore.getState().voiceModeEnabled && listeningTriggerCallback) {
              setTimeout(() => {
                if (listeningTriggerCallback) {
                  listeningTriggerCallback();
                }
              }, 300);
            }
          };

          utterance.onerror = () => {
            ttsStore.setSpeakingMessageId(null);
          };

          window.speechSynthesis.speak(utterance);
        }
      }, 100);
    }
  }, [voiceModeEnabled]);

  // Interrupt speech if user starts speaking
  useEffect(() => {
    if (voiceModeEnabled && isListening && isSpeaking) {
      stop();
      useTTSStore.getState().setSpeakingMessageId(null);
    }
  }, [voiceModeEnabled, isListening, isSpeaking, stop]);

  // Stop all speech when voice mode is disabled
  useEffect(() => {
    if (!voiceModeEnabled && isSpeaking) {
      stop();
      useTTSStore.getState().setSpeakingMessageId(null);
    }
  }, [voiceModeEnabled, isSpeaking, stop]);

  const startListeningAfterSpeech = useCallback(() => {
    if (listeningTriggerCallback) {
      listeningTriggerCallback();
    }
  }, []);

  return {
    voiceModeEnabled,
    toggleVoiceMode,
    setVoiceModeEnabled,
    startListeningAfterSpeech,
  };
}
