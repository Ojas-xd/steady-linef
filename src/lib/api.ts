import axios from "axios";
import type { Token, IssueCategory } from "./mockData";
import { generateTokens, forecastData, hourlyDistribution, weeklyTrend } from "./mockData";

// Point this to your FastAPI backend URL
const API_BASE = import.meta.env.VITE_API_BASE_URL || "http://localhost:8000";

const api = axios.create({
  baseURL: `${API_BASE}/api`,
  headers: { "Content-Type": "application/json" },
});

// Attach JWT token to every request if available
api.interceptors.request.use((config) => {
  const token = localStorage.getItem("auth_token");
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

// Helper: try API call, fall back to mock data
async function withFallback<T>(apiCall: () => Promise<T>, fallback: T): Promise<T> {
  try {
    return await apiCall();
  } catch (err) {
    console.warn("[API] Backend unavailable, using mock data:", err);
    return fallback;
  }
}

// ── Auth ──────────────────────────────────────────────

export interface LoginPayload {
  email: string;
  password: string;
}

export interface RegisterPayload {
  email: string;
  password: string;
  full_name: string;
  role?: "admin" | "staff" | "customer";
}

export interface AuthResponse {
  access_token: string;
  token_type: string;
  user: { id: string; email: string; full_name: string; role: string };
}

export const authApi = {
  login: async (data: LoginPayload): Promise<AuthResponse> => {
    const res = await api.post("/auth/login", data);
    if (res.data.access_token) {
      localStorage.setItem("auth_token", res.data.access_token);
    }
    return res.data;
  },

  register: async (data: RegisterPayload): Promise<AuthResponse> => {
    const res = await api.post("/auth/register", data);
    if (res.data.access_token) {
      localStorage.setItem("auth_token", res.data.access_token);
    }
    return res.data;
  },

  logout: () => {
    localStorage.removeItem("auth_token");
  },

  getToken: () => localStorage.getItem("auth_token"),
  isAuthenticated: () => !!localStorage.getItem("auth_token"),
};

// ── Tokens / Queue ────────────────────────────────────

export interface TokenResponse extends Token {
  customer_name?: string;
}

export interface ServePayload {
  category: IssueCategory;
  estimated_minutes: number;
  issue_description?: string;
  counter?: number;
}

export const tokensApi = {
  /** Customer self-issues a token via QR scan */
  issueToken: async (customerName?: string): Promise<TokenResponse> => {
    const res = await api.post("/tokens/", { customer_name: customerName });
    return res.data;
  },

  /** Get all tokens (staff view) */
  getAll: async (): Promise<Token[]> => {
    return withFallback(
      async () => {
        const res = await api.get("/tokens/");
        return res.data;
      },
      generateTokens()
    );
  },

  /** Get a single token status (customer view) */
  getById: async (tokenId: string): Promise<TokenResponse | null> => {
    return withFallback(
      async () => {
        const res = await api.get(`/tokens/${tokenId}`);
        return res.data;
      },
      null
    );
  },

  /** Staff categorizes & starts serving a token */
  serve: async (tokenId: string, payload: ServePayload): Promise<TokenResponse> => {
    const res = await api.patch(`/tokens/${tokenId}/serve`, payload);
    return res.data;
  },

  /** Staff marks a token as completed */
  complete: async (tokenId: string): Promise<TokenResponse> => {
    const res = await api.patch(`/tokens/${tokenId}/complete`);
    return res.data;
  },

  /** Get queue position & wait time for a specific token */
  getQueueStatus: async (tokenId: string): Promise<{
    position: number;
    estimated_wait: number;
    status: string;
    counter?: number;
  }> => {
    return withFallback(
      async () => {
        const res = await api.get(`/tokens/${tokenId}/status`);
        return res.data;
      },
      { position: 5, estimated_wait: 12, status: "waiting" }
    );
  },
};

// ── Dashboard / Stats ─────────────────────────────────

export interface DashboardStats {
  live_count: number;
  active_tokens: number;
  avg_wait_minutes: number;
  peak_hour: string;
}

export const dashboardApi = {
  getStats: async (): Promise<DashboardStats> => {
    return withFallback(
      async () => {
        const res = await api.get("/dashboard/stats");
        return res.data;
      },
      { live_count: 23, active_tokens: 10, avg_wait_minutes: 8, peak_hour: "12 PM" }
    );
  },

  getForecast: async (): Promise<typeof forecastData> => {
    return withFallback(
      async () => {
        const res = await api.get("/dashboard/forecast");
        return res.data;
      },
      forecastData
    );
  },
};

// ── Display (TV screen) ──────────────────────────────

export interface NowServingData {
  serving_token: string;
  serving_counter: number;
  upcoming_tokens: string[];
  live_count: number;
}

export const displayApi = {
  getNowServing: async (): Promise<NowServingData> => {
    return withFallback(
      async () => {
        const res = await api.get("/display/now-serving");
        return res.data;
      },
      {
        serving_token: "T-011",
        serving_counter: 2,
        upcoming_tokens: ["T-012", "T-013", "T-014", "T-015", "T-016"],
        live_count: 18,
      }
    );
  },
};

// ── Analytics ─────────────────────────────────────────

export interface AnalyticsData {
  tokens_served: number;
  peak_time: string;
  peak_count: number;
  avg_service_minutes: number;
  busiest_day: string;
  busiest_day_count: number;
  hourly_distribution: typeof hourlyDistribution;
  weekly_trend: typeof weeklyTrend;
  completed_tokens: Token[];
}

export const analyticsApi = {
  getAnalytics: async (date?: string): Promise<AnalyticsData> => {
    const mockTokens = generateTokens();
    const completed = mockTokens.filter((t) => t.status === "completed");
    return withFallback(
      async () => {
        const res = await api.get("/analytics/", { params: date ? { date } : undefined });
        return res.data;
      },
      {
        tokens_served: completed.length,
        peak_time: "12 PM",
        peak_count: 28,
        avg_service_minutes: 7.2,
        busiest_day: "Thu",
        busiest_day_count: 168,
        hourly_distribution: hourlyDistribution,
        weekly_trend: weeklyTrend,
        completed_tokens: completed,
      }
    );
  },
};

// ── Crowd / YOLO ──────────────────────────────────────

export const crowdApi = {
  /** Get current YOLO people count */
  getLiveCount: async (): Promise<{ count: number; timestamp: string }> => {
    return withFallback(
      async () => {
        const res = await api.get("/crowd/count");
        return res.data;
      },
      { count: 23, timestamp: new Date().toISOString() }
    );
  },

  /** Upload a frame for YOLO analysis */
  analyzeFrame: async (imageFile: File): Promise<{ count: number }> => {
    const formData = new FormData();
    formData.append("file", imageFile);
    const res = await api.post("/crowd/analyze", formData);
    return res.data;
  },
};

export default api;
