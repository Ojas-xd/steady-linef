import { useState, useEffect, useMemo } from "react";
import { motion } from "framer-motion";
import { BarChart, Bar, LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Area, AreaChart } from "recharts";
import { CalendarDays, TrendingUp, Clock, Award, Download, Filter, AlertTriangle, Zap, Sun, Moon, ShieldAlert, Brain } from "lucide-react";
import StatCard from "@/components/StatCard";
import LiveClock from "@/components/LiveClock";
import { generateTokens, hourlyDistribution, weeklyTrend, type Token } from "@/lib/mockData";
import { useSampleData } from "@/contexts/SampleDataContext";

// Helper to format token number for display (e.g., "0423-5" → "5")
const formatTokenDisplay = (tokenNumber: string | undefined): string => {
  if (!tokenNumber) return "";
  const parts = tokenNumber.split('-');
  return parts.length === 2 ? parts[1] : tokenNumber;
};

interface Insight {
  icon: React.ElementType;
  title: string;
  description: string;
  severity: "high" | "medium" | "low";
  tag: string;
}

function generateInsights(
  weekly: { day: string; crowd: number }[],
  hourly: { hour: string; count: number }[],
  avgService: number
): Insight[] {
  const insights: Insight[] = [];

  // Find busiest days
  const sorted = [...weekly].sort((a, b) => b.crowd - a.crowd);
  const busiestDay = sorted[0];
  const quietestDay = sorted[sorted.length - 1];
  const avgCrowd = weekly.reduce((s, d) => s + d.crowd, 0) / (weekly.length || 1);

  // Top rush days (above average)
  const rushDays = sorted.filter((d) => d.crowd > avgCrowd * 1.1);
  if (rushDays.length > 0) {
    const dayNames = rushDays.map((d) => d.day).join(", ");
    insights.push({
      icon: AlertTriangle,
      title: `${dayNames} — High Rush Days`,
      description: `These days see ${Math.round(((rushDays[0].crowd - avgCrowd) / avgCrowd) * 100)}% more visitors than average. Consider adding extra staff or opening more counters.`,
      severity: "high",
      tag: "Weekly Pattern",
    });
  }

  // Peak hours
  const sortedHours = [...hourly].sort((a, b) => b.count - a.count);
  const peakHours = sortedHours.slice(0, 3);
  if (peakHours.length > 0) {
    insights.push({
      icon: Zap,
      title: `Peak Rush: ${peakHours.map((h) => h.hour).join(", ")}`,
      description: `These hours consistently have the highest crowd density. Pre-assign staff to counters 15 minutes before ${peakHours[0].hour} to reduce wait times.`,
      severity: "high",
      tag: "Hourly Pattern",
    });
  }

  // Quiet periods
  const quietHours = sortedHours.slice(-2);
  if (quietHours.length > 0) {
    insights.push({
      icon: Moon,
      title: `Low Traffic: ${quietHours.map((h) => h.hour).join(", ")}`,
      description: `These hours have minimal crowd. Use this time for staff breaks, training, or system maintenance.`,
      severity: "low",
      tag: "Optimization",
    });
  }

  // Weekend vs weekday comparison
  const weekdays = weekly.filter((d) => !["Sat", "Sun"].includes(d.day));
  const weekends = weekly.filter((d) => ["Sat", "Sun"].includes(d.day));
  const weekdayAvg = weekdays.reduce((s, d) => s + d.crowd, 0) / (weekdays.length || 1);
  const weekendAvg = weekends.reduce((s, d) => s + d.crowd, 0) / (weekends.length || 1);

  if (weekdayAvg > 0 && weekendAvg > 0) {
    const diff = Math.round(((weekdayAvg - weekendAvg) / weekdayAvg) * 100);
    insights.push({
      icon: Sun,
      title: diff > 0 ? `Weekends are ${diff}% quieter` : `Weekends are ${Math.abs(diff)}% busier`,
      description: diff > 0
        ? `Weekend traffic drops significantly. Consider reducing counter staff on Saturdays and Sundays.`
        : `Weekend traffic surges above weekday levels. Ensure full staffing on weekends.`,
      severity: Math.abs(diff) > 40 ? "medium" : "low",
      tag: "Weekend Analysis",
    });
  }

  // Service time warning
  if (avgService > 10) {
    insights.push({
      icon: ShieldAlert,
      title: "High Average Service Time",
      description: `Average service time is ${avgService}m — above the 10m target. Review complex cases and consider adding a "Quick Service" express lane.`,
      severity: "high",
      tag: "Efficiency Alert",
    });
  }

  // Busiest day prep
  if (busiestDay && quietestDay) {
    const ratio = Math.round(busiestDay.crowd / (quietestDay.crowd || 1));
    if (ratio >= 2) {
      insights.push({
        icon: Brain,
        title: `${busiestDay.day} needs ${ratio}x more capacity than ${quietestDay.day}`,
        description: `Plan staffing dynamically: ${busiestDay.day} requires significantly more resources. Consider staggered shifts to match demand curves.`,
        severity: "medium",
        tag: "Capacity Planning",
      });
    }
  }

  return insights;
}

