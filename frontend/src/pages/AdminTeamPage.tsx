import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import {
  useTeamMembers,
  useTeamInvites,
  useTeamCompany,
  useInviteMember,
  useCancelInvite,
  useResendInvite,
  useChangeMemberRole,
  useDeactivateMember,
  useReactivateMember,
  useUpdateCompany,
} from "@/hooks/useTeam";
import { useProfile } from "@/hooks/useAccount";
import {
  UserPlus,
  Mail,
  Shield,
  Check,
  X,
  Loader2,
  ChevronDown,
  MoreVertical,
  Building2,
  Crown,
} from "lucide-react";
import { HelpTooltip } from "@/components/HelpTooltip";

type Role = "user" | "manager" | "admin";

// Role badge colors
const roleConfig: Record<
  Role,
  { label: string; bg: string; text: string; border: string; icon: typeof Shield }
> = {
  admin: {
    label: "Admin",
    bg: "bg-success/10",
    text: "text-success",
    border: "border-success/30",
    icon: Crown,
  },
  manager: {
    label: "Manager",
    bg: "bg-secondary/10",
    text: "text-secondary",
    border: "border-secondary/30",
    icon: Shield,
  },
  user: {
    label: "User",
    bg: "bg-interactive/10",
    text: "text-interactive",
    border: "border-interactive/30",
    icon: UserPlus,
  },
};

