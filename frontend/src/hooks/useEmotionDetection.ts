/**
 * useEmotionDetection — Listens for Raven-0 emotion events
 *
 * Receives emotion.detected events from WebSocket (sent by Tavus
 * Raven-0 via the backend) and posts them to the perception API.
 * Updates the perceptionStore for UI consumption.
 */

import { useEffect, useRef } from 'react';
import { wsManager } from '@/core/WebSocketManager';
import { WS_EVENTS } from '@/types/chat';
import { usePerceptionStore, type DetectedEmotion, type EmotionReading } from '@/stores/perceptionStore';

interface EmotionEventPayload {
  emotion: string;
  confidence: number;
  timestamp?: string;
}

const DEBOUNCE_MS = 2000;

export function useEmotionDetection() {
  const setCurrentEmotion = usePerceptionStore((s) => s.setCurrentEmotion);
  const lastSentRef = useRef(0);

  useEffect(() => {
    const handleEmotion = (payload: unknown) => {
      const data = payload as EmotionEventPayload;
      const now = Date.now();

      const reading: EmotionReading = {
        emotion: data.emotion as DetectedEmotion,
        confidence: data.confidence,
        timestamp: data.timestamp ?? new Date().toISOString(),
      };

      setCurrentEmotion(reading);

      if (now - lastSentRef.current < DEBOUNCE_MS) return;
      lastSentRef.current = now;

      const token = localStorage.getItem('access_token');
      fetch('/api/v1/perception/emotion', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          ...(token ? { Authorization: `Bearer ${token}` } : {}),
        },
        body: JSON.stringify({
          emotion: reading.emotion,
          confidence: reading.confidence,
          timestamp: reading.timestamp,
        }),
      }).catch(() => {
        // Swallow — perception is non-critical
      });
    };

    wsManager.on(WS_EVENTS.EMOTION_DETECTED, handleEmotion);

    return () => {
      wsManager.off(WS_EVENTS.EMOTION_DETECTED, handleEmotion);
    };
  }, [setCurrentEmotion]);
}
