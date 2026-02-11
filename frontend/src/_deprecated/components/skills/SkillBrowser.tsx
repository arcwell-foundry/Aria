import { useState, useMemo } from "react";
import type { TrustLevel } from "@/api/skills";
import {
  useAvailableSkills,
  useInstalledSkills,
  useInstallSkill,
} from "@/hooks/useSkills";
import { SkillCard } from "./SkillCard";

const trustFilters: { value: TrustLevel | "all"; label: string }[] = [
  { value: "all", label: "All" },
  { value: "core", label: "Core" },
  { value: "verified", label: "Verified" },
  { value: "community", label: "Community" },
  { value: "user", label: "User" },
];

export function SkillBrowser() {
  const [search, setSearch] = useState("");
  const [trustFilter, setTrustFilter] = useState<TrustLevel | "all">("all");

  const filters = useMemo(
    () => ({
      query: search || undefined,
      trust_level: trustFilter === "all" ? undefined : trustFilter,
    }),
    [search, trustFilter]
  );

  const { data: skills, isLoading, error } = useAvailableSkills(filters);
  const { data: installed } = useInstalledSkills();
  const installSkill = useInstallSkill();

  const installedIds = useMemo(
    () => new Set(installed?.map((s) => s.skill_id) ?? []),
    [installed]
  );

  return (
    <div>
      {/* Search + filters */}
      <div className="flex flex-col sm:flex-row gap-3 mb-6">
        <div className="relative flex-1">
          <svg
            className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-500"
            fill="none"
            stroke="currentColor"
            viewBox="0 0 24 24"
          >
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              strokeWidth={2}
              d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z"
            />
          </svg>
          <input
            type="text"
            placeholder="Search skills..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="w-full pl-10 pr-4 py-2.5 bg-slate-800 border border-slate-700 rounded-lg text-white placeholder-slate-500 focus:outline-none focus:border-primary-500 focus:ring-1 focus:ring-primary-500 transition-colors"
          />
        </div>
      </div>

      {/* Trust level filter pills */}
      <div className="flex gap-2 mb-6 overflow-x-auto pb-2">
        {trustFilters.map((filter) => (
          <button
            key={filter.value}
            onClick={() => setTrustFilter(filter.value)}
            className={`px-4 py-2 text-sm font-medium rounded-lg whitespace-nowrap transition-colors ${
              trustFilter === filter.value
                ? "bg-primary-600/20 text-primary-400 border border-primary-500/30"
                : "text-slate-400 hover:text-white hover:bg-slate-800"
            }`}
          >
            {filter.label}
          </button>
        ))}
      </div>

      {/* Error */}
      {error && (
        <div className="bg-critical/10 border border-critical/30 rounded-xl p-4 mb-6">
          <p className="text-critical">
            Failed to load skills. Please try again.
          </p>
        </div>
      )}

      {/* Loading skeleton */}
      {isLoading && (
        <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
          {[1, 2, 3, 4, 5, 6].map((i) => (
            <div
              key={i}
              className="bg-slate-800/50 border border-slate-700 rounded-xl p-5 animate-pulse"
            >
              <div className="flex items-start justify-between mb-3">
                <div className="flex-1 space-y-2">
                  <div className="h-5 bg-slate-700 rounded w-3/4" />
                  <div className="h-3 bg-slate-700 rounded w-1/3" />
                </div>
                <div className="h-8 w-20 bg-slate-700 rounded-lg" />
              </div>
              <div className="h-4 bg-slate-700 rounded w-full mb-2" />
              <div className="h-4 bg-slate-700 rounded w-2/3 mb-3" />
              <div className="flex gap-2">
                <div className="h-6 bg-slate-700 rounded-full w-20" />
                <div className="h-6 bg-slate-700 rounded-full w-16" />
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Empty state */}
      {!isLoading && skills && skills.length === 0 && (
        <div className="flex flex-col items-center justify-center py-16 px-4">
          <div className="relative">
            <div className="absolute inset-0 bg-primary-500/20 blur-3xl rounded-full" />
            <div className="relative w-24 h-24 bg-slate-800 border border-slate-700 rounded-2xl flex items-center justify-center">
              <svg
                className="w-12 h-12 text-slate-500"
                fill="none"
                stroke="currentColor"
                viewBox="0 0 24 24"
              >
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  strokeWidth={1.5}
                  d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z"
                />
              </svg>
            </div>
          </div>
          <h3 className="mt-6 text-xl font-semibold text-white">
            No skills found
          </h3>
          <p className="mt-2 text-slate-400 text-center max-w-md">
            {search
              ? `No skills match "${search}". Try a different search term.`
              : "No skills available with the current filters."}
          </p>
        </div>
      )}

      {/* Skills grid */}
      {!isLoading && skills && skills.length > 0 && (
        <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
          {skills.map((skill, index) => (
            <div
              key={skill.id}
              className="animate-in fade-in slide-in-from-bottom-4"
              style={{
                animationDelay: `${index * 50}ms`,
                animationFillMode: "both",
              }}
            >
              <SkillCard
                skill={skill}
                isInstalled={installedIds.has(skill.id)}
                onInstall={() => installSkill.mutate(skill.id)}
                isInstalling={
                  installSkill.isPending &&
                  installSkill.variables === skill.id
                }
              />
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
