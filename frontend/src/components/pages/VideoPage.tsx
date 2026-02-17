/**
 * VideoPage - Tavus avatar video session page.
 *
 * Provides pre-call device check (HairCheck) and in-call video conversation.
 * Route: /dashboard/aria/video
 */

import { useState, useCallback } from "react";
import { useNavigate } from "react-router-dom";
import {
  ArrowLeft,
  Target,
  Activity,
  MessageSquare,
  Calendar,
  History,
  Layers,
} from "lucide-react";
import { CVIProvider } from "@/components/cvi/components/cvi-provider";
import { HairCheck } from "@/components/cvi/components/hair-check";
import { Conversation } from "@/components/cvi/components/conversation";
import { useVideoSession } from "@/hooks/useVideoSession";
import type { SessionType } from "@/api/video";
import { useGoals } from "@/hooks/useGoals";
import { useActivityFeed } from "@/hooks/useActivity";
import { VideoSessionHistory } from "@/components/video";

// Session type options
const SESSION_TYPES: { value: SessionType; label: string; description: string }[] = [
  { value: "chat", label: "Chat", description: "General conversation with ARIA" },
  { value: "briefing", label: "Briefing", description: "Get updates on priorities" },
  { value: "debrief", label: "Debrief", description: "Review recent activities" },
  { value: "consultation", label: "Consultation", description: "Strategic guidance" },
];

/**
 * Session context panel showing goals, activity, and transcript.
 */
function SessionContextPanel() {
  const { data: goalsData } = useGoals("active");
  const { data: activityData } = useActivityFeed();

  const activeGoals = goalsData?.slice(0, 3) ?? [];
  const recentActivity = activityData?.pages?.flatMap((p) => p.items).slice(0, 5) ?? [];

  return (
    <div className="flex flex-col h-full bg-[#0F1117] text-white">
      {/* Header */}
      <div className="px-4 py-3 border-b border-white/10">
        <h2 className="text-sm font-medium text-[#8B8FA3]">Session Context</h2>
      </div>

      {/* Active Goals */}
      <div className="px-4 py-3 border-b border-white/10">
        <div className="flex items-center gap-2 mb-2">
          <Target size={14} className="text-[#2E66FF]" />
          <span className="text-xs font-medium text-[#8B8FA3]">Active Goals</span>
        </div>
        {activeGoals.length === 0 ? (
          <p className="text-xs text-[#6B7280]">No active goals</p>
        ) : (
          <ul className="space-y-2">
            {activeGoals.map((goal) => (
              <li
                key={goal.id}
                className="text-sm text-white/90 truncate"
              >
                {goal.title}
              </li>
            ))}
          </ul>
        )}
      </div>

      {/* Recent Activity */}
      <div className="px-4 py-3 border-b border-white/10">
        <div className="flex items-center gap-2 mb-2">
          <Activity size={14} className="text-[#2E66FF]" />
          <span className="text-xs font-medium text-[#8B8FA3]">Recent ARIA Activity</span>
        </div>
        {recentActivity.length === 0 ? (
          <p className="text-xs text-[#6B7280]">No recent activity</p>
        ) : (
          <ul className="space-y-2">
            {recentActivity.map((item) => (
              <li
                key={item.id}
                className="text-xs text-white/70 truncate"
              >
                {item.description || item.activity_type}
              </li>
            ))}
          </ul>
        )}
      </div>

      {/* Live Transcript Placeholder */}
      <div className="flex-1 px-4 py-3 overflow-hidden">
        <div className="flex items-center gap-2 mb-2">
          <MessageSquare size={14} className="text-[#2E66FF]" />
          <span className="text-xs font-medium text-[#8B8FA3]">Live Transcript</span>
        </div>
        <div className="h-full overflow-y-auto">
          <p className="text-xs text-[#6B7280] italic">
            Transcript will appear here during the call...
          </p>
        </div>
      </div>
    </div>
  );
}

/**
 * Tab type for context panel
 */
type ContextTab = "context" | "history";

/**
 * Tabbed context panel with session context and history tabs.
 */
function TabbedContextPanel() {
  const [activeTab, setActiveTab] = useState<ContextTab>("context");

  return (
    <div className="flex flex-col h-full bg-[#0F1117] text-white">
      {/* Tab Header */}
      <div className="flex border-b border-white/10">
        <button
          type="button"
          onClick={() => setActiveTab("context")}
          className={`
            flex-1 px-4 py-2.5 text-xs font-medium
            flex items-center justify-center gap-1.5
            transition-colors
            ${activeTab === "context"
              ? "text-white bg-white/5 border-b-2 border-[#2E66FF] -mb-px"
              : "text-[#8B8FA3] hover:text-white hover:bg-white/5"
            }
          `}
        >
          <Layers size={14} />
          Context
        </button>
        <button
          type="button"
          onClick={() => setActiveTab("history")}
          className={`
            flex-1 px-4 py-2.5 text-xs font-medium
            flex items-center justify-center gap-1.5
            transition-colors
            ${activeTab === "history"
              ? "text-white bg-white/5 border-b-2 border-[#2E66FF] -mb-px"
              : "text-[#8B8FA3] hover:text-white hover:bg-white/5"
            }
          `}
        >
          <History size={14} />
          History
        </button>
      </div>

      {/* Tab Content */}
      <div className="flex-1 overflow-hidden">
        {activeTab === "context" ? (
          <SessionContextPanel />
        ) : (
          <VideoSessionHistory compact title="Past Sessions" />
        )}
      </div>
    </div>
  );
}

