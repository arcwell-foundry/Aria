import {
  ArrowDownAZ,
  ArrowUpAZ,
  Download,
  Filter,
  Grid3X3,
  List,
  Search,
  X,
} from "lucide-react";
import { useState, useMemo } from "react";
import type { Lead, LeadFilters, LeadStatus, LifecycleStage } from "@/api/leads";
import { DashboardLayout } from "@/components/DashboardLayout";
import {
  AddNoteModal,
  EmptyLeads,
  LeadCard,
  LeadsSkeleton,
  LeadTableRow,
} from "@/components/leads";
import { useAddNote, useExportLeads, useLeads } from "@/hooks/useLeads";
import { HelpTooltip } from "@/components/HelpTooltip";

type ViewMode = "card" | "table";
type SortField = "health" | "last_activity" | "name" | "value";
type SortOrder = "asc" | "desc";

const statusOptions: { value: LeadStatus | "all"; label: string }[] = [
  { value: "all", label: "All Status" },
  { value: "active", label: "Active" },
  { value: "won", label: "Won" },
  { value: "lost", label: "Lost" },
  { value: "dormant", label: "Dormant" },
];

const stageOptions: { value: LifecycleStage | "all"; label: string }[] = [
  { value: "all", label: "All Stages" },
  { value: "lead", label: "Lead" },
  { value: "opportunity", label: "Opportunity" },
  { value: "account", label: "Account" },
];

const healthRanges = [
  { value: "all", label: "All Health", min: undefined, max: undefined },
  { value: "healthy", label: "Healthy (70+)", min: 70, max: 100 },
  { value: "attention", label: "Needs Attention (40-69)", min: 40, max: 69 },
  { value: "risk", label: "At Risk (<40)", min: 0, max: 39 },
];

const sortOptions: { value: SortField; label: string }[] = [
  { value: "last_activity", label: "Last Activity" },
  { value: "health", label: "Health Score" },
  { value: "name", label: "Company Name" },
  { value: "value", label: "Expected Value" },
];

