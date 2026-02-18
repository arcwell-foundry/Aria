import { Video, Phone, MessageSquare } from 'lucide-react';
import { modalityController } from '@/core/ModalityController';
import { useAuth } from '@/hooks/useAuth';

function getGreeting(): string {
  const hour = new Date().getHours();
  if (hour < 12) return 'Good morning';
  if (hour < 17) return 'Good afternoon';
  return 'Good evening';
}

interface WelcomeCTAsProps {
  onStartTyping: () => void;
}

interface CTAButtonProps {
  icon: React.ReactNode;
  label: string;
  subtitle: string;
  onClick: () => void;
}

function CTAButton({ icon, label, subtitle, onClick }: CTAButtonProps) {
  return (
    <button
      onClick={onClick}
      className="flex flex-col items-center gap-2 w-[140px] px-4 py-5 rounded-xl border border-[#1A1A2E] bg-[#111318] hover:border-[#2E66FF]/30 hover:bg-[#111318]/80 transition-all hover:-translate-y-0.5 hover:shadow-lg hover:shadow-[#2E66FF]/5"
    >
      <div className="w-10 h-10 rounded-lg bg-[#2E66FF]/10 flex items-center justify-center">
        {icon}
      </div>
      <span className="text-sm font-medium text-[#F8FAFC]">{label}</span>
      <span className="text-[11px] text-[#8B8FA3]">{subtitle}</span>
    </button>
  );
}

export function WelcomeCTAs({ onStartTyping }: WelcomeCTAsProps) {
  const { user } = useAuth();
  const firstName = user?.user_metadata?.first_name || user?.email?.split('@')[0] || 'there';
  const greeting = getGreeting();

  return (
    <div
      className="flex flex-col items-center justify-center h-full"
      data-aria-id="welcome-ctas"
    >
      {/* Avatar */}
      <div className="w-20 h-20 rounded-full overflow-hidden mb-5 border-2 border-[#2E66FF]/20" style={{ boxShadow: '0 0 30px rgba(46,102,255,0.15)' }}>
        <img
          src="/aria-avatar.png"
          alt="ARIA"
          className="w-full h-full object-cover"
          onError={(e) => {
            (e.target as HTMLImageElement).style.display = 'none';
          }}
        />
      </div>

      {/* Greeting */}
      <h1
        className="text-2xl text-[#F8FAFC] mb-1"
        style={{ fontFamily: "'Instrument Serif', Georgia, serif", fontStyle: 'italic' }}
      >
        {greeting}, {firstName}
      </h1>
      <p className="text-sm text-[#8B8FA3] mb-8 max-w-[320px] text-center">
        I've been reviewing your pipeline overnight. How would you like to connect?
      </p>

      {/* CTA buttons */}
      <div className="flex items-center gap-4">
        <CTAButton
          icon={<Video size={20} className="text-[#2E66FF]" />}
          label="Morning Briefing"
          subtitle="Video walkthrough"
          onClick={() => modalityController.switchTo('avatar', 'briefing')}
        />
        <CTAButton
          icon={<Phone size={20} className="text-[#2E66FF]" />}
          label="Quick Question"
          subtitle="Voice call"
          onClick={() => modalityController.switchToAudioCall('chat')}
        />
        <CTAButton
          icon={<MessageSquare size={20} className="text-[#2E66FF]" />}
          label="Type a message"
          subtitle="Text chat"
          onClick={onStartTyping}
        />
      </div>
    </div>
  );
}
