import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { BrowserRouter, Route, Routes } from "react-router-dom";
import { Toaster as Sonner } from "@/components/ui/sonner";
import { Toaster } from "@/components/ui/toaster";
import { TooltipProvider } from "@/components/ui/tooltip";
import { AuthProvider } from "@/contexts/AuthContext";
import { SampleDataProvider } from "@/contexts/SampleDataContext";
import ProtectedRoute from "@/components/ProtectedRoute";
import AppLayout from "@/components/AppLayout";
import WelcomePage from "@/pages/WelcomePage";
import LoginPage from "@/pages/LoginPage";
import SignupPage from "@/pages/SignupPage";
import Dashboard from "@/pages/Dashboard";
import TokenPage from "@/pages/TokenPage";
import DisplayPage from "@/pages/DisplayPage";
import CameraPage from "@/pages/CameraPage";
import Analytics from "@/pages/Analytics";
import QRScanPage from "@/pages/QRScanPage";
import NotFound from "./pages/NotFound";

const queryClient = new QueryClient();

const App = () => (
  <QueryClientProvider client={queryClient}>
    <TooltipProvider>
      <Toaster />
      <Sonner />
      <BrowserRouter>
        <SampleDataProvider>
          <AuthProvider>
            <Routes>
            <Route path="/" element={<WelcomePage />} />
            <Route path="/login" element={<LoginPage />} />
            <Route path="/signup" element={<SignupPage />} />
            <Route element={
              <ProtectedRoute allowedRoles={["admin", "staff"]}>
                <AppLayout />
              </ProtectedRoute>
            }>
              <Route path="/dashboard" element={<Dashboard />} />
              <Route path="/analytics" element={
                <ProtectedRoute allowedRoles={["admin"]}>
                  <Analytics />
                </ProtectedRoute>
              } />
            </Route>
            <Route path="/token" element={<TokenPage />} />
            <Route path="/qr" element={<QRScanPage />} />
            <Route path="/display" element={<DisplayPage />} />
            <Route path="/camera" element={<CameraPage />} />
            <Route path="*" element={<NotFound />} />
          </Routes>
        </AuthProvider>
      </SampleDataProvider>
      </BrowserRouter>
    </TooltipProvider>
  </QueryClientProvider>
);

export default App;
