import { useState } from "react";
import { useProfile, useSessions, useUpdateProfile, useChangePassword, useSetup2FA, useVerify2FA, useDisable2FA, useRevokeSession, useDeleteAccount } from "@/hooks/useAccount";
import { Shield, Key, Smartphone, Monitor, AlertTriangle, Camera, Mail, ChevronDown, ChevronUp, Check, X, Loader2 } from "lucide-react";
import { EmailPreferencesSection } from "@/components/settings/EmailPreferencesSection";
import { HelpTooltip } from "@/components/HelpTooltip";

export function SettingsAccountPage() {
  const { data: profile, isLoading: profileLoading } = useProfile();
  const { data: sessions = [], isLoading: sessionsLoading } = useSessions();

  const updateProfile = useUpdateProfile();
  const changePassword = useChangePassword();
  const setup2FA = useSetup2FA();
  const verify2FA = useVerify2FA();
  const disable2FA = useDisable2FA();
  const revokeSession = useRevokeSession();
  const deleteAccount = useDeleteAccount();

  // Profile editing state
  const [isEditingProfile, setIsEditingProfile] = useState(false);
  const [editName, setEditName] = useState(profile?.full_name || "");
  const [editAvatar, setEditAvatar] = useState(profile?.avatar_url || "");

  // Password section state
  const [isPasswordExpanded, setIsPasswordExpanded] = useState(false);
  const [currentPassword, setCurrentPassword] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");

  // 2FA state
  const [is2FAExpanded, setIs2FAExpanded] = useState(false);
  const [twoFactorData, setTwoFactorData] = useState<{ secret: string; qr_code_uri: string } | null>(null);
  const [twoFactorCode, setTwoFactorCode] = useState("");
  const [disable2FAPassword, setDisable2FAPassword] = useState("");

  // Account deletion state
  const [deleteConfirmation, setDeleteConfirmation] = useState("");
  const [deletePassword, setDeletePassword] = useState("");

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

  const handleSaveProfile = async () => {
    try {
      await updateProfile.mutateAsync({
        full_name: editName || undefined,
        avatar_url: editAvatar || undefined,
      });
      setIsEditingProfile(false);
      showSuccess("Profile updated");
    } catch (err: unknown) {
      showError(err instanceof Error ? err.message : "Failed to update profile");
    }
  };

  const handleChangePassword = async () => {
    if (newPassword !== confirmPassword) {
      showError("Passwords do not match");
      return;
    }
    if (newPassword.length < 8) {
      showError("Password must be at least 8 characters");
      return;
    }
    try {
      await changePassword.mutateAsync({
        current_password: currentPassword,
        new_password: newPassword,
      });
      setCurrentPassword("");
      setNewPassword("");
      setConfirmPassword("");
      setIsPasswordExpanded(false);
      showSuccess("Password changed");
    } catch (err: unknown) {
      showError(err instanceof Error ? err.message : "Failed to change password");
    }
  };

  const handleSetup2FA = async () => {
    try {
      const data = await setup2FA.mutateAsync();
      setTwoFactorData(data);
    } catch (err: unknown) {
      showError(err instanceof Error ? err.message : "Failed to setup 2FA");
    }
  };

  const handleVerify2FA = async () => {
    if (!twoFactorData) return;
    try {
      await verify2FA.mutateAsync({
        code: twoFactorCode,
        secret: twoFactorData.secret,
      });
      setTwoFactorData(null);
      setTwoFactorCode("");
      setIs2FAExpanded(false);
      showSuccess("2FA enabled");
    } catch (err: unknown) {
      showError(err instanceof Error ? err.message : "Invalid code");
    }
  };

  const handleDisable2FA = async () => {
    try {
      await disable2FA.mutateAsync({ password: disable2FAPassword });
      setDisable2FAPassword("");
      setIs2FAExpanded(false);
      showSuccess("2FA disabled");
    } catch (err: unknown) {
      showError(err instanceof Error ? err.message : "Failed to disable 2FA");
    }
  };

  const handleRevokeSession = async (sessionId: string) => {
    try {
      await revokeSession.mutateAsync(sessionId);
      showSuccess("Session revoked");
    } catch (err: unknown) {
      showError(err instanceof Error ? err.message : "Failed to revoke session");
    }
  };

  const handleDeleteAccount = async () => {
    if (deleteConfirmation !== "DELETE MY ACCOUNT") {
      showError('Please type "DELETE MY ACCOUNT" exactly');
      return;
    }
    try {
      await deleteAccount.mutateAsync({
        confirmation: deleteConfirmation,
        password: deletePassword,
      });
      // Account deleted, will be redirected by auth
      window.location.href = "/login";
    } catch (err: unknown) {
      showError(err instanceof Error ? err.message : "Failed to delete account");
    }
  };

  const getPasswordStrength = (password: string) => {
    if (password.length === 0) return { label: "", color: "", percent: 0 };
    if (password.length < 8) return { label: "Weak", color: "bg-critical", percent: 25 };
    if (password.length < 12) return { label: "Fair", color: "bg-warning", percent: 50 };
    if (!/[A-Z]/.test(password) || !/[0-9]/.test(password)) {
      return { label: "Good", color: "bg-secondary", percent: 75 };
    }
    return { label: "Strong", color: "bg-success", percent: 100 };
  };

  if (profileLoading) {
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
        <div className="max-w-3xl mx-auto px-6 py-8">
          <div className="flex items-center gap-2">
            <h1 className="font-display text-[2rem] text-content">Account Settings</h1>
            <HelpTooltip content="Manage your profile, security settings, and account preferences." placement="right" />
          </div>
          <p className="text-secondary mt-2">Manage your account and security preferences</p>
        </div>
      </div>

      {/* Messages */}
      {successMessage && (
        <div className="max-w-3xl mx-auto px-6 mt-6">
          <div className="bg-success/10 border border-success/30 rounded-lg px-4 py-3 flex items-center gap-3">
            <Check className="w-5 h-5 text-success" />
            <span className="text-content">{successMessage}</span>
          </div>
        </div>
      )}
      {errorMessage && (
        <div className="max-w-3xl mx-auto px-6 mt-6">
          <div className="bg-critical/10 border border-critical/30 rounded-lg px-4 py-3 flex items-center gap-3">
            <X className="w-5 h-5 text-critical" />
            <span className="text-content">{errorMessage}</span>
          </div>
        </div>
      )}

      <div className="max-w-3xl mx-auto px-6 py-8 space-y-6">
        {/* Profile Section */}
        <div className="bg-elevated border border-border rounded-xl p-6">
          <div className="flex items-center justify-between mb-6">
            <div className="flex items-center gap-3">
              <div className="w-10 h-10 rounded-full bg-subtle flex items-center justify-center">
                {profile?.avatar_url ? (
                  <img src={profile.avatar_url} alt="" className="w-full h-full rounded-full object-cover" />
                ) : (
                  <Camera className="w-5 h-5 text-interactive" />
                )}
              </div>
              <div>
                <h2 className="text-content font-sans text-[1.125rem] font-medium">Profile</h2>
                <p className="text-secondary text-[0.8125rem]">Your personal information</p>
              </div>
            </div>
            {!isEditingProfile && (
              <button
                onClick={() => {
                  setIsEditingProfile(true);
                  setEditName(profile?.full_name || "");
                  setEditAvatar(profile?.avatar_url || "");
                }}
                className="text-interactive text-[0.875rem] hover:text-interactive-hover transition-colors duration-150"
              >
                Edit
              </button>
            )}
          </div>

          {isEditingProfile ? (
            <div className="space-y-4">
              <div>
                <label className="block text-secondary text-[0.8125rem] font-medium mb-1.5">Full Name</label>
                <input
                  type="text"
                  value={editName}
                  onChange={(e) => setEditName(e.target.value)}
                  className="w-full bg-subtle border border-border rounded-lg px-4 py-3 text-content text-[0.9375rem] focus:border-interactive focus:ring-1 focus:ring-interactive outline-none transition-colors duration-150"
                  placeholder="Your full name"
                />
              </div>
              <div>
                <label className="block text-secondary text-[0.8125rem] font-medium mb-1.5">Avatar URL</label>
                <input
                  type="url"
                  value={editAvatar}
                  onChange={(e) => setEditAvatar(e.target.value)}
                  className="w-full bg-subtle border border-border rounded-lg px-4 py-3 text-content text-[0.9375rem] focus:border-interactive focus:ring-1 focus:ring-interactive outline-none transition-colors duration-150"
                  placeholder="https://example.com/avatar.jpg"
                />
              </div>
              <div className="flex gap-3 pt-2">
                <button
                  onClick={handleSaveProfile}
                  disabled={updateProfile.isPending}
                  className="px-5 py-2.5 bg-interactive text-white rounded-lg font-sans text-[0.875rem] font-medium hover:bg-interactive-hover active:bg-interactive-hover transition-colors duration-150 disabled:opacity-50 disabled:cursor-not-allowed min-h-[44px] flex items-center justify-center"
                >
                  {updateProfile.isPending ? (
                    <Loader2 className="w-4 h-4 animate-spin" />
                  ) : (
                    "Save Changes"
                  )}
                </button>
                <button
                  onClick={() => setIsEditingProfile(false)}
                  className="px-5 py-2.5 bg-transparent border border-interactive text-interactive rounded-lg font-sans text-[0.875rem] font-medium hover:bg-interactive/10 transition-colors duration-150 min-h-[44px]"
                >
                  Cancel
                </button>
              </div>
            </div>
          ) : (
            <div className="space-y-3">
              <div className="flex justify-between items-center py-2">
                <span className="text-secondary text-[0.875rem]">Name</span>
                <span className="text-content text-[0.875rem]">{profile?.full_name || "Not set"}</span>
              </div>
              <div className="flex justify-between items-center py-2">
                <span className="text-secondary text-[0.875rem]">Email</span>
                <span className="text-content text-[0.875rem] flex items-center gap-2">
                  <Mail className="w-4 h-4" />
                  {/* Email would come from auth context */}
                  user@example.com
                </span>
              </div>
            </div>
          )}
        </div>

        {/* Password Section */}
        <div className="bg-elevated border border-border rounded-xl overflow-hidden">
          <button
            onClick={() => setIsPasswordExpanded(!isPasswordExpanded)}
            className="w-full px-6 py-5 flex items-center justify-between text-left hover:bg-subtle transition-colors duration-150"
          >
            <div className="flex items-center gap-3">
              <Key className="w-5 h-5 text-interactive" />
              <div>
                <h2 className="text-content font-sans text-[1.125rem] font-medium">Password</h2>
                <p className="text-secondary text-[0.8125rem]">Change your password</p>
              </div>
            </div>
            {isPasswordExpanded ? (
              <ChevronUp className="w-5 h-5 text-interactive" />
            ) : (
              <ChevronDown className="w-5 h-5 text-interactive" />
            )}
          </button>

          {isPasswordExpanded && (
            <div className="px-6 pb-6 pt-2 border-t border-border">
              <div className="space-y-4">
                <div>
                  <label className="block text-secondary text-[0.8125rem] font-medium mb-1.5">Current Password</label>
                  <input
                    type="password"
                    value={currentPassword}
                    onChange={(e) => setCurrentPassword(e.target.value)}
                    className="w-full bg-subtle border border-border rounded-lg px-4 py-3 text-content text-[0.9375rem] focus:border-interactive focus:ring-1 focus:ring-interactive outline-none transition-colors duration-150"
                  />
                </div>
                <div>
                  <label className="block text-secondary text-[0.8125rem] font-medium mb-1.5">New Password</label>
                  <input
                    type="password"
                    value={newPassword}
                    onChange={(e) => setNewPassword(e.target.value)}
                    className="w-full bg-subtle border border-border rounded-lg px-4 py-3 text-content text-[0.9375rem] focus:border-interactive focus:ring-1 focus:ring-interactive outline-none transition-colors duration-150"
                  />
                  {newPassword && (
                    <div className="mt-2">
                      <div className="h-1 bg-border rounded-full overflow-hidden">
                        <div
                          className={`h-full ${getPasswordStrength(newPassword).color} transition-all duration-300`}
                          style={{ width: `${getPasswordStrength(newPassword).percent}%` }}
                        />
                      </div>
                      <p className="text-secondary text-[0.75rem] mt-1">
                        Password strength: <span className="text-content">{getPasswordStrength(newPassword).label}</span>
                      </p>
                    </div>
                  )}
                </div>
                <div>
                  <label className="block text-secondary text-[0.8125rem] font-medium mb-1.5">Confirm New Password</label>
                  <input
                    type="password"
                    value={confirmPassword}
                    onChange={(e) => setConfirmPassword(e.target.value)}
                    className="w-full bg-subtle border border-border rounded-lg px-4 py-3 text-content text-[0.9375rem] focus:border-interactive focus:ring-1 focus:ring-interactive outline-none transition-colors duration-150"
                  />
                  {confirmPassword && newPassword !== confirmPassword && (
                    <p className="text-critical text-[0.75rem] mt-1">Passwords do not match</p>
                  )}
                </div>
                <button
                  onClick={handleChangePassword}
                  disabled={changePassword.isPending || !currentPassword || !newPassword || newPassword !== confirmPassword}
                  className="px-5 py-2.5 bg-interactive text-white rounded-lg font-sans text-[0.875rem] font-medium hover:bg-interactive-hover active:bg-interactive-hover transition-colors duration-150 disabled:opacity-50 disabled:cursor-not-allowed min-h-[44px] flex items-center justify-center"
                >
                  {changePassword.isPending ? (
                    <Loader2 className="w-4 h-4 animate-spin" />
                  ) : (
                    "Update Password"
                  )}
                </button>
              </div>
            </div>
          )}
        </div>

        {/* Two-Factor Authentication */}
        <div className="bg-elevated border border-border rounded-xl overflow-hidden">
          <button
            onClick={() => setIs2FAExpanded(!is2FAExpanded)}
            className="w-full px-6 py-5 flex items-center justify-between text-left hover:bg-subtle transition-colors duration-150"
          >
            <div className="flex items-center gap-3">
              <Shield className="w-5 h-5 text-interactive" />
              <div>
                <div className="flex items-center gap-3">
                  <h2 className="text-content font-sans text-[1.125rem] font-medium">Two-Factor Authentication</h2>
                  {profile?.is_2fa_enabled && (
                    <span className="px-2 py-0.5 bg-success/10 border border-success/30 rounded text-success text-[0.6875rem] font-medium">
                      Enabled
                    </span>
                  )}
                </div>
                <p className="text-secondary text-[0.8125rem]">Add an extra layer of security</p>
              </div>
            </div>
            {is2FAExpanded ? (
              <ChevronUp className="w-5 h-5 text-interactive" />
            ) : (
              <ChevronDown className="w-5 h-5 text-interactive" />
            )}
          </button>

          {is2FAExpanded && (
            <div className="px-6 pb-6 pt-2 border-t border-border">
              {profile?.is_2fa_enabled ? (
                // Disable 2FA
                <div className="space-y-4">
                  <p className="text-secondary text-[0.875rem]">
                    Your account is protected with two-factor authentication using an authenticator app.
                  </p>
                  <div>
                    <label className="block text-secondary text-[0.8125rem] font-medium mb-1.5">
                      Enter your password to disable 2FA
                    </label>
                    <input
                      type="password"
                      value={disable2FAPassword}
                      onChange={(e) => setDisable2FAPassword(e.target.value)}
                      className="w-full bg-subtle border border-border rounded-lg px-4 py-3 text-content text-[0.9375rem] focus:border-interactive focus:ring-1 focus:ring-interactive outline-none transition-colors duration-150"
                      placeholder="Your password"
                    />
                  </div>
                  <button
                    onClick={handleDisable2FA}
                    disabled={disable2FA.isPending || !disable2FAPassword}
                    className="px-5 py-2.5 bg-transparent border border-critical text-critical rounded-lg font-sans text-[0.875rem] font-medium hover:bg-critical/10 transition-colors duration-150 disabled:opacity-50 disabled:cursor-not-allowed min-h-[44px] flex items-center justify-center"
                  >
                    {disable2FA.isPending ? (
                      <Loader2 className="w-4 h-4 animate-spin" />
                    ) : (
                      "Disable 2FA"
                    )}
                  </button>
                </div>
              ) : twoFactorData ? (
                // Verify 2FA
                <div className="space-y-4">
                  <p className="text-secondary text-[0.875rem]">
                    Scan the QR code below with your authenticator app (Google Authenticator, Authy, etc.)
                  </p>
                  <div className="flex justify-center py-4">
                    <img src={twoFactorData.qr_code_uri} alt="QR Code" className="w-48 h-48" />
                  </div>
                  <div>
                    <label className="block text-secondary text-[0.8125rem] font-medium mb-1.5">
                      Or enter this code manually
                    </label>
                    <code className="block bg-subtle border border-border rounded-lg px-4 py-3 text-content font-mono text-[0.8125rem] break-all">
                      {twoFactorData.secret}
                    </code>
                  </div>
                  <div>
                    <label className="block text-secondary text-[0.8125rem] font-medium mb-1.5">
                      Enter the 6-digit code from your app
                    </label>
                    <input
                      type="text"
                      value={twoFactorCode}
                      onChange={(e) => setTwoFactorCode(e.target.value.replace(/\D/g, "").slice(0, 6))}
                      className="w-full bg-subtle border border-border rounded-lg px-4 py-3 text-content text-[0.9375rem] font-mono text-center tracking-widest focus:border-interactive focus:ring-1 focus:ring-interactive outline-none transition-colors duration-150"
                      placeholder="000000"
                      maxLength={6}
                    />
                  </div>
                  <div className="flex gap-3">
                    <button
                      onClick={handleVerify2FA}
                      disabled={verify2FA.isPending || twoFactorCode.length !== 6}
                      className="px-5 py-2.5 bg-interactive text-white rounded-lg font-sans text-[0.875rem] font-medium hover:bg-interactive-hover active:bg-interactive-hover transition-colors duration-150 disabled:opacity-50 disabled:cursor-not-allowed min-h-[44px] flex items-center justify-center"
                    >
                      {verify2FA.isPending ? (
                        <Loader2 className="w-4 h-4 animate-spin" />
                      ) : (
                        "Verify & Enable"
                      )}
                    </button>
                    <button
                      onClick={() => {
                        setTwoFactorData(null);
                        setTwoFactorCode("");
                      }}
                      className="px-5 py-2.5 bg-transparent border border-interactive text-interactive rounded-lg font-sans text-[0.875rem] font-medium hover:bg-interactive/10 transition-colors duration-150 min-h-[44px]"
                    >
                      Cancel
                    </button>
                  </div>
                </div>
              ) : (
                // Setup 2FA
                <div className="space-y-4">
                  <p className="text-secondary text-[0.875rem]">
                    Two-factor authentication adds an extra layer of security to your account.
                  </p>
                  <button
                    onClick={handleSetup2FA}
                    disabled={setup2FA.isPending}
                    className="px-5 py-2.5 bg-interactive text-white rounded-lg font-sans text-[0.875rem] font-medium hover:bg-interactive-hover active:bg-interactive-hover transition-colors duration-150 disabled:opacity-50 disabled:cursor-not-allowed min-h-[44px] flex items-center justify-center gap-2"
                  >
                    {setup2FA.isPending ? (
                      <>
                        <Loader2 className="w-4 h-4 animate-spin" />
                        Setting up...
                      </>
                    ) : (
                      <>
                        <Smartphone className="w-4 h-4" />
                        Enable 2FA
                      </>
                    )}
                  </button>
                </div>
              )}
            </div>
          )}
        </div>

        {/* Active Sessions */}
        <div className="bg-elevated border border-border rounded-xl p-6">
          <div className="flex items-center gap-3 mb-6">
            <Monitor className="w-5 h-5 text-interactive" />
            <div>
              <h2 className="text-content font-sans text-[1.125rem] font-medium">Active Sessions</h2>
              <p className="text-secondary text-[0.8125rem]">Manage your logged-in devices</p>
            </div>
          </div>

          {sessionsLoading ? (
            <div className="flex justify-center py-8">
              <Loader2 className="w-6 h-6 text-interactive animate-spin" />
            </div>
          ) : sessions.length === 0 ? (
            <p className="text-secondary text-[0.875rem] text-center py-4">No active sessions</p>
          ) : (
            <div className="space-y-3">
              {sessions.map((session) => (
                <div
                  key={session.id}
                  className="flex items-center justify-between py-3 px-4 bg-subtle rounded-lg border border-border"
                >
                  <div className="flex items-center gap-3">
                    <Monitor className="w-4 h-4 text-interactive" />
                    <div>
                      <p className="text-content text-[0.875rem] font-medium">
                        {session.device}
                        {session.is_current && (
                          <span className="ml-2 text-success text-[0.75rem]">(Current)</span>
                        )}
                      </p>
                      <p className="text-secondary text-[0.75rem] font-mono">
                        IP: {session.ip_address}
                      </p>
                      {session.last_active && (
                        <p className="text-secondary text-[0.75rem]">
                          Last active: {new Date(session.last_active).toLocaleString()}
                        </p>
                      )}
                    </div>
                  </div>
                  {!session.is_current && (
                    <button
                      onClick={() => handleRevokeSession(session.id)}
                      disabled={revokeSession.isPending}
                      className="px-4 py-2 text-critical text-[0.8125rem] hover:bg-critical/10 rounded-lg transition-colors duration-150 min-h-[36px]"
                    >
                      Revoke
                    </button>
                  )}
                </div>
              ))}
            </div>
          )}
        </div>

        {/* Email Preferences */}
        <EmailPreferencesSection />

        {/* Danger Zone */}
        <div className="bg-elevated border border-critical/30 rounded-xl p-6">
          <div className="flex items-center gap-3 mb-6">
            <AlertTriangle className="w-5 h-5 text-critical" />
            <div>
              <h2 className="text-critical font-sans text-[1.125rem] font-medium">Danger Zone</h2>
              <p className="text-secondary text-[0.8125rem]">Irreversible actions</p>
            </div>
          </div>

          <div className="border-t border-critical/20 pt-6">
            <div className="space-y-4">
              <p className="text-secondary text-[0.875rem]">
                Deleting your account is permanent. All your data will be permanently removed and cannot be recovered.
              </p>
              <div>
                <label className="block text-secondary text-[0.8125rem] font-medium mb-1.5">
                  Type <span className="text-content font-mono">DELETE MY ACCOUNT</span> to confirm
                </label>
                <input
                  type="text"
                  value={deleteConfirmation}
                  onChange={(e) => setDeleteConfirmation(e.target.value)}
                  className="w-full bg-subtle border border-border rounded-lg px-4 py-3 text-content text-[0.9375rem] focus:border-critical focus:ring-1 focus:ring-critical outline-none transition-colors duration-150"
                  placeholder="DELETE MY ACCOUNT"
                />
              </div>
              <div>
                <label className="block text-secondary text-[0.8125rem] font-medium mb-1.5">
                  Enter your password
                </label>
                <input
                  type="password"
                  value={deletePassword}
                  onChange={(e) => setDeletePassword(e.target.value)}
                  className="w-full bg-subtle border border-border rounded-lg px-4 py-3 text-content text-[0.9375rem] focus:border-critical focus:ring-1 focus:ring-critical outline-none transition-colors duration-150"
                  placeholder="Your password"
                />
              </div>
              <button
                onClick={handleDeleteAccount}
                disabled={deleteAccount.isPending || deleteConfirmation !== "DELETE MY ACCOUNT" || !deletePassword}
                className="px-5 py-2.5 bg-transparent border border-critical text-critical rounded-lg font-sans text-[0.875rem] font-medium hover:bg-critical/10 transition-colors duration-150 disabled:opacity-50 disabled:cursor-not-allowed min-h-[44px] flex items-center justify-center"
              >
                {deleteAccount.isPending ? (
                  <>
                    <Loader2 className="w-4 h-4 animate-spin mr-2" />
                    Deleting...
                  </>
                ) : (
                  "Delete Account"
                )}
              </button>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
