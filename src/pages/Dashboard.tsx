import { useState, useEffect, useMemo, useCallback } from "react";
import { motion } from "framer-motion";
import { Users, Ticket, Clock, TrendingUp, AlertTriangle, Bell, Search, Timer, Zap, Briefcase, Settings, Store } from "lucide-react";
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Area, AreaChart } from "recharts";
import { QRCodeSVG } from "qrcode.react";
import StatCard from "@/components/StatCard";
import LiveClock from "@/components/LiveClock";
import { forecastData, generateTokens, type Token, type IssueCategory } from "@/lib/mockData";
import { tokensApi, crowdApi, type ServePayload } from "@/lib/api";
import { useSampleData } from "@/contexts/SampleDataContext";

// Helper to format token number for display (e.g., "0423-5" → "5")
const formatTokenDisplay = (tokenNumber: string | undefined): string => {
  if (!tokenNumber) return "";
  const parts = tokenNumber.split('-');
  return parts.length === 2 ? parts[1] : tokenNumber;
};

const CATEGORY_CONFIG = {
  quick: { label: "Quick", icon: Zap, minutes: 5, color: "bg-accent/15 text-accent border-accent/30", description: "Simple query, ID check, quick info" },
  standard: { label: "Standard", icon: Briefcase, minutes: 10, color: "bg-primary/15 text-primary border-primary/30", description: "Form filling, document submission" },
  complex: { label: "Complex", icon: Settings, minutes: 15, color: "bg-warning/15 text-warning border-warning/30", description: "Detailed review, multiple steps" },
};

