/** AdminLayout - Minimal shell for the admin dashboard.
 *
 * No sidebar or IntelPanel. Logo, "Back to ARIA" link,
 * and a tab bar for 5 dashboard sections.
 */

import { ArrowLeft } from "lucide-react";
import { Link } from "react-router-dom";
import { cn } from "@/utils/cn";

export type AdminTab =
  | "ooda"
  | "agents"
  | "tokens"
  | "trust"
  | "verification";

const TABS: { id: AdminTab; label: string }[] = [
  { id: "ooda", label: "OODA Monitor" },
  { id: "agents", label: "Agent Waterfall" },
  { id: "tokens", label: "Token Usage" },
  { id: "trust", label: "Trust Evolution" },
  { id: "verification", label: "Verification" },
];

interface AdminLayoutProps {
  activeTab: AdminTab;
  onTabChange: (tab: AdminTab) => void;
  children: React.ReactNode;
}

export function AdminLayout({ activeTab, onTabChange, children }: AdminLayoutProps) {
  return (
    <div
      className="min-h-screen flex flex-col"
      style={{ backgroundColor: "var(--bg-primary)", color: "var(--text-primary)" }}
    >
      {/* Header */}
      <header
        className="flex items-center justify-between px-6 py-3 border-b"
        style={{ borderColor: "var(--border)", backgroundColor: "var(--bg-elevated)" }}
      >
        <div className="flex items-center gap-4">
          <Link
            to="/"
            className="flex items-center gap-1.5 text-xs font-medium transition-colors"
            style={{ color: "var(--text-secondary)" }}
            onMouseEnter={(e) => (e.currentTarget.style.color = "var(--accent)")}
            onMouseLeave={(e) => (e.currentTarget.style.color = "var(--text-secondary)")}
          >
            <ArrowLeft className="w-3.5 h-3.5" />
            Back to ARIA
          </Link>
          <div className="h-4 w-px" style={{ backgroundColor: "var(--border)" }} />
          <h1
            className="font-mono text-sm font-semibold tracking-wider uppercase"
            style={{ color: "var(--text-primary)" }}
          >
            Admin Dashboard
          </h1>
        </div>
      </header>

      {/* Tab Bar */}
      <nav
        className="flex gap-0 px-6 border-b overflow-x-auto"
        style={{ borderColor: "var(--border)", backgroundColor: "var(--bg-elevated)" }}
      >
        {TABS.map((tab) => (
          <button
            key={tab.id}
            onClick={() => onTabChange(tab.id)}
            className={cn(
              "px-4 py-2.5 text-xs font-medium tracking-wide whitespace-nowrap",
              "border-b-2 transition-colors cursor-pointer",
            )}
            style={{
              borderColor: activeTab === tab.id ? "var(--accent)" : "transparent",
              color: activeTab === tab.id ? "var(--accent)" : "var(--text-secondary)",
            }}
            onMouseEnter={(e) => {
              if (activeTab !== tab.id) {
                e.currentTarget.style.color = "var(--text-primary)";
              }
            }}
            onMouseLeave={(e) => {
              if (activeTab !== tab.id) {
                e.currentTarget.style.color = "var(--text-secondary)";
              }
            }}
          >
            {tab.label}
          </button>
        ))}
      </nav>

      {/* Content */}
      <main className="flex-1 p-6 overflow-auto">
        {children}
      </main>
    </div>
  );
}
