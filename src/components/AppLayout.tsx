import { Outlet } from "react-router-dom";
import AppSidebar from "./AppSidebar";
import { useSampleData } from "@/contexts/SampleDataContext";

const AppLayout = () => {
  const { sampleDataEnabled, toggleSampleData } = useSampleData();

  return (
    <div className="flex min-h-screen">
      <AppSidebar />
      <main className="flex-1 lg:ml-64 p-4 lg:p-8 pt-16 lg:pt-8">
        <div className="mb-6 flex flex-col sm:flex-row items-start sm:items-center justify-between gap-3">
          <div className="text-sm text-muted-foreground">
            Sample data is <span className="font-semibold text-foreground">{sampleDataEnabled ? "enabled" : "disabled"}</span>.
          </div>
          <button
            type="button"
            onClick={toggleSampleData}
            className="inline-flex items-center justify-center rounded-xl border border-border bg-secondary px-4 py-2 text-sm font-semibold text-foreground hover:bg-primary/10 transition"
          >
            {sampleDataEnabled ? "Clear sample data" : "Load sample data"}
          </button>
        </div>
        <Outlet />
      </main>
    </div>
  );
};

export default AppLayout;
