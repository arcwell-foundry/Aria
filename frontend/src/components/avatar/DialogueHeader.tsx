import { Video, VideoOff, MessageSquare, FileText } from 'lucide-react';
import { useModalityStore } from '@/stores/modalityStore';
import { modalityController } from '@/core/ModalityController';
import { EmotionIndicator } from '@/components/shell/EmotionIndicator';

interface DialogueHeaderProps {
  viewMode?: 'dialogue' | 'text';
  onViewModeChange?: (mode: 'dialogue' | 'text') => void;
}

export function DialogueHeader({ viewMode = 'dialogue', onViewModeChange }: DialogueHeaderProps) {
  const tavusSession = useModalityStore((s) => s.tavusSession);
  const isActive = tavusSession.status === 'active';

  return (
    <div className="flex items-center justify-between px-6 py-3 border-b border-[#1A1A2E] bg-[#0A0A0B]">
      <div className="flex items-center gap-3">
        {/* Dialogue Mode tab */}
        <button
          onClick={() => onViewModeChange?.('dialogue')}
          className={`flex items-center gap-2 px-3 py-1.5 rounded-lg border transition-colors ${
            viewMode === 'dialogue'
              ? 'bg-[#2E66FF]/10 border-[#2E66FF]/20'
              : 'bg-transparent border-transparent hover:bg-[#1A1A2E] cursor-pointer'
          }`}
        >
          <Video size={16} className={viewMode === 'dialogue' ? 'text-[#2E66FF]' : 'text-[#555770]'} />
          <span
            className={`font-mono text-[11px] tracking-wider ${
              viewMode === 'dialogue' ? 'text-[#2E66FF]' : 'text-[#555770]'
            }`}
          >
            DIALOGUE MODE
          </span>
        </button>

        {/* Text Mode tab */}
        <button
          onClick={() => onViewModeChange?.('text')}
          className={`flex items-center gap-2 px-3 py-1.5 rounded-lg border transition-colors ${
            viewMode === 'text'
              ? 'bg-[#2E66FF]/10 border-[#2E66FF]/20'
              : 'bg-transparent border-transparent hover:bg-[#1A1A2E] cursor-pointer'
          }`}
        >
          <FileText size={16} className={viewMode === 'text' ? 'text-[#2E66FF]' : 'text-[#555770]'} />
          <span
            className={`font-mono text-[11px] tracking-wider ${
              viewMode === 'text' ? 'text-[#2E66FF]' : 'text-[#555770]'
            }`}
          >
            TEXT MODE
          </span>
        </button>

        {/* Connection status dot — small indicator, not a tab */}
        {(isActive || tavusSession.status === 'connecting') && (
          <div className="flex items-center gap-1.5 ml-1">
            <div
              className={`w-2 h-2 rounded-full ${
                isActive
                  ? 'bg-emerald-400 animate-pulse'
                  : 'bg-amber-400 animate-pulse'
              }`}
            />
            <span className="font-mono text-[10px] text-[#8B8FA3]">
              {isActive ? 'LIVE' : 'CONNECTING'}
            </span>
          </div>
        )}
      </div>

      <EmotionIndicator />

      {(isActive || tavusSession.status === 'connecting') && (
        <div className="flex items-center gap-2">
          <button
            onClick={() => modalityController.switchToChat()}
            className="flex items-center gap-2 px-3 py-1.5 rounded-lg text-[#8B8FA3] hover:text-[#2E66FF] hover:bg-[#2E66FF]/10 transition-colors"
            title="Switch to Chat"
          >
            <MessageSquare size={14} />
            <span className="text-xs">Chat</span>
          </button>
          <button
            onClick={() => modalityController.endSession()}
            className="flex items-center gap-2 px-3 py-1.5 rounded-lg text-[#8B8FA3] hover:text-red-400 hover:bg-red-400/10 transition-colors"
          >
            <VideoOff size={14} />
            <span className="text-xs">End Session</span>
          </button>
        </div>
      )}
    </div>
  );
}
