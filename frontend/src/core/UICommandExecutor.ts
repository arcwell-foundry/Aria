/**
 * UICommandExecutor - Processes UICommand[] from ARIA's messages
 *
 * Executes commands sequentially with 150ms delay between each for visual
 * feedback. Uses React Router navigate, DOM APIs for highlights/scrolling,
 * and store updates for panel/sidebar/notification changes.
 *
 * Initialized by useUICommands hook with the router navigate function.
 */

import type { UICommand, HighlightEffect } from '@/api/chat';
import { useNavigationStore } from '@/stores/navigationStore';
import { useNotificationsStore } from '@/stores/notificationsStore';
import { modalityController } from './ModalityController';

type NavigateFunction = (to: string) => void;

const COMMAND_DELAY_MS = 150;
const DEFAULT_HIGHLIGHT_DURATION_MS = 3000;

class UICommandExecutorImpl {
  private navigateFn: NavigateFunction | null = null;
  private intelPanelUpdateHandler: ((content: Record<string, unknown>) => void) | null = null;

  /**
   * Must be called once by useUICommands with the React Router navigate function.
   */
  setNavigate(fn: NavigateFunction): void {
    this.navigateFn = fn;
  }

  /**
   * Register callback for intel panel updates.
   */
  setIntelPanelHandler(handler: (content: Record<string, unknown>) => void): void {
    this.intelPanelUpdateHandler = handler;
  }

  /**
   * Execute an array of UICommands sequentially with delays.
   */
  async executeCommands(commands: UICommand[]): Promise<void> {
    if (!commands.length) return;

    for (let i = 0; i < commands.length; i++) {
      await this.executeCommand(commands[i]);
      if (i < commands.length - 1) {
        await this.delay(COMMAND_DELAY_MS);
      }
    }
  }

  private async executeCommand(cmd: UICommand): Promise<void> {
    try {
      switch (cmd.action) {
        case 'navigate':
          this.handleNavigate(cmd);
          break;
        case 'highlight':
          this.handleHighlight(cmd);
          break;
        case 'update_intel_panel':
          this.handleUpdateIntelPanel(cmd);
          break;
        case 'scroll_to':
          this.handleScrollTo(cmd);
          break;
        case 'switch_mode':
          this.handleSwitchMode(cmd);
          break;
        case 'show_notification':
          this.handleShowNotification(cmd);
          break;
        case 'update_sidebar_badge':
          this.handleUpdateSidebarBadge(cmd);
          break;
        case 'open_modal':
          this.handleOpenModal(cmd);
          break;
        default:
          console.warn(`[UICommandExecutor] Unknown command action: ${(cmd as UICommand).action}`);
      }
    } catch (err) {
      console.warn(`[UICommandExecutor] Failed to execute ${cmd.action}:`, err);
    }
  }

  private handleNavigate(cmd: UICommand): void {
    if (!cmd.route || !this.navigateFn) return;
    this.navigateFn(cmd.route);
    useNavigationStore.getState().setCurrentRoute(cmd.route);
  }

  private handleHighlight(cmd: UICommand): void {
    if (!cmd.element) return;

    const el = document.querySelector(`[data-aria-id="${cmd.element}"]`);
    if (!el) return;

    const effect: HighlightEffect = cmd.effect || 'glow';
    const className = `aria-highlight-${effect}`;
    const duration = cmd.duration || DEFAULT_HIGHLIGHT_DURATION_MS;

    el.classList.add(className);
    setTimeout(() => {
      el.classList.remove(className);
    }, duration);
  }

  private handleUpdateIntelPanel(cmd: UICommand): void {
    if (!cmd.content) return;
    this.intelPanelUpdateHandler?.(cmd.content);
  }

  private handleScrollTo(cmd: UICommand): void {
    if (!cmd.element) return;

    const el = document.querySelector(`[data-aria-id="${cmd.element}"]`);
    el?.scrollIntoView({ behavior: 'smooth', block: 'center' });
  }

  private handleSwitchMode(cmd: UICommand): void {
    if (!cmd.mode) return;

    switch (cmd.mode) {
      case 'workspace':
        modalityController.switchTo('text');
        break;
      case 'dialogue':
        modalityController.switchTo('avatar');
        break;
      case 'compact_avatar':
        modalityController.switchTo('text');
        break;
      default:
        console.warn(`[UICommandExecutor] Unknown mode: ${cmd.mode}`);
    }
  }

  private handleShowNotification(cmd: UICommand): void {
    const store = useNotificationsStore.getState();
    const typeMap: Record<string, 'info' | 'success' | 'warning' | 'error'> = {
      signal: 'info',
      alert: 'warning',
      success: 'success',
      info: 'info',
    };
    store.addNotification({
      type: typeMap[cmd.notification_type || 'info'] || 'info',
      title: cmd.notification_message || 'ARIA Notification',
      message: typeof cmd.content?.detail === 'string' ? cmd.content.detail : undefined,
    });
  }

  private handleUpdateSidebarBadge(cmd: UICommand): void {
    if (!cmd.sidebar_item || cmd.badge_count === undefined) return;
    window.dispatchEvent(
      new CustomEvent('aria:sidebar-badge', {
        detail: { item: cmd.sidebar_item, count: cmd.badge_count },
      }),
    );
  }

  private handleOpenModal(cmd: UICommand): void {
    if (!cmd.modal_id) return;
    window.dispatchEvent(
      new CustomEvent('aria:open-modal', {
        detail: { id: cmd.modal_id, data: cmd.modal_data || cmd.content },
      }),
    );
  }

  private delay(ms: number): Promise<void> {
    return new Promise((resolve) => setTimeout(resolve, ms));
  }
}

/** Singleton instance */
export const uiCommandExecutor = new UICommandExecutorImpl();