export function AdminTeamPage() {
  const navigate = useNavigate();
  const { data: profile } = useProfile();

  const { data: team = [], isLoading: teamLoading } = useTeamMembers();
  const { data: invites = [] } = useTeamInvites();
  const { data: company } = useTeamCompany();

  const inviteMember = useInviteMember();
  const cancelInvite = useCancelInvite();
  const resendInvite = useResendInvite();
  const changeRole = useChangeMemberRole();
  const deactivateMember = useDeactivateMember();
  const reactivateMember = useReactivateMember();
  const updateCompany = useUpdateCompany();

  // Invite modal state
  const [showInviteModal, setShowInviteModal] = useState(false);
  const [inviteEmail, setInviteEmail] = useState("");
  const [inviteRole, setInviteRole] = useState<Role>("user");

  // Actions dropdown state
  const [activeDropdown, setActiveDropdown] = useState<string | null>(null);

  // Edit company state
  const [isEditingCompany, setIsEditingCompany] = useState(false);
  const [companyName, setCompanyName] = useState(company?.name || "");

  // Messages
  const [successMessage, setSuccessMessage] = useState("");
  const [errorMessage, setErrorMessage] = useState("");

  // Check if user is admin or manager
  const userRole = profile?.role || "user";
  const isAdmin = userRole === "admin";

  // Redirect non-admins/managers using useEffect
  useEffect(() => {
    if (!isAdmin && userRole !== "manager") {
      navigate("/dashboard");
    }
  }, [isAdmin, userRole, navigate]);

  // Don't render if user should be redirected
  if (!isAdmin && userRole !== "manager") {
    return null;
  }

  const showError = (msg: string) => {
    setErrorMessage(msg);
    setTimeout(() => setErrorMessage(""), 5000);
  };

  const showSuccess = (msg: string) => {
    setSuccessMessage(msg);
    setTimeout(() => setSuccessMessage(""), 3000);
  };

  const handleInvite = async () => {
    if (!inviteEmail || !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(inviteEmail)) {
      showError("Please enter a valid email address");
      return;
    }

    try {
      await inviteMember.mutateAsync({ email: inviteEmail, role: inviteRole });
      setShowInviteModal(false);
      setInviteEmail("");
      setInviteRole("user");
      showSuccess("Invite sent successfully");
    } catch (err: unknown) {
      showError(err instanceof Error ? err.message : "Failed to send invite");
    }
  };

  const handleCancelInvite = async (inviteId: string) => {
    try {
      await cancelInvite.mutateAsync(inviteId);
      showSuccess("Invite cancelled");
    } catch (err: unknown) {
      showError(err instanceof Error ? err.message : "Failed to cancel invite");
    }
  };

  const handleResendInvite = async (inviteId: string) => {
    try {
      await resendInvite.mutateAsync(inviteId);
      showSuccess("Invite resent");
    } catch (err: unknown) {
      showError(err instanceof Error ? err.message : "Failed to resend invite");
    }
  };

  const handleChangeRole = async (userId: string, newRole: Role) => {
    try {
      await changeRole.mutateAsync({ userId, data: { role: newRole } });
      setActiveDropdown(null);
      showSuccess("Role updated");
    } catch (err: unknown) {
      showError(err instanceof Error ? err.message : "Failed to change role");
    }
  };

  const handleDeactivate = async (userId: string) => {
    try {
      await deactivateMember.mutateAsync(userId);
      setActiveDropdown(null);
      showSuccess("User deactivated");
    } catch (err: unknown) {
      showError(err instanceof Error ? err.message : "Failed to deactivate user");
    }
  };

  const handleReactivate = async (userId: string) => {
    try {
      await reactivateMember.mutateAsync(userId);
      setActiveDropdown(null);
      showSuccess("User reactivated");
    } catch (err: unknown) {
      showError(err instanceof Error ? err.message : "Failed to reactivate user");
    }
  };

  const handleUpdateCompany = async () => {
    if (!companyName.trim()) {
      showError("Company name cannot be empty");
      return;
    }

    try {
      await updateCompany.mutateAsync({ name: companyName });
      setIsEditingCompany(false);
      showSuccess("Company updated");
    } catch (err: unknown) {
      showError(err instanceof Error ? err.message : "Failed to update company");
    }
  };

  const formatDate = (dateStr: string | null) => {
    if (!dateStr) return "Never";
    return new Date(dateStr).toLocaleDateString();
  };

  const StatusDot = ({ active }: { active: boolean }) => (
    <div className={`w-2 h-2 rounded-full ${active ? "bg-success" : "bg-critical"}`} />
  );

  if (teamLoading) {
    return (
      <div className="min-h-screen bg-primary flex items-center justify-center">
        <Loader2 className="w-8 h-8 text-interactive animate-spin" />
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-primary">
      {/* Header */}
      <div className="border-b border-border">
        <div className="max-w-[960px] mx-auto px-6 py-8">
          <div className="flex items-center gap-2">
            <h1 className="font-display text-[2rem] text-content">Team Management</h1>
            <HelpTooltip content="Invite team members, manage roles, and configure company settings." placement="right" />
          </div>
          <p className="text-secondary mt-2">Manage team members and company settings</p>
        </div>
      </div>

      {/* Messages */}
      {successMessage && (
        <div className="max-w-[960px] mx-auto px-6 mt-6">
          <div className="bg-success/10 border border-success/30 rounded-lg px-4 py-3 flex items-center gap-3">
            <Check className="w-5 h-5 text-success" />
            <span className="text-content">{successMessage}</span>
          </div>
        </div>
      )}
      {errorMessage && (
        <div className="max-w-[960px] mx-auto px-6 mt-6">
          <div className="bg-critical/10 border border-critical/30 rounded-lg px-4 py-3 flex items-center gap-3">
            <X className="w-5 h-5 text-critical" />
            <span className="text-content">{errorMessage}</span>
          </div>
        </div>
      )}

      <div className="max-w-[960px] mx-auto px-6 py-8 space-y-6">
        {/* Company Details */}
        <div className="bg-elevated border border-border rounded-xl p-6">
          <div className="flex items-center justify-between mb-6">
            <div className="flex items-center gap-3">
              <Building2 className="w-5 h-5 text-interactive" />
              <div>
                <h2 className="text-content font-sans text-[1.125rem] font-medium">Company Details</h2>
                <p className="text-secondary text-[0.8125rem]">Your organization information</p>
              </div>
            </div>
            {isAdmin && !isEditingCompany && (
              <button
                onClick={() => {
                  setIsEditingCompany(true);
                  setCompanyName(company?.name || "");
                }}
                className="text-interactive text-[0.875rem] hover:text-interactive-hover transition-colors duration-150"
              >
                Edit
              </button>
            )}
          </div>

          {isEditingCompany ? (
            <div className="flex gap-3">
              <input
                type="text"
                value={companyName}
                onChange={(e) => setCompanyName(e.target.value)}
                className="flex-1 bg-subtle border border-border rounded-lg px-4 py-2.5 text-content text-[0.9375rem] focus:border-interactive focus:ring-1 focus:ring-interactive outline-none transition-colors duration-150"
                placeholder="Company name"
              />
              <button
                onClick={handleUpdateCompany}
                disabled={updateCompany.isPending}
                className="px-4 py-2.5 bg-interactive text-white rounded-lg font-sans text-[0.875rem] font-medium hover:bg-interactive-hover active:bg-interactive-hover transition-colors duration-150 disabled:opacity-50 disabled:cursor-not-allowed min-h-[44px] flex items-center justify-center"
              >
                {updateCompany.isPending ? <Loader2 className="w-4 h-4 animate-spin" /> : "Save"}
              </button>
              <button
                onClick={() => setIsEditingCompany(false)}
                className="px-4 py-2.5 bg-transparent border border-interactive text-interactive rounded-lg font-sans text-[0.875rem] font-medium hover:bg-interactive/10 transition-colors duration-150 min-h-[44px]"
              >
                Cancel
              </button>
            </div>
          ) : (
            <div className="space-y-3">
              <div className="flex justify-between items-center py-2">
                <span className="text-secondary text-[0.875rem]">Company Name</span>
                <span className="text-content text-[0.875rem]">{company?.name || "Not set"}</span>
              </div>
              {company?.domain && (
                <div className="flex justify-between items-center py-2">
                  <span className="text-secondary text-[0.875rem]">Domain</span>
                  <span className="text-content text-[0.875rem] font-mono">{company.domain}</span>
                </div>
              )}
            </div>
          )}
        </div>

        {/* Invite Button */}
        {isAdmin && (
          <div className="flex justify-end">
            <button
              onClick={() => setShowInviteModal(true)}
              className="px-5 py-2.5 bg-interactive text-white rounded-lg font-sans text-[0.875rem] font-medium hover:bg-interactive-hover active:bg-interactive-hover transition-colors duration-150 min-h-[44px] flex items-center gap-2"
            >
              <UserPlus className="w-4 h-4" />
              Invite Member
            </button>
          </div>
        )}

        {/* Team Table */}
        <div className="bg-elevated border border-border rounded-xl overflow-hidden">
          <div className="px-6 py-4 border-b border-border">
            <h3 className="text-content font-sans text-[1rem] font-medium">Team Members</h3>
            <p className="text-secondary text-[0.8125rem] mt-1">
              {team.length} {team.length === 1 ? "member" : "members"}
            </p>
          </div>

          <div className="overflow-x-auto">
            <table className="w-full">
              <thead>
                <tr className="border-b border-border">
                  <th className="text-left px-6 py-3 text-secondary text-[0.75rem] font-medium uppercase tracking-wider">
                    Name
                  </th>
                  <th className="text-left px-6 py-3 text-secondary text-[0.75rem] font-medium uppercase tracking-wider">
                    Email
                  </th>
                  <th className="text-left px-6 py-3 text-secondary text-[0.75rem] font-medium uppercase tracking-wider">
                    Role
                  </th>
                  <th className="text-left px-6 py-3 text-secondary text-[0.75rem] font-medium uppercase tracking-wider">
                    Status
                  </th>
                  <th className="text-left px-6 py-3 text-secondary text-[0.75rem] font-medium uppercase tracking-wider">
                    Last Active
                  </th>
                  {isAdmin && (
                    <th className="text-right px-6 py-3 text-secondary text-[0.75rem] font-medium uppercase tracking-wider">
                      Actions
                    </th>
                  )}
                </tr>
              </thead>
              <tbody>
                {team.map((member) => {
                  const RoleIcon = roleConfig[member.role as Role].icon;
                  return (
                    <tr key={member.id} className="border-b border-border last:border-0 hover:bg-subtle transition-colors duration-150">
                      <td className="px-6 py-4">
                        <div className="flex items-center gap-3">
                          <div className="w-8 h-8 rounded-full bg-subtle flex items-center justify-center">
                            <span className="text-interactive text-[0.8125rem] font-medium">
                              {member.full_name?.charAt(0).toUpperCase() ||
                                member.email.charAt(0).toUpperCase()}
                            </span>
                          </div>
                          <span className="text-content text-[0.875rem]">{member.full_name || "Unnamed User"}</span>
                        </div>
                      </td>
                      <td className="px-6 py-4">
                        <span className="text-secondary text-[0.8125rem]">{member.email}</span>
                      </td>
                      <td className="px-6 py-4">
                        <span
                          className={`inline-flex items-center gap-1.5 px-2 py-1 rounded-md border ${
                            roleConfig[member.role as Role].bg
                          } ${roleConfig[member.role as Role].text} ${
                            roleConfig[member.role as Role].border
                          }`}
                        >
                          <RoleIcon className="w-3 h-3" />
                          <span className="text-[0.6875rem] font-medium">
                            {roleConfig[member.role as Role].label}
                          </span>
                        </span>
                      </td>
                      <td className="px-6 py-4">
                        <div className="flex items-center gap-2">
                          <StatusDot active={member.is_active} />
                          <span className="text-secondary text-[0.8125rem]">{member.is_active ? "Active" : "Inactive"}</span>
                        </div>
                      </td>
                      <td className="px-6 py-4">
                        <span className="text-secondary text-[0.8125rem] font-mono">{formatDate(member.last_active)}</span>
                      </td>
                      {isAdmin && (
                        <td className="px-6 py-4">
                          <div className="relative">
                            <button
                              onClick={() =>
                                setActiveDropdown(activeDropdown === member.id ? null : member.id)
                              }
                              className="p-2 hover:bg-subtle rounded-lg transition-colors duration-150"
                            >
                              <MoreVertical className="w-4 h-4 text-interactive" />
                            </button>
                            {activeDropdown === member.id && (
                              <>
                                <div className="fixed inset-0 z-10" onClick={() => setActiveDropdown(null)} />
                                <div className="absolute right-0 top-full mt-2 w-48 bg-elevated border border-border rounded-lg shadow-lg z-20 py-1">
                                  <button
                                    onClick={() => handleChangeRole(member.id, "admin")}
                                    className="w-full px-4 py-2 text-left text-[0.8125rem] hover:bg-subtle transition-colors duration-150 text-content"
                                  >
                                    Make Admin
                                  </button>
                                  <button
                                    onClick={() => handleChangeRole(member.id, "manager")}
                                    className="w-full px-4 py-2 text-left text-[0.8125rem] hover:bg-subtle transition-colors duration-150 text-content"
                                  >
                                    Make Manager
                                  </button>
                                  <button
                                    onClick={() => handleChangeRole(member.id, "user")}
                                    className="w-full px-4 py-2 text-left text-[0.8125rem] hover:bg-subtle transition-colors duration-150 text-content"
                                  >
                                    Make User
                                  </button>
                                  <div className="border-t border-border my-1" />
                                  {member.is_active ? (
                                    <button
                                      onClick={() => handleDeactivate(member.id)}
                                      className="w-full px-4 py-2 text-left text-[0.8125rem] hover:bg-critical/10 transition-colors duration-150 text-critical"
                                    >
                                      Deactivate
                                    </button>
                                  ) : (
                                    <button
                                      onClick={() => handleReactivate(member.id)}
                                      className="w-full px-4 py-2 text-left text-[0.8125rem] hover:bg-success/10 transition-colors duration-150 text-success"
                                    >
                                      Reactivate
                                    </button>
                                  )}
                                </div>
                              </>
                            )}
                          </div>
                        </td>
                      )}
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </div>

        {/* Pending Invites */}
        {isAdmin && invites.length > 0 && (
          <div className="bg-elevated border border-border rounded-xl p-6">
            <div className="flex items-center gap-3 mb-6">
              <Mail className="w-5 h-5 text-interactive" />
              <div>
                <h3 className="text-content font-sans text-[1rem] font-medium">Pending Invites</h3>
                <p className="text-secondary text-[0.8125rem] mt-1">
                  {invites.length} {invites.length === 1 ? "invite" : "invites"} awaiting response
                </p>
              </div>
            </div>

            <div className="space-y-3">
              {invites.map((invite) => {
                const RoleIcon = roleConfig[invite.role].icon;
                return (
                  <div key={invite.id} className="flex items-center justify-between py-3 px-4 bg-subtle rounded-lg border border-border">
                    <div className="flex items-center gap-3">
                      <Mail className="w-4 h-4 text-interactive" />
                      <div>
                        <p className="text-content text-[0.875rem]">{invite.email}</p>
                        <div className="flex items-center gap-2 mt-1">
                          <span
                            className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-md border ${
                              roleConfig[invite.role].bg
                            } ${roleConfig[invite.role].text} ${roleConfig[invite.role].border}`}
                          >
                            <RoleIcon className="w-3 h-3" />
                            <span className="text-[0.6875rem]">{roleConfig[invite.role].label}</span>
                          </span>
                          <span className="text-secondary text-[0.75rem]">Sent {formatDate(invite.created_at)}</span>
                        </div>
                      </div>
                    </div>
                    <div className="flex items-center gap-2">
                      <button
                        onClick={() => handleResendInvite(invite.id)}
                        disabled={resendInvite.isPending}
                        className="px-3 py-1.5 text-interactive text-[0.8125rem] hover:bg-subtle rounded-lg transition-colors duration-150 min-h-[32px]"
                      >
                        Resend
                      </button>
                      <button
                        onClick={() => handleCancelInvite(invite.id)}
                        disabled={cancelInvite.isPending}
                        className="px-3 py-1.5 text-critical text-[0.8125rem] hover:bg-critical/10 rounded-lg transition-colors duration-150 min-h-[32px]"
                      >
                        Cancel
                      </button>
                    </div>
                  </div>
                );
              })}
            </div>
          </div>
        )}
      </div>

      {/* Invite Modal */}
      {showInviteModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center">
          <div className="absolute inset-0 bg-black/50" onClick={() => setShowInviteModal(false)} />
          <div className="relative bg-elevated border border-border rounded-xl p-6 w-full max-w-md mx-4 shadow-xl">
            <h3 className="font-display text-[1.5rem] text-content mb-2">Invite Team Member</h3>
            <p className="text-secondary text-[0.875rem] mb-6">Send an invitation to join your team</p>

            <div className="space-y-4">
              <div>
                <label className="block text-secondary text-[0.8125rem] font-medium mb-1.5">Email Address</label>
                <input
                  type="email"
                  value={inviteEmail}
                  onChange={(e) => setInviteEmail(e.target.value)}
                  className="w-full bg-subtle border border-border rounded-lg px-4 py-3 text-content text-[0.9375rem] focus:border-interactive focus:ring-1 focus:ring-interactive outline-none transition-colors duration-150"
                  placeholder="colleague@company.com"
                />
              </div>

              <div>
                <label className="block text-secondary text-[0.8125rem] font-medium mb-1.5">Role</label>
                <div className="relative">
                  <select
                    value={inviteRole}
                    onChange={(e) => setInviteRole(e.target.value as Role)}
                    className="w-full bg-subtle border border-border rounded-lg px-4 py-3 text-content text-[0.9375rem] focus:border-interactive focus:ring-1 focus:ring-interactive outline-none transition-colors duration-150 appearance-none cursor-pointer"
                  >
                    <option value="user">User - Personal + shared access</option>
                    <option value="manager">Manager - Team access, no billing</option>
                    <option value="admin">Admin - Full access</option>
                  </select>
                  <ChevronDown className="absolute right-4 top-1/2 -translate-y-1/2 w-4 h-4 text-interactive pointer-events-none" />
                </div>
              </div>

              <div className="flex gap-3 pt-2">
                <button
                  onClick={handleInvite}
                  disabled={inviteMember.isPending || !inviteEmail}
                  className="flex-1 px-5 py-2.5 bg-interactive text-white rounded-lg font-sans text-[0.875rem] font-medium hover:bg-interactive-hover active:bg-interactive-hover transition-colors duration-150 disabled:opacity-50 disabled:cursor-not-allowed min-h-[44px] flex items-center justify-center gap-2"
                >
                  {inviteMember.isPending ? (
                    <>
                      <Loader2 className="w-4 h-4 animate-spin" />
                      Sending...
                    </>
                  ) : (
                    <>
                      <Mail className="w-4 h-4" />
                      Send Invite
                    </>
                  )}
                </button>
                <button
                  onClick={() => {
                    setShowInviteModal(false);
                    setInviteEmail("");
                    setInviteRole("user");
                  }}
                  className="px-5 py-2.5 bg-transparent border border-interactive text-interactive rounded-lg font-sans text-[0.875rem] font-medium hover:bg-interactive/10 transition-colors duration-150 min-h-[44px]"
                >
                  Cancel
                </button>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
