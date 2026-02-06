import type { AvailableSkill } from "@/api/skills";
import { TrustLevelBadge } from "./TrustLevelBadge";

interface SkillCardProps {
  skill: AvailableSkill;
  isInstalled: boolean;
  onInstall: () => void;
  isInstalling?: boolean;
}

export function SkillCard({
  skill,
  isInstalled,
  onInstall,
  isInstalling = false,
}: SkillCardProps) {
  return (
    <div className="group relative bg-slate-800/50 border border-slate-700 rounded-xl p-5 transition-all duration-200 hover:bg-slate-800/80 hover:border-slate-600 hover:shadow-lg hover:shadow-slate-900/50">
      {/* Gradient border effect on hover */}
      <div className="absolute inset-0 rounded-xl bg-gradient-to-r from-primary-500/0 via-primary-500/10 to-accent-500/0 opacity-0 group-hover:opacity-100 transition-opacity duration-300 pointer-events-none" />

      <div className="relative">
        {/* Header: name + action */}
        <div className="flex items-start justify-between gap-3">
          <div className="flex-1 min-w-0">
            <h3 className="text-lg font-semibold text-white truncate group-hover:text-primary-400 transition-colors">
              {skill.skill_name}
            </h3>
            {skill.author && (
              <p className="mt-0.5 text-xs text-slate-500">
                by {skill.author}
                {skill.version && (
                  <span className="ml-2 text-slate-600">v{skill.version}</span>
                )}
              </p>
            )}
          </div>

          {/* Install button */}
          {isInstalled ? (
            <span className="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium text-emerald-400 bg-emerald-500/10 border border-emerald-500/20 rounded-lg">
              <svg
                className="w-3.5 h-3.5"
                fill="none"
                stroke="currentColor"
                viewBox="0 0 24 24"
              >
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  strokeWidth={2}
                  d="M5 13l4 4L19 7"
                />
              </svg>
              Installed
            </span>
          ) : (
            <button
              onClick={onInstall}
              disabled={isInstalling}
              className="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium text-white bg-primary-600 hover:bg-primary-500 disabled:opacity-50 disabled:cursor-not-allowed rounded-lg transition-colors shadow-sm"
            >
              {isInstalling ? (
                <>
                  <svg
                    className="w-3.5 h-3.5 animate-spin"
                    fill="none"
                    viewBox="0 0 24 24"
                  >
                    <circle
                      className="opacity-25"
                      cx="12"
                      cy="12"
                      r="10"
                      stroke="currentColor"
                      strokeWidth="4"
                    />
                    <path
                      className="opacity-75"
                      fill="currentColor"
                      d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z"
                    />
                  </svg>
                  Installing
                </>
              ) : (
                <>
                  <svg
                    className="w-3.5 h-3.5"
                    fill="none"
                    stroke="currentColor"
                    viewBox="0 0 24 24"
                  >
                    <path
                      strokeLinecap="round"
                      strokeLinejoin="round"
                      strokeWidth={2}
                      d="M12 4v16m8-8H4"
                    />
                  </svg>
                  Install
                </>
              )}
            </button>
          )}
        </div>

        {/* Description */}
        {skill.description && (
          <p className="mt-2 text-sm text-slate-400 line-clamp-2">
            {skill.description}
          </p>
        )}

        {/* Footer: badges + tags */}
        <div className="mt-3 flex flex-wrap items-center gap-2">
          <TrustLevelBadge level={skill.trust_level} size="sm" />
          {skill.life_sciences_relevant && (
            <span className="inline-flex items-center gap-1 px-2 py-0.5 text-xs font-medium text-violet-400 bg-violet-500/15 border border-violet-500/20 rounded-full">
              <svg
                className="w-3 h-3"
                fill="none"
                stroke="currentColor"
                viewBox="0 0 24 24"
              >
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  strokeWidth={2}
                  d="M19.428 15.428a2 2 0 00-1.022-.547l-2.387-.477a6 6 0 00-3.86.517l-.318.158a6 6 0 01-3.86.517L6.05 15.21a2 2 0 00-1.806.547M8 4h8l-1 1v5.172a2 2 0 00.586 1.414l5 5c1.26 1.26.367 3.414-1.415 3.414H4.828c-1.782 0-2.674-2.154-1.414-3.414l5-5A2 2 0 009 10.172V5L8 4z"
                />
              </svg>
              Life Sciences
            </span>
          )}
          {skill.tags.slice(0, 3).map((tag) => (
            <span
              key={tag}
              className="px-2 py-0.5 text-xs text-slate-500 bg-slate-700/50 rounded-full"
            >
              {tag}
            </span>
          ))}
        </div>
      </div>
    </div>
  );
}
