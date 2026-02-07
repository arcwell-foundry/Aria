import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import {
  useBillingStatus,
  useInvoices,
  useCheckoutSession,
  usePortalSession,
} from "@/hooks/useBilling";
import { useProfile } from "@/hooks/useAccount";
import {
  CreditCard,
  Calendar,
  Download,
  AlertCircle,
  Loader2,
  Users,
  BarChart3,
} from "lucide-react";

type SubscriptionStatus = "trial" | "active" | "past_due" | "canceled" | "incomplete";

// Status badge configuration
const statusConfig: Record<
  SubscriptionStatus,
  { label: string; bg: string; text: string; border: string }
> = {
  trial: {
    label: "Trial",
    bg: "bg-[#7B8EAA]/10",
    text: "text-[#7B8EAA]",
    border: "border-[#7B8EAA]/30",
  },
  active: {
    label: "Active",
    bg: "bg-[#6B8F71]/10",
    text: "text-[#6B8F71]",
    border: "border-[#6B8F71]/30",
  },
  past_due: {
    label: "Payment Required",
    bg: "bg-[#A66B6B]/10",
    text: "text-[#A66B6B]",
    border: "border-[#A66B6B]/30",
  },
  canceled: {
    label: "Canceled",
    bg: "bg-[#8B92A5]/10",
    text: "text-[#8B92A5]",
    border: "border-[#8B92A5]/30",
  },
  incomplete: {
    label: "Incomplete",
    bg: "bg-[#B8956A]/10",
    text: "text-[#B8956A]",
    border: "border-[#B8956A]/30",
  },
};

// Format currency
function formatCurrency(amount: number, currency: string = "usd"): string {
  return new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: currency.toUpperCase(),
    minimumFractionDigits: 2,
  }).format(amount);
}

// Format date
function formatDate(dateString: string | null): string {
  if (!dateString) return "N/A";
  return new Date(dateString).toLocaleDateString("en-US", {
    year: "numeric",
    month: "long",
    day: "numeric",
  });
}

