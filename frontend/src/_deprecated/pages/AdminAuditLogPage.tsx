import { useEffect, useState, useCallback } from "react";
import { useNavigate } from "react-router-dom";
import { useProfile } from "@/hooks/useAccount";
import { useAuditLogs } from "@/hooks/useAuditLog";
import { exportAuditLogs } from "@/api/auditLog";
import type { AuditLogEntry, AuditLogFilters } from "@/api/auditLog";
import { HelpTooltip } from "@/components/HelpTooltip";
import {
  ChevronDown,
  ChevronLeft,
  ChevronRight,
  Download,
  FileText,
  Loader2,
  Search,
  Shield,
  X,
} from "lucide-react";

// Event type options for the filter dropdown
const EVENT_TYPE_OPTIONS = [
  { value: "", label: "All Operations" },
  { value: "login", label: "Login" },
  { value: "logout", label: "Logout" },
  { value: "password_change", label: "Password Change" },
  { value: "2fa_enabled", label: "2FA Enabled" },
  { value: "2fa_disabled", label: "2FA Disabled" },
  { value: "account_deleted", label: "Account Deleted" },
  { value: "session_revoked", label: "Session Revoked" },
  { value: "role_changed", label: "Role Changed" },
  { value: "data_export", label: "Data Export" },
  { value: "data_deletion", label: "Data Deletion" },
  { value: "create", label: "Memory Create" },
  { value: "update", label: "Memory Update" },
  { value: "delete", label: "Memory Delete" },
  { value: "query", label: "Memory Query" },
  { value: "invalidate", label: "Memory Invalidate" },
];

// Source badge config
const sourceBadge: Record<string, { label: string; bg: string; text: string; border: string }> = {
  security: {
    label: "Security",
    bg: "bg-warning/10",
    text: "text-warning",
    border: "border-warning/30",
  },
  memory: {
    label: "Memory",
    bg: "bg-info/10",
    text: "text-info",
    border: "border-info/30",
  },
};

function formatTimestamp(iso: string): string {
  if (!iso) return "—";
  const d = new Date(iso);
  return d.toLocaleString("en-US", {
    year: "numeric",
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
    hour12: false,
  });
}

function formatEventType(type: string): string {
  return type
    .replace(/_/g, " ")
    .replace(/\b\w/g, (c) => c.toUpperCase());
}