export function LeadsPage() {
  // View state
  const [viewMode, setViewMode] = useState<ViewMode>("card");
  const [showFilters, setShowFilters] = useState(false);

  // Filter state
  const [searchQuery, setSearchQuery] = useState("");
  const [statusFilter, setStatusFilter] = useState<LeadStatus | "all">("all");
  const [stageFilter, setStageFilter] = useState<LifecycleStage | "all">("all");
  const [healthFilter, setHealthFilter] = useState<string>("all");
  const [sortBy, setSortBy] = useState<SortField>("last_activity");
  const [sortOrder, setSortOrder] = useState<SortOrder>("desc");

  // Selection state
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set());

  // Modal state
  const [noteModalLead, setNoteModalLead] = useState<Lead | null>(null);

  // Build filters object
  const filters: LeadFilters = useMemo(() => {
    const healthRange = healthRanges.find((r) => r.value === healthFilter);
    return {
      status: statusFilter !== "all" ? statusFilter : undefined,
      stage: stageFilter !== "all" ? stageFilter : undefined,
      minHealth: healthRange?.min,
      maxHealth: healthRange?.max,
      search: searchQuery || undefined,
      sortBy,
      sortOrder,
    };
  }, [statusFilter, stageFilter, healthFilter, searchQuery, sortBy, sortOrder]);

  const hasActiveFilters =
    statusFilter !== "all" ||
    stageFilter !== "all" ||
    healthFilter !== "all" ||
    searchQuery !== "";

  // Queries and mutations
  const { data: leads, isLoading, error } = useLeads(filters);
  const addNoteMutation = useAddNote();
  const exportMutation = useExportLeads();

  // Selection handlers
  const toggleSelection = (id: string) => {
    setSelectedIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) {
        next.delete(id);
      } else {
        next.add(id);
      }
      return next;
    });
  };

  const selectAll = () => {
    if (leads) {
      setSelectedIds(new Set(leads.map((l) => l.id)));
    }
  };

  const clearSelection = () => {
    setSelectedIds(new Set());
  };

  const clearFilters = () => {
    setSearchQuery("");
    setStatusFilter("all");
    setStageFilter("all");
    setHealthFilter("all");
  };

  // Action handlers
  const handleAddNote = (content: string) => {
    if (noteModalLead) {
      addNoteMutation.mutate(
        { leadId: noteModalLead.id, note: { content } },
        {
          onSuccess: () => {
            setNoteModalLead(null);
          },
        }
      );
    }
  };

  const handleExport = () => {
    if (selectedIds.size > 0) {
      exportMutation.mutate(Array.from(selectedIds));
    }
  };

  const toggleSortOrder = () => {
    setSortOrder((prev) => (prev === "asc" ? "desc" : "asc"));
  };

  return (
    <DashboardLayout>
      <div className="relative min-h-screen">
        {/* Subtle gradient background */}
        <div className="absolute inset-0 bg-[radial-gradient(ellipse_at_top,_var(--tw-gradient-stops))] from-slate-800 via-slate-900 to-slate-900 pointer-events-none" />

        <div className="relative max-w-7xl mx-auto px-4 py-8 lg:px-8">
          {/* Header */}
          <div className="flex flex-col lg:flex-row lg:items-center lg:justify-between gap-4 mb-8">
            <div>
              <div className="flex items-center gap-2">
                <h1 className="text-3xl font-bold text-white tracking-tight">Lead Memory</h1>
                <HelpTooltip content="Track and manage your sales leads. ARIA monitors health scores and suggests next actions." placement="right" />
              </div>
              <p className="mt-1 text-slate-400">
                Track and manage your sales pursuits with AI-powered insights
              </p>
            </div>

            {/* View toggle and export */}
            <div className="flex items-center gap-3">
              {selectedIds.size > 0 && (
                <button
                  onClick={handleExport}
                  disabled={exportMutation.isPending}
                  className="inline-flex items-center gap-2 px-4 py-2.5 bg-primary-600 hover:bg-primary-500 disabled:bg-primary-600/50 text-white font-medium rounded-lg transition-colors shadow-lg shadow-primary-600/25"
                >
                  <Download className="w-4 h-4" />
                  Export ({selectedIds.size})
                </button>
              )}

              <div className="flex items-center bg-slate-800/50 border border-slate-700/50 rounded-lg p-1">
                <button
                  onClick={() => setViewMode("card")}
                  className={`p-2 rounded-md transition-colors ${
                    viewMode === "card"
                      ? "bg-slate-700 text-white"
                      : "text-slate-400 hover:text-white"
                  }`}
                  title="Card view"
                >
                  <Grid3X3 className="w-5 h-5" />
                </button>
                <button
                  onClick={() => setViewMode("table")}
                  className={`p-2 rounded-md transition-colors ${
                    viewMode === "table"
                      ? "bg-slate-700 text-white"
                      : "text-slate-400 hover:text-white"
                  }`}
                  title="Table view"
                >
                  <List className="w-5 h-5" />
                </button>
              </div>
            </div>
          </div>

          {/* Search and filters bar */}
          <div className="flex flex-col sm:flex-row gap-3 mb-6">
            {/* Search */}
            <div className="relative flex-1 max-w-md">
              <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-5 h-5 text-slate-500" />
              <input
                type="text"
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                placeholder="Search by company name..."
                className="w-full pl-10 pr-4 py-2.5 bg-slate-800/50 border border-slate-700/50 rounded-lg text-white placeholder-slate-500 focus:outline-none focus:ring-2 focus:ring-primary-500/50 focus:border-primary-500/50 transition-all"
              />
              {searchQuery && (
                <button
                  onClick={() => setSearchQuery("")}
                  className="absolute right-3 top-1/2 -translate-y-1/2 text-slate-500 hover:text-slate-400"
                >
                  <X className="w-4 h-4" />
                </button>
              )}
            </div>

            {/* Filter toggle */}
            <button
              onClick={() => setShowFilters(!showFilters)}
              className={`inline-flex items-center gap-2 px-4 py-2.5 border rounded-lg font-medium transition-colors ${
                showFilters || hasActiveFilters
                  ? "bg-primary-600/20 border-primary-500/30 text-primary-400"
                  : "bg-slate-800/50 border-slate-700/50 text-slate-400 hover:text-white hover:border-slate-600/50"
              }`}
            >
              <Filter className="w-4 h-4" />
              Filters
              {hasActiveFilters && (
                <span className="w-2 h-2 rounded-full bg-primary-500" />
              )}
            </button>

            {/* Sort controls */}
            <div className="flex items-center gap-2">
              <select
                value={sortBy}
                onChange={(e) => setSortBy(e.target.value as SortField)}
                className="px-3 py-2.5 bg-slate-800/50 border border-slate-700/50 rounded-lg text-slate-300 focus:outline-none focus:ring-2 focus:ring-primary-500/50"
              >
                {sortOptions.map((opt) => (
                  <option key={opt.value} value={opt.value}>
                    Sort: {opt.label}
                  </option>
                ))}
              </select>
              <button
                onClick={toggleSortOrder}
                className="p-2.5 bg-slate-800/50 border border-slate-700/50 rounded-lg text-slate-400 hover:text-white transition-colors"
                title={sortOrder === "asc" ? "Ascending" : "Descending"}
              >
                {sortOrder === "asc" ? (
                  <ArrowUpAZ className="w-5 h-5" />
                ) : (
                  <ArrowDownAZ className="w-5 h-5" />
                )}
              </button>
            </div>
          </div>

          {/* Expanded filters */}
          {showFilters && (
            <div className="mb-6 p-4 bg-slate-800/30 border border-slate-700/30 rounded-xl animate-in fade-in slide-in-from-top-2 duration-200">
              <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
                {/* Status filter */}
                <div>
                  <label className="block text-sm font-medium text-slate-400 mb-2">
                    Status
                  </label>
                  <select
                    value={statusFilter}
                    onChange={(e) => setStatusFilter(e.target.value as LeadStatus | "all")}
                    className="w-full px-3 py-2.5 bg-slate-800/50 border border-slate-700/50 rounded-lg text-slate-300 focus:outline-none focus:ring-2 focus:ring-primary-500/50"
                  >
                    {statusOptions.map((opt) => (
                      <option key={opt.value} value={opt.value}>
                        {opt.label}
                      </option>
                    ))}
                  </select>
                </div>

                {/* Stage filter */}
                <div>
                  <label className="block text-sm font-medium text-slate-400 mb-2">
                    Stage
                  </label>
                  <select
                    value={stageFilter}
                    onChange={(e) => setStageFilter(e.target.value as LifecycleStage | "all")}
                    className="w-full px-3 py-2.5 bg-slate-800/50 border border-slate-700/50 rounded-lg text-slate-300 focus:outline-none focus:ring-2 focus:ring-primary-500/50"
                  >
                    {stageOptions.map((opt) => (
                      <option key={opt.value} value={opt.value}>
                        {opt.label}
                      </option>
                    ))}
                  </select>
                </div>

                {/* Health filter */}
                <div>
                  <label className="block text-sm font-medium text-slate-400 mb-2">
                    Health Score
                  </label>
                  <select
                    value={healthFilter}
                    onChange={(e) => setHealthFilter(e.target.value)}
                    className="w-full px-3 py-2.5 bg-slate-800/50 border border-slate-700/50 rounded-lg text-slate-300 focus:outline-none focus:ring-2 focus:ring-primary-500/50"
                  >
                    {healthRanges.map((opt) => (
                      <option key={opt.value} value={opt.value}>
                        {opt.label}
                      </option>
                    ))}
                  </select>
                </div>
              </div>

              {hasActiveFilters && (
                <div className="mt-4 pt-4 border-t border-slate-700/30 flex justify-end">
                  <button
                    onClick={clearFilters}
                    className="text-sm text-slate-400 hover:text-white transition-colors"
                  >
                    Clear all filters
                  </button>
                </div>
              )}
            </div>
          )}

          {/* Selection bar */}
          {leads && leads.length > 0 && (
            <div className="flex items-center justify-between mb-4">
              <div className="flex items-center gap-4">
                <button
                  onClick={selectedIds.size === leads.length ? clearSelection : selectAll}
                  className="text-sm text-slate-400 hover:text-white transition-colors"
                >
                  {selectedIds.size === leads.length ? "Deselect all" : "Select all"}
                </button>
                {selectedIds.size > 0 && (
                  <span className="text-sm text-slate-500">
                    {selectedIds.size} of {leads.length} selected
                  </span>
                )}
              </div>
              <span className="text-sm text-slate-500">
                {leads.length} lead{leads.length !== 1 ? "s" : ""}
              </span>
            </div>
          )}

          {/* Error state */}
          {error && (
            <div className="bg-red-500/10 border border-red-500/30 rounded-xl p-4 mb-6">
              <p className="text-red-400">Failed to load leads. Please try again.</p>
            </div>
          )}

          {/* Loading state */}
          {isLoading && <LeadsSkeleton viewMode={viewMode} />}

          {/* Empty state */}
          {!isLoading && leads && leads.length === 0 && (
            <EmptyLeads hasFilters={hasActiveFilters} onClearFilters={clearFilters} />
          )}

          {/* Lead grid/table */}
          {!isLoading && leads && leads.length > 0 && (
            <>
              {viewMode === "card" ? (
                <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
                  {leads.map((lead, index) => (
                    <div
                      key={lead.id}
                      className="animate-in fade-in slide-in-from-bottom-4"
                      style={{
                        animationDelay: `${Math.min(index * 50, 300)}ms`,
                        animationFillMode: "both",
                      }}
                    >
                      <LeadCard
                        lead={lead}
                        isSelected={selectedIds.has(lead.id)}
                        onSelect={() => toggleSelection(lead.id)}
                        onAddNote={() => setNoteModalLead(lead)}
                      />
                    </div>
                  ))}
                </div>
              ) : (
                <div className="bg-slate-800/40 border border-slate-700/50 rounded-xl overflow-hidden overflow-x-auto">
                  <table className="w-full min-w-[800px]">
                    <thead>
                      <tr className="bg-slate-800/60 text-left">
                        <th className="w-12 px-4 py-3">
                          <button
                            onClick={selectedIds.size === leads.length ? clearSelection : selectAll}
                            className={`w-5 h-5 rounded border-2 transition-all duration-200 flex items-center justify-center ${
                              selectedIds.size === leads.length
                                ? "bg-primary-500 border-primary-500"
                                : "border-slate-600 hover:border-slate-500"
                            }`}
                          >
                            {selectedIds.size === leads.length && (
                              <svg
                                className="w-3 h-3 text-white"
                                fill="none"
                                viewBox="0 0 24 24"
                                stroke="currentColor"
                              >
                                <path
                                  strokeLinecap="round"
                                  strokeLinejoin="round"
                                  strokeWidth={3}
                                  d="M5 13l4 4L19 7"
                                />
                              </svg>
                            )}
                          </button>
                        </th>
                        <th className="px-4 py-3 text-sm font-medium text-slate-400">Company</th>
                        <th className="px-4 py-3 text-sm font-medium text-slate-400">Health</th>
                        <th className="px-4 py-3 text-sm font-medium text-slate-400">Stage</th>
                        <th className="px-4 py-3 text-sm font-medium text-slate-400">Status</th>
                        <th className="px-4 py-3 text-sm font-medium text-slate-400">Value</th>
                        <th className="px-4 py-3 text-sm font-medium text-slate-400">
                          Last Activity
                        </th>
                        <th className="px-4 py-3 text-sm font-medium text-slate-400">Actions</th>
                      </tr>
                    </thead>
                    <tbody>
                      {leads.map((lead) => (
                        <LeadTableRow
                          key={lead.id}
                          lead={lead}
                          isSelected={selectedIds.has(lead.id)}
                          onSelect={() => toggleSelection(lead.id)}
                          onAddNote={() => setNoteModalLead(lead)}
                        />
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </>
          )}
        </div>

        {/* Add Note Modal */}
        <AddNoteModal
          lead={noteModalLead}
          isOpen={noteModalLead !== null}
          onClose={() => setNoteModalLead(null)}
          onSubmit={handleAddNote}
          isLoading={addNoteMutation.isPending}
        />
      </div>
    </DashboardLayout>
  );
}
