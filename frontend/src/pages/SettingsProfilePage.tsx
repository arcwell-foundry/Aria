import { useState, useCallback, useRef, type KeyboardEvent } from "react";
import { Link, useLocation } from "react-router-dom";
import {
  User,
  Building2,
  FileText,
  Link2,
  Shield,
  Upload,
  Trash2,
  RefreshCw,
  Check,
  X,
  Loader2,
  Plus,
  Mail,
  Calendar,
  MessageSquare,
  Settings,
  CreditCard,
  Users,
  Lock,
} from "lucide-react";
import { useAuth } from "@/hooks/useAuth";
import {
  useFullProfile,
  useProfileDocuments,
  useUpdateUserDetails,
  useUpdateCompanyDetails,
} from "@/hooks/useProfilePage";
import { HelpTooltip } from "@/components/HelpTooltip";
import type { FullProfile, ProfileDocuments } from "@/api/profile";

// --- Settings sidebar nav items ---
const settingsNav = [
  { name: "Profile", href: "/settings/profile", icon: User },
  { name: "ARIA Config", href: "/settings/preferences", icon: Settings },
  { name: "Account", href: "/settings/account", icon: Lock },
  { name: "Team", href: "/admin/team", icon: Users },
  { name: "Billing", href: "/admin/billing", icon: CreditCard },
  { name: "Privacy", href: "/settings/privacy", icon: Shield },
];

// --- Tab definitions ---
type TabId = "personal" | "company" | "documents" | "integrations";

const tabs: { id: TabId; label: string; icon: typeof User }[] = [
  { id: "personal", label: "Personal Details", icon: User },
  { id: "company", label: "Company", icon: Building2 },
  { id: "documents", label: "Documents", icon: FileText },
  { id: "integrations", label: "Integrations", icon: Link2 },
];

// --- Helpers ---

function formatFileSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

function formatDate(iso: string): string {
  return new Date(iso).toLocaleDateString("en-US", {
    month: "short",
    day: "numeric",
    year: "numeric",
  });
}

function fileTypeIcon(type: string): string {
  const map: Record<string, string> = {
    pdf: "PDF",
    doc: "DOC",
    docx: "DOC",
    ppt: "PPT",
    pptx: "PPT",
    xls: "XLS",
    xlsx: "XLS",
    csv: "CSV",
    txt: "TXT",
  };
  return map[type.toLowerCase()] || type.toUpperCase().slice(0, 3);
}

function qualityBadge(score: number | null) {
  if (score === null) return null;
  const pct = Math.round(score * 100);
  let color = "text-[#945A5A] bg-[#945A5A]/8 border-[#945A5A]/20";
  if (pct >= 80) color = "text-[#5A7D60] bg-[#5A7D60]/8 border-[#5A7D60]/20";
  else if (pct >= 50) color = "text-[#A6845A] bg-[#A6845A]/8 border-[#A6845A]/20";
  return (
    <span
      className={`inline-flex items-center px-2 py-0.5 rounded border text-[0.6875rem] font-mono font-medium ${color}`}
    >
      {pct}%
    </span>
  );
}

// --- Shared styles ---
const inputCls =
  "w-full bg-white border border-[#E2E0DC] rounded-lg px-4 py-3 text-[0.9375rem] font-sans text-[#1A1D27] placeholder-[#6B7280]/60 focus:border-[#5B6E8A] focus:ring-1 focus:ring-[#5B6E8A] outline-none transition-colors duration-150";
const labelCls = "block text-[#6B7280] text-[0.8125rem] font-sans font-medium mb-1.5";
const primaryBtnCls =
  "px-5 py-2.5 bg-[#5B6E8A] text-white rounded-lg font-sans text-[0.875rem] font-medium hover:bg-[#4A5D79] active:bg-[#3D5070] transition-colors duration-150 disabled:opacity-50 disabled:cursor-not-allowed min-h-[44px] flex items-center justify-center cursor-pointer";
const secondaryBtnCls =
  "px-5 py-2.5 bg-transparent border border-[#5B6E8A] text-[#5B6E8A] rounded-lg font-sans text-[0.875rem] font-medium hover:bg-[#5B6E8A]/10 transition-colors duration-150 min-h-[44px] cursor-pointer";
const tagCls =
  "inline-flex items-center gap-1.5 px-3 py-1 bg-[#F5F5F0] border border-[#E2E0DC] rounded-lg text-[0.8125rem] text-[#1A1D27] font-sans";

// --- Wrapper component: fetches data, then renders form with key-based reset ---