export function AdminAuditLogPage() {
  const navigate = useNavigate();
  const { data: profile } = useProfile();

  // Filters
  const [eventType, setEventType] = useState("");
  const [userId, setUserId] = useState("");
  const [dateFrom, setDateFrom] = useState("");
  const [dateTo, setDateTo] = useState("");
  const [searchTerm, setSearchTerm] = useState("");
  const [searchInput, setSearchInput] = useState("");
  const [page, setPage] = useState(1);
  const [expandedRow, setExpandedRow] = useState<string | null>(null);
  const [isExporting, setIsExporting] = useState(false);

  // Build filters object
  const filters: AuditLogFilters = {
    page,
    page_size: 50,
    ...(eventType && { event_type: eventType }),
    ...(userId && { user_id: userId }),
    ...(dateFrom && { date_from: new Date(dateFrom).toISOString() }),
    ...(dateTo && { date_to: new Date(dateTo + "T23:59:59").toISOString() }),
    ...(searchTerm && { search: searchTerm }),
  };

  const { data, isLoading } = useAuditLogs(filters);

  // Admin check
  const userRole = profile?.role || "user";
  const isAdmin = userRole === "admin";

  // Reset page on filter change
  const handleFilterChange = useCallback(() => {
    setPage(1);
  }, []);

  useEffect(() => {
    if (!isAdmin) {
      navigate("/dashboard");
    }
  }, [isAdmin, navigate]);

  if (!isAdmin) return null;

  const handleSearch = () => {
    setSearchTerm(searchInput);
    handleFilterChange();
  };

  const handleSearchKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Enter") {
      handleSearch();
    }
  };

  const clearFilters = () => {
    setEventType("");
    setUserId("");
    setDateFrom("");
    setDateTo("");
    setSearchTerm("");
    setSearchInput("");
    setPage(1);
  };

  const hasActiveFilters = eventType || userId || dateFrom || dateTo || searchTerm;

  const handleExport = async () => {
    setIsExporting(true);
    try {
      const blob = await exportAuditLogs(filters);
      const url = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = `audit_log_${new Date().toISOString().slice(0, 10)}.csv`;
      document.body.appendChild(link);
      link.click();
      document.body.removeChild(link);
      URL.revokeObjectURL(url);
    } catch {
      // Error handled by apiClient interceptor
    } finally {
      setIsExporting(false);
    }
  };

  const toggleRow = (id: string) => {
    setExpandedRow(expandedRow === id ? null : id);
  };

  const items = data?.items || [];
  const total = data?.total || 0;
  const hasMore = data?.has_more || false;
  const totalPages = Math.ceil(total / 50);

  return (
    <div className="min-h-screen bg-primary">
      {/* Header */}
      <div className="border-b border-border">
        <div className="max-w-[1120px] mx-auto px-6 py-8">
          <div className="flex items-start justify-between">
            <div>
              <div className="flex items-center gap-2">
                <h1 className="font-display text-[2rem] text-content">
                  Audit Trail
                </h1>
                <HelpTooltip
                  content="View all security and data events across your organization for compliance monitoring."
                  placement="right"
                />
              </div>
              <p className="text-secondary mt-2 text-[0.9375rem]">
                Security events, data access, and memory operations
              </p>
            </div>
            <button
              onClick={handleExport}
              disabled={isExporting || total === 0}
              className="px-5 py-2.5 bg-interactive text-white rounded-lg font-sans text-[0.875rem] font-medium hover:bg-interactive-hover active:bg-interactive-hover transition-colors duration-150 disabled:opacity-50 disabled:cursor-not-allowed cursor-pointer min-h-[44px] flex items-center gap-2"
            >
              {isExporting ? (
                <>
                  <Loader2 className="w-4 h-4 animate-spin" />
                  Exporting...
                </>
              ) : (
                <>
                  <Download className="w-4 h-4" />
                  Export CSV
                </>
              )}
            </button>
          </div>
        </div>
      </div>

      <div className="max-w-[1120px] mx-auto px-6 py-6 space-y-6">
        {/* Filter Bar */}
        <div className="bg-elevated border border-border rounded-xl p-4">
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-3">
            {/* Date From */}
            <div>
              <label className="block text-secondary text-[0.75rem] font-medium uppercase tracking-wider mb-1.5">
                From
              </label>
              <input
                type="date"
                value={dateFrom}
                onChange={(e) => {
                  setDateFrom(e.target.value);
                  handleFilterChange();
                }}
                className="w-full bg-subtle border border-border rounded-lg px-3 py-2.5 text-content text-[0.8125rem] font-mono focus:border-interactive focus:ring-1 focus:ring-interactive outline-none transition-colors duration-150"
              />
            </div>

            {/* Date To */}
            <div>
              <label className="block text-secondary text-[0.75rem] font-medium uppercase tracking-wider mb-1.5">
                To
              </label>
              <input
                type="date"
                value={dateTo}
                onChange={(e) => {
                  setDateTo(e.target.value);
                  handleFilterChange();
                }}
                className="w-full bg-subtle border border-border rounded-lg px-3 py-2.5 text-content text-[0.8125rem] font-mono focus:border-interactive focus:ring-1 focus:ring-interactive outline-none transition-colors duration-150"
              />
            </div>

            {/* Event Type */}
            <div>
              <label className="block text-secondary text-[0.75rem] font-medium uppercase tracking-wider mb-1.5">
                Operation
              </label>
              <div className="relative">
                <select
                  value={eventType}
                  onChange={(e) => {
                    setEventType(e.target.value);
                    handleFilterChange();
                  }}
                  className="w-full bg-subtle border border-border rounded-lg px-3 py-2.5 text-content text-[0.8125rem] focus:border-interactive focus:ring-1 focus:ring-interactive outline-none transition-colors duration-150 appearance-none cursor-pointer pr-8"
                >
                  {EVENT_TYPE_OPTIONS.map((opt) => (
                    <option key={opt.value} value={opt.value}>
                      {opt.label}
                    </option>
                  ))}
                </select>
                <ChevronDown className="absolute right-3 top-1/2 -translate-y-1/2 w-4 h-4 text-secondary pointer-events-none" />
              </div>
            </div>

            {/* Search */}
            <div>
              <label className="block text-secondary text-[0.75rem] font-medium uppercase tracking-wider mb-1.5">
                Search
              </label>
              <div className="relative">
                <input
                  type="text"
                  value={searchInput}
                  onChange={(e) => setSearchInput(e.target.value)}
                  onKeyDown={handleSearchKeyDown}
                  placeholder="Resource ID or description..."
                  className="w-full bg-subtle border border-border rounded-lg pl-9 pr-3 py-2.5 text-content text-[0.8125rem] placeholder:text-secondary/50 focus:border-interactive focus:ring-1 focus:ring-interactive outline-none transition-colors duration-150"
                />
                <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-secondary" />
              </div>
            </div>
          </div>

          {/* Active filters indicator */}
          {hasActiveFilters && (
            <div className="mt-3 pt-3 border-t border-border flex items-center justify-between">
              <span className="text-secondary text-[0.75rem]">
                {total} {total === 1 ? "result" : "results"} matching filters
              </span>
              <button
                onClick={clearFilters}
                className="flex items-center gap-1 text-interactive text-[0.75rem] hover:text-interactive-hover transition-colors duration-150 cursor-pointer"
              >
                <X className="w-3 h-3" />
                Clear filters
              </button>
            </div>
          )}
        </div>

        {/* Log Table */}
        <div className="bg-elevated border border-border rounded-xl overflow-hidden">
          {isLoading ? (
            <div className="flex items-center justify-center py-16">
              <Loader2 className="w-6 h-6 text-interactive animate-spin" />
            </div>
          ) : items.length === 0 ? (
            <div className="text-center py-16">
              <Shield className="w-12 h-12 text-border mx-auto mb-3" />
              <p className="text-secondary text-[0.9375rem]">
                No audit events match your filters
              </p>
              {hasActiveFilters && (
                <button
                  onClick={clearFilters}
                  className="mt-3 text-interactive text-[0.8125rem] hover:text-interactive-hover transition-colors duration-150 cursor-pointer"
                >
                  Clear all filters
                </button>
              )}
            </div>
          ) : (
            <>
              <div className="overflow-x-auto">
                <table className="w-full">
                  <thead>
                    <tr className="border-b border-border">
                      <th className="text-left px-5 py-3 text-secondary text-[0.6875rem] font-medium uppercase tracking-wider">
                        Timestamp
                      </th>
                      <th className="text-left px-5 py-3 text-secondary text-[0.6875rem] font-medium uppercase tracking-wider">
                        User
                      </th>
                      <th className="text-left px-5 py-3 text-secondary text-[0.6875rem] font-medium uppercase tracking-wider">
                        Operation
                      </th>
                      <th className="text-left px-5 py-3 text-secondary text-[0.6875rem] font-medium uppercase tracking-wider">
                        Source
                      </th>
                      <th className="text-left px-5 py-3 text-secondary text-[0.6875rem] font-medium uppercase tracking-wider">
                        Resource
                      </th>
                      <th className="text-left px-5 py-3 text-secondary text-[0.6875rem] font-medium uppercase tracking-wider">
                        Details
                      </th>
                    </tr>
                  </thead>
                  <tbody>
                    {items.map((entry: AuditLogEntry) => {
                      const badge = sourceBadge[entry.source] || sourceBadge.security;
                      const isExpanded = expandedRow === entry.id;
                      const metadataKeys = Object.keys(entry.metadata || {});
                      const detailPreview = metadataKeys.length > 0
                        ? metadataKeys.slice(0, 2).map((k) => `${k}: ${JSON.stringify(entry.metadata[k])}`).join(", ")
                        : "—";

                      return (
                        <tr
                          key={entry.id}
                          onClick={() => toggleRow(entry.id)}
                          className="border-b border-border last:border-0 hover:bg-subtle transition-colors duration-150 cursor-pointer group"
                        >
                          <td className="px-5 py-3.5">
                            <span className="font-mono text-[0.75rem] text-content whitespace-nowrap">
                              {formatTimestamp(entry.created_at)}
                            </span>
                          </td>
                          <td className="px-5 py-3.5">
                            <span className="font-mono text-[0.75rem] text-secondary" title={entry.user_id || ""}>
                              {entry.user_id ? entry.user_id.slice(0, 8) + "..." : "—"}
                            </span>
                          </td>
                          <td className="px-5 py-3.5">
                            <span className="text-[0.8125rem] text-content">
                              {formatEventType(entry.event_type)}
                            </span>
                          </td>
                          <td className="px-5 py-3.5">
                            <span
                              className={`inline-flex items-center px-2 py-0.5 rounded-md border text-[0.6875rem] font-medium ${badge.bg} ${badge.text} ${badge.border}`}
                            >
                              {badge.label}
                            </span>
                          </td>
                          <td className="px-5 py-3.5">
                            <div className="flex flex-col">
                              {entry.resource_type && (
                                <span className="text-[0.75rem] text-secondary">
                                  {entry.resource_type}
                                </span>
                              )}
                              {entry.resource_id && (
                                <span className="font-mono text-[0.6875rem] text-secondary/70" title={entry.resource_id}>
                                  {entry.resource_id.length > 12
                                    ? entry.resource_id.slice(0, 12) + "..."
                                    : entry.resource_id}
                                </span>
                              )}
                              {!entry.resource_type && !entry.resource_id && (
                                <span className="text-[0.75rem] text-secondary/50">—</span>
                              )}
                            </div>
                          </td>
                          <td className="px-5 py-3.5">
                            {isExpanded ? (
                              <pre className="font-mono text-[0.6875rem] text-secondary whitespace-pre-wrap max-w-[320px] bg-primary rounded-lg p-3 border border-border">
                                {JSON.stringify(entry.metadata, null, 2)}
                              </pre>
                            ) : (
                              <span className="text-[0.75rem] text-secondary max-w-[240px] truncate block">
                                {detailPreview.length > 60
                                  ? detailPreview.slice(0, 60) + "..."
                                  : detailPreview}
                              </span>
                            )}
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>

              {/* Pagination */}
              <div className="px-5 py-3 border-t border-border flex items-center justify-between">
                <span className="text-secondary text-[0.75rem]">
                  Showing {(page - 1) * 50 + 1}–{Math.min(page * 50, total)} of{" "}
                  {total.toLocaleString()} events
                </span>
                <div className="flex items-center gap-1">
                  <button
                    onClick={() => setPage(Math.max(1, page - 1))}
                    disabled={page <= 1}
                    className="p-2 rounded-lg hover:bg-subtle transition-colors duration-150 disabled:opacity-30 disabled:cursor-not-allowed cursor-pointer"
                    aria-label="Previous page"
                  >
                    <ChevronLeft className="w-4 h-4 text-secondary" />
                  </button>
                  <span className="text-content text-[0.8125rem] font-mono px-2">
                    {page} / {totalPages || 1}
                  </span>
                  <button
                    onClick={() => setPage(page + 1)}
                    disabled={!hasMore}
                    className="p-2 rounded-lg hover:bg-subtle transition-colors duration-150 disabled:opacity-30 disabled:cursor-not-allowed cursor-pointer"
                    aria-label="Next page"
                  >
                    <ChevronRight className="w-4 h-4 text-secondary" />
                  </button>
                </div>
              </div>
            </>
          )}
        </div>

        {/* Footer */}
        <div className="flex items-center gap-2 text-secondary text-[0.75rem]">
          <FileText className="w-3.5 h-3.5" />
          <span>
            Audit logs are retained for 90 days (queries) and 180 days (writes) per retention policy.
          </span>
        </div>
      </div>
    </div>
  );
}
