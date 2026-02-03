import { useEffect, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { motion } from "framer-motion";
import { DashboardLayout } from "@/components/DashboardLayout";
import { useConnectIntegration } from "@/hooks/useIntegrations";

export function IntegrationsCallbackPage() {
  const [searchParams] = useSearchParams();
  const navigate = useNavigate();
  const [status, setStatus] = useState<"loading" | "success" | "error">("loading");
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  const connectMutation = useConnectIntegration();

  useEffect(() => {
    const handleCallback = async () => {
      const code = searchParams.get("code");
      const state = searchParams.get("state");
      const error = searchParams.get("error");
      const integrationType = searchParams.get("integration");

      if (error) {
        setStatus("error");
        setErrorMessage(
          error === "access_denied"
            ? "Access was denied. Please try again."
            : "An error occurred during authentication."
        );
        return;
      }

      if (!code || !integrationType) {
        setStatus("error");
        setErrorMessage("Invalid callback parameters.");
        return;
      }

      try {
        await connectMutation.mutateAsync({
          integrationType: integrationType as any,
          data: {
            code,
            state: state || undefined,
          },
        });

        setStatus("success");

        // Redirect to settings after a delay
        setTimeout(() => {
          navigate("/settings/integrations", { replace: true });
        }, 2000);
      } catch (err) {
        setStatus("error");
        setErrorMessage(
          err instanceof Error ? err.message : "Failed to connect integration."
        );
      }
    };

    handleCallback();
  }, [searchParams, navigate, connectMutation]);

  return (
    <DashboardLayout>
      <div className="relative">
        {/* Background pattern */}
        <div className="absolute inset-0 bg-[radial-gradient(ellipse_at_top,_var(--tw-gradient-stops))] from-slate-800 via-slate-900 to-slate-900 pointer-events-none" />

        <div className="relative max-w-md mx-auto px-4 py-16 lg:px-8">
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
                  className="w-16 h-16 bg-emerald-500/20 rounded-full flex items-center justify-center mx-auto mb-4"
                >
                  <svg
                    className="w-8 h-8 text-emerald-400"
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
                  className="w-16 h-16 bg-red-500/20 rounded-full flex items-center justify-center mx-auto mb-4"
                >
                  <svg
                    className="w-8 h-8 text-red-400"
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
                  onClick={() => navigate("/settings/integrations")}
                  className="px-6 py-2 bg-primary-600 hover:bg-primary-500 text-white font-medium rounded-lg transition-colors"
                >
                  Back to Settings
                </button>
              </>
            )}
          </motion.div>
        </div>
      </div>
    </DashboardLayout>
  );
}