const Dashboard = () => {
  const { sampleDataEnabled } = useSampleData();
  const [liveCount, setLiveCount] = useState(0);
  const [tokens, setTokens] = useState<Token[]>([]);
  const [searchQuery, setSearchQuery] = useState("");
  const [forecast, setForecast] = useState<typeof forecastData>([]);

  // Serve modal state — shown when staff clicks "Serve" to categorize the issue
  const [serveModalTokenId, setServeModalTokenId] = useState<string | null>(null);
  const [selectedCategory, setSelectedCategory] = useState<IssueCategory>("standard");
  const [customMinutes, setCustomMinutes] = useState(8);
  const [issueNote, setIssueNote] = useState("");
  const [isUpdateTimeMode, setIsUpdateTimeMode] = useState(false);  // True when updating time for auto-called customer

  // Fetch tokens from API when not using sample data
  useEffect(() => {
    if (sampleDataEnabled) {
      setTokens(generateTokens());
      setLiveCount(23);
      setForecast(forecastData);
      return;
    }

    // Fetch real data from backend
    const fetchData = async () => {
      try {
        const [tokensData, statsData, countersData] = await Promise.all([
          tokensApi.getAll(),
          crowdApi.getLiveCount().catch(() => ({ count: 0 })),
          tokensApi.getCounters().catch(() => ({ total_counters: 5, active_counters: 0, available_counters: 5 })),
        ]);
        setTokens(tokensData);
        setLiveCount(statsData.count || 0);
        setTotalCounters(countersData.total_counters);
        setAvailableCounters(countersData.available_counters);
      } catch (err) {
        console.warn("[Dashboard] Failed to fetch data:", err);
      }
    };

    fetchData();
    const interval = setInterval(fetchData, 5000); // Refresh every 5 seconds
    return () => clearInterval(interval);
  }, [sampleDataEnabled]);

  const activeTokens = tokens.filter((t) => t.status !== "completed" && t.status !== "cancelled");
  const servingTokens = tokens.filter((t) => t.status === "serving");
  const activeCounters = servingTokens.length;
  const showAlert = liveCount > 20;

  // Counter management state
  const [totalCounters, setTotalCounters] = useState(5);
  const [availableCounters, setAvailableCounters] = useState(5);

  // Calculate estimated wait for each waiting token
  const waitingTokensWithWait = useMemo(() => {
    const serving = tokens.filter((t) => t.status === "serving");
    const waiting = tokens.filter((t) => t.status === "waiting");
    // Sum remaining time from currently serving tokens (assume half done on average)
    const servingRemaining = serving.reduce((sum, t) => sum + ((t.estimatedMinutes || 10) / 2), 0);
    let cumulative = servingRemaining;
    return waiting.map((t) => {
      const wait = Math.round(cumulative);
      // Waiting tokens don't have category yet, use average estimate
      cumulative += (t.estimatedMinutes || 10);
      return { ...t, calculatedWait: wait };
    });
  }, [tokens]);

  const handleComplete = useCallback(async (id: string) => {
    // Optimistic update
    setTokens((prev) =>
      prev.map((t) => (t.id === id ? { ...t, status: "completed" as const } : t))
    );
    if (sampleDataEnabled) {
      return;
    }
    try {
      await tokensApi.complete(id);
    } catch (err) {
      console.warn("[API] Complete failed, using local state:", err);
    }
  }, [sampleDataEnabled]);

  const handleServeConfirm = useCallback(async () => {
    if (!serveModalTokenId) return;
    const estMinutes = customMinutes;

    // If updating time for already-serving token
    if (isUpdateTimeMode) {
      // Optimistic update
      setTokens((prev) =>
        prev.map((t) =>
          t.id === serveModalTokenId
            ? { ...t, estimatedMinutes: estMinutes, issueDescription: issueNote || undefined }
            : t
        )
      );

      const resetModal = () => {
        setServeModalTokenId(null);
        setIsUpdateTimeMode(false);
        setIssueNote("");
      };

      if (sampleDataEnabled) {
        resetModal();
        return;
      }

      try {
        await tokensApi.updateTime(serveModalTokenId, estMinutes, issueNote || undefined);
      } catch (err) {
        console.warn("[API] Update time failed, using local state:", err);
      }

      resetModal();
      return;
    }

    // Regular serve flow for waiting tokens
    const counter = Math.ceil(Math.random() * 5);

    // Optimistic update
    setTokens((prev) =>
      prev.map((t) =>
        t.id === serveModalTokenId
          ? { ...t, status: "serving" as const, counter, category: selectedCategory, estimatedMinutes: estMinutes, issueDescription: issueNote || undefined }
          : t
      )
    );

    const payload: ServePayload = {
      category: selectedCategory,
      estimated_minutes: estMinutes,
      issue_description: issueNote || undefined,
      counter,
    };

    const resetModal = () => {
      setServeModalTokenId(null);
      setSelectedCategory("standard");
      setCustomMinutes(8);
      setIssueNote("");
    };

    if (sampleDataEnabled) {
      resetModal();
      return;
    }

    try {
      await tokensApi.serve(serveModalTokenId, payload);
    } catch (err) {
      console.warn("[API] Serve failed, using local state:", err);
    }

    resetModal();
  }, [serveModalTokenId, selectedCategory, customMinutes, issueNote, sampleDataEnabled, isUpdateTimeMode]);

  const filteredTokens = activeTokens.filter(
    (t) => !searchQuery || t.id.toLowerCase().includes(searchQuery.toLowerCase())
  );

  // Counter management functions
  const increaseCounters = async () => {
    if (totalCounters >= 20) return;
    const newTotal = totalCounters + 1;
    setTotalCounters(newTotal);
    if (!sampleDataEnabled) {
      try {
        await tokensApi.setCounters(newTotal);
      } catch (err) {
        console.warn("[API] Failed to update counters:", err);
      }
    }
  };

  const decreaseCounters = async () => {
    if (totalCounters <= 1) return;
    if (activeCounters >= totalCounters) {
      alert("Cannot remove counter while all counters are active. Complete some tokens first.");
      return;
    }
    const newTotal = totalCounters - 1;
    setTotalCounters(newTotal);
    if (!sampleDataEnabled) {
      try {
        await tokensApi.setCounters(newTotal);
      } catch (err) {
        console.warn("[API] Failed to update counters:", err);
      }
    }
  };

  const tooltipStyle = { background: "hsl(217 33% 14%)", border: "1px solid hsl(217 33% 22%)", borderRadius: "12px", color: "#fff", fontSize: "12px" };

  return (
    <div className="space-y-6">
      {showAlert && (
        <motion.div
          initial={{ opacity: 0, y: -10 }}
          animate={{ opacity: 1, y: 0 }}
          className="flex items-center gap-3 p-4 rounded-xl bg-warning/10 border border-warning/30"
        >
          <div className="w-8 h-8 rounded-lg bg-warning/20 flex items-center justify-center">
            <AlertTriangle className="w-4 h-4 text-warning" />
          </div>
          <div className="flex-1">
            <span className="text-sm font-semibold text-warning">High Congestion Alert</span>
            <p className="text-xs text-warning/70">{liveCount} people detected in queue area — consider opening additional counters</p>
          </div>
          <div className="flex gap-1">
            {[1, 2, 3, 4, 5].map((i) => (
              <div key={i} className={`w-1.5 h-6 rounded-full ${i <= Math.ceil(liveCount / 6) ? "bg-warning" : "bg-warning/20"}`} />
            ))}
          </div>
        </motion.div>
      )}

      <div className="flex flex-col lg:flex-row items-start lg:items-center justify-between gap-4">
        <div>
          <h1 className="text-xl lg:text-2xl font-bold text-foreground">Staff Dashboard</h1>
          <LiveClock className="text-sm text-muted-foreground" />
        </div>
        <div className="flex items-center gap-3">
          <div className="relative">
            <Bell className="w-5 h-5 text-muted-foreground" />
            <span className="absolute -top-1 -right-1 w-2.5 h-2.5 rounded-full bg-destructive animate-pulse-slow" />
          </div>
        </div>
      </div>

      <div className="grid grid-cols-2 lg:grid-cols-5 gap-3 lg:gap-4">
        <StatCard title="Live Count" value={liveCount} subtitle="Auto-refreshing" icon={Users} glowClass="stat-glow-blue" iconColorClass="text-primary" trend={{ value: "12%", positive: true }} />
        <StatCard title="Active Tokens" value={activeTokens.length} subtitle="Waiting + Serving" icon={Ticket} glowClass="stat-glow-green" iconColorClass="text-accent" />
        <StatCard title="Active Counters" value={activeCounters} subtitle={`of ${totalCounters} Total`} icon={Store} glowClass="stat-glow-blue" iconColorClass="text-primary" />
        <StatCard title="Avg Wait" value="8m" subtitle="Last hour" icon={Clock} glowClass="stat-glow-yellow" iconColorClass="text-warning" trend={{ value: "2m", positive: false }} />
        <StatCard title="Peak Hour" value="12 PM" subtitle="AI Forecast" icon={TrendingUp} glowClass="stat-glow-blue" iconColorClass="text-primary" />
      </div>

      {/* Counter Management */}
      <motion.div
        initial={{ opacity: 0, y: 10 }}
        animate={{ opacity: 1, y: 0 }}
        className="glass-card rounded-xl p-4 border border-border/50"
      >
        <div className="flex flex-col sm:flex-row items-center justify-between gap-4">
          <div className="flex items-center gap-3">
            <div className="p-2 rounded-lg bg-primary/10">
              <Store className="w-5 h-5 text-primary" />
            </div>
            <div>
              <h3 className="font-semibold text-foreground">Counter Management</h3>
              <p className="text-xs text-muted-foreground">
                {activeCounters} of {totalCounters} counters active • {availableCounters} available
              </p>
            </div>
          </div>
          <div className="flex items-center gap-2">
            <button
              onClick={decreaseCounters}
              disabled={totalCounters <= 1 || activeCounters >= totalCounters}
              className="flex items-center justify-center w-10 h-10 rounded-lg bg-secondary border border-border hover:bg-secondary/80 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
            >
              <span className="text-lg font-bold text-foreground">−</span>
            </button>
            <div className="px-4 py-2 rounded-lg bg-secondary border border-border min-w-[80px] text-center">
              <span className="font-semibold text-foreground">{totalCounters}</span>
            </div>
            <button
              onClick={increaseCounters}
              disabled={totalCounters >= 20}
              className="flex items-center justify-center w-10 h-10 rounded-lg bg-primary/10 border border-primary/30 hover:bg-primary/20 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
            >
              <span className="text-lg font-bold text-primary">+</span>
            </button>
          </div>
        </div>
      </motion.div>

      {/* QR Code for Customers */}
      <motion.div
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        className="glass-card rounded-xl p-5 border border-primary/20"
      >
        <div className="flex flex-col sm:flex-row items-center gap-4">
          <div className="bg-white p-3 rounded-xl shrink-0">
            <QRCodeSVG
              value={`${window.location.origin}/token`}
              size={80}
              bgColor="#ffffff"
              fgColor="#000000"
            />
          </div>
          <div className="text-center sm:text-left">
            <h3 className="text-base font-semibold text-foreground">Customer QR Check-in</h3>
            <p className="text-sm text-muted-foreground mt-1">Customers scan this QR code to join the queue</p>
            <p className="text-xs text-primary mt-2">Or click "QR Scan" in sidebar for fullscreen view</p>
          </div>
        </div>
      </motion.div>

      {/* Forecast chart */}
      <div className="glass-card rounded-xl p-5 lg:p-6">
        <div className="flex items-center justify-between mb-4">
          <div>
            <h2 className="text-base lg:text-lg font-semibold text-foreground">8-Hour Crowd Forecast</h2>
            <p className="text-xs text-muted-foreground">AI prediction vs actual crowd levels</p>
          </div>
          <div className="flex items-center gap-4 text-xs">
            <div className="flex items-center gap-1.5"><span className="w-3 h-0.5 rounded-full bg-primary" /> Predicted</div>
            <div className="flex items-center gap-1.5"><span className="w-3 h-0.5 rounded-full bg-accent" /> Actual</div>
          </div>
        </div>
        <ResponsiveContainer width="100%" height={240}>
          <AreaChart data={forecast}>
            <defs>
              <linearGradient id="gradBlue" x1="0" y1="0" x2="0" y2="1">
                <stop offset="5%" stopColor="hsl(217 91% 60%)" stopOpacity={0.2} />
                <stop offset="95%" stopColor="hsl(217 91% 60%)" stopOpacity={0} />
              </linearGradient>
            </defs>
            <CartesianGrid strokeDasharray="3 3" stroke="hsl(217 33% 20%)" />
            <XAxis dataKey="hour" stroke="hsl(215 20% 45%)" fontSize={11} tickLine={false} />
            <YAxis stroke="hsl(215 20% 45%)" fontSize={11} tickLine={false} />
            <Tooltip contentStyle={tooltipStyle} />
            <Area type="monotone" dataKey="predicted" stroke="hsl(217 91% 60%)" fill="url(#gradBlue)" strokeWidth={2} />
            <Line type="monotone" dataKey="actual" stroke="hsl(160 84% 39%)" strokeWidth={2} dot={{ fill: "hsl(160 84% 39%)", r: 4 }} />
          </AreaChart>
        </ResponsiveContainer>
      </div>

      {/* Token table */}
      <div className="glass-card rounded-xl p-5 lg:p-6">
        <div className="flex flex-col lg:flex-row items-start lg:items-center justify-between gap-3 mb-4">
          <div>
            <h2 className="text-base lg:text-lg font-semibold text-foreground">Token Queue</h2>
            <p className="text-xs text-muted-foreground">{activeTokens.length} active — customers join via QR scan</p>
          </div>
          <div className="relative w-full lg:w-64">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" />
            <input
              type="text"
              placeholder="Search tokens..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="w-full pl-9 pr-4 py-2 rounded-lg bg-secondary border border-border text-foreground text-sm placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-primary/50"
            />
          </div>
        </div>
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-border">
                <th className="text-left py-3 px-3 text-muted-foreground font-medium text-xs uppercase tracking-wider">Token</th>
                <th className="text-left py-3 px-3 text-muted-foreground font-medium text-xs uppercase tracking-wider hidden sm:table-cell">Joined At</th>
                <th className="text-left py-3 px-3 text-muted-foreground font-medium text-xs uppercase tracking-wider">Status</th>
                <th className="text-left py-3 px-3 text-muted-foreground font-medium text-xs uppercase tracking-wider hidden md:table-cell">Category</th>
                <th className="text-left py-3 px-3 text-muted-foreground font-medium text-xs uppercase tracking-wider hidden md:table-cell">Est. Wait</th>
                <th className="text-left py-3 px-3 text-muted-foreground font-medium text-xs uppercase tracking-wider hidden lg:table-cell">Counter</th>
                <th className="text-left py-3 px-3 text-muted-foreground font-medium text-xs uppercase tracking-wider">Action</th>
              </tr>
            </thead>
            <tbody>
              {filteredTokens.map((token, i) => {
                const catConfig = token.category && token.category !== "custom" ? CATEGORY_CONFIG[token.category as keyof typeof CATEGORY_CONFIG] : null;
                const waitInfo = waitingTokensWithWait.find((w) => w.id === token.id);
                return (
                  <motion.tr
                    key={token.id}
                    initial={{ opacity: 0 }}
                    animate={{ opacity: 1 }}
                    transition={{ delay: i * 0.03 }}
                    className="border-b border-border/30 hover:bg-secondary/50 transition-colors"
                  >
                    <td className="py-3 px-3 font-mono font-bold text-foreground">#{formatTokenDisplay(token.tokenNumber) || token.id.slice(0,8)}</td>
                    <td className="py-3 px-3 text-muted-foreground hidden sm:table-cell">{token.issuedAt}</td>
                    <td className="py-3 px-3">
                      <span className={`inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-[11px] font-semibold ${
                        token.status === "waiting" ? "bg-warning/15 text-warning" :
                        token.status === "serving" ? "bg-primary/15 text-primary" :
                        "bg-accent/15 text-accent"
                      }`}>
                        <span className={`w-1.5 h-1.5 rounded-full ${
                          token.status === "waiting" ? "bg-warning" :
                          token.status === "serving" ? "bg-primary animate-pulse-slow" :
                          "bg-accent"
                        }`} />
                        {token.status.charAt(0).toUpperCase() + token.status.slice(1)}
                      </span>
                    </td>
                    <td className="py-3 px-3 hidden md:table-cell">
                      {catConfig ? (
                        <span className={`inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-[11px] font-semibold border ${catConfig.color}`}>
                          <catConfig.icon className="w-3 h-3" />
                          {catConfig.label}
                        </span>
                      ) : token.category === "custom" ? (
                        <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-[11px] font-semibold border bg-muted/15 text-muted-foreground border-border">
                          <Timer className="w-3 h-3" />
                          Custom
                        </span>
                      ) : (
                        <span className="text-xs text-muted-foreground">—</span>
                      )}
                    </td>
                    <td className="py-3 px-3 hidden md:table-cell">
                      {token.status === "waiting" && waitInfo ? (
                        <span className="font-mono font-semibold text-muted-foreground">~{waitInfo.calculatedWait}m</span>
                      ) : token.status === "serving" ? (
                        <span className="font-mono font-semibold text-primary">{Math.round(token.estimatedMinutes || 0)}m</span>
                      ) : (
                        <span className="text-muted-foreground">—</span>
                      )}
                    </td>
                    <td className="py-3 px-3 text-muted-foreground hidden lg:table-cell">
                      {token.status === "serving" ? (
                        <span className="text-primary font-semibold">Counter {token.counter}</span>
                      ) : "—"}
                    </td>
                    <td className="py-3 px-3">
                      {token.status === "waiting" && (
                        <button onClick={() => setServeModalTokenId(token.id)} className="px-3 py-1.5 rounded-lg bg-primary/15 text-primary text-xs font-semibold hover:bg-primary/25 transition-colors">
                          Serve
                        </button>
                      )}
                      {token.status === "serving" && (
                        <div className="flex gap-2">
                          <button 
                            onClick={() => {
                              setServeModalTokenId(token.id);
                              setIsUpdateTimeMode(true);
                              setCustomMinutes(token.estimatedMinutes || 10);
                            }} 
                            className="px-3 py-1.5 rounded-lg bg-primary/15 text-primary text-xs font-semibold hover:bg-primary/25 transition-colors"
                          >
                            Update Time
                          </button>
                          <button onClick={() => handleComplete(token.id)} className="px-3 py-1.5 rounded-lg bg-accent/15 text-accent text-xs font-semibold hover:bg-accent/25 transition-colors">
                            Complete
                          </button>
                        </div>
                      )}
                    </td>
                  </motion.tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </div>

      {/* Serve & Categorize Modal */}
      {serveModalTokenId && (
        <div className="fixed inset-0 bg-background/80 backdrop-blur-sm flex items-center justify-center z-50" onClick={() => setServeModalTokenId(null)}>
          <motion.div
            initial={{ scale: 0.9, opacity: 0 }}
            animate={{ scale: 1, opacity: 1 }}
            className="glass-card rounded-2xl p-6 lg:p-8 max-w-md w-full mx-4"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="text-center mb-6">
              <div className="w-14 h-14 rounded-2xl hero-gradient-bg flex items-center justify-center mx-auto mb-3">
                <Ticket className="w-7 h-7 text-primary-foreground" />
              </div>
              <h3 className="text-lg font-bold text-foreground">
                {isUpdateTimeMode ? "Update Service Time" : "Serve Customer"}
              </h3>
              <p className="text-sm text-muted-foreground">
                {isUpdateTimeMode 
                  ? "Customer has been called. Ask how much time they need." 
                  : "Ask customer how much time they need, then enter below"}
              </p>
            </div>

            {/* Time Selection - Staff asks customer */}
            <div className="space-y-4 mb-5">
              <p className="text-xs font-semibold text-muted-foreground uppercase tracking-wider text-center">
                How much time does the customer need?
              </p>
              
              {/* Quick preset buttons */}
              <div className="grid grid-cols-4 gap-2">
                {[5, 10, 15, 20].map((mins) => (
                  <button
                    key={mins}
                    onClick={() => {
                      setSelectedCategory("custom");
                      setCustomMinutes(mins);
                    }}
                    className={`p-2 rounded-xl border-2 transition-all duration-200 text-center ${
                      selectedCategory === "custom" && customMinutes === mins
                        ? "border-primary bg-primary/10"
                        : "border-border bg-secondary hover:border-muted-foreground/30"
                    }`}
                  >
                    <span className="text-sm font-bold">{mins}</span>
                    <span className="text-[10px] text-muted-foreground block">min</span>
                  </button>
                ))}
              </div>

              {/* Custom time input */}
              <div className="flex items-center justify-center gap-3 p-3 rounded-xl border-2 border-border bg-secondary">
                <Timer className="w-5 h-5 text-muted-foreground" />
                <div className="flex items-center gap-2">
                  <input
                    type="number"
                    min={1}
                    max={120}
                    value={customMinutes}
                    onChange={(e) => setCustomMinutes(Math.max(1, Math.min(120, Number(e.target.value) || 1)))}
                    className="w-20 px-3 py-2 rounded-lg bg-background border border-border text-foreground text-lg font-bold text-center focus:outline-none focus:ring-2 focus:ring-primary/50"
                  />
                  <span className="text-sm text-muted-foreground font-medium">minutes</span>
                </div>
              </div>
            </div>

            {/* Customer name note */}
            <div className="mb-5">
              <p className="text-xs font-semibold text-muted-foreground uppercase tracking-wider mb-2">Customer / Issue Note (optional)</p>
              <input
                type="text"
                placeholder="e.g., Bill payment, Account opening..."
                value={issueNote}
                onChange={(e) => setIssueNote(e.target.value)}
                maxLength={100}
                className="w-full px-3 py-2 rounded-lg bg-secondary border border-border text-foreground text-sm placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-primary/50"
              />
            </div>

            {/* Summary */}
            <div className="bg-primary/10 rounded-xl p-4 mb-5 text-center border border-primary/20">
              <span className="text-xs text-primary/70 uppercase tracking-wider block mb-1">Customer will be notified</span>
              <span className="text-2xl font-bold text-primary font-mono">
                {customMinutes} minutes
              </span>
              <span className="text-xs text-muted-foreground block mt-1">
                Estimated service time
              </span>
            </div>

            <div className="flex gap-3">
              <button onClick={() => { setServeModalTokenId(null); setSelectedCategory("standard"); setIssueNote(""); setIsUpdateTimeMode(false); }} className="flex-1 px-4 py-2.5 rounded-xl bg-secondary text-foreground text-sm font-medium hover:bg-secondary/80 transition-colors">
                Cancel
              </button>
              <button 
                onClick={() => {
                  setSelectedCategory("custom");
                  handleServeConfirm();
                  setIsUpdateTimeMode(false);
                }} 
                className="flex-1 px-4 py-2.5 rounded-xl hero-gradient-bg text-primary-foreground text-sm font-semibold hover:opacity-90 transition-opacity"
              >
                {isUpdateTimeMode ? `Update Time (${customMinutes} min)` : `Start Serving (${customMinutes} min)`}
              </button>
            </div>
          </motion.div>
        </div>
      )}
    </div>
  );
};

export default Dashboard;
