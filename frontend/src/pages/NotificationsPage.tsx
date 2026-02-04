import { DashboardLayout } from "@/components/DashboardLayout";
import { NotificationsPageContent } from "@/components/notifications/NotificationsPageContent";

export function NotificationsPage() {
  return (
    <DashboardLayout>
      <div className="p-6 lg:p-8">
        <NotificationsPageContent />
      </div>
    </DashboardLayout>
  );
}
