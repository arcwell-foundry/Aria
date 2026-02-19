/** AdminDashboardPage - Admin monitoring dashboard.
 *
 * Wraps AdminLayout with tab state management and renders
 * the active section component.
 */

import { useState } from "react";
import { AdminLayout, type AdminTab } from "@/components/admin/AdminLayout";
import { OODAMonitorSection } from "@/components/admin/OODAMonitorSection";
import { AgentWaterfallSection } from "@/components/admin/AgentWaterfallSection";
import { TokenUsageSection } from "@/components/admin/TokenUsageSection";
import { TrustEvolutionSection } from "@/components/admin/TrustEvolutionSection";
import { VerificationSection } from "@/components/admin/VerificationSection";

const SECTIONS: Record<AdminTab, React.ComponentType> = {
  ooda: OODAMonitorSection,
  agents: AgentWaterfallSection,
  tokens: TokenUsageSection,
  trust: TrustEvolutionSection,
  verification: VerificationSection,
};

export function AdminDashboardPage() {
  const [activeTab, setActiveTab] = useState<AdminTab>("ooda");
  const Section = SECTIONS[activeTab];

  return (
    <AdminLayout activeTab={activeTab} onTabChange={setActiveTab}>
      <Section />
    </AdminLayout>
  );
}
