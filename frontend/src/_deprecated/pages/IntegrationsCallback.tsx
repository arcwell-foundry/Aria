import { useEffect, useState, useRef } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { motion } from "framer-motion";
import { recordIntegrationConnection } from "@/api/onboarding";

/** Map Composio app names to the integration_type values our backend expects. */
const APP_NAME_TO_TYPE: Record<string, string> = {
  SALESFORCE: "salesforce",
  HUBSPOT: "hubspot",
  GOOGLECALENDAR: "googlecalendar",
  OUTLOOK365CALENDAR: "outlook",
  SLACK: "slack",
  // Email-step values (already lowercase)
  gmail: "gmail",
  outlook: "outlook",
  salesforce: "salesforce",
  hubspot: "hubspot",
  slack: "slack",
  googlecalendar: "googlecalendar",
};

function cleanupSessionStorage() {
  sessionStorage.removeItem("pending_integration");
  sessionStorage.removeItem("pending_connection_id");
  sessionStorage.removeItem("pending_integration_origin");
}

export function IntegrationsCallbackPage() {
  const [searchParams] = useSearchParams();
  const navigate = useNavigate();
  const [status, setStatus] = useState<"loading" | "success" | "error">("loading");
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const hasRun = useRef(false);

  // Determine where to redirect on completion/error
  const redirectTo = searchParams.get("redirect_to");
  const origin = sessionStorage.getItem("pending_integration_origin");
  const isFromOnboarding = redirectTo === "onboarding" || origin === "onboarding";

  useEffect(() => {
    // Prevent double-run in React strict mode
    if (hasRun.current) return;
    hasRun.current = true;

    const handleCallback = async () => {
      const error = searchParams.get("error");

      // Read context stored before the OAuth redirect
      const pendingIntegration = sessionStorage.getItem("pending_integration");
      const pendingConnectionId = sessionStorage.getItem("pending_connection_id");

      if (error) {
        setStatus("error");
        setErrorMessage(
          error === "access_denied"
            ? "Access was denied. Please try again."
            : "An error occurred during authentication."
        );
        cleanupSessionStorage();
        return;
      }

      if (!pendingIntegration || !pendingConnectionId) {
        setStatus("error");
        setErrorMessage(
          "Missing connection context. Please try connecting again from the integrations page."
        );
        cleanupSessionStorage();
        return;
      }

      // Resolve integration_type from the stored app name
      const integrationType = APP_NAME_TO_TYPE[pendingIntegration] ?? pendingIntegration.toLowerCase();

      try {
        await recordIntegrationConnection({
          integration_type: integrationType,
          connection_id: pendingConnectionId,
        });

        setStatus("success");
        cleanupSessionStorage();

        // Redirect after brief success message
        const destination = isFromOnboarding ? "/onboarding" : "/settings/integrations";
        setTimeout(() => {
          navigate(destination, { replace: true });
        }, 1500);
      } catch (err) {
        setStatus("error");
        setErrorMessage(
          err instanceof Error ? err.message : "Failed to record integration connection."
        );
        cleanupSessionStorage();
      }
    };

    handleCallback();
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  const handleBack = () => {
    navigate(isFromOnboarding ? "/onboarding" : "/settings/integrations", { replace: true });
  };

  return (
    <div className="min-h-screen bg-slate-900 flex items-center justify-center">
      <div className="max-w-md w-full mx-auto px-4">
        <motion.div
          initial={{ opacity: 0, scale: 0.95 }}
          animate={{ opacity: 1, scale: 1 }}
          transition={{ duration: 0.3 }}
          className="bg-slate-800/50 backdrop-blur-sm border border-slate-700/50 rounded-2xl p-8 text-center"
        >
          {status === "loading" && (
            <>
              <motion.div
                animate={{ rotate: 360 }}
                transition={{ duration: 1, repeat: Infinity, ease: "linear" }}
                className="w-16 h-16 border-4 border-primary-500 border-t-transparent rounded-full mx-auto mb-4"
              />
              <h2 className="text-xl font-semibold text-white mb-2">
                Connecting...
              </h2>
              <p className="text-slate-400">
                Please wait while we connect your integration.
              </p>
            </>
          )}

          {status === "success" && (
            <>
              <motion.div
                initial={{ scale: 0 }}
                animate={{ scale: 1 }}
                transition={{ type: "spring", duration: 0.5 }}
                className="w-16 h-16 bg-success/20 rounded-full flex items-center justify-center mx-auto mb-4"
              >
                <svg
                  className="w-8 h-8 text-success"
                  fill="none"
                  stroke="currentColor"
                  viewBox="0 0 24 24"
                >
                  <path
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    strokeWidth={2}
                    d="M5 13l4 4L19 7"
                  />
                </svg>
              </motion.div>
              <h2 className="text-xl font-semibold text-white mb-2">
                Connected!
              </h2>
              <p className="text-slate-400">
                Your integration has been connected successfully. Redirecting...
              </p>
            </>
          )}

          {status === "error" && (
            <>
              <motion.div
                initial={{ scale: 0 }}
                animate={{ scale: 1 }}
                transition={{ type: "spring", duration: 0.5 }}
                className="w-16 h-16 bg-critical/20 rounded-full flex items-center justify-center mx-auto mb-4"
              >
                <svg
                  className="w-8 h-8 text-critical"
                  fill="none"
                  stroke="currentColor"
                  viewBox="0 0 24 24"
                >
                  <path
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    strokeWidth={2}
                    d="M6 18L18 6M6 6l12 12"
                  />
                </svg>
              </motion.div>
              <h2 className="text-xl font-semibold text-white mb-2">
                Connection Failed
              </h2>
              <p className="text-slate-400 mb-6">{errorMessage}</p>
              <button
                onClick={handleBack}
                className="px-6 py-2 bg-primary-600 hover:bg-primary-500 text-white font-medium rounded-lg transition-colors"
              >
                {isFromOnboarding ? "Back to Onboarding" : "Back to Settings"}
              </button>
            </>
          )}
        </motion.div>
      </div>
    </div>
  );
}
