import { Eye, MessageSquarePlus } from "lucide-react";
import { Link } from "react-router-dom";
import type { Lead } from "@/api/leads";

interface LeadTableRowProps {
  lead: Lead;
  isSelected: boolean;
  onSelect: () => void;
  onAddNote: () => void;
}

function HealthIndicator({ score }: { score: number }) {
  const getConfig = (score: number) => {
    if (score >= 70) return { emoji: "🟢", color: "text-success" };
    if (score >= 40) return { emoji: "🟡", color: "text-warning" };
    return { emoji: "🔴", color: "text-critical" };
  };

  const { emoji, color } = getConfig(score);

  return (
    <div className="flex items-center gap-2">
      <span>{emoji}</span>
      <span className={`font-medium ${color}`}>{score}</span>
    </div>
  );
}

export function LeadTableRow({ lead, isSelected, onSelect, onAddNote }: LeadTableRowProps) {
  const formatDate = (dateStr: string | null) => {
    if (!dateStr) return "—";
    const date = new Date(dateStr);
    return date.toLocaleDateString("en-US", {
      month: "short",
      day: "numeric",
      year: "numeric",
    });
  };

  const formatCurrency = (value: number | null) => {
    if (!value) return "—";
    return new Intl.NumberFormat("en-US", {
      style: "currency",
      currency: "USD",
      notation: "compact",
      maximumFractionDigits: 1,
    }).format(value);
  };

  return (
    <tr
      className={`group border-b border-slate-700/30 transition-colors hover:bg-slate-800/30 ${
        isSelected ? "bg-primary-500/5" : ""
      }`}
    >
      {/* Checkbox */}
      <td className="w-12 px-4 py-4">
        <button
          onClick={onSelect}
          className={`w-5 h-5 rounded border-2 transition-all duration-200 flex items-center justify-center ${
            isSelected
              ? "bg-primary-500 border-primary-500"
              : "border-slate-600 hover:border-slate-500"
          }`}
        >
          {isSelected && (
            <svg className="w-3 h-3 text-white" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={3} d="M5 13l4 4L19 7" />
            </svg>
          )}
        </button>
      </td>

      {/* Company Name */}
      <td className="px-4 py-4">
        <Link
          to={`/dashboard/leads/${lead.id}`}
          className="font-medium text-white hover:text-primary-300 transition-colors"
        >
          {lead.company_name}
        </Link>
      </td>

      {/* Health Score */}
      <td className="px-4 py-4">
        <HealthIndicator score={lead.health_score} />
      </td>

      {/* Stage */}
      <td className="px-4 py-4">
        <span
          className={`inline-flex items-center px-2.5 py-1 rounded-full text-xs font-medium capitalize ${
            lead.lifecycle_stage === "account"
              ? "bg-accent-500/10 text-accent-400"
              : lead.lifecycle_stage === "opportunity"
                ? "bg-primary-500/10 text-primary-400"
                : "bg-slate-500/10 text-slate-400"
          }`}
        >
          {lead.lifecycle_stage}
        </span>
      </td>

      {/* Status */}
      <td className="px-4 py-4">
        <span
          className={`inline-flex items-center px-2.5 py-1 rounded-full text-xs font-medium capitalize ${
            lead.status === "active"
              ? "bg-success/10 text-success"
              : lead.status === "won"
                ? "bg-primary-500/10 text-primary-400"
                : lead.status === "lost"
                  ? "bg-critical/10 text-critical"
                  : "bg-slate-500/10 text-slate-500"
          }`}
        >
          {lead.status}
        </span>
      </td>

      {/* Expected Value */}
      <td className="px-4 py-4 text-slate-400">
        {formatCurrency(lead.expected_value)}
      </td>

      {/* Last Activity */}
      <td className="px-4 py-4 text-slate-400">
        {formatDate(lead.last_activity_at)}
      </td>

      {/* Actions */}
      <td className="px-4 py-4">
        <div className="flex items-center gap-1 opacity-0 group-hover:opacity-100 transition-opacity">
          <Link
            to={`/dashboard/leads/${lead.id}`}
            className="p-2 rounded-lg hover:bg-slate-700/50 text-slate-400 hover:text-white transition-colors"
            title="View details"
          >
            <Eye className="w-4 h-4" />
          </Link>
          <button
            onClick={onAddNote}
            className="p-2 rounded-lg hover:bg-slate-700/50 text-slate-400 hover:text-primary-400 transition-colors"
            title="Add note"
          >
            <MessageSquarePlus className="w-4 h-4" />
          </button>
        </div>
      </td>
    </tr>
  );
}
