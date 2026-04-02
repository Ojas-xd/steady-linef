import { createContext, useContext, useEffect, useState, type ReactNode } from "react";

interface SampleDataContextType {
  sampleDataEnabled: boolean;
  setSampleDataEnabled: (value: boolean) => void;
  toggleSampleData: () => void;
}

const SampleDataContext = createContext<SampleDataContextType | undefined>(undefined);

export const SampleDataProvider = ({ children }: { children: ReactNode }) => {
  const [sampleDataEnabled, setSampleDataEnabled] = useState<boolean>(() => {
    if (typeof window === "undefined") return false;
    return window.localStorage.getItem("sample_data_enabled") === "true";
  });

  useEffect(() => {
    window.localStorage.setItem("sample_data_enabled", sampleDataEnabled ? "true" : "false");
  }, [sampleDataEnabled]);

  const toggleSampleData = () => setSampleDataEnabled((current) => !current);

  return (
    <SampleDataContext.Provider value={{ sampleDataEnabled, setSampleDataEnabled, toggleSampleData }}>
      {children}
    </SampleDataContext.Provider>
  );
};

export const useSampleData = () => {
  const context = useContext(SampleDataContext);
  if (!context) {
    throw new Error("useSampleData must be used within a SampleDataProvider");
  }
  return context;
};
