import { useState, useEffect } from "react";
import { motion } from "framer-motion";
import { Clock, Users, ArrowLeft } from "lucide-react";
import { QRCodeSVG } from "qrcode.react";
import { Link, useSearchParams } from "react-router-dom";
import { tokensApi } from "@/lib/api";
import { useSampleData } from "@/contexts/SampleDataContext";

const TokenPage = () => {
  const [searchParams] = useSearchParams();
  const tokenId = searchParams.get("id") || "T-047";

  const { sampleDataEnabled } = useSampleData();
  const [tokenData, setTokenData] = useState({
    id: sampleDataEnabled ? tokenId : "N/A",
    status: sampleDataEnabled ? "waiting" as "waiting" | "serving" | "completed" : "waiting",
    position: sampleDataEnabled ? 5 : 0,
    totalAhead: sampleDataEnabled ? 5 : 0,
    estimatedWait: sampleDataEnabled ? 12 : 0,
    counter: sampleDataEnabled ? 3 : 0,
  });

  // Self-issue token if no ID provided and sample data is enabled
  useEffect(() => {
    if (!sampleDataEnabled) {
      setTokenData({
        id: "N/A",
        status: "waiting",
        position: 0,
        totalAhead: 0,
        estimatedWait: 0,
        counter: 0,
      });
      return;
    }

    if (!searchParams.get("id")) {
      tokensApi.issueToken().then((token) => {
        if (token) {
          setTokenData((prev) => ({ ...prev, id: token.id }));
        }
      }).catch(() => {});
    }
  }, [searchParams, sampleDataEnabled]);

  // Poll queue status from API only when sample data is enabled
  useEffect(() => {
    if (!sampleDataEnabled) return;

    const fetchStatus = () => {
      tokensApi.getQueueStatus(tokenData.id).then((data) => {
        setTokenData((prev) => ({
          ...prev,
          position: data.position,
          estimatedWait: data.estimated_wait,
          status: data.status as typeof prev.status,
          counter: data.counter || prev.counter,
        }));
      }).catch(() => {});
    };
    fetchStatus();
    const interval = setInterval(fetchStatus, 15000);
    return () => clearInterval(interval);
  }, [tokenData.id, sampleDataEnabled]);

  const progressPercent = tokenData.totalAhead > 0 
    ? ((tokenData.totalAhead - tokenData.position) / tokenData.totalAhead) * 100 
    : 100;

  const statusConfig = {
    waiting: { color: "bg-warning/15 text-warning border-warning/20", dotColor: "bg-warning", label: "Waiting", message: "Please wait, we'll call you soon 🙏", emoji: "⏳" },
    serving: { color: "bg-primary/15 text-primary border-primary/20", dotColor: "bg-primary animate-pulse-slow", label: "Now Serving", message: "Your turn is coming up! 🎉", emoji: "🔔" },
    completed: { color: "bg-accent/15 text-accent border-accent/20", dotColor: "bg-accent", label: "Completed", message: "Please proceed to Counter " + tokenData.counter + " ✅", emoji: "✅" },
  };

  const config = statusConfig[tokenData.status];

  return (
    <div className="min-h-screen flex flex-col items-center justify-center p-4 relative overflow-hidden">
      {/* Background effects */}
      <div className="absolute inset-0 bg-grid-pattern opacity-20" />
      <div className="absolute top-1/3 left-1/2 -translate-x-1/2 w-[500px] h-[500px] rounded-full bg-primary/5 blur-3xl" />

      <div className="relative z-10 w-full max-w-sm">
        <Link to="/" className="flex items-center gap-2 text-sm text-muted-foreground hover:text-foreground transition-colors mb-6">
          <ArrowLeft className="w-4 h-4" /> Back to Home
        </Link>

        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          className="glass-card rounded-2xl overflow-hidden"
        >
          {/* Gradient header */}
          <div className="hero-gradient-bg p-6 text-center">
            <p className="text-primary-foreground/70 text-xs font-semibold uppercase tracking-widest">Your Token Number</p>
            <motion.p
              key={tokenData.id}
              initial={{ scale: 0.5 }}
              animate={{ scale: 1 }}
              className="text-6xl font-black text-primary-foreground mt-2 font-mono"
            >
              #{tokenData.id.split("-")[1]}
            </motion.p>
          </div>

          <div className="p-6 space-y-5">
            {/* Status badge */}
            <div className="flex justify-center">
              <span className={`inline-flex items-center gap-2 px-5 py-2 rounded-full text-sm font-semibold border ${config.color}`}>
                <span className={`w-2 h-2 rounded-full ${config.dotColor}`} />
                {config.label}
              </span>
            </div>

            {/* Stats */}
            <div className="grid grid-cols-2 gap-3">
              <div className="bg-secondary rounded-xl p-4 text-center">
                <Users className="w-5 h-5 text-primary mx-auto mb-1.5" />
                <p className="text-2xl font-bold text-foreground font-mono">{tokenData.position}</p>
                <p className="text-[11px] text-muted-foreground mt-0.5">People Ahead</p>
              </div>
              <div className="bg-secondary rounded-xl p-4 text-center">
                <Clock className="w-5 h-5 text-warning mx-auto mb-1.5" />
                <p className="text-2xl font-bold text-foreground font-mono">{tokenData.estimatedWait}m</p>
                <p className="text-[11px] text-muted-foreground mt-0.5">Est. Wait</p>
              </div>
            </div>

            {/* Progress bar */}
            <div>
              <div className="flex justify-between text-xs text-muted-foreground mb-2">
                <span>Queue Progress</span>
                <span className="font-mono font-semibold">{Math.round(progressPercent)}%</span>
              </div>
              <div className="w-full h-3 rounded-full bg-secondary overflow-hidden">
                <motion.div
                  className="h-full rounded-full hero-gradient-bg"
                  initial={{ width: 0 }}
                  animate={{ width: `${progressPercent}%` }}
                  transition={{ duration: 1, ease: "easeOut" }}
                />
              </div>
            </div>

            {/* Counter assignment */}
            {tokenData.status === "serving" && (
              <motion.div
                initial={{ opacity: 0, scale: 0.95 }}
                animate={{ opacity: 1, scale: 1 }}
                className="bg-primary/10 border border-primary/20 rounded-xl p-4 text-center"
              >
                <p className="text-xs text-primary/70 font-medium">Assigned to</p>
                <p className="text-2xl font-bold text-primary font-mono">Counter {tokenData.counter}</p>
              </motion.div>
            )}

            {/* Message */}
            <div className="bg-secondary/50 rounded-xl p-4 text-center">
              <span className="text-lg">{config.emoji}</span>
              <p className="text-sm text-muted-foreground mt-1">{config.message}</p>
            </div>

            {/* QR Code */}
            <div className="flex flex-col items-center pt-2">
              <div className="p-3 bg-foreground rounded-xl">
                <QRCodeSVG
                  value={`https://queue.ai/token/${tokenData.id}`}
                  size={100}
                  bgColor="hsl(210 40% 98%)"
                  fgColor="hsl(222 47% 11%)"
                />
              </div>
              <p className="text-[11px] text-muted-foreground mt-2">Scan to share your token link</p>
            </div>
          </div>
        </motion.div>

        <p className="text-center text-[11px] text-muted-foreground mt-4">
          Auto-refreshes every 15 seconds • Token ID: {tokenData.id}
        </p>
      </div>
    </div>
  );
};

export default TokenPage;
