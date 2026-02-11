/**
 * ModalityController - Orchestrates modality switches between text, voice, and avatar
 *
 * Manages Tavus session lifecycle (create/end) and coordinates navigation
 * with the modality store. When avatar creation fails, still navigates to
 * dialogue mode so AvatarContainer can render the static fallback.
 *
 * Initialized by AppShell with the React Router navigate function.
 */

import { apiClient } from '@/api/client';
import { useModalityStore } from '@/stores/modalityStore';
import type { Modality, TavusSessionType } from '@/stores/modalityStore';

type NavigateFunction = (to: string) => void;

interface TavusCreateResponse {
  session_id: string;
  room_url: string;
}

class ModalityControllerImpl {
  private navigateFn: NavigateFunction | null = null;

  /**
   * Must be called once by AppShell with the React Router navigate function.
   */
  setNavigate(fn: NavigateFunction): void {
    this.navigateFn = fn;
  }

  /**
   * Switch to a given modality.
   *
   * - 'avatar': Creates a Tavus session via API, navigates to /dialogue or /briefing.
   *   If API fails, still navigates so the static fallback renders.
   * - 'voice': Sets modality to voice (no navigation change).
   * - 'text': Sets modality to text, shows PiP if Tavus session is active, navigates to /.
   */
  async switchTo(modality: Modality, sessionType?: TavusSessionType): Promise<void> {
    const store = useModalityStore.getState();

    switch (modality) {
      case 'avatar':
        await this.switchToAvatar(sessionType || 'chat');
        break;

      case 'text':
        store.setActiveModality('text');
        // Show PiP if there's an active Tavus session
        if (store.tavusSession.status === 'active') {
          store.setIsPipVisible(true);
        }
        this.navigateFn?.('/');
        break;

      case 'voice':
        store.setActiveModality('voice');
        break;
    }
  }

  /**
   * End the current Tavus session, clear store state, and navigate to /.
   */
  async endSession(): Promise<void> {
    const store = useModalityStore.getState();
    const sessionId = store.tavusSession.id;

    if (sessionId) {
      store.setTavusSession({ status: 'ending' });

      try {
        await apiClient.post(`/video/sessions/${sessionId}/end`);
      } catch (err) {
        console.warn('[ModalityController] Failed to end Tavus session:', err);
      }
    }

    store.clearTavusSession();
    store.setActiveModality('text');
    store.setIsSpeaking(false);
    this.navigateFn?.('/');
  }

  /**
   * Hide the PiP overlay. The Tavus session stays alive in the background.
   */
  dismissPip(): void {
    useModalityStore.getState().setIsPipVisible(false);
  }

  /**
   * Show the PiP overlay if there's an active Tavus session and the user
   * is not currently on the dialogue route.
   */
  restorePip(): void {
    const store = useModalityStore.getState();
    if (store.tavusSession.status === 'active') {
      store.setIsPipVisible(true);
    }
  }

  private async switchToAvatar(sessionType: TavusSessionType): Promise<void> {
    const store = useModalityStore.getState();
    const route = sessionType === 'briefing' ? '/briefing' : '/dialogue';

    // If there's already an active session, just navigate
    if (store.tavusSession.status === 'active' && store.tavusSession.id) {
      store.setActiveModality('avatar');
      store.setTavusSession({ sessionType });
      store.setIsPipVisible(false);
      this.navigateFn?.(route);
      return;
    }

    // Start connecting
    store.setActiveModality('avatar');
    store.setTavusSession({ status: 'connecting', sessionType });
    store.setIsPipVisible(false);

    try {
      const response = await apiClient.post<TavusCreateResponse>('/video/sessions', {
        session_type: sessionType,
      });

      const { session_id, room_url } = response.data;

      store.setTavusSession({
        id: session_id,
        roomUrl: room_url,
        status: 'active',
      });
    } catch (err) {
      console.warn('[ModalityController] Failed to create Tavus session:', err);
      // Reset session state but keep modality as avatar for static fallback
      store.setTavusSession({ status: 'idle' });
    }

    // Navigate regardless of API success — AvatarContainer shows static fallback
    this.navigateFn?.(route);
  }
}

/** Singleton instance */
export const modalityController = new ModalityControllerImpl();
