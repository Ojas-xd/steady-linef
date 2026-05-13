import { useEffect, useRef, useState } from "react";
import LiveClock from "@/components/LiveClock";
import { Camera, Zap, Activity } from "lucide-react";
import { crowdApi } from "@/lib/api";

const CameraPage = () => {
  const [cameraActive, setCameraActive] = useState(false);
  const [cameraError, setCameraError] = useState<string | null>(null);
  const [analysisCount, setAnalysisCount] = useState<number | null>(null);
  const [annotatedImage, setAnnotatedImage] = useState<string | null>(null);
  const [detections, setDetections] = useState<Array<{ box: number[]; confidence: number }>>([]);
  const [isAnalyzing, setIsAnalyzing] = useState(false);
  const [autoAnalyzeEnabled, setAutoAnalyzeEnabled] = useState(true);
  const [showAnnotated, setShowAnnotated] = useState(true);
  const [healthStatus, setHealthStatus] = useState<{
    status: string;
    model_loaded?: boolean;
    error?: string;
    message?: string;
  } | null>(null);
  const [isCheckingHealth, setIsCheckingHealth] = useState(false);
  const videoRef = useRef<HTMLVideoElement | null>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const analysisTimerRef = useRef<number | null>(null);

  const checkHealth = async () => {
    setIsCheckingHealth(true);
    try {
      const status = await crowdApi.getHealth();
      setHealthStatus(status);
      console.log("[YOLO] Health check:", status);
    } catch (err: any) {
      setHealthStatus({ status: "error", error: err.message });
      console.error("[YOLO] Health check failed:", err);
    } finally {
      setIsCheckingHealth(false);
    }
  };

  const stopCamera = () => {
    if (analysisTimerRef.current !== null) {
      window.clearInterval(analysisTimerRef.current);
      analysisTimerRef.current = null;
    }
    if (streamRef.current) {
      streamRef.current.getTracks().forEach((track) => track.stop());
      streamRef.current = null;
    }
    setCameraActive(false);
  };

  const startCamera = async () => {
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ video: true, audio: false });
      streamRef.current = stream;
      if (videoRef.current) {
        videoRef.current.srcObject = stream;
        await videoRef.current.play();
      }
      setCameraError(null);
      setCameraActive(true);
    } catch (error) {
      console.error("Camera start failed", error);
      setCameraError("Unable to access the camera. Please allow camera permission or use a supported browser.");
    }
  };

  const captureFrame = async (): Promise<Blob | null> => {
    const video = videoRef.current;
    if (!video || video.readyState < 2) return null;

    const canvas = document.createElement("canvas");
    const originalWidth = video.videoWidth || 640;
    const originalHeight = video.videoHeight || 480;
    const maxWidth = 960;
    const scale = originalWidth > maxWidth ? maxWidth / originalWidth : 1;
    canvas.width = Math.round(originalWidth * scale);
    canvas.height = Math.round(originalHeight * scale);
    const ctx = canvas.getContext("2d");
    if (!ctx) return null;
    ctx.drawImage(video, 0, 0, canvas.width, canvas.height);

    return await new Promise((resolve) => {
      canvas.toBlob((blob) => resolve(blob), "image/jpeg", 0.8);
    });
  };

  const captureAndAnalyze = async () => {
    if (!cameraActive || isAnalyzing) {
      setCameraError("Start the camera first before analyzing a frame.");
      return;
    }

    setIsAnalyzing(true);
    try {
      const blob = await captureFrame();
      if (!blob) throw new Error("Camera frame is not ready.");
      const file = new File([blob], "frame.jpg", { type: "image/jpeg" });
      const result = await crowdApi.analyzeFrame(file);
      setAnalysisCount(result.count);
      setAnnotatedImage(result.image || null);
      setDetections(result.detections || []);
      setCameraError(null);
    } catch (error) {
      console.error("YOLO analysis failed", error);
      const message =
        error instanceof Error ? error.message : "Unable to analyze the camera frame. Try again.";
      setCameraError(message);
    } finally {
      setIsAnalyzing(false);
    }
  };

  useEffect(() => {
    if (!cameraActive || !autoAnalyzeEnabled) {
      if (analysisTimerRef.current !== null) {
        window.clearInterval(analysisTimerRef.current);
        analysisTimerRef.current = null;
      }
      return;
    }

    const runAnalysis = () => {
      void captureAndAnalyze();
    };

    runAnalysis();
    analysisTimerRef.current = window.setInterval(runAnalysis, 3000);

    return () => {
      if (analysisTimerRef.current !== null) {
        window.clearInterval(analysisTimerRef.current);
        analysisTimerRef.current = null;
      }
    };
  }, [cameraActive, autoAnalyzeEnabled]);

  useEffect(() => {
    return () => {
      stopCamera();
    };
  }, []);

  return (
    <div className="min-h-screen bg-background text-foreground">
      <div className="relative bg-primary/5 border-b border-primary/10 px-6 lg:px-10 py-6">
        <div className="max-w-7xl mx-auto flex flex-col lg:flex-row items-start lg:items-center justify-between gap-4">
          <div className="flex items-center gap-3">
            <div className="w-12 h-12 rounded-2xl hero-gradient-bg flex items-center justify-center shadow-lg">
              <Zap className="w-6 h-6 text-primary-foreground" />
            </div>
            <div>
              <p className="text-sm uppercase tracking-[0.24em] text-muted-foreground font-semibold">YOLO Camera</p>
              <h1 className="text-3xl font-bold">Live People Counter</h1>
            </div>
          </div>
          <LiveClock className="text-xl lg:text-3xl font-bold text-foreground font-mono" />
        </div>
      </div>

      <div className="max-w-7xl mx-auto px-6 lg:px-10 py-10 grid gap-10 lg:grid-cols-[1.4fr_0.9fr]">
        <div className="rounded-[2rem] border border-border bg-surface/80 p-6 shadow-sm">
          <div className="flex items-center justify-between mb-6">
            <div>
              <p className="text-sm text-muted-foreground uppercase tracking-[0.24em]">Camera Feed</p>
              <h2 className="text-2xl font-bold mt-2">Capture frame for YOLO</h2>
            </div>
            <div className="inline-flex items-center gap-2 rounded-2xl bg-primary/10 px-4 py-3 text-sm font-semibold text-primary">
              <Camera className="w-5 h-5" /> Live model
            </div>
          </div>

          {/* Toggle between live video and annotated view */}
          {annotatedImage && (
            <div className="mb-4 flex items-center justify-between rounded-xl border border-border/70 bg-background px-4 py-3">
              <p className="text-sm text-muted-foreground">View mode</p>
              <div className="flex gap-2">
                <button
                  type="button"
                  onClick={() => setShowAnnotated(false)}
                  className={`rounded-lg px-3 py-1.5 text-xs font-semibold transition ${
                    !showAnnotated ? "bg-primary text-primary-foreground" : "bg-secondary text-foreground"
                  }`}
                >
                  Live Camera
                </button>
                <button
                  type="button"
                  onClick={() => setShowAnnotated(true)}
                  className={`rounded-lg px-3 py-1.5 text-xs font-semibold transition ${
                    showAnnotated ? "bg-primary text-primary-foreground" : "bg-secondary text-foreground"
                  }`}
                >
                  YOLO Detection
                </button>
              </div>
            </div>
          )}

          <div className="rounded-[2rem] overflow-hidden border border-border/70 bg-black/5 mb-4 relative">
            {annotatedImage && showAnnotated ? (
              <img 
                src={annotatedImage} 
                alt="YOLO detections" 
                className="w-full h-[420px] object-contain bg-black"
              />
            ) : (
              <video ref={videoRef} className="w-full h-[420px] object-cover bg-black" muted playsInline />
            )}
            {!cameraActive && !annotatedImage && (
              <div className="absolute inset-0 flex flex-col items-center justify-center gap-3 bg-black/40 text-center px-6">
                <p className="text-base font-semibold text-white">Camera preview will appear here</p>
                <p className="text-sm text-muted-foreground">Click start to grant browser camera access.</p>
              </div>
            )}
          </div>

          {/* Health Status */}
          <div className="mb-4 flex items-center justify-between rounded-xl border border-border/70 bg-background px-4 py-3">
            <div className="flex items-center gap-2">
              <Activity className="w-4 h-4 text-muted-foreground" />
              <span className="text-sm text-muted-foreground">YOLO Model</span>
              {healthStatus && (
                <span
                  className={`text-xs font-semibold px-2 py-0.5 rounded ${
                    healthStatus.model_loaded
                      ? "bg-accent/20 text-accent"
                      : healthStatus.status === "pending"
                        ? "bg-amber-500/15 text-amber-700 dark:text-amber-400"
                        : "bg-destructive/20 text-destructive"
                  }`}
                >
                  {healthStatus.model_loaded
                    ? "Ready"
                    : healthStatus.status === "pending"
                      ? "Loading…"
                      : "Not Ready"}
                </span>
              )}
            </div>
            <button
              onClick={checkHealth}
              disabled={isCheckingHealth}
              className="text-xs font-semibold text-primary hover:text-primary/80 disabled:opacity-50"
            >
              {isCheckingHealth ? "Checking..." : "Check Health"}
            </button>
          </div>

          {healthStatus?.message && healthStatus.status === "pending" && (
            <div className="mb-4 rounded-xl border border-amber-500/20 bg-amber-500/10 p-3">
              <p className="text-xs text-amber-800 dark:text-amber-200 font-medium">{healthStatus.message}</p>
            </div>
          )}

          {healthStatus?.error && (
            <div className="mb-4 rounded-xl border border-destructive/20 bg-destructive/10 p-3">
              <p className="text-xs text-destructive font-semibold">Error: {healthStatus.error}</p>
            </div>
          )}

          {cameraError && (
            <div className="mb-4 rounded-xl border border-destructive/20 bg-destructive/10 p-3">
              <p className="text-xs text-destructive font-semibold">{cameraError}</p>
            </div>
          )}

          <div className="grid gap-3 sm:grid-cols-2">
            <button
              type="button"
              onClick={cameraActive ? stopCamera : startCamera}
              className="inline-flex items-center justify-center rounded-xl bg-primary px-4 py-3 text-sm font-semibold text-primary-foreground transition hover:bg-primary/90"
            >
              {cameraActive ? "Stop camera" : "Start camera"}
            </button>
            <button
              type="button"
              onClick={captureAndAnalyze}
              disabled={!cameraActive || isAnalyzing}
              className="inline-flex items-center justify-center rounded-xl border border-border bg-background px-4 py-3 text-sm font-semibold text-foreground transition hover:bg-secondary/90 disabled:cursor-not-allowed disabled:opacity-50"
            >
              {isAnalyzing ? "Analyzing…" : "Capture & analyze"}
            </button>
          </div>

          <div className="mt-4 flex items-center justify-between rounded-xl border border-border/70 bg-background px-4 py-3">
            <p className="text-sm text-muted-foreground">Auto analyze every 3 seconds</p>
            <button
              type="button"
              onClick={() => setAutoAnalyzeEnabled((prev) => !prev)}
              className={`rounded-lg px-3 py-1.5 text-xs font-semibold transition ${
                autoAnalyzeEnabled
                  ? "bg-primary text-primary-foreground"
                  : "bg-secondary text-foreground"
              }`}
            >
              {autoAnalyzeEnabled ? "On" : "Off"}
            </button>
          </div>
        </div>

        <div className="rounded-[2rem] border border-border bg-surface/80 p-6 shadow-sm">
          <div className="mb-6">
            <p className="text-sm text-muted-foreground uppercase tracking-[0.24em]">Analysis results</p>
            <h2 className="text-2xl font-bold mt-2">People detected</h2>
          </div>

          {/* Annotated Image Preview */}
          {annotatedImage && (
            <div className="rounded-[2rem] border border-border/70 bg-background p-4 mb-4">
              <p className="text-sm text-muted-foreground uppercase tracking-[0.24em] mb-3 text-center">YOLO Detection View</p>
              <img 
                src={annotatedImage} 
                alt="YOLO detections" 
                className="w-full h-auto rounded-xl border border-border"
              />
            </div>
          )}

          <div className="rounded-[2rem] border border-border/70 bg-background p-6 text-center">
            <p className="text-sm text-muted-foreground uppercase tracking-[0.24em] mb-3">People Count</p>
            <p className="text-6xl font-black text-primary">{analysisCount ?? "--"}</p>
            <p className="text-sm text-muted-foreground mt-3">YOLOv8 detected people in the current frame</p>
          </div>

          {/* Detection Details */}
          {detections.length > 0 && (
            <div className="mt-4 rounded-[2rem] border border-border/70 bg-background p-4">
              <p className="text-sm text-muted-foreground uppercase tracking-[0.24em] mb-3">Detection Details</p>
              <div className="max-h-40 overflow-y-auto space-y-2">
                {detections.map((det, i) => (
                  <div key={i} className="flex items-center justify-between p-2 rounded-lg bg-secondary/50">
                    <span className="text-sm font-medium">Person {i + 1}</span>
                    <span className="text-xs font-mono bg-primary/10 text-primary px-2 py-1 rounded">
                      {(det.confidence * 100).toFixed(0)}%
                    </span>
                  </div>
                ))}
              </div>
            </div>
          )}

          <div className="mt-8 space-y-4 text-sm text-muted-foreground">
            <p>• Use a modern browser with HTTPS or localhost for camera access.</p>
            <p>• The backend must be running at the configured API URL.</p>
            <p>• If the model endpoint is unavailable, the page will show an error.</p>
          </div>
        </div>
      </div>
    </div>
  );
};

export default CameraPage;
