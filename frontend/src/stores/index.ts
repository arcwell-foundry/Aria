/**
 * Zustand Stores - Global state management for ARIA
 *
 * Store structure:
 * - conversationStore: Chat/conversation state
 * - navigationStore: Navigation and sidebar state
 * - notificationsStore: Toast and notification state
 * - modalityStore: Avatar/voice/text modality state
 * - perceptionStore: Raven-0 emotion detection state
 */

export { useConversationStore, type ConversationState } from './conversationStore';
export { useModalityStore, type ModalityState } from './modalityStore';
export { useNavigationStore, type NavigationState } from './navigationStore';
export { useNotificationsStore, type NotificationsState, type Notification } from './notificationsStore';
export { usePerceptionStore, type PerceptionState, type EmotionReading, type DetectedEmotion } from './perceptionStore';
export { useAgentStatusStore, type AgentStatusState } from './agentStatusStore';
export { useActionQueueStore, type ActionQueueState } from './actionQueueStore';
