import { FormEvent, useEffect, useMemo, useRef, useState } from "react";
import { motion } from "framer-motion";
import { Clock, Users, ArrowLeft } from "lucide-react";
import { QRCodeSVG } from "qrcode.react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { tokensApi } from "@/lib/api";

const TokenPage = () => {
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const tokenId = searchParams.get("id");
  const [formName, setFormName] = useState("");
  const [formPhone, setFormPhone] = useState("");
  const [formError, setFormError] = useState<string | null>(null);
  const [isIssuingToken, setIsIssuingToken] = useState(false);

  const [tokenData, setTokenData] = useState({
    id: tokenId ?? "N/A",
    tokenNumber: "",
    status: "waiting" as "waiting" | "serving" | "completed" | "cancelled",
    position: 0,
    peopleAhead: 0,
    estimatedWait: 0,
    counter: 0,
    serviceTime: 0,  // Actual time taken to complete service
    completedAt: "",  // When service was completed
  });
  const [isCancelling, setIsCancelling] = useState(false);

  const hasTokenId = !!tokenId;

  // Notification when status changes to serving
  const prevStatusRef = useRef<string | null>(null);
  const audioRef = useRef<HTMLAudioElement | null>(null);
  const [notificationPermission, setNotificationPermission] = useState<NotificationPermission>("default");
  
  // Request notification permission on load
  useEffect(() => {
    if ("Notification" in window) {
      Notification.requestPermission().then(permission => {
        setNotificationPermission(permission);
        console.log("[TokenPage] Notification permission:", permission);
      });
    }
  }, []);

  useEffect(() => {
    if (!tokenId) return;

    setTokenData((prev) => ({ ...prev, id: tokenId }));

    const fetchStatus = async () => {
      try {
        // Fetch both status and token details
        const [statusData, tokenData] = await Promise.all([
          tokensApi.getQueueStatus(tokenId),
          tokensApi.getById(tokenId),
        ]);
        
        // position from backend is 1-indexed (includes user), so peopleAhead = position - 1
        const peopleAhead = statusData.status === "waiting" ? Math.max(0, statusData.position - 1) : 0;
        
        // Check if status changed to serving - trigger notification
        const prevStatus = prevStatusRef.current;
        if (prevStatus && prevStatus !== "serving" && statusData.status === "serving") {
          // Play notification sound
          if (audioRef.current) {
            audioRef.current.play().catch(() => {});
          }
          // Vibrate on mobile devices
          if (navigator.vibrate) {
            navigator.vibrate([200, 100, 200, 100, 400]);
          }
          // Show browser notification
          if ("Notification" in window && Notification.permission === "granted") {
            new Notification("🎉 Your turn is here!", {
              body: `Token #${tokenData?.token_number || tokenId} - Please proceed to the counter`,
              icon: "/favicon.ico",
              requireInteraction: true,
            });
          }
        }
        prevStatusRef.current = statusData.status;
        
        setTokenData((prev) => ({
          ...prev,
          tokenNumber: tokenData?.token_number || prev.tokenNumber,
          position: statusData.position,
          peopleAhead,
          estimatedWait: statusData.estimated_wait,
          status: statusData.status as typeof prev.status,
          counter: statusData.counter || prev.counter,
          serviceTime: tokenData?.service_time || prev.serviceTime,
          completedAt: tokenData?.completed_at || prev.completedAt,
        }));
        setFormError(null);
      } catch {
        setFormError("Unable to fetch token status. Please refresh and try again.");
      }
    };

    fetchStatus();
    // Faster refresh when waiting (5s) vs serving/completed (10s)
    const refreshInterval = tokenData.status === "waiting" ? 5000 : 10000;
    const interval = setInterval(fetchStatus, refreshInterval);
    return () => clearInterval(interval);
  }, [tokenId, tokenData.status]);

  const progressPercent = useMemo(() => {
    if (tokenData.status !== "waiting") return 100;
    // When joining, peopleAhead starts at some number and decreases as queue moves
    // Progress = 100% - (peopleAhead / initialEstimate * 100)
    // For simplicity, use inverse of peopleAhead relative to initial position
    if (tokenData.peopleAhead <= 0) return 100;
    // Estimate: when joined, people ahead was roughly position - 1
    const initialEstimate = Math.max(tokenData.position, tokenData.peopleAhead + 1);
    return Math.min(100, Math.max(0, ((initialEstimate - tokenData.peopleAhead) / initialEstimate) * 100));
  }, [tokenData.position, tokenData.status, tokenData.peopleAhead]);

  const statusConfig = {
    waiting: { color: "bg-warning/15 text-warning border-warning/20", dotColor: "bg-warning", label: "Waiting", message: "Please wait, we'll call you soon 🙏", emoji: "⏳" },
    serving: { color: "bg-primary/15 text-primary border-primary/20", dotColor: "bg-primary animate-pulse-slow", label: "Now Serving", message: "Your turn is coming up! 🎉", emoji: "🔔" },
    completed: { color: "bg-accent/15 text-accent border-accent/20", dotColor: "bg-accent", label: "Completed", message: `Service completed in ${tokenData.serviceTime}m at Counter ${tokenData.counter} ✅`, emoji: "✅" },
    cancelled: { color: "bg-destructive/15 text-destructive border-destructive/20", dotColor: "bg-destructive", label: "Cancelled", message: "You have left the queue", emoji: "❌" },
  };

  const config = statusConfig[tokenData.status];
  const shareTokenUrl = tokenData.tokenNumber 
    ? `${window.location.origin}/token?num=${encodeURIComponent(tokenData.tokenNumber)}`
    : `${window.location.origin}/token?id=${encodeURIComponent(tokenData.id)}`;
  
  // Check if just started serving (for visual notification)
  const justStartedServing = tokenData.status === "serving" && prevStatusRef.current === "serving";

  const handleJoinQueue = async (event: FormEvent) => {
    event.preventDefault();
    setFormError(null);

    const normalizedName = formName.trim();
    const normalizedPhone = formPhone.trim();

    if (!normalizedName || !normalizedPhone) {
      setFormError("Please enter both name and phone number.");
      return;
    }

    setIsIssuingToken(true);
    try {
      const token = await tokensApi.issueToken({
        customerName: normalizedName,
        customerPhone: normalizedPhone,
      });
      // Store token number for display, but use ID for URL
      setTokenData(prev => ({ ...prev, tokenNumber: token.token_number || "" }));
      navigate(`/token?id=${encodeURIComponent(token.id)}`);
    } catch {
      setFormError("Unable to join queue right now. Please try again.");
    } finally {
      setIsIssuingToken(false);
    }
  };

  const handleCancel = async () => {
    if (!tokenId) return;
    if (!window.confirm("Are you sure you want to leave the queue?")) return;

    setIsCancelling(true);
    try {
      await tokensApi.cancel(tokenId);
      setTokenData((prev) => ({ ...prev, status: "cancelled" }));
    } catch {
      setFormError("Unable to cancel. Please try again.");
    } finally {
      setIsCancelling(false);
    }
  };

  return (
    <div className="min-h-screen flex flex-col items-center justify-center p-4 relative overflow-hidden">
      {/* Audio for notification */}
      <audio
        ref={audioRef}
        preload="auto"
        src="data:audio/wav;base64,UklGRnoGAABXQVZFZm10IBAAAAABAAEAQB8AAEAfAAABAAgAZGF0YQoGAACBhYqFbF1fdJivrJBhNjVgodDbq2EcBj+a2/LDciUFLIHO8tiJNwgZaLvt559NEAxQp+PwtmMcBjiR1/LMeSwFJHfH8N2QQAoUXrTp66hVFApGn+DyvmwhBTGH0fPTgjMGHm7A7+OZSA0PVanu87plHQUuh9Dz2YU2Bhxqv+zplkcODVGm5O+4ZSAEMYrO89GFNwYdcfH+7JtJDQtPp+XyxWUeBjqS1/LQiTYGH3Dy/+ybSA0MTaLs8blmHwU2kNjyxYU1Bhxw8v7omUgNC1Ko6O/BZSAFNo/R8tSFNwYccPH+75xJDQxPp+zwuGUhBDeP0/LNhjYGHG7w/+ydSA0LUqzs8blnIAU2j9Xy0YU1Bhxvv//CdSU0LVKo7O++ZSAFNo/V8tGFNwYccPD+8J1KDQ1So+zzvmUgBTeP1/LShjYGHG/z/vCc="
      />
      
      {/* Background effects */}
      <div className="absolute inset-0 bg-grid-pattern opacity-20" />
      <div className="absolute top-1/3 left-1/2 -translate-x-1/2 w-[500px] h-[500px] rounded-full bg-primary/5 blur-3xl" />

      <div className="relative z-10 w-full max-w-sm">
        <Link to="/" className="flex items-center gap-2 text-sm text-muted-foreground hover:text-foreground transition-colors mb-6">
          <ArrowLeft className="w-4 h-4" /> Back to Home
        </Link>

        {!hasTokenId ? (
          <motion.form
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            onSubmit={handleJoinQueue}
            className="glass-card rounded-2xl overflow-hidden"
          >
            <div className="hero-gradient-bg p-6 text-center">
              <p className="text-primary-foreground/70 text-xs font-semibold uppercase tracking-widest">Get Your Token</p>
              <p className="text-3xl font-black text-primary-foreground mt-2">Join Queue</p>
            </div>
            <div className="p-6 space-y-4">
              <div>
                <label className="mb-2 block text-sm font-semibold text-foreground" htmlFor="customer-name">Full Name</label>
                <input
                  id="customer-name"
                  type="text"
                  value={formName}
                  onChange={(e) => setFormName(e.target.value)}
                  placeholder="Enter your name"
                  className="w-full rounded-xl border border-border bg-background px-4 py-3 text-sm text-foreground outline-none focus:ring-2 focus:ring-primary/40"
                  required
                />
              </div>
              <div>
                <label className="mb-2 block text-sm font-semibold text-foreground" htmlFor="customer-phone">Phone Number</label>
                <input
                  id="customer-phone"
                  type="tel"
                  value={formPhone}
                  onChange={(e) => setFormPhone(e.target.value)}
                  placeholder="Enter your phone number"
                  className="w-full rounded-xl border border-border bg-background px-4 py-3 text-sm text-foreground outline-none focus:ring-2 focus:ring-primary/40"
                  required
                />
              </div>
              {formError && <p className="text-sm text-destructive">{formError}</p>}
              <button
                type="submit"
                disabled={isIssuingToken}
                className="w-full rounded-xl hero-gradient-bg px-4 py-3 text-sm font-semibold text-primary-foreground transition hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-60"
              >
                {isIssuingToken ? "Joining queue..." : "Join Queue"}
              </button>
            </div>
          </motion.form>
        ) : (
          <motion.div
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            className="glass-card rounded-2xl overflow-hidden"
          >
            {/* Gradient header */}
            <div className="hero-gradient-bg p-6 text-center">
              <p className="text-primary-foreground/70 text-xs font-semibold uppercase tracking-widest">Your Token Number</p>
              <motion.p
                key={tokenData.tokenNumber || tokenData.id}
                initial={{ scale: 0.5 }}
                animate={{ scale: 1 }}
                className="text-6xl font-black text-primary-foreground mt-2 font-mono"
              >
                #{tokenData.tokenNumber || tokenData.id.slice(0, 8)}
              </motion.p>
            </div>

            <div className="p-6 space-y-5">
            {/* Notification Banner - When Serving */}
              {tokenData.status === "serving" && (
                <motion.div
                  initial={{ opacity: 0, scale: 0.9 }}
                  animate={{ opacity: 1, scale: 1 }}
                  className="bg-accent/20 border-2 border-accent rounded-xl p-4 text-center animate-pulse-slow"
                >
                  <p className="text-2xl mb-1">🎉</p>
                  <p className="text-lg font-bold text-accent">Your turn is here!</p>
                  <p className="text-sm text-accent/80">Please proceed to the counter</p>
                </motion.div>
              )}
              
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
                  <p className="text-2xl font-bold text-foreground font-mono">{tokenData.peopleAhead}</p>
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
                    animate={{ width: `${Math.max(0, Math.min(100, progressPercent))}%` }}
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
              {formError && <p className="text-sm text-destructive">{formError}</p>}

            {/* QR Code */}
              <div className="flex flex-col items-center pt-2">
                <div className="p-3 bg-foreground rounded-xl">
                  <QRCodeSVG
                    value={shareTokenUrl}
                    size={100}
                    bgColor="hsl(210 40% 98%)"
                    fgColor="hsl(222 47% 11%)"
                  />
                </div>
                <p className="text-[11px] text-muted-foreground mt-2">Scan to share your token link</p>
              </div>

            {/* Cancel Button - Only when waiting */}
              {tokenData.status === "waiting" && (
                <button
                  type="button"
                  onClick={handleCancel}
                  disabled={isCancelling}
                  className="w-full rounded-xl border-2 border-destructive/30 bg-destructive/10 px-4 py-3 text-sm font-semibold text-destructive transition hover:bg-destructive/20 disabled:opacity-50"
                >
                  {isCancelling ? "Cancelling..." : "Leave Queue"}
                </button>
              )}
            </div>
          </motion.div>
        )}

        {hasTokenId && (
          <p className="text-center text-[11px] text-muted-foreground mt-4">
            Auto-refreshes every 15 seconds • Token ID: {tokenData.id}
          </p>
        )}
      </div>
    </div>
  );
};

export default TokenPage;
