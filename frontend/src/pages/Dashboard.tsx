import { DashboardLayout } from "@/components/DashboardLayout";

export function DashboardPage() {
  return (
    <DashboardLayout>
      <div className="p-4 lg:p-8">
        <div className="max-w-4xl mx-auto">
          <h1 className="text-3xl font-bold text-white mb-2">Welcome to ARIA</h1>
          <p className="text-slate-400 mb-8">
            Your AI-powered Department Director for Life Sciences commercial teams.
          </p>

          <div className="grid gap-6 md:grid-cols-2">
            <div className="bg-slate-800/50 border border-slate-700 rounded-xl p-6">
              <h2 className="text-lg font-semibold text-white mb-2">Get Started</h2>
              <p className="text-slate-400 text-sm">
                Start a conversation with ARIA to begin optimizing your sales workflow.
              </p>
            </div>

            <div className="bg-slate-800/50 border border-slate-700 rounded-xl p-6">
              <h2 className="text-lg font-semibold text-white mb-2">Quick Stats</h2>
              <p className="text-slate-400 text-sm">
                Your personalized dashboard metrics will appear here.
              </p>
            </div>
          </div>
        </div>
      </div>
    </DashboardLayout>
  );
}
