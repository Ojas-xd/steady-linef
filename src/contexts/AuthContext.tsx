import { createContext, useContext, useState, useEffect, type ReactNode } from "react";
import { authApi, type AuthResponse } from "@/lib/api";

interface User {
  id: string;
  email: string;
  full_name: string;
  role: string;
}

interface AuthContextType {
  user: User | null;
  isAuthenticated: boolean;
  isLoading: boolean;
  login: (email: string, password: string) => Promise<void>;
  register: (email: string, password: string, fullName: string, role?: string) => Promise<void>;
  logout: () => void;
}

const AuthContext = createContext<AuthContextType | undefined>(undefined);

export const AuthProvider = ({ children }: { children: ReactNode }) => {
  const [user, setUser] = useState<User | null>(null);
  const [isLoading, setIsLoading] = useState(true);

  useEffect(() => {
    // Restore user from localStorage on mount
    const stored = localStorage.getItem("auth_user");
    if (stored && authApi.isAuthenticated()) {
      try {
        setUser(JSON.parse(stored));
      } catch {
        authApi.logout();
      }
    }
    setIsLoading(false);
  }, []);

  const login = async (email: string, password: string) => {
    const res: AuthResponse = await authApi.login({ email, password });
    const u = res.user;
    setUser(u);
    localStorage.setItem("auth_user", JSON.stringify(u));
  };

  const register = async (email: string, password: string, fullName: string, role?: string) => {
    const res: AuthResponse = await authApi.register({
      email,
      password,
      full_name: fullName,
      role: (role as "admin" | "staff" | "customer") || "staff",
    });
    const u = res.user;
    setUser(u);
    localStorage.setItem("auth_user", JSON.stringify(u));
  };

  const logout = () => {
    authApi.logout();
    setUser(null);
    localStorage.removeItem("auth_user");
  };

  return (
    <AuthContext.Provider value={{ user, isAuthenticated: !!user, isLoading, login, register, logout }}>
      {children}
    </AuthContext.Provider>
  );
};

export const useAuth = () => {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used within AuthProvider");
  return ctx;
};