/**
 * Session type selector in the top bar.
 */
function SessionTypeSelector({
  value,
  onChange,
  disabled,
}: {
  value: SessionType;
  onChange: (type: SessionType) => void;
  disabled?: boolean;
}) {
  return (
    <div className="flex items-center gap-1 bg-[#1E2028] rounded-lg p-1">
      {SESSION_TYPES.map((type) => (
        <button
          key={type.value}
          type="button"
          onClick={() => onChange(type.value)}
          disabled={disabled}
          className={`
            px-3 py-1.5 text-xs font-medium rounded-md transition-colors
            ${value === type.value
              ? "bg-[#2E66FF] text-white"
              : "text-[#8B8FA3] hover:text-white hover:bg-white/5"
            }
            ${disabled ? "opacity-50 cursor-not-allowed" : ""}
          `}
          title={type.description}
        >
          {type.label}
        </button>
      ))}
    </div>
  );
}

/**
 * Video page content - handles state transitions.
 */
function VideoPageContent() {
  const navigate = useNavigate();
  const [sessionType, setSessionType] = useState<SessionType>("chat");

  const {
    connectionState,
    error,
    roomUrl,
    isCreating,
    startHaircheck,
    cancelHaircheck,
    joinCall,
    leaveCall,
    reset,
  } = useVideoSession();

  // Handle join from haircheck
  const handleJoin = useCallback(() => {
    joinCall(sessionType);
  }, [joinCall, sessionType]);

  // Handle leave from conversation
  const handleLeave = useCallback(() => {
    leaveCall();
  }, [leaveCall]);

  // Handle back navigation
  const handleBack = useCallback(() => {
    if (connectionState === "haircheck") {
      cancelHaircheck();
    } else if (connectionState === "error") {
      reset();
    }
    navigate(-1);
  }, [connectionState, cancelHaircheck, reset, navigate]);

  // Start haircheck on mount if idle
  // This effect is handled by parent component

  return (
    <div className="flex flex-col h-full bg-[#0A0A0B]">
      {/* Top Bar */}
      <div className="flex items-center justify-between px-4 py-3 border-b border-white/10">
        <div className="flex items-center gap-3">
          <button
            type="button"
            onClick={handleBack}
            className="flex items-center gap-1.5 text-[#8B8FA3] hover:text-white transition-colors"
          >
            <ArrowLeft size={16} />
            <span className="text-sm">Back</span>
          </button>
          <div className="h-4 w-px bg-white/10" />
          <h1 className="text-sm font-medium text-white">
            {connectionState === "haircheck" && "Prepare for Video Call"}
            {connectionState === "connecting" && "Connecting..."}
            {connectionState === "connected" && "Video Session"}
            {(connectionState === "idle" || connectionState === "error") && "ARIA Video"}
          </h1>
        </div>
        <SessionTypeSelector
          value={sessionType}
          onChange={setSessionType}
          disabled={connectionState === "connected" || connectionState === "connecting"}
        />
      </div>

      {/* Main Content */}
      <div className="flex-1 flex overflow-hidden">
        {/* Video Area */}
        <div className="flex-1 flex items-center justify-center p-4">
          {error && (
            <div className="text-center">
              <p className="text-red-400 mb-4">{error}</p>
              <button
                type="button"
                onClick={reset}
                className="px-4 py-2 bg-[#2E66FF] text-white rounded-lg text-sm hover:bg-[#2E66FF]/80"
              >
                Try Again
              </button>
            </div>
          )}

          {connectionState === "idle" && !error && (
            <div className="text-center">
              <div className="w-24 h-24 mx-auto mb-6 rounded-full bg-[#2E66FF]/20 flex items-center justify-center">
                <Calendar size={40} className="text-[#2E66FF]" />
              </div>
              <h2 className="text-xl font-medium text-white mb-2">
                Start a Video Session with ARIA
              </h2>
              <p className="text-[#8B8FA3] mb-6 max-w-md">
                Have a face-to-face conversation with your AI colleague.
                Select a session type and start when ready.
              </p>
              <button
                type="button"
                onClick={startHaircheck}
                className="px-6 py-3 bg-[#2E66FF] text-white rounded-lg text-sm font-medium hover:bg-[#2E66FF]/80 transition-colors"
              >
                Start Video Call
              </button>
            </div>
          )}

          {connectionState === "haircheck" && (
            <div className="w-full max-w-4xl">
              <HairCheck
                isJoinBtnLoading={isCreating}
                onJoin={handleJoin}
                onCancel={cancelHaircheck}
              />
            </div>
          )}

          {(connectionState === "connecting" || connectionState === "connected") && roomUrl && (
            <div className="w-full h-full">
              <Conversation
                conversationUrl={roomUrl}
                onLeave={handleLeave}
              />
            </div>
          )}

          {connectionState === "disconnecting" && (
            <div className="text-center">
              <p className="text-[#8B8FA3]">Ending session...</p>
            </div>
          )}
        </div>

        {/* Context Panel (40% width on desktop, hidden on mobile) */}
        <div className="hidden lg:block w-[40%] max-w-[400px] border-l border-white/10">
          <TabbedContextPanel />
        </div>
      </div>
    </div>
  );
}

/**
 * VideoPage - wrapped with CVIProvider for Daily.co context.
 */
export function VideoPage() {
  return (
    <CVIProvider>
      <VideoPageContent />
    </CVIProvider>
  );
}