export function SettingsProfilePage() {
  const { data: profile, isLoading: profileLoading } = useFullProfile();
  const { data: documents, isLoading: docsLoading } = useProfileDocuments();

  if (profileLoading) {
    return (
      <div className="min-h-screen bg-[#FAFAF9] flex items-center justify-center">
        <Loader2 className="w-8 h-8 text-[#5B6E8A] animate-spin" />
      </div>
    );
  }

  // Use updated_at as key so the form remounts with fresh initial state on data changes
  const formKey = profile?.user?.updated_at ?? "loaded";

  return (
    <ProfilePageInner
      key={formKey}
      profile={profile ?? null}
      documents={documents ?? null}
      docsLoading={docsLoading}
    />
  );
}

// --- Inner component: owns all form state, initialized from props ---

interface ProfilePageInnerProps {
  profile: FullProfile | null;
  documents: ProfileDocuments | null;
  docsLoading: boolean;
}

function ProfilePageInner({ profile, documents, docsLoading }: ProfilePageInnerProps) {
  const location = useLocation();
  const { user } = useAuth();
  const [activeTab, setActiveTab] = useState<TabId>("personal");

  // Mutations
  const updateUser = useUpdateUserDetails();
  const updateCompany = useUpdateCompanyDetails();

  // Toast
  const [toast, setToast] = useState<{ type: "success" | "error"; message: string } | null>(null);
  const toastTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  const showToast = useCallback((type: "success" | "error", message: string) => {
    setToast({ type, message });
    if (toastTimer.current) clearTimeout(toastTimer.current);
    toastTimer.current = setTimeout(() => setToast(null), 3000);
  }, []);

  // Derive initial values from profile props
  const u = profile?.user;
  const prefs = u?.communication_preferences as Record<string, string> | undefined;
  const c = profile?.company;

  // --- Personal Details form state ---
  const [fullName, setFullName] = useState(u?.full_name || "");
  const [title, setTitle] = useState(u?.title || "");
  const [department, setDepartment] = useState(u?.department || "");
  const [linkedinUrl, setLinkedinUrl] = useState(u?.linkedin_url || "");
  const [preferredName, setPreferredName] = useState(prefs?.preferred_name || "");
  const [timezone, setTimezone] = useState(prefs?.timezone || "");
  const [notifFrequency, setNotifFrequency] = useState(prefs?.notification_frequency || "daily");
  const [defaultTone, setDefaultTone] = useState<"formal" | "friendly" | "urgent">(
    (u?.default_tone as "formal" | "friendly" | "urgent") || "friendly",
  );
  const [competitors, setCompetitors] = useState<string[]>(u?.tracked_competitors || []);
  const [competitorInput, setCompetitorInput] = useState("");
  const [privacyExclusions, setPrivacyExclusions] = useState<string[]>(
    u?.privacy_exclusions || [],
  );
  const [exclusionInput, setExclusionInput] = useState("");

  // --- Company form state ---
  const [companyName, setCompanyName] = useState(c?.name || "");
  const [companyWebsite, setCompanyWebsite] = useState(c?.website || "");
  const [companyIndustry, setCompanyIndustry] = useState(c?.industry || "");
  const [companySubVertical, setCompanySubVertical] = useState(c?.sub_vertical || "");
  const [companyDescription, setCompanyDescription] = useState(c?.description || "");
  const [companyProducts, setCompanyProducts] = useState<string[]>(c?.key_products || []);
  const [productInput, setProductInput] = useState("");

  const isAdmin = u?.role === "admin";

  // --- Handlers ---

  const handleSavePersonal = async () => {
    try {
      await updateUser.mutateAsync({
        full_name: fullName || undefined,
        title: title || undefined,
        department: department || undefined,
        linkedin_url: linkedinUrl || undefined,
        communication_preferences: {
          preferred_name: preferredName || undefined,
          timezone: timezone || undefined,
          notification_frequency: notifFrequency,
        },
        default_tone: defaultTone,
        tracked_competitors: competitors,
        privacy_exclusions: privacyExclusions,
      });
      showToast("success", "Personal details saved");
    } catch (err: unknown) {
      showToast("error", err instanceof Error ? err.message : "Failed to save");
    }
  };

  const handleSaveCompany = async () => {
    try {
      await updateCompany.mutateAsync({
        name: companyName || undefined,
        website: companyWebsite || undefined,
        industry: companyIndustry || undefined,
        sub_vertical: companySubVertical || undefined,
        description: companyDescription || undefined,
        key_products: companyProducts.length > 0 ? companyProducts : undefined,
      });
      showToast("success", "Company details saved");
    } catch (err: unknown) {
      showToast("error", err instanceof Error ? err.message : "Failed to save");
    }
  };

  const addTag = (
    value: string,
    list: string[],
    setList: (v: string[]) => void,
    setInput: (v: string) => void,
  ) => {
    const trimmed = value.trim();
    if (trimmed && !list.includes(trimmed)) {
      setList([...list, trimmed]);
    }
    setInput("");
  };

  const removeTag = (index: number, list: string[], setList: (v: string[]) => void) => {
    setList(list.filter((_, i) => i !== index));
  };

  const handleTagKeyDown = (
    e: KeyboardEvent<HTMLInputElement>,
    value: string,
    list: string[],
    setList: (v: string[]) => void,
    setInput: (v: string) => void,
  ) => {
    if (e.key === "Enter" || e.key === ",") {
      e.preventDefault();
      addTag(value, list, setList, setInput);
    }
  };

  return (
    <div className="min-h-screen bg-[#FAFAF9]">
      <div className="flex">
        {/* Left Settings Sidebar */}
        <aside className="hidden lg:block w-60 min-h-screen border-r border-[#E2E0DC] bg-[#F5F5F0] shrink-0">
          <div className="px-6 pt-8 pb-6">
            <h2 className="font-display text-[1.5rem] text-[#1A1D27]">Settings</h2>
          </div>
          <nav className="px-3 space-y-0.5">
            {settingsNav.map((item) => {
              const Icon = item.icon;
              const active = location.pathname === item.href;
              return (
                <Link
                  key={item.name}
                  to={item.href}
                  className={`flex items-center gap-3 px-4 py-2.5 rounded-lg text-[0.875rem] font-sans transition-colors duration-150 ${
                    active
                      ? "bg-white text-[#1A1D27] font-medium shadow-sm border border-[#E2E0DC]"
                      : "text-[#6B7280] hover:text-[#1A1D27] hover:bg-white/60"
                  }`}
                >
                  <Icon className="w-[18px] h-[18px] stroke-[1.5]" />
                  {item.name}
                </Link>
              );
            })}
          </nav>
        </aside>

        {/* Main content */}
        <div className="flex-1 min-w-0">
          {/* Header */}
          <div className="border-b border-[#E2E0DC]">
            <div className="max-w-3xl mx-auto px-6 lg:px-8 pt-8 pb-6">
              <div className="flex items-center gap-2">
                <h1 className="font-display text-[2rem] text-[#1A1D27] leading-tight">
                  Profile
                </h1>
                <HelpTooltip
                  content="Manage your personal details, company information, documents, and integration settings."
                  placement="right"
                />
              </div>
              <p className="text-[#6B7280] text-[0.9375rem] mt-2 font-sans">
                Your information helps ARIA personalize her intelligence for you.
              </p>
            </div>

            {/* Tabs */}
            <div className="max-w-3xl mx-auto px-6 lg:px-8">
              <div className="flex gap-0 -mb-px">
                {tabs.map((tab) => {
                  const Icon = tab.icon;
                  const active = activeTab === tab.id;
                  return (
                    <button
                      key={tab.id}
                      onClick={() => setActiveTab(tab.id)}
                      className={`flex items-center gap-2 px-4 py-3 text-[0.875rem] font-sans font-medium border-b-2 transition-colors duration-150 cursor-pointer ${
                        active
                          ? "border-[#5B6E8A] text-[#1A1D27]"
                          : "border-transparent text-[#6B7280] hover:text-[#1A1D27] hover:border-[#E2E0DC]"
                      }`}
                    >
                      <Icon className="w-4 h-4 stroke-[1.5]" />
                      {tab.label}
                    </button>
                  );
                })}
              </div>
            </div>
          </div>

          {/* Tab content */}
          <div className="max-w-3xl mx-auto px-6 lg:px-8 py-8">
            {/* ==================== TAB 1: Personal Details ==================== */}
            {activeTab === "personal" && (
              <div className="space-y-8">
                {/* Basic info */}
                <section className="bg-white border border-[#E2E0DC] rounded-xl p-6 shadow-sm">
                  <h3 className="font-display text-[1.25rem] text-[#1A1D27] mb-6">
                    Basic Information
                  </h3>
                  <div className="space-y-4">
                    <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                      <div>
                        <label htmlFor="fullName" className={labelCls}>
                          Full Name
                        </label>
                        <input
                          id="fullName"
                          type="text"
                          value={fullName}
                          onChange={(e) => setFullName(e.target.value)}
                          className={inputCls}
                          placeholder="Jane Smith"
                        />
                      </div>
                      <div>
                        <label htmlFor="title" className={labelCls}>
                          Title
                        </label>
                        <input
                          id="title"
                          type="text"
                          value={title}
                          onChange={(e) => setTitle(e.target.value)}
                          className={inputCls}
                          placeholder="VP of Sales"
                        />
                      </div>
                    </div>
                    <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                      <div>
                        <label htmlFor="department" className={labelCls}>
                          Department
                        </label>
                        <input
                          id="department"
                          type="text"
                          value={department}
                          onChange={(e) => setDepartment(e.target.value)}
                          className={inputCls}
                          placeholder="Commercial"
                        />
                      </div>
                      <div>
                        <label htmlFor="linkedinUrl" className={labelCls}>
                          LinkedIn URL
                        </label>
                        <input
                          id="linkedinUrl"
                          type="url"
                          value={linkedinUrl}
                          onChange={(e) => setLinkedinUrl(e.target.value)}
                          className={inputCls}
                          placeholder="https://www.linkedin.com/in/..."
                        />
                      </div>
                    </div>
                  </div>
                </section>

                {/* Communication preferences */}
                <section className="bg-white border border-[#E2E0DC] rounded-xl p-6 shadow-sm">
                  <h3 className="font-display text-[1.25rem] text-[#1A1D27] mb-6">
                    Communication Preferences
                  </h3>
                  <div className="space-y-4">
                    <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                      <div>
                        <label htmlFor="preferredName" className={labelCls}>
                          Preferred Name
                        </label>
                        <input
                          id="preferredName"
                          type="text"
                          value={preferredName}
                          onChange={(e) => setPreferredName(e.target.value)}
                          className={inputCls}
                          placeholder="Jane"
                        />
                      </div>
                      <div>
                        <label htmlFor="timezone" className={labelCls}>
                          Timezone
                        </label>
                        <input
                          id="timezone"
                          type="text"
                          value={timezone}
                          onChange={(e) => setTimezone(e.target.value)}
                          className={inputCls}
                          placeholder="America/New_York"
                        />
                      </div>
                    </div>
                    <div>
                      <label htmlFor="notifFrequency" className={labelCls}>
                        Notification Frequency
                      </label>
                      <select
                        id="notifFrequency"
                        value={notifFrequency}
                        onChange={(e) => setNotifFrequency(e.target.value)}
                        className={inputCls}
                      >
                        <option value="realtime">Real-time</option>
                        <option value="hourly">Hourly digest</option>
                        <option value="daily">Daily digest</option>
                        <option value="weekly">Weekly summary</option>
                      </select>
                    </div>
                  </div>
                </section>

                {/* Competitors */}
                <section className="bg-white border border-[#E2E0DC] rounded-xl p-6 shadow-sm">
                  <h3 className="font-display text-[1.25rem] text-[#1A1D27] mb-1">
                    Competitors to Track
                  </h3>
                  <p className="text-[#6B7280] text-[0.8125rem] font-sans mb-4">
                    ARIA will monitor these companies for competitive intelligence.
                  </p>
                  <div className="flex flex-wrap gap-2 mb-3">
                    {competitors.map((comp, i) => (
                      <span key={i} className={tagCls}>
                        {comp}
                        <button
                          onClick={() => removeTag(i, competitors, setCompetitors)}
                          className="text-[#6B7280] hover:text-[#945A5A] transition-colors cursor-pointer"
                          aria-label={`Remove ${comp}`}
                        >
                          <X className="w-3.5 h-3.5" />
                        </button>
                      </span>
                    ))}
                  </div>
                  <div className="flex gap-2">
                    <input
                      type="text"
                      value={competitorInput}
                      onChange={(e) => setCompetitorInput(e.target.value)}
                      onKeyDown={(e) =>
                        handleTagKeyDown(
                          e,
                          competitorInput,
                          competitors,
                          setCompetitors,
                          setCompetitorInput,
                        )
                      }
                      className={inputCls}
                      placeholder="Type a competitor name and press Enter"
                    />
                    <button
                      onClick={() =>
                        addTag(competitorInput, competitors, setCompetitors, setCompetitorInput)
                      }
                      disabled={!competitorInput.trim()}
                      className={`${secondaryBtnCls} shrink-0`}
                    >
                      <Plus className="w-4 h-4" />
                    </button>
                  </div>
                </section>

                {/* Default tone */}
                <section className="bg-white border border-[#E2E0DC] rounded-xl p-6 shadow-sm">
                  <h3 className="font-display text-[1.25rem] text-[#1A1D27] mb-1">
                    Default Tone
                  </h3>
                  <p className="text-[#6B7280] text-[0.8125rem] font-sans mb-4">
                    How ARIA should communicate with you by default.
                  </p>
                  <div className="flex rounded-lg border border-[#E2E0DC] overflow-hidden">
                    {(["formal", "friendly", "urgent"] as const).map((tone) => (
                      <button
                        key={tone}
                        onClick={() => setDefaultTone(tone)}
                        className={`flex-1 py-3 px-4 text-[0.875rem] font-sans font-medium transition-colors duration-150 cursor-pointer ${
                          defaultTone === tone
                            ? "bg-[#5B6E8A] text-white"
                            : "bg-white text-[#6B7280] hover:bg-[#F5F5F0]"
                        }`}
                      >
                        {tone === "formal"
                          ? "More Direct"
                          : tone === "friendly"
                            ? "Balanced"
                            : "More Diplomatic"}
                      </button>
                    ))}
                  </div>
                </section>

                {/* Privacy exclusions */}
                <section className="bg-white border border-[#E2E0DC] rounded-xl p-6 shadow-sm">
                  <h3 className="font-display text-[1.25rem] text-[#1A1D27] mb-1">
                    Privacy Exclusions
                  </h3>
                  <p className="text-[#6B7280] text-[0.8125rem] font-sans mb-4">
                    Domains or senders ARIA should never process from your email.
                  </p>
                  <div className="flex flex-wrap gap-2 mb-3">
                    {privacyExclusions.map((ex, i) => (
                      <span key={i} className={tagCls}>
                        {ex}
                        <button
                          onClick={() =>
                            removeTag(i, privacyExclusions, setPrivacyExclusions)
                          }
                          className="text-[#6B7280] hover:text-[#945A5A] transition-colors cursor-pointer"
                          aria-label={`Remove ${ex}`}
                        >
                          <X className="w-3.5 h-3.5" />
                        </button>
                      </span>
                    ))}
                  </div>
                  <div className="flex gap-2">
                    <input
                      type="text"
                      value={exclusionInput}
                      onChange={(e) => setExclusionInput(e.target.value)}
                      onKeyDown={(e) =>
                        handleTagKeyDown(
                          e,
                          exclusionInput,
                          privacyExclusions,
                          setPrivacyExclusions,
                          setExclusionInput,
                        )
                      }
                      className={inputCls}
                      placeholder="e.g. personal@gmail.com or example.com"
                    />
                    <button
                      onClick={() =>
                        addTag(
                          exclusionInput,
                          privacyExclusions,
                          setPrivacyExclusions,
                          setExclusionInput,
                        )
                      }
                      disabled={!exclusionInput.trim()}
                      className={`${secondaryBtnCls} shrink-0`}
                    >
                      <Plus className="w-4 h-4" />
                    </button>
                  </div>
                </section>

                {/* Save */}
                <div className="flex justify-end">
                  <button
                    onClick={handleSavePersonal}
                    disabled={updateUser.isPending}
                    className={primaryBtnCls}
                  >
                    {updateUser.isPending ? (
                      <Loader2 className="w-4 h-4 animate-spin" />
                    ) : (
                      "Save Changes"
                    )}
                  </button>
                </div>
              </div>
            )}

            {/* ==================== TAB 2: Company ==================== */}
            {activeTab === "company" && (
              <div className="space-y-8">
                <section className="bg-white border border-[#E2E0DC] rounded-xl p-6 shadow-sm">
                  <div className="flex items-center justify-between mb-6">
                    <h3 className="font-display text-[1.25rem] text-[#1A1D27]">
                      Company Information
                    </h3>
                    {!isAdmin && (
                      <span className="inline-flex items-center gap-1.5 px-2.5 py-1 bg-[#F5F5F0] border border-[#E2E0DC] rounded text-[0.6875rem] font-sans font-medium text-[#6B7280]">
                        <Lock className="w-3 h-3" />
                        Admin only
                      </span>
                    )}
                  </div>

                  {/* Classification badge */}
                  {profile?.company?.classification && (
                    <div className="mb-6 flex items-center gap-3 flex-wrap">
                      <span className="inline-flex items-center px-3 py-1.5 bg-[#5B6E8A]/8 border border-[#5B6E8A]/20 rounded-lg text-[0.8125rem] font-mono font-medium text-[#5B6E8A]">
                        {profile.company.classification}
                      </span>
                      {profile.company.last_enriched_at && (
                        <span className="text-[#6B7280] text-[0.75rem] font-sans">
                          Last enriched:{" "}
                          <span className="font-mono text-[#1A1D27]">
                            {formatDate(profile.company.last_enriched_at)}
                          </span>
                        </span>
                      )}
                      <button
                        className={`${secondaryBtnCls} py-1.5 px-3 min-h-[32px] text-[0.75rem]`}
                      >
                        <RefreshCw className="w-3.5 h-3.5 mr-1.5" />
                        Re-research
                      </button>
                    </div>
                  )}

                  <div className="space-y-4">
                    <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                      <div>
                        <label htmlFor="companyName" className={labelCls}>
                          Company Name
                        </label>
                        <input
                          id="companyName"
                          type="text"
                          value={companyName}
                          onChange={(e) => setCompanyName(e.target.value)}
                          className={inputCls}
                          disabled={!isAdmin}
                          placeholder="Acme Biologics"
                        />
                      </div>
                      <div>
                        <label htmlFor="companyWebsite" className={labelCls}>
                          Website
                        </label>
                        <input
                          id="companyWebsite"
                          type="url"
                          value={companyWebsite}
                          onChange={(e) => setCompanyWebsite(e.target.value)}
                          className={inputCls}
                          disabled={!isAdmin}
                          placeholder="https://acme-bio.com"
                        />
                      </div>
                    </div>
                    <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                      <div>
                        <label htmlFor="companyIndustry" className={labelCls}>
                          Industry
                        </label>
                        <input
                          id="companyIndustry"
                          type="text"
                          value={companyIndustry}
                          onChange={(e) => setCompanyIndustry(e.target.value)}
                          className={inputCls}
                          disabled={!isAdmin}
                          placeholder="Life Sciences"
                        />
                      </div>
                      <div>
                        <label htmlFor="companySubVertical" className={labelCls}>
                          Sub-vertical
                        </label>
                        <input
                          id="companySubVertical"
                          type="text"
                          value={companySubVertical}
                          onChange={(e) => setCompanySubVertical(e.target.value)}
                          className={inputCls}
                          disabled={!isAdmin}
                          placeholder="Biologics CDMO"
                        />
                      </div>
                    </div>
                    <div>
                      <label htmlFor="companyDescription" className={labelCls}>
                        Description
                      </label>
                      <textarea
                        id="companyDescription"
                        value={companyDescription}
                        onChange={(e) => setCompanyDescription(e.target.value)}
                        className={`${inputCls} resize-none`}
                        rows={3}
                        disabled={!isAdmin}
                        placeholder="Brief description of the company..."
                      />
                    </div>

                    {/* Key products */}
                    <div>
                      <label className={labelCls}>Key Products / Services</label>
                      <div className="flex flex-wrap gap-2 mb-3">
                        {companyProducts.map((p, i) => (
                          <span key={i} className={tagCls}>
                            {p}
                            {isAdmin && (
                              <button
                                onClick={() =>
                                  removeTag(i, companyProducts, setCompanyProducts)
                                }
                                className="text-[#6B7280] hover:text-[#945A5A] transition-colors cursor-pointer"
                                aria-label={`Remove ${p}`}
                              >
                                <X className="w-3.5 h-3.5" />
                              </button>
                            )}
                          </span>
                        ))}
                      </div>
                      {isAdmin && (
                        <div className="flex gap-2">
                          <input
                            type="text"
                            value={productInput}
                            onChange={(e) => setProductInput(e.target.value)}
                            onKeyDown={(e) =>
                              handleTagKeyDown(
                                e,
                                productInput,
                                companyProducts,
                                setCompanyProducts,
                                setProductInput,
                              )
                            }
                            className={inputCls}
                            placeholder="Type a product/service and press Enter"
                          />
                          <button
                            onClick={() =>
                              addTag(
                                productInput,
                                companyProducts,
                                setCompanyProducts,
                                setProductInput,
                              )
                            }
                            disabled={!productInput.trim()}
                            className={`${secondaryBtnCls} shrink-0`}
                          >
                            <Plus className="w-4 h-4" />
                          </button>
                        </div>
                      )}
                    </div>
                  </div>

                  {isAdmin && (
                    <div className="flex justify-end mt-6">
                      <button
                        onClick={handleSaveCompany}
                        disabled={updateCompany.isPending}
                        className={primaryBtnCls}
                      >
                        {updateCompany.isPending ? (
                          <Loader2 className="w-4 h-4 animate-spin" />
                        ) : (
                          "Save Changes"
                        )}
                      </button>
                    </div>
                  )}
                </section>
              </div>
            )}

            {/* ==================== TAB 3: Documents ==================== */}
            {activeTab === "documents" && (
              <div className="space-y-8">
                {docsLoading ? (
                  <div className="flex justify-center py-16">
                    <Loader2 className="w-6 h-6 text-[#5B6E8A] animate-spin" />
                  </div>
                ) : (
                  <>
                    {/* Company Documents */}
                    <section className="bg-white border border-[#E2E0DC] rounded-xl p-6 shadow-sm">
                      <div className="flex items-center justify-between mb-6">
                        <div className="flex items-center gap-2">
                          <Building2 className="w-5 h-5 text-[#5B6E8A] stroke-[1.5]" />
                          <h3 className="font-display text-[1.25rem] text-[#1A1D27]">
                            Company Documents
                          </h3>
                        </div>
                        <button
                          className={`${secondaryBtnCls} py-2 px-4 min-h-[36px] text-[0.8125rem]`}
                        >
                          <Upload className="w-4 h-4 mr-1.5" />
                          Upload
                        </button>
                      </div>

                      {(documents?.company_documents?.length ?? 0) === 0 ? (
                        <p className="text-[#6B7280] text-[0.875rem] text-center py-8 font-sans">
                          No company documents uploaded yet. Upload pitch decks, data sheets,
                          or competitive materials.
                        </p>
                      ) : (
                        <div className="divide-y divide-[#E2E0DC]">
                          {documents?.company_documents.map((doc) => (
                            <div
                              key={doc.id}
                              className="flex items-center justify-between py-3"
                            >
                              <div className="flex items-center gap-3 min-w-0">
                                <span className="inline-flex items-center justify-center w-9 h-9 bg-[#F5F5F0] border border-[#E2E0DC] rounded-lg text-[0.6875rem] font-mono font-medium text-[#5B6E8A] shrink-0">
                                  {fileTypeIcon(doc.file_type)}
                                </span>
                                <div className="min-w-0">
                                  <p className="text-[#1A1D27] text-[0.875rem] font-sans font-medium truncate">
                                    {doc.name}
                                  </p>
                                  <p className="text-[#6B7280] text-[0.75rem] font-mono">
                                    {formatDate(doc.created_at)} &middot;{" "}
                                    {formatFileSize(doc.file_size)}
                                  </p>
                                </div>
                              </div>
                              <div className="flex items-center gap-3 shrink-0 ml-4">
                                {qualityBadge(doc.quality_score)}
                                {doc.uploaded_by === user?.id && (
                                  <button
                                    className="p-1.5 text-[#6B7280] hover:text-[#945A5A] rounded-lg hover:bg-[#945A5A]/8 transition-colors cursor-pointer"
                                    aria-label={`Delete ${doc.name}`}
                                  >
                                    <Trash2 className="w-4 h-4" />
                                  </button>
                                )}
                              </div>
                            </div>
                          ))}
                        </div>
                      )}
                    </section>

                    {/* User Documents */}
                    <section className="bg-white border border-[#E2E0DC] rounded-xl p-6 shadow-sm">
                      <div className="flex items-center justify-between mb-6">
                        <div className="flex items-center gap-2">
                          <User className="w-5 h-5 text-[#5B6E8A] stroke-[1.5]" />
                          <h3 className="font-display text-[1.25rem] text-[#1A1D27]">
                            My Writing Samples
                          </h3>
                        </div>
                        <button
                          className={`${secondaryBtnCls} py-2 px-4 min-h-[36px] text-[0.8125rem]`}
                        >
                          <Upload className="w-4 h-4 mr-1.5" />
                          Upload
                        </button>
                      </div>

                      {(documents?.user_documents?.length ?? 0) === 0 ? (
                        <p className="text-[#6B7280] text-[0.875rem] text-center py-8 font-sans">
                          No writing samples yet. Upload emails, reports, or presentations so
                          ARIA can learn your voice.
                        </p>
                      ) : (
                        <div className="divide-y divide-[#E2E0DC]">
                          {documents?.user_documents.map((doc) => (
                            <div
                              key={doc.id}
                              className="flex items-center justify-between py-3"
                            >
                              <div className="flex items-center gap-3 min-w-0">
                                <span className="inline-flex items-center justify-center w-9 h-9 bg-[#F5F5F0] border border-[#E2E0DC] rounded-lg text-[0.6875rem] font-mono font-medium text-[#5B6E8A] shrink-0">
                                  {fileTypeIcon(doc.file_type)}
                                </span>
                                <div className="min-w-0">
                                  <p className="text-[#1A1D27] text-[0.875rem] font-sans font-medium truncate">
                                    {doc.name}
                                  </p>
                                  <p className="text-[#6B7280] text-[0.75rem] font-mono">
                                    {formatDate(doc.created_at)} &middot;{" "}
                                    {formatFileSize(doc.file_size)}
                                  </p>
                                </div>
                              </div>
                              <div className="flex items-center gap-3 shrink-0 ml-4">
                                {qualityBadge(doc.quality_score)}
                                <button
                                  className="p-1.5 text-[#6B7280] hover:text-[#945A5A] rounded-lg hover:bg-[#945A5A]/8 transition-colors cursor-pointer"
                                  aria-label={`Delete ${doc.name}`}
                                >
                                  <Trash2 className="w-4 h-4" />
                                </button>
                              </div>
                            </div>
                          ))}
                        </div>
                      )}
                    </section>
                  </>
                )}
              </div>
            )}

            {/* ==================== TAB 4: Integrations ==================== */}
            {activeTab === "integrations" && (
              <div className="space-y-4">
                {[
                  {
                    category: "Email",
                    icon: Mail,
                    description:
                      "Connect your email for ARIA to draft and analyze communications.",
                  },
                  {
                    category: "CRM",
                    icon: Users,
                    description: "Sync contacts, deals, and account data from your CRM.",
                  },
                  {
                    category: "Calendar",
                    icon: Calendar,
                    description: "Let ARIA prepare meeting briefs and track follow-ups.",
                  },
                  {
                    category: "Slack",
                    icon: MessageSquare,
                    description: "Receive ARIA intelligence and notifications in Slack.",
                  },
                ].map((cat) => {
                  const integration = profile?.integrations?.find(
                    (i) => i.category.toLowerCase() === cat.category.toLowerCase(),
                  );
                  const connected = integration?.status === "connected";
                  const Icon = cat.icon;

                  return (
                    <div
                      key={cat.category}
                      className="bg-white border border-[#E2E0DC] rounded-xl p-6 shadow-sm"
                    >
                      <div className="flex items-start justify-between">
                        <div className="flex items-start gap-4">
                          <div className="w-10 h-10 rounded-lg bg-[#F5F5F0] border border-[#E2E0DC] flex items-center justify-center shrink-0">
                            <Icon className="w-5 h-5 text-[#5B6E8A] stroke-[1.5]" />
                          </div>
                          <div>
                            <div className="flex items-center gap-2 mb-0.5">
                              <h3 className="text-[#1A1D27] text-[0.9375rem] font-sans font-medium">
                                {cat.category}
                              </h3>
                              {connected ? (
                                <span className="inline-flex items-center gap-1 px-2 py-0.5 bg-[#5A7D60]/8 border border-[#5A7D60]/20 rounded text-[0.6875rem] font-sans font-medium text-[#5A7D60]">
                                  <span className="w-1.5 h-1.5 bg-[#5A7D60] rounded-full" />
                                  Connected
                                </span>
                              ) : (
                                <span className="inline-flex items-center px-2 py-0.5 bg-[#F5F5F0] border border-[#E2E0DC] rounded text-[0.6875rem] font-sans font-medium text-[#6B7280]">
                                  Disconnected
                                </span>
                              )}
                            </div>
                            {connected && integration?.provider && (
                              <p className="text-[#1A1D27] text-[0.8125rem] font-sans mb-0.5">
                                {integration.provider}
                              </p>
                            )}
                            <p className="text-[#6B7280] text-[0.8125rem] font-sans">
                              {cat.description}
                            </p>
                            {connected && integration?.last_sync_at && (
                              <p className="text-[#6B7280] text-[0.75rem] font-mono mt-1">
                                Last synced: {formatDate(integration.last_sync_at)}
                              </p>
                            )}
                          </div>
                        </div>
                        <div className="flex items-center gap-2 shrink-0 ml-4">
                          {connected ? (
                            <>
                              <Link
                                to="/settings/integrations"
                                className="text-[#5B6E8A] text-[0.8125rem] font-sans font-medium hover:text-[#4A5D79] transition-colors"
                              >
                                Manage
                              </Link>
                              <button className="px-4 py-2 text-[#945A5A] text-[0.8125rem] font-sans font-medium hover:bg-[#945A5A]/8 rounded-lg transition-colors min-h-[36px] cursor-pointer">
                                Disconnect
                              </button>
                            </>
                          ) : (
                            <Link
                              to="/settings/integrations"
                              className={`${primaryBtnCls} py-2 px-4 min-h-[36px] text-[0.8125rem]`}
                            >
                              Connect
                            </Link>
                          )}
                        </div>
                      </div>
                    </div>
                  );
                })}
              </div>
            )}
          </div>
        </div>
      </div>

      {/* Toast notification */}
      {toast && (
        <div className="fixed bottom-6 right-6 z-50">
          <div
            className={`flex items-center gap-3 px-5 py-3 rounded-xl shadow-lg border ${
              toast.type === "success"
                ? "bg-white border-[#5A7D60]/30 text-[#5A7D60]"
                : "bg-white border-[#945A5A]/30 text-[#945A5A]"
            }`}
          >
            {toast.type === "success" ? (
              <Check className="w-4 h-4 shrink-0" />
            ) : (
              <X className="w-4 h-4 shrink-0" />
            )}
            <span className="text-[0.875rem] font-sans font-medium">{toast.message}</span>
          </div>
        </div>
      )}
    </div>
  );
}