const severityConfig = {
  high: {
    card: "border-destructive/30 bg-destructive/5",
    icon: "text-destructive bg-destructive/10",
    tag: "bg-destructive/15 text-destructive",
  },
  medium: {
    card: "border-warning/30 bg-warning/5",
    icon: "text-warning bg-warning/10",
    tag: "bg-warning/15 text-warning",
  },
  low: {
    card: "border-accent/30 bg-accent/5",
    icon: "text-accent bg-accent/10",
    tag: "bg-accent/15 text-accent",
  },
};

const Analytics = () => {
  const { sampleDataEnabled } = useSampleData();
  const [dateFilter, setDateFilter] = useState("2026-03-26");
  const [completedTokens, setCompletedTokens] = useState<Token[]>([]);
  const [stats, setStats] = useState({
    tokens_served: 0,
    peak_time: "",
    peak_count: 0,
    avg_service_minutes: 0,
    busiest_day: "",
    busiest_day_count: 0,
    hourly: [] as typeof hourlyDistribution,
    weekly: [] as typeof weeklyTrend,
  });

  useEffect(() => {
    if (sampleDataEnabled) {
      setCompletedTokens(generateTokens().filter((token) => token.status === "completed"));
      setStats({
        tokens_served: 25,
        peak_time: "12 PM",
        peak_count: 28,
        avg_service_minutes: 7.2,
        busiest_day: "Thu",
        busiest_day_count: 168,
        hourly: hourlyDistribution,
        weekly: weeklyTrend,
      });
    } else {
      setCompletedTokens([]);
      setStats({
        tokens_served: 0,
        peak_time: "",
        peak_count: 0,
        avg_service_minutes: 0,
        busiest_day: "",
        busiest_day_count: 0,
        hourly: [],
        weekly: [],
      });
    }
  }, [sampleDataEnabled]);

  const insights = useMemo(
    () => generateInsights(stats.weekly, stats.hourly, stats.avg_service_minutes),
    [stats.weekly, stats.hourly, stats.avg_service_minutes]
  );

  const handleExport = () => {
    alert("Exporting analytics report for " + dateFilter + "...");
  };

  const tooltipStyle = { background: "hsl(217 33% 14%)", border: "1px solid hsl(217 33% 22%)", borderRadius: "12px", color: "#fff", fontSize: "12px" };

  return (
    <div className="space-y-6">
      <div className="flex flex-col lg:flex-row items-start lg:items-center justify-between gap-4">
        <div>
          <h1 className="text-xl lg:text-2xl font-bold text-foreground">Analytics</h1>
          <LiveClock className="text-sm text-muted-foreground" />
        </div>
        <div className="flex items-center gap-3 flex-wrap">
          <div className="flex items-center gap-2 px-3 py-2 rounded-lg bg-secondary border border-border">
            <Filter className="w-4 h-4 text-muted-foreground" />
            <input
              type="date"
              value={dateFilter}
              onChange={(e) => setDateFilter(e.target.value)}
              className="bg-transparent text-foreground text-sm focus:outline-none"
            />
          </div>
          <button
            onClick={handleExport}
            className="flex items-center gap-2 px-4 py-2.5 rounded-xl hero-gradient-bg text-primary-foreground text-sm font-semibold hover:opacity-90 transition-opacity"
          >
            <Download className="w-4 h-4" />
            Export Report
          </button>
        </div>
      </div>

      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3 lg:gap-4">
        <StatCard title="Tokens Served" value={stats.tokens_served} subtitle="Today" icon={Award} glowClass="stat-glow-green" iconColorClass="text-accent" trend={{ value: "18%", positive: true }} />
        <StatCard title="Peak Time" value={stats.peak_time} subtitle={`${stats.peak_count} people`} icon={TrendingUp} glowClass="stat-glow-blue" iconColorClass="text-primary" />
        <StatCard title="Avg Service" value={`${stats.avg_service_minutes}m`} subtitle="Per token" icon={Clock} glowClass="stat-glow-yellow" iconColorClass="text-warning" trend={{ value: "1.3m", positive: false }} />
        <StatCard title="Busiest Day" value={stats.busiest_day} subtitle={`${stats.busiest_day_count} visitors`} icon={CalendarDays} glowClass="stat-glow-blue" iconColorClass="text-primary" />
      </div>

      {/* AI Predictive Insights */}
      <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.15 }} className="glass-card rounded-xl p-5 lg:p-6">
        <div className="flex items-center gap-3 mb-5">
          <div className="p-2.5 rounded-xl bg-primary/10">
            <Brain className="w-5 h-5 text-primary" />
          </div>
          <div>
            <h2 className="text-base lg:text-lg font-semibold text-foreground">AI Predictive Insights</h2>
            <p className="text-xs text-muted-foreground">Pattern-based recommendations from historical data</p>
          </div>
        </div>
        <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-3">
          {insights.map((insight, i) => (
            <motion.div
              key={i}
              initial={{ opacity: 0, y: 12 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: 0.2 + i * 0.06 }}
              className={`relative rounded-xl border p-4 transition-all hover:scale-[1.01] ${severityConfig[insight.severity].card}`}
            >
              <div className="flex items-start gap-3">
                <div className={`p-2 rounded-lg shrink-0 ${severityConfig[insight.severity].icon}`}>
                  <insight.icon className="w-4 h-4" />
                </div>
                <div className="min-w-0">
                  <div className="flex items-center gap-2 mb-1 flex-wrap">
                    <span className={`text-[10px] font-semibold uppercase tracking-wider px-2 py-0.5 rounded-full ${severityConfig[insight.severity].tag}`}>
                      {insight.tag}
                    </span>
                  </div>
                  <h3 className="text-sm font-semibold text-foreground leading-snug mb-1">{insight.title}</h3>
                  <p className="text-xs text-muted-foreground leading-relaxed">{insight.description}</p>
                </div>
              </div>
            </motion.div>
          ))}
        </div>
      </motion.div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-5">
        <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} className="glass-card rounded-xl p-5 lg:p-6">
          <div className="mb-4">
            <h2 className="text-base lg:text-lg font-semibold text-foreground">Hourly Distribution</h2>
            <p className="text-xs text-muted-foreground">Crowd levels by hour today</p>
          </div>
          <ResponsiveContainer width="100%" height={240}>
            <BarChart data={stats.hourly}>
              <defs>
                <linearGradient id="barGrad" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%" stopColor="hsl(217 91% 60%)" stopOpacity={1} />
                  <stop offset="100%" stopColor="hsl(217 91% 60%)" stopOpacity={0.4} />
                </linearGradient>
              </defs>
              <CartesianGrid strokeDasharray="3 3" stroke="hsl(217 33% 20%)" />
              <XAxis dataKey="hour" stroke="hsl(215 20% 45%)" fontSize={11} tickLine={false} />
              <YAxis stroke="hsl(215 20% 45%)" fontSize={11} tickLine={false} />
              <Tooltip contentStyle={tooltipStyle} />
              <Bar dataKey="count" fill="url(#barGrad)" radius={[6, 6, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </motion.div>

        <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.1 }} className="glass-card rounded-xl p-5 lg:p-6">
          <div className="mb-4">
            <h2 className="text-base lg:text-lg font-semibold text-foreground">7-Day Trend</h2>
            <p className="text-xs text-muted-foreground">Weekly crowd pattern</p>
          </div>
          <ResponsiveContainer width="100%" height={240}>
            <AreaChart data={stats.weekly}>
              <defs>
                <linearGradient id="trendGrad" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="5%" stopColor="hsl(160 84% 39%)" stopOpacity={0.2} />
                  <stop offset="95%" stopColor="hsl(160 84% 39%)" stopOpacity={0} />
                </linearGradient>
              </defs>
              <CartesianGrid strokeDasharray="3 3" stroke="hsl(217 33% 20%)" />
              <XAxis dataKey="day" stroke="hsl(215 20% 45%)" fontSize={11} tickLine={false} />
              <YAxis stroke="hsl(215 20% 45%)" fontSize={11} tickLine={false} />
              <Tooltip contentStyle={tooltipStyle} />
              <Area type="monotone" dataKey="crowd" stroke="hsl(160 84% 39%)" fill="url(#trendGrad)" strokeWidth={2} dot={{ fill: "hsl(160 84% 39%)", r: 4 }} />
            </AreaChart>
          </ResponsiveContainer>
        </motion.div>
      </div>

      {/* Completed tokens table */}
      <div className="glass-card rounded-xl p-5 lg:p-6">
        <div className="mb-4">
          <h2 className="text-base lg:text-lg font-semibold text-foreground">Completed Tokens</h2>
          <p className="text-xs text-muted-foreground">{completedTokens.length} tokens served today</p>
        </div>
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-border">
                <th className="text-left py-3 px-3 text-muted-foreground font-medium text-xs uppercase tracking-wider">Token</th>
                <th className="text-left py-3 px-3 text-muted-foreground font-medium text-xs uppercase tracking-wider">Issued</th>
                <th className="text-left py-3 px-3 text-muted-foreground font-medium text-xs uppercase tracking-wider hidden sm:table-cell">Completed</th>
                <th className="text-left py-3 px-3 text-muted-foreground font-medium text-xs uppercase tracking-wider">Service Time</th>
              </tr>
            </thead>
            <tbody>
              {completedTokens.map((token, i) => (
                <motion.tr
                  key={token.id}
                  initial={{ opacity: 0 }}
                  animate={{ opacity: 1 }}
                  transition={{ delay: i * 0.03 }}
                  className="border-b border-border/30 hover:bg-secondary/50 transition-colors"
                >
                  <td className="py-3 px-3 font-mono font-bold text-foreground">#{formatTokenDisplay(token.tokenNumber) || token.id.slice(0,8)}</td>
                  <td className="py-3 px-3 text-muted-foreground">{token.issuedAt}</td>
                  <td className="py-3 px-3 text-muted-foreground hidden sm:table-cell">{token.completedAt}</td>
                  <td className="py-3 px-3">
                    <span className={`font-semibold font-mono ${
                      Math.round(token.serviceTime || 0) <= 5 ? "text-accent" :
                      Math.round(token.serviceTime || 0) <= 10 ? "text-warning" :
                      "text-destructive"
                    }`}>
                      {Math.round(token.serviceTime || 0)}m
                    </span>
                  </td>
                </motion.tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
};

export default Analytics;
