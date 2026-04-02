import { useState, useEffect, useRef } from "react";
import { motion, AnimatePresence } from "framer-motion";
import LiveClock from "@/components/LiveClock";
import { Zap } from "lucide-react";
import { displayApi } from "@/lib/api";
import { useSampleData } from "@/contexts/SampleDataContext";

const DisplayPage = () => {
  const { sampleDataEnabled } = useSampleData();
  const [liveCount, setLiveCount] = useState(18);
  const [servingToken, setServingToken] = useState("T-011");
  const [servingCounter, setServingCounter] = useState(2);
  const [upcomingTokens, setUpcomingTokens] = useState(["T-012", "T-013", "T-014", "T-015", "T-016"]);
  const [announcement, setAnnouncement] = useState("");
  const prevServingRef = useRef(servingToken);

  // Poll display data from API only when sample data is enabled
  useEffect(() => {
    if (!sampleDataEnabled) {
      setLiveCount(0);
      setServingToken("—");
      setServingCounter(0);
      setUpcomingTokens([]);
      setAnnouncement("");
      return;
    }

    const fetchDisplay = async () => {
      const data = await displayApi.getNowServing();
      setLiveCount(data.live_count);
      setUpcomingTokens(data.upcoming_tokens);

      // Trigger announcement if serving token changed
      if (data.serving_token !== prevServingRef.current) {
        setServingToken(data.serving_token);
        setServingCounter(data.serving_counter);
        setAnnouncement(`Token ${data.serving_token}, please proceed to Counter ${data.serving_counter}`);
        setTimeout(() => setAnnouncement(""), 5000);
        prevServingRef.current = data.serving_token;
      }
    };
    fetchDisplay();
    const interval = setInterval(fetchDisplay, 5000);
    return () => {
      clearInterval(interval);
    };
  }, [sampleDataEnabled]);

  return (
    <div className="fixed inset-0 bg-background flex flex-col overflow-hidden">
      {/* Subtle grid background */}
      <div className="absolute inset-0 bg-grid-pattern opacity-15" />

      {/* Top bar */}
      <div className="relative flex items-center justify-between px-6 lg:px-10 py-4 lg:py-6 border-b border-border">
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 rounded-xl hero-gradient-bg flex items-center justify-center">
            <Zap className="w-5 h-5 text-primary-foreground" />
          </div>
          <span className="text-xl font-bold text-foreground hidden sm:inline">AI Queue System</span>
        </div>
        <LiveClock className="text-xl lg:text-3xl font-bold text-foreground font-mono" />
      </div>

      {/* Announcement banner */}
      <AnimatePresence>
        {announcement && (
          <motion.div
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: "auto", opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            className="relative bg-accent/10 border-b border-accent/20 overflow-hidden"
          >
            <div className="flex items-center justify-center gap-3 py-3 px-6">
              <span className="text-lg">🔔</span>
              <p className="text-accent font-semibold text-base lg:text-lg">{announcement}</p>
            </div>
          </motion.div>
        )}
      </AnimatePresence>

      {/* Main content */}
      <div className="flex-1 relative grid grid-cols-1 lg:grid-cols-2 gap-0">
        {/* Left: Live count + serving */}
        <div className="flex flex-col items-center justify-center border-b lg:border-b-0 lg:border-r border-border py-8 lg:py-0 space-y-8 lg:space-y-12">
          <div className="text-center">
            <p className="text-sm lg:text-base text-muted-foreground font-semibold uppercase tracking-[0.2em]">People in Queue</p>
            <div className="relative">
              <motion.p
                key={liveCount}
                initial={{ scale: 0.85, opacity: 0.5 }}
                animate={{ scale: 1, opacity: 1 }}
                className="text-8xl lg:text-[12rem] font-black text-primary leading-none font-mono"
              >
                {liveCount}
              </motion.p>
              {/* Pulsing rings */}
              <div className="absolute inset-0 flex items-center justify-center pointer-events-none">
                <div className="w-32 h-32 lg:w-48 lg:h-48 rounded-full border-2 border-primary/20 animate-pulse-ring" />
              </div>
            </div>
          </div>

          <div className="text-center">
            <p className="text-sm lg:text-base text-muted-foreground font-semibold uppercase tracking-[0.2em]">Now Serving</p>
            <motion.p
              key={servingToken}
              initial={{ y: 20, opacity: 0 }}
              animate={{ y: 0, opacity: 1 }}
              className="text-5xl lg:text-8xl font-black text-accent mt-2 font-mono"
            >
              {servingToken}
            </motion.p>
            <p className="text-lg lg:text-2xl text-accent/70 font-semibold mt-1">Counter {servingCounter}</p>
          </div>
        </div>

        {/* Right: Upcoming tokens */}
        <div className="flex flex-col items-center justify-center px-6 lg:px-10 py-8 lg:py-0">
          <p className="text-sm lg:text-base text-muted-foreground font-semibold uppercase tracking-[0.2em] mb-6 lg:mb-8">Coming Up Next</p>
          <div className="space-y-3 lg:space-y-4 w-full max-w-md">
            <AnimatePresence mode="popLayout">
              {upcomingTokens.map((token, i) => (
                <motion.div
                  key={token}
                  layout
                  initial={{ opacity: 0, x: 40 }}
                  animate={{ opacity: 1, x: 0 }}
                  exit={{ opacity: 0, x: -40 }}
                  transition={{ delay: i * 0.05, type: "spring", damping: 20 }}
                  className={`flex items-center justify-between p-4 lg:p-5 rounded-xl transition-colors ${
                    i === 0
                      ? "bg-primary/15 border-2 border-primary/30"
                      : "bg-secondary/80 border border-border/50"
                  }`}
                >
                  <div className="flex items-center gap-3 lg:gap-4">
                    <span className={`w-8 h-8 lg:w-10 lg:h-10 rounded-lg flex items-center justify-center text-xs lg:text-sm font-bold ${
                      i === 0 ? "bg-primary/20 text-primary" : "bg-secondary text-muted-foreground"
                    }`}>
                      {i + 1}
                    </span>
                    <span className={`text-2xl lg:text-3xl font-bold font-mono ${i === 0 ? "text-primary" : "text-foreground"}`}>
                      {token}
                    </span>
                  </div>
                  <span className={`text-xs lg:text-sm font-medium px-3 py-1 rounded-full ${
                    i === 0 ? "bg-primary/20 text-primary" : "text-muted-foreground"
                  }`}>
                    {i === 0 ? "Next" : `#${i + 1}`}
                  </span>
                </motion.div>
              ))}
            </AnimatePresence>
          </div>

          <div className="w-full max-w-md mt-10 rounded-3xl border border-border bg-surface/90 p-5 shadow-sm">
            <div className="text-center">
              <p className="text-sm font-semibold uppercase tracking-[0.2em] text-muted-foreground">Display mode only</p>
              <p className="text-2xl font-bold text-foreground">Live queue board</p>
              <p className="text-sm text-muted-foreground mt-2">The camera and YOLO analyzer are now on a separate page.</p>
            </div>
          </div>
        </div>
      </div>

      {/* Bottom ticker */}
      <div className="relative bg-primary/5 border-t border-primary/10 py-3 overflow-hidden">
        <div className="animate-ticker whitespace-nowrap">
          <span className="text-sm text-primary/80 font-medium">
            ✦ Thank you for your patience &nbsp;&nbsp;•&nbsp;&nbsp; Average wait today: 8 mins &nbsp;&nbsp;•&nbsp;&nbsp; AI-powered crowd prediction active &nbsp;&nbsp;•&nbsp;&nbsp; Please have your documents ready &nbsp;&nbsp;•&nbsp;&nbsp; System status: Online ✦
          </span>
        </div>
      </div>
    </div>
  );
};

export default DisplayPage;
