/**
 * useUICommands - React hook wrapping UICommandExecutor
 *
 * Auto-initializes with React Router's navigate function.
 * Listens for aria.message and aria.metadata events to auto-execute ui_commands.
 * Also exposes executeUICommands() for manual execution.
 */

import { useEffect, useCallback, useRef } from 'react';
import { useNavigate } from 'react-router-dom';
import { uiCommandExecutor } from '@/core/UICommandExecutor';
import { wsManager } from '@/core/WebSocketManager';
import type { UICommand } from '@/api/chat';
import type { AriaMessagePayload } from '@/types/chat';

export function useUICommands() {
  const navigate = useNavigate();
  const initializedRef = useRef(false);

  // Initialize executor with navigate function
  useEffect(() => {
    if (!initializedRef.current) {
      uiCommandExecutor.setNavigate(navigate);
      initializedRef.current = true;
    }
  }, [navigate]);

  // Listen for aria.message events and auto-execute ui_commands
  useEffect(() => {
    const handleAriaMessage = (payload: unknown) => {
      const data = payload as AriaMessagePayload;
      if (data.ui_commands?.length) {
        void uiCommandExecutor.executeCommands(data.ui_commands as UICommand[]);
      }
    };

    const handleMetadata = (payload: unknown) => {
      const data = payload as { ui_commands?: UICommand[] };
      if (data.ui_commands?.length) {
        void uiCommandExecutor.executeCommands(data.ui_commands);
      }
    };

    wsManager.on('aria.message', handleAriaMessage);
    wsManager.on('aria.metadata', handleMetadata);

    return () => {
      wsManager.off('aria.message', handleAriaMessage);
      wsManager.off('aria.metadata', handleMetadata);
    };
  }, []);

  const executeUICommands = useCallback((commands: UICommand[]) => {
    return uiCommandExecutor.executeCommands(commands);
  }, []);

  return { executeUICommands };
}
