export type IssueCategory = "quick" | "standard" | "complex" | "custom";

export interface Token {
  id: string;
  issuedAt: string;
  status: "waiting" | "serving" | "completed";
  completedAt?: string;
  serviceTime?: number;
  counter?: number;
  category?: IssueCategory;
  estimatedMinutes?: number;
  issueDescription?: string;
}

export const generateTokens = (): Token[] => {
  const statuses: Token["status"][] = ["waiting", "serving", "completed"];
  const tokens: Token[] = [];
  for (let i = 1; i <= 25; i++) {
    const status = i <= 8 ? "completed" : i <= 10 ? "serving" : i <= 18 ? "waiting" : "completed";
    const hour = 8 + Math.floor(i / 4);
    const min = (i * 7) % 60;
    const categories: IssueCategory[] = ["quick", "standard", "complex"];
    const category = categories[Math.floor(Math.random() * 3)];
    const estMinutes = category === "quick" ? 5 : category === "standard" ? 10 : 15;
    tokens.push({
      id: `T-${String(i).padStart(3, "0")}`,
      issuedAt: `${String(hour).padStart(2, "0")}:${String(min).padStart(2, "0")}`,
      status,
      completedAt: status === "completed" ? `${String(hour + 1).padStart(2, "0")}:${String((min + 12) % 60).padStart(2, "0")}` : undefined,
      serviceTime: status === "completed" ? Math.floor(Math.random() * 15) + 3 : undefined,
      category,
      estimatedMinutes: estMinutes,
    });
  }
  return tokens;
};

export const forecastData = [
  { hour: "9AM", predicted: 12, actual: 14 },
  { hour: "10AM", predicted: 18, actual: 16 },
  { hour: "11AM", predicted: 25, actual: null },
  { hour: "12PM", predicted: 30, actual: null },
  { hour: "1PM", predicted: 28, actual: null },
  { hour: "2PM", predicted: 22, actual: null },
  { hour: "3PM", predicted: 19, actual: null },
  { hour: "4PM", predicted: 15, actual: null },
];

export const hourlyDistribution = [
  { hour: "8AM", count: 5 },
  { hour: "9AM", count: 14 },
  { hour: "10AM", count: 16 },
  { hour: "11AM", count: 22 },
  { hour: "12PM", count: 28 },
  { hour: "1PM", count: 25 },
  { hour: "2PM", count: 18 },
  { hour: "3PM", count: 12 },
  { hour: "4PM", count: 9 },
  { hour: "5PM", count: 6 },
];

export const weeklyTrend = [
  { day: "Mon", crowd: 120 },
  { day: "Tue", crowd: 145 },
  { day: "Wed", crowd: 132 },
  { day: "Thu", crowd: 168 },
  { day: "Fri", crowd: 155 },
  { day: "Sat", crowd: 89 },
  { day: "Sun", crowd: 42 },
];