export function AdminBillingPage() {
  const navigate = useNavigate();
  const { data: profile } = useProfile();

  const { data: billing } = useBillingStatus();
  const { data: invoices = [], isLoading: invoicesLoading } = useInvoices();
  const checkoutSession = useCheckoutSession();
  const portalSession = usePortalSession();

  const [isRedirecting, setIsRedirecting] = useState(false);
  const [successMessage] = useState("");
  const [errorMessage, setErrorMessage] = useState("");

  // Check if user is admin
  const userRole = profile?.role || "user";
  const isAdmin = userRole === "admin";

  // Redirect non-admins
  useEffect(() => {
    if (!isAdmin) {
      navigate("/dashboard");
    }
  }, [isAdmin, navigate]);

  // Handle checkout/portal redirect
  const handleManageSubscription = async () => {
    setIsRedirecting(true);
    setErrorMessage("");

    try {
      const result = await portalSession.mutateAsync({});
      window.location.href = result.url;
    } catch {
      setErrorMessage("Failed to open billing portal. Please try again.");
      setIsRedirecting(false);
    }
  };

  const handleStartSubscription = async () => {
    setIsRedirecting(true);
    setErrorMessage("");

    try {
      const result = await checkoutSession.mutateAsync({});
      window.location.href = result.url;
    } catch {
      setErrorMessage("Failed to open checkout. Please try again.");
      setIsRedirecting(false);
    }
  };

  const handleUpdatePayment = async () => {
    setIsRedirecting(true);
    setErrorMessage("");

    try {
      const result = await portalSession.mutateAsync({});
      window.location.href = result.url;
    } catch {
      setErrorMessage("Failed to open payment portal. Please try again.");
      setIsRedirecting(false);
    }
  };

  if (!isAdmin) {
    return null;
  }

  const status = billing?.status || "trial";
  const statusInfo = statusConfig[status];
  const needsSubscription = status === "trial";
  const hasPaymentIssue = status === "past_due";

  // Mock usage data - in production, fetch from actual usage endpoints
  const usageData = {
    apiCalls: { used: 12450, limit: 100000, percentage: 12 },
    storage: { used: 2.4, limit: 100, percentage: 2, unit: "GB" },
    seats: { used: billing?.seats_used || 1, limit: 10, percentage: 10 },
  };

  return (
    <div className="min-h-screen bg-[#0F1117] text-[#E8E6E1]">
      <div className="max-w-5xl mx-auto px-6 py-12">
        {/* Header */}
        <div className="mb-8">
          <h1 className="font-display text-[2rem] leading-[1.2] mb-2">
            Billing & Subscription
          </h1>
          <p className="text-[#8B92A5] text-[0.9375rem]">
            Manage your ARIA subscription and billing information
          </p>
        </div>

        {/* Payment Issue Banner */}
        {hasPaymentIssue && (
          <div className="mb-6 bg-[#A66B6B]/10 border border-[#A66B6B]/30 rounded-xl p-4 flex items-center gap-3">
            <AlertCircle className="w-5 h-5 text-[#A66B6B] flex-shrink-0" />
            <div className="flex-1">
              <p className="text-[#E8E6E1] text-[0.9375rem]">
                Payment required. Please update your payment method to continue
                using ARIA.
              </p>
            </div>
            <button
              onClick={handleUpdatePayment}
              disabled={isRedirecting}
              className="px-4 py-2 bg-[#A66B6B] text-white rounded-lg text-[0.875rem] font-medium hover:bg-[#8B5A5A] transition-colors duration-150 disabled:opacity-50 disabled:cursor-not-allowed cursor-pointer"
            >
              {isRedirecting ? (
                <span className="flex items-center gap-2">
                  <Loader2 className="w-4 h-4 animate-spin" />
                  Loading...
                </span>
              ) : (
                "Update Payment"
              )}
            </button>
          </div>
        )}

        {/* Messages */}
        {successMessage && (
          <div className="mb-6 bg-[#6B8F71]/10 border border-[#6B8F71]/30 rounded-xl p-4 text-[#6B8F71] text-[0.9375rem]">
            {successMessage}
          </div>
        )}
        {errorMessage && (
          <div className="mb-6 bg-[#A66B6B]/10 border border-[#A66B6B]/30 rounded-xl p-4 text-[#A66B6B] text-[0.9375rem]">
            {errorMessage}
          </div>
        )}

        {/* Subscription Card */}
        <div className="bg-[#161B2E] border border-[#2A2F42] rounded-xl p-6 mb-6">
          <div className="flex items-start justify-between mb-6">
            <div>
              <h2 className="font-display text-[1.5rem] leading-[1.3] mb-2">
                ARIA Annual
              </h2>
              <div className="flex items-center gap-2">
                <span
                  className={`px-3 py-1 rounded-full text-[0.6875rem] font-medium border ${statusInfo.bg} ${statusInfo.text} ${statusInfo.border}`}
                >
                  {statusInfo.label}
                </span>
                <span className="text-[#8B92A5] text-[0.8125rem]">
                  ${'200,000'}/year
                </span>
              </div>
            </div>
            {needsSubscription ? (
              <button
                onClick={handleStartSubscription}
                disabled={isRedirecting}
                className="px-5 py-2.5 bg-[#5B6E8A] text-white rounded-lg text-[0.9375rem] font-medium hover:bg-[#4A5D79] transition-colors duration-150 disabled:opacity-50 disabled:cursor-not-allowed cursor-pointer"
              >
                {isRedirecting ? (
                  <span className="flex items-center gap-2">
                    <Loader2 className="w-4 h-4 animate-spin" />
                    Loading...
                  </span>
                ) : (
                  "Start Subscription"
                )}
              </button>
            ) : (
              <button
                onClick={handleManageSubscription}
                disabled={isRedirecting}
                className="px-5 py-2.5 bg-[#5B6E8A] text-white rounded-lg text-[0.9375rem] font-medium hover:bg-[#4A5D79] transition-colors duration-150 disabled:opacity-50 disabled:cursor-not-allowed cursor-pointer"
              >
                {isRedirecting ? (
                  <span className="flex items-center gap-2">
                    <Loader2 className="w-4 h-4 animate-spin" />
                    Loading...
                  </span>
                ) : (
                  "Manage Subscription"
                )}
              </button>
            )}
          </div>

          {/* Subscription Details */}
          <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
            <div>
              <div className="flex items-center gap-2 text-[#8B92A5] text-[0.8125rem] mb-1">
                <Users className="w-4 h-4" />
                Seats Used
              </div>
              <div className="font-mono text-[0.8125rem] text-[#E8E6E1]">
                {billing?.seats_used || 1} / 10
              </div>
            </div>
            <div>
              <div className="flex items-center gap-2 text-[#8B92A5] text-[0.8125rem] mb-1">
                <Calendar className="w-4 h-4" />
                Next Billing Date
              </div>
              <div className="text-[0.8125rem] text-[#E8E6E1]">
                {billing?.current_period_end
                  ? formatDate(billing.current_period_end)
                  : "N/A"}
              </div>
            </div>
            <div>
              <div className="flex items-center gap-2 text-[#8B92A5] text-[0.8125rem] mb-1">
                <CreditCard className="w-4 h-4" />
                Auto-Renew
              </div>
              <div className="text-[0.8125rem] text-[#E8E6E1]">
                {billing?.cancel_at_period_end ? "Off" : "On"}
              </div>
            </div>
          </div>
        </div>

        {/* Usage Summary */}
        <div className="bg-[#161B2E] border border-[#2A2F42] rounded-xl p-6 mb-6">
          <div className="flex items-center gap-2 mb-6">
            <BarChart3 className="w-5 h-5 text-[#7B8EAA]" />
            <h3 className="text-[1.125rem] font-medium text-[#E8E6E1]">
              Usage Summary
            </h3>
          </div>

          <div className="space-y-4">
            {/* API Calls */}
            <div>
              <div className="flex justify-between items-center mb-2">
                <span className="text-[0.875rem] text-[#8B92A5]">API Calls</span>
                <span className="font-mono text-[0.8125rem] text-[#E8E6E1]">
                  {usageData.apiCalls.used.toLocaleString()} /{" "}
                  {usageData.apiCalls.limit.toLocaleString()}
                </span>
              </div>
              <div className="h-2 bg-[#0F1117] rounded-full overflow-hidden">
                <div
                  className="h-full bg-[#5B6E8A] rounded-full transition-all duration-300"
                  style={{ width: `${usageData.apiCalls.percentage}%` }}
                />
              </div>
            </div>

            {/* Storage */}
            <div>
              <div className="flex justify-between items-center mb-2">
                <span className="text-[0.875rem] text-[#8B92A5]">Storage</span>
                <span className="font-mono text-[0.8125rem] text-[#E8E6E1]">
                  {usageData.storage.used} / {usageData.storage.limit}{" "}
                  {usageData.storage.unit}
                </span>
              </div>
              <div className="h-2 bg-[#0F1117] rounded-full overflow-hidden">
                <div
                  className="h-full bg-[#5B6E8A] rounded-full transition-all duration-300"
                  style={{ width: `${usageData.storage.percentage}%` }}
                />
              </div>
            </div>

            {/* Seats */}
            <div>
              <div className="flex justify-between items-center mb-2">
                <span className="text-[0.875rem] text-[#8B92A5]">Seats</span>
                <span className="font-mono text-[0.8125rem] text-[#E8E6E1]">
                  {usageData.seats.used} / {usageData.seats.limit}
                </span>
              </div>
              <div className="h-2 bg-[#0F1117] rounded-full overflow-hidden">
                <div
                  className="h-full bg-[#5B6E8A] rounded-full transition-all duration-300"
                  style={{ width: `${usageData.seats.percentage}%` }}
                />
              </div>
            </div>
          </div>
        </div>

        {/* Invoice History */}
        <div className="bg-[#161B2E] border border-[#2A2F42] rounded-xl p-6">
          <h3 className="text-[1.125rem] font-medium text-[#E8E6E1] mb-6">
            Invoice History
          </h3>

          {invoicesLoading ? (
            <div className="flex items-center justify-center py-12">
              <Loader2 className="w-6 h-6 text-[#7B8EAA] animate-spin" />
            </div>
          ) : invoices.length === 0 ? (
            <div className="text-center py-12">
              <CreditCard className="w-12 h-12 text-[#2A2F42] mx-auto mb-3" />
              <p className="text-[#8B92A5] text-[0.9375rem]">No invoices yet</p>
            </div>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full">
                <thead>
                  <tr className="border-b border-[#2A2F42]">
                    <th className="text-left py-3 px-4 text-[0.8125rem] font-medium text-[#8B92A5]">
                      Date
                    </th>
                    <th className="text-right py-3 px-4 text-[0.8125rem] font-medium text-[#8B92A5]">
                      Amount
                    </th>
                    <th className="text-center py-3 px-4 text-[0.8125rem] font-medium text-[#8B92A5]">
                      Status
                    </th>
                    <th className="text-right py-3 px-4 text-[0.8125rem] font-medium text-[#8B92A5]">
                      Download
                    </th>
                  </tr>
                </thead>
                <tbody>
                  {invoices.map((invoice) => {
                    const invoiceStatus = invoice.status === "paid"
                      ? { label: "Paid", color: "text-[#6B8F71]" }
                      : { label: invoice.status, color: "text-[#8B92A5]" };

                    return (
                      <tr
                        key={invoice.id}
                        className="border-b border-[#2A2F42] last:border-0 hover:bg-[#1E2235] transition-colors"
                      >
                        <td className="py-3 px-4 text-[0.875rem] text-[#E8E6E1]">
                          {formatDate(invoice.date)}
                        </td>
                        <td className="py-3 px-4 text-right font-mono text-[0.8125rem] text-[#E8E6E1]">
                          {formatCurrency(invoice.amount, invoice.currency)}
                        </td>
                        <td className="py-3 px-4 text-center">
                          <span
                            className={`text-[0.8125rem] ${invoiceStatus.color}`}
                          >
                            {invoiceStatus.label}
                          </span>
                        </td>
                        <td className="py-3 px-4 text-right">
                          {invoice.pdf_url ? (
                            <a
                              href={invoice.pdf_url}
                              target="_blank"
                              rel="noopener noreferrer"
                              className="inline-flex items-center gap-1 text-[#7B8EAA] hover:text-[#95A5BD] transition-colors text-[0.8125rem] cursor-pointer"
                            >
                              <Download className="w-3.5 h-3.5" />
                              PDF
                            </a>
                          ) : (
                            <span className="text-[#2A2F42] text-[0.8125rem]">
                              N/A
                            </span>
                          )}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}
        </div>

        {/* Help Text */}
        <div className="mt-6 text-center">
          <p className="text-[#8B92A5] text-[0.8125rem]">
            Questions about billing?{" "}
            <a
              href="mailto:support@aria.ai"
              className="text-[#7B8EAA] hover:text-[#95A5BD] transition-colors cursor-pointer"
            >
              Contact support
            </a>
          </p>
        </div>
      </div>
    </div>
  );
}
