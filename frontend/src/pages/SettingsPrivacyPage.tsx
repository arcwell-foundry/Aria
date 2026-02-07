import { useState } from "react";
import {
  useDataExport,
  useConsentStatus,
  useRetentionPolicies,
  useDeleteUserData,
  useDeleteDigitalTwin,
  useUpdateConsent,
  useRefreshDataExport,
} from "@/hooks/useCompliance";
import {
  Shield,
  Download,
  Trash2,
  AlertTriangle,
  Clock,
  FileText,
  Mail,
  Database,
  Brain,
  Check,
  X,
  Loader2,
  ChevronDown,
  ChevronUp,
} from "lucide-react";
import { HelpTooltip } from "@/components/HelpTooltip";

export function SettingsPrivacyPage() {
  const { data: dataExport, isLoading: exportLoading } = useDataExport();
  const { data: consentStatus, isLoading: consentLoading } = useConsentStatus();
  const { data: retentionPolicies, isLoading: retentionLoading } = useRetentionPolicies();

  const deleteUserData = useDeleteUserData();
  const deleteDigitalTwin = useDeleteDigitalTwin();
  const updateConsent = useUpdateConsent();
  const refreshDataExport = useRefreshDataExport();

  // UI State
  const [isExportExpanded, setIsExportExpanded] = useState(false);
  const [isDigitalTwinExpanded, setIsDigitalTwinExpanded] = useState(false);
  const [isRetentionExpanded, setIsRetentionExpanded] = useState(false);
  const [isDangerZoneExpanded, setIsDangerZoneExpanded] = useState(false);

  // Deletion state
  const [deleteConfirmation, setDeleteConfirmation] = useState("");

  // Messages
  const [successMessage, setSuccessMessage] = useState("");
  const [errorMessage, setErrorMessage] = useState("");

  const showError = (msg: string) => {
    setErrorMessage(msg);
    setTimeout(() => setErrorMessage(""), 5000);
  };

  const showSuccess = (msg: string) => {
    setSuccessMessage(msg);
    setTimeout(() => setSuccessMessage(""), 3000);
  };

  const handleDownloadExport = () => {
    if (!dataExport) return;

    // Create a downloadable JSON file
    const blob = new Blob([JSON.stringify(dataExport, null, 2)], {
      type: "application/json",
    });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = `aria-data-export-${dataExport.user_id}-${dataExport.export_date}.json`;
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
    URL.revokeObjectURL(url);

    showSuccess("Data export downloaded");
  };

  const handleRefreshExport = async () => {
    try {
      await refreshDataExport.mutateAsync();
      showSuccess("Data export refreshed");
    } catch (err: unknown) {
      showError(err instanceof Error ? err.message : "Failed to refresh export");
    }
  };

  const handleUpdateConsent = async (
    category: "email_analysis" | "document_learning" | "crm_processing" | "writing_style_learning",
    granted: boolean
  ) => {
    try {
      await updateConsent.mutateAsync({ category, granted });
      showSuccess(`Consent updated for ${category.replace(/_/g, " ")}`);
    } catch (err: unknown) {
      showError(err instanceof Error ? err.message : "Failed to update consent");
    }
  };

  const handleDeleteDigitalTwin = async () => {
    if (!confirm("Are you sure you want to delete your Digital Twin? This will remove ARIA's learned understanding of your writing style and communication patterns.")) {
      return;
    }

    try {
      await deleteDigitalTwin.mutateAsync();
      setIsDigitalTwinExpanded(false);
      showSuccess("Digital Twin deleted successfully");
    } catch (err: unknown) {
      showError(err instanceof Error ? err.message : "Failed to delete Digital Twin");
    }
  };

  const handleDeleteUserData = async () => {
    if (deleteConfirmation !== "DELETE MY DATA") {
      showError('Please type "DELETE MY DATA" exactly');
      return;
    }

    if (!confirm("WARNING: This will permanently delete all your data. This action cannot be undone.")) {
      return;
    }

    try {
      await deleteUserData.mutateAsync({
        confirmation: deleteConfirmation,
      });
      // Data deleted, will be redirected by auth
      window.location.href = "/login";
    } catch (err: unknown) {
      showError(err instanceof Error ? err.message : "Failed to delete data");
    }
  };

  const consentCategories = [
    {
      key: "email_analysis" as const,
      label: "Email Analysis",
      description: "Allow ARIA to analyze your email communications to understand your communication patterns and relationships",
      icon: Mail,
    },
    {
      key: "document_learning" as const,
      label: "Document Learning",
      description: "Allow ARIA to learn from uploaded documents to build corporate memory and context",
      icon: FileText,
    },
    {
      key: "crm_processing" as const,
      label: "CRM Processing",
      description: "Allow ARIA to access and process CRM data for leads, contacts, and opportunities",
      icon: Database,
    },
    {
      key: "writing_style_learning" as const,
      label: "Writing Style Learning",
      description: "Allow ARIA to learn your writing style for the Digital Twin feature (personalized tone calibration)",
      icon: Brain,
    },
  ];

  if (consentLoading) {
    return (
      <div className="min-h-screen bg-[#0F1117] flex items-center justify-center">
        <Loader2 className="w-8 h-8 text-[#7B8EAA] animate-spin" />
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-[#0F1117]">
      {/* Header */}
      <div className="border-b border-[#2A2A2E]">
        <div className="max-w-[640px] mx-auto px-6 py-8">
          <div className="flex items-center gap-2">
            <h1 className="font-display text-[2rem] text-[#E8E6E1]">Privacy Settings</h1>
            <HelpTooltip content="Control how ARIA uses your data. Export, delete, or adjust consent settings." placement="right" />
          </div>
          <p className="text-[#8B92A5] mt-2">Manage your data, consent, and privacy preferences</p>
        </div>
      </div>

      {/* Messages */}
      {successMessage && (
        <div className="max-w-[640px] mx-auto px-6 mt-6">
          <div className="bg-[#6B8F71]/10 border border-[#6B8F71]/30 rounded-lg px-4 py-3 flex items-center gap-3">
            <Check className="w-5 h-5 text-[#6B8F71]" />
            <span className="text-[#E8E6E1]">{successMessage}</span>
          </div>
        </div>
      )}
      {errorMessage && (
        <div className="max-w-[640px] mx-auto px-6 mt-6">
          <div className="bg-[#A66B6B]/10 border border-[#A66B6B]/30 rounded-lg px-4 py-3 flex items-center gap-3">
            <X className="w-5 h-5 text-[#A66B6B]" />
            <span className="text-[#E8E6E1]">{errorMessage}</span>
          </div>
        </div>
      )}

      <div className="max-w-[640px] mx-auto px-6 py-8 space-y-6">
        {/* Data Export Section */}
        <div className="bg-[#161B2E] border border-[#2A2A2E] rounded-xl overflow-hidden">
          <button
            onClick={() => setIsExportExpanded(!isExportExpanded)}
            className="w-full px-6 py-5 flex items-center justify-between text-left hover:bg-[#1E2235] transition-colors duration-150"
          >
            <div className="flex items-center gap-3">
              <Download className="w-5 h-5 text-[#7B8EAA]" />
              <div>
                <h2 className="text-[#E8E6E1] font-sans text-[1.125rem] font-medium">Data Export</h2>
                <p className="text-[#8B92A5] text-[0.8125rem]">Download all your data (GDPR right to access)</p>
              </div>
            </div>
            {isExportExpanded ? (
              <ChevronUp className="w-5 h-5 text-[#7B8EAA]" />
            ) : (
              <ChevronDown className="w-5 h-5 text-[#7B8EAA]" />
            )}
          </button>

          {isExportExpanded && (
            <div className="px-6 pb-6 pt-2 border-t border-[#2A2A2E]">
              <p className="text-[#8B92A5] text-[0.875rem] mb-4">
                Export all your personal data including profile, settings, memory, conversations, and documents.
              </p>

              {exportLoading ? (
                <div className="flex justify-center py-8">
                  <Loader2 className="w-6 h-6 text-[#7B8EAA] animate-spin" />
                </div>
              ) : dataExport ? (
                <div className="space-y-4">
                  <div className="bg-[#1E2235] border border-[#2A2A2E] rounded-lg p-4">
                    <p className="text-[#8B92A5] text-[0.75rem] mb-2">Last export date</p>
                    <p className="text-[#E8E6E1] text-[0.875rem] font-mono">
                      {new Date(dataExport.export_date).toLocaleString()}
                    </p>
                  </div>

                  <div className="grid grid-cols-2 gap-3">
                    <div className="bg-[#1E2235] border border-[#2A2A2E] rounded-lg p-3">
                      <p className="text-[#8B92A5] text-[0.75rem]">Conversations</p>
                      <p className="text-[#E8E6E1] text-[1rem] font-medium">
                        {dataExport.conversations?.length || 0}
                      </p>
                    </div>
                    <div className="bg-[#1E2235] border border-[#2A2A2E] rounded-lg p-3">
                      <p className="text-[#8B92A5] text-[0.75rem]">Messages</p>
                      <p className="text-[#E8E6E1] text-[1rem] font-medium">
                        {dataExport.messages?.length || 0}
                      </p>
                    </div>
                    <div className="bg-[#1E2235] border border-[#2A2A2E] rounded-lg p-3">
                      <p className="text-[#8B92A5] text-[0.75rem]">Documents</p>
                      <p className="text-[#E8E6E1] text-[1rem] font-medium">
                        {dataExport.documents?.length || 0}
                      </p>
                    </div>
                    <div className="bg-[#1E2235] border border-[#2A2A2E] rounded-lg p-3">
                      <p className="text-[#8B92A5] text-[0.75rem]">Memory entries</p>
                      <p className="text-[#E8E6E1] text-[1rem] font-medium">
                        {(dataExport.semantic_memory?.length || 0) + (dataExport.prospective_memory?.length || 0)}
                      </p>
                    </div>
                  </div>

                  <div className="flex gap-3">
                    <button
                      onClick={handleDownloadExport}
                      disabled={refreshDataExport.isPending}
                      className="flex-1 px-5 py-2.5 bg-[#5B6E8A] text-white rounded-lg font-sans text-[0.875rem] font-medium hover:bg-[#4A5D79] active:bg-[#3D5070] transition-colors duration-150 disabled:opacity-50 disabled:cursor-not-allowed min-h-[44px] flex items-center justify-center gap-2"
                    >
                      <Download className="w-4 h-4" />
                      Download Export
                    </button>
                    <button
                      onClick={handleRefreshExport}
                      disabled={refreshDataExport.isPending}
                      className="px-5 py-2.5 bg-transparent border border-[#5B6E8A] text-[#5B6E8A] rounded-lg font-sans text-[0.875rem] font-medium hover:bg-[#5B6E8A]/10 transition-colors duration-150 min-h-[44px] flex items-center justify-center"
                    >
                      {refreshDataExport.isPending ? (
                        <Loader2 className="w-4 h-4 animate-spin" />
                      ) : (
                        "Refresh"
                      )}
                    </button>
                  </div>
                </div>
              ) : null}
            </div>
          )}
        </div>

        {/* Consent Management Section */}
        <div className="bg-[#161B2E] border border-[#2A2A2E] rounded-xl p-6">
          <div className="flex items-center gap-3 mb-6">
            <Shield className="w-5 h-5 text-[#7B8EAA]" />
            <div>
              <h2 className="text-[#E8E6E1] font-sans text-[1.125rem] font-medium">Data Consent</h2>
              <p className="text-[#8B92A5] text-[0.8125rem]">Control how ARIA processes your data</p>
            </div>
          </div>

          <div className="space-y-4">
            {consentCategories.map((category) => {
              const Icon = category.icon;
              const isGranted = consentStatus?.[category.key] ?? false;

              return (
                <div
                  key={category.key}
                  className="flex items-start justify-between py-3 px-4 bg-[#1E2235] rounded-lg border border-[#2A2A2E]"
                >
                  <div className="flex items-start gap-3 flex-1">
                    <Icon className="w-5 h-5 text-[#7B8EAA] mt-0.5" />
                    <div className="flex-1">
                      <p className="text-[#E8E6E1] text-[0.875rem] font-medium">{category.label}</p>
                      <p className="text-[#8B92A5] text-[0.75rem] mt-1">{category.description}</p>
                    </div>
                  </div>
                  <button
                    onClick={() => handleUpdateConsent(category.key, !isGranted)}
                    disabled={updateConsent.isPending}
                    className={`ml-4 relative inline-flex h-6 w-11 items-center rounded-full transition-colors duration-150 ${
                      isGranted ? "bg-[#6B8F71]" : "bg-[#2A2A2E]"
                    }`}
                  >
                    <span
                      className={`inline-block h-4 w-4 transform rounded-full bg-white transition-transform duration-150 ${
                        isGranted ? "translate-x-6" : "translate-x-1"
                      }`}
                    />
                  </button>
                </div>
              );
            })}
          </div>
        </div>

        {/* Digital Twin Section */}
        <div className="bg-[#161B2E] border border-[#2A2A2E] rounded-xl overflow-hidden">
          <button
            onClick={() => setIsDigitalTwinExpanded(!isDigitalTwinExpanded)}
            className="w-full px-6 py-5 flex items-center justify-between text-left hover:bg-[#1E2235] transition-colors duration-150"
          >
            <div className="flex items-center gap-3">
              <Brain className="w-5 h-5 text-[#7B8EAA]" />
              <div>
                <h2 className="text-[#E8E6E1] font-sans text-[1.125rem] font-medium">Digital Twin</h2>
                <p className="text-[#8B92A5] text-[0.8125rem]">Manage your writing style and communication patterns</p>
              </div>
            </div>
            {isDigitalTwinExpanded ? (
              <ChevronUp className="w-5 h-5 text-[#7B8EAA]" />
            ) : (
              <ChevronDown className="w-5 h-5 text-[#7B8EAA]" />
            )}
          </button>

          {isDigitalTwinExpanded && (
            <div className="px-6 pb-6 pt-2 border-t border-[#2A2A2E]">
              <p className="text-[#8B92A5] text-[0.875rem] mb-4">
                Your Digital Twin allows ARIA to calibrate her tone and communication style to match yours. This data is never shared with other users, even within your company.
              </p>
              <button
                onClick={handleDeleteDigitalTwin}
                disabled={deleteDigitalTwin.isPending}
                className="px-5 py-2.5 bg-transparent border border-[#A66B6B] text-[#A66B6B] rounded-lg font-sans text-[0.875rem] font-medium hover:bg-[#A66B6B]/10 transition-colors duration-150 disabled:opacity-50 disabled:cursor-not-allowed min-h-[44px] flex items-center justify-center gap-2"
              >
                {deleteDigitalTwin.isPending ? (
                  <>
                    <Loader2 className="w-4 h-4 animate-spin" />
                    Deleting...
                  </>
                ) : (
                  <>
                    <Trash2 className="w-4 h-4" />
                    Delete Digital Twin
                  </>
                )}
              </button>
            </div>
          )}
        </div>

        {/* Retention Policies Section */}
        <div className="bg-[#161B2E] border border-[#2A2A2E] rounded-xl overflow-hidden">
          <button
            onClick={() => setIsRetentionExpanded(!isRetentionExpanded)}
            className="w-full px-6 py-5 flex items-center justify-between text-left hover:bg-[#1E2235] transition-colors duration-150"
          >
            <div className="flex items-center gap-3">
              <Clock className="w-5 h-5 text-[#7B8EAA]" />
              <div>
                <h2 className="text-[#E8E6E1] font-sans text-[1.125rem] font-medium">Data Retention</h2>
                <p className="text-[#8B92A5] text-[0.8125rem]">How long we keep your data</p>
              </div>
            </div>
            {isRetentionExpanded ? (
              <ChevronUp className="w-5 h-5 text-[#7B8EAA]" />
            ) : (
              <ChevronDown className="w-5 h-5 text-[#7B8EAA]" />
            )}
          </button>

          {isRetentionExpanded && (
            <div className="px-6 pb-6 pt-2 border-t border-[#2A2A2E]">
              {retentionLoading ? (
                <div className="flex justify-center py-8">
                  <Loader2 className="w-6 h-6 text-[#7B8EAA] animate-spin" />
                </div>
              ) : retentionPolicies ? (
                <div className="space-y-4">
                  <div className="bg-[#1E2235] border border-[#2A2A2E] rounded-lg p-4">
                    <p className="text-[#E8E6E1] text-[0.875rem] font-medium mb-1">Audit Logs</p>
                    <p className="text-[#8B92A5] text-[0.8125rem]">
                      Query logs: {(retentionPolicies.audit_query_logs as { retention_days?: number } | undefined)?.retention_days || 90} days
                    </p>
                    <p className="text-[#8B92A5] text-[0.8125rem]">
                      Write logs: {(retentionPolicies.audit_write_logs as { retention_days?: number } | undefined)?.retention_days || 180} days
                    </p>
                  </div>

                  <div className="bg-[#1E2235] border border-[#2A2A2E] rounded-lg p-4">
                    <p className="text-[#E8E6E1] text-[0.875rem] font-medium mb-1">Email Data</p>
                    <p className="text-[#8B92A5] text-[0.8125rem]">
                      {(retentionPolicies.email_data as { description?: string } | undefined)?.description || "Retained for analysis while account is active"}
                    </p>
                  </div>

                  <div className="bg-[#1E2235] border border-[#2A2A2E] rounded-lg p-4">
                    <p className="text-[#E8E6E1] text-[0.875rem] font-medium mb-1">Conversation History</p>
                    <p className="text-[#8B92A5] text-[0.8125rem]">
                      {(retentionPolicies.conversation_history as { description?: string } | undefined)?.description || "Retained while account is active"}
                    </p>
                  </div>

                  {retentionPolicies.note && (
                    <div className="bg-[#6B7FA3]/10 border border-[#6B7FA3]/30 rounded-lg p-3">
                      <p className="text-[#E8E6E1] text-[0.8125rem]">{retentionPolicies.note}</p>
                    </div>
                  )}
                </div>
              ) : null}
            </div>
          )}
        </div>

        {/* Danger Zone */}
        <div className="bg-[#161B2E] border border-[#A66B6B]/30 rounded-xl overflow-hidden">
          <button
            onClick={() => setIsDangerZoneExpanded(!isDangerZoneExpanded)}
            className="w-full px-6 py-5 flex items-center justify-between text-left hover:bg-[#1E2235] transition-colors duration-150"
          >
            <div className="flex items-center gap-3">
              <AlertTriangle className="w-5 h-5 text-[#A66B6B]" />
              <div>
                <h2 className="text-[#A66B6B] font-sans text-[1.125rem] font-medium">Danger Zone</h2>
                <p className="text-[#8B92A5] text-[0.8125rem]">Irreversible data deletion</p>
              </div>
            </div>
            {isDangerZoneExpanded ? (
              <ChevronUp className="w-5 h-5 text-[#7B8EAA]" />
            ) : (
              <ChevronDown className="w-5 h-5 text-[#7B8EAA]" />
            )}
          </button>

          {isDangerZoneExpanded && (
            <div className="px-6 pb-6 pt-2 border-t border-[#A66B6B]/20">
              <div className="space-y-4">
                <p className="text-[#8B92A5] text-[0.875rem]">
                  Deleting all your data is permanent. This will remove your profile, memories, conversations, documents, and settings. This action cannot be undone.
                </p>

                <div>
                  <label className="block text-[#8B92A5] text-[0.8125rem] font-medium mb-1.5">
                    Type <span className="text-[#E8E6E1] font-mono">DELETE MY DATA</span> to confirm
                  </label>
                  <input
                    type="text"
                    value={deleteConfirmation}
                    onChange={(e) => setDeleteConfirmation(e.target.value)}
                    className="w-full bg-[#1E2235] border border-[#2A2A2E] rounded-lg px-4 py-3 text-[#E8E6E1] text-[0.9375rem] focus:border-[#A66B6B] focus:ring-1 focus:ring-[#A66B6B] outline-none transition-colors duration-150"
                    placeholder="DELETE MY DATA"
                  />
                </div>

                <button
                  onClick={handleDeleteUserData}
                  disabled={deleteUserData.isPending || deleteConfirmation !== "DELETE MY DATA"}
                  className="w-full px-5 py-2.5 bg-transparent border border-[#A66B6B] text-[#A66B6B] rounded-lg font-sans text-[0.875rem] font-medium hover:bg-[#A66B6B]/10 transition-colors duration-150 disabled:opacity-50 disabled:cursor-not-allowed min-h-[44px] flex items-center justify-center"
                >
                  {deleteUserData.isPending ? (
                    <>
                      <Loader2 className="w-4 h-4 animate-spin mr-2" />
                      Deleting...
                    </>
                  ) : (
                    <>
                      <Trash2 className="w-4 h-4 mr-2" />
                      Delete All My Data
                    </>
                  )}
                </button>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
