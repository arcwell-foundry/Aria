import { Video, VideoOff, MessageSquare } from 'lucide-react';
import { useModalityStore } from '@/stores/modalityStore';
import { modalityController } from '@/core/ModalityController';
import { EmotionIndicator } from '@/components/shell/EmotionIndicator';

export function DialogueHeader() {
  const tavusSession = useModalityStore((s) => s.tavusSession);
  const isActive = tavusSession.status === 'active';

  return (
    <div className="flex items-center justify-between px-6 py-3 border-b border-[#1A1A2E] bg-[#0A0A0B]">
      <div className="flex items-center gap-3">
        <div className="flex items-center gap-2 px-3 py-1.5 rounded-lg bg-[#2E66FF]/10 border border-[#2E66FF]/20">
          <Video size={16} className="text-[#2E66FF]" />
          <span className="font-mono text-[11px] text-[#2E66FF] tracking-wider">
            DIALOGUE MODE
          </span>
        </div>

        <div className="flex items-center gap-2">
          <div
            className={`w-2 h-2 rounded-full ${
              isActive
                ? 'bg-emerald-400 animate-pulse'
                : tavusSession.status === 'connecting'
                  ? 'bg-amber-400 animate-pulse'
                  : 'bg-[#555770]'
            }`}
          />
          <span className="font-mono text-[11px] text-[#8B8FA3]">
            {isActive ? 'LIVE' : tavusSession.status === 'connecting' ? 'CONNECTING' : 'OFFLINE'}
          </span>
        </div>
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
