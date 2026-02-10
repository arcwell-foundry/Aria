import { useParams } from "react-router-dom";
import { DashboardLayout } from "@/components/DashboardLayout";
import { ExecutionReplayViewer } from "@/components/skills/ExecutionReplayViewer";

export function ExecutionReplayPage() {
  const { executionId } = useParams<{ executionId: string }>();
  return (
    <DashboardLayout>
      <ExecutionReplayViewer executionId={executionId ?? null} />
    </DashboardLayout>
  );
}
