import { useCallback, useEffect, useRef, useState } from "react";
import LiveClock from "@/components/LiveClock";
import { Camera, Zap, Activity, SquareDashed } from "lucide-react";
import { crowdApi } from "@/lib/api";

/** Map pointer to normalized [0,1] coords in actual video pixels (handles letterboxing with object-contain). */
function clientToNormVideo(clientX: number, clientY: number, video: HTMLVideoElement): { nx: number; ny: number } | null {
  const vw = video.videoWidth;
  const vh = video.videoHeight;
  if (!vw || !vh) return null;
  const rect = video.getBoundingClientRect();
  const scale = Math.min(rect.width / vw, rect.height / vh);
  const dispW = vw * scale;
  const dispH = vh * scale;
  const offX = rect.left + (rect.width - dispW) / 2;
  const offY = rect.top + (rect.height - dispH) / 2;
  const mx = clientX - offX;
  const my = clientY - offY;
  const nx = mx / dispW;
  const ny = my / dispH;
  if (nx < 0 || nx > 1 || ny < 0 || ny > 1) return null;
  return { nx, ny };
}

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
  const [queueZoneDraw, setQueueZoneDraw] = useState(false);
  const [roiNorm, setRoiNorm] = useState<{ x: number; y: number; w: number; h: number } | null>(null);
  const [zoneDragStart, setZoneDragStart] = useState<{ nx: number; ny: number } | null>(null);
  const [zoneDragCurrent, setZoneDragCurrent] = useState<{ nx: number; ny: number } | null>(null);
  const [queueZoneAppliedLast, setQueueZoneAppliedLast] = useState(false);
  const [framePersonTotal, setFramePersonTotal] = useState<number | null>(null);
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
    if (videoRef.current) {
      videoRef.current.srcObject = null;
    }
    setCameraActive(false);
  };

  const startCamera = async () => {
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ video: true, audio: false });
      streamRef.current = stream;
      const el = videoRef.current;
      if (!el) {
        stream.getTracks().forEach((t) => t.stop());
        throw new Error("Video element not mounted");
      }
      el.srcObject = stream;
      await el.play();
      setShowAnnotated(false);
      setCameraError(null);
      setCameraActive(true);
    } catch (error) {
      console.error("Camera start failed", error);
      setCameraError("Unable to access the camera. Please allow camera permission or use a supported browser.");
    }
  };

  /** Wait until the browser exposes non-zero video dimensions (avoids "frame not ready" on first ticks). */
  const waitForVideoDimensions = (video: HTMLVideoElement, maxMs = 5000): Promise<boolean> => {
    const ready = () =>
      video.videoWidth > 0 &&
      video.videoHeight > 0 &&
      video.readyState >= HTMLMediaElement.HAVE_CURRENT_DATA;

    if (ready()) return Promise.resolve(true);

    return new Promise((resolve) => {
      const start = Date.now();
      const finish = (ok: boolean) => {
        video.removeEventListener("loadeddata", onEvt);
        video.removeEventListener("loadedmetadata", onEvt);
        video.removeEventListener("canplay", onEvt);
        window.clearInterval(iv);
        resolve(ok);
      };
      const onEvt = () => {
        if (ready()) finish(true);
      };
      video.addEventListener("loadeddata", onEvt);
      video.addEventListener("loadedmetadata", onEvt);
      video.addEventListener("canplay", onEvt);
      const iv = window.setInterval(() => {
        if (ready()) finish(true);
        else if (Date.now() - start > maxMs) finish(false);
      }, 50);
    });
  };

  const waitOneVideoFrame = (video: HTMLVideoElement): Promise<void> =>
    new Promise((resolve) => {
      if (typeof video.requestVideoFrameCallback === "function") {
        video.requestVideoFrameCallback(() => resolve());
      } else {
        requestAnimationFrame(() => resolve());
      }
    });

  const captureFrame = async (): Promise<Blob | null> => {
    const video = videoRef.current;
    if (!video || !cameraActive) return null;

    const dimsOk = await waitForVideoDimensions(video);
    if (!dimsOk || !video.videoWidth || !video.videoHeight) return null;

    await waitOneVideoFrame(video);

    const canvas = document.createElement("canvas");
    const originalWidth = video.videoWidth;
    const originalHeight = video.videoHeight;
    const maxWidth = 960;
    const scale = originalWidth > maxWidth ? maxWidth / originalWidth : 1;
    canvas.width = Math.round(originalWidth * scale);
    canvas.height = Math.round(originalHeight * scale);
    const ctx = canvas.getContext("2d");
    if (!ctx) return null;
    try {
      ctx.drawImage(video, 0, 0, canvas.width, canvas.height);
    } catch {
      return null;
    }

    return await new Promise((resolve) => {
      canvas.toBlob(
        (blob) => {
          if (blob) resolve(blob);
          else {
            try {
              const data = canvas.toDataURL("image/jpeg", 0.85);
              const arr = data.split(",");
              const mime = arr[0].match(/:(.*?);/)?.[1] ?? "image/jpeg";
              const bstr = atob(arr[1] ?? "");
              const u8 = new Uint8Array(bstr.length);
              for (let i = 0; i < bstr.length; i++) u8[i] = bstr.charCodeAt(i);
              resolve(new Blob([u8], { type: mime }));
            } catch {
              resolve(null);
            }
          }
        },
        "image/jpeg",
        0.8
      );
    });
  };

  const analyzeLockRef = useRef(false);

  const captureAndAnalyze = useCallback(async () => {
    if (!cameraActive || analyzeLockRef.current) {
      if (!cameraActive) setCameraError("Start the camera first before analyzing a frame.");
      return;
    }

    analyzeLockRef.current = true;
    setIsAnalyzing(true);
    try {
      const blob = await captureFrame();
      if (!blob) throw new Error("Camera frame is not ready. Switch to Live Camera view or wait a second after starting the camera.");
      const file = new File([blob], "frame.jpg", { type: "image/jpeg" });
      const roi =
        roiNorm && roiNorm.w > 0.03 && roiNorm.h > 0.03
          ? roiNorm
          : null;
      const result = await crowdApi.analyzeFrame(file, roi);
      setAnalysisCount(result.count);
      setAnnotatedImage(result.image || null);
      setDetections(result.detections || []);
      setQueueZoneAppliedLast(Boolean(result.queue_zone_applied));
      setFramePersonTotal(
        typeof result.total_persons_frame === "number" ? result.total_persons_frame : null
      );
      setCameraError(null);
    } catch (error) {
      console.error("YOLO analysis failed", error);
      const message =
        error instanceof Error ? error.message : "Unable to analyze the camera frame. Try again.";
      setCameraError(message);
    } finally {
      analyzeLockRef.current = false;
      setIsAnalyzing(false);
    }
  }, [cameraActive, roiNorm]);

  useEffect(() => {
    if (!cameraActive || !autoAnalyzeEnabled) {
      if (analysisTimerRef.current !== null) {
        window.clearInterval(analysisTimerRef.current);
        analysisTimerRef.current = null;
      }
      return;
    }

    let firstTimer: number | null = null;
    const runAnalysis = () => {
      void captureAndAnalyze();
    };

    firstTimer = window.setTimeout(runAnalysis, 400);
    analysisTimerRef.current = window.setInterval(runAnalysis, 3000);

    return () => {
      if (firstTimer !== null) window.clearTimeout(firstTimer);
      if (analysisTimerRef.current !== null) {
        window.clearInterval(analysisTimerRef.current);
        analysisTimerRef.current = null;
      }
    };
  }, [cameraActive, autoAnalyzeEnabled, captureAndAnalyze]);

  const onZonePointerDown = (e: React.MouseEvent) => {
    if (!queueZoneDraw || !videoRef.current) return;
    const p = clientToNormVideo(e.clientX, e.clientY, videoRef.current);
    if (!p) return;
    e.preventDefault();
    setZoneDragStart(p);
    setZoneDragCurrent(p);
  };

  const onZonePointerMove = (e: React.MouseEvent) => {
    if (!zoneDragStart || !videoRef.current) return;
    const p = clientToNormVideo(e.clientX, e.clientY, videoRef.current);
    if (p) setZoneDragCurrent(p);
  };

  const finishZoneDrag = () => {
    if (!zoneDragStart || !zoneDragCurrent) {
      setZoneDragStart(null);
      setZoneDragCurrent(null);
      return;
    }
    const x1 = zoneDragStart.nx;
    const y1 = zoneDragStart.ny;
    const x2 = zoneDragCurrent.nx;
    const y2 = zoneDragCurrent.ny;
    const x = Math.min(x1, x2);
    const y = Math.min(y1, y2);
    const w = Math.abs(x2 - x1);
    const h = Math.abs(y2 - y1);
    if (w > 0.03 && h > 0.03) {
      setRoiNorm({
        x: Math.max(0, Math.min(1 - w, x)),
        y: Math.max(0, Math.min(1 - h, y)),
        w: Math.min(w, 1),
        h: Math.min(h, 1),
      });
    }
    setZoneDragStart(null);
    setZoneDragCurrent(null);
  };

  const previewRect = (): { left: number; top: number; width: number; height: number } | null => {
    if (!zoneDragStart || !zoneDragCurrent) return null;
    const x = Math.min(zoneDragStart.nx, zoneDragCurrent.nx);
    const y = Math.min(zoneDragStart.ny, zoneDragCurrent.ny);
    const w = Math.abs(zoneDragCurrent.nx - zoneDragStart.nx);
    const h = Math.abs(zoneDragCurrent.ny - zoneDragStart.ny);
    return { left: x * 100, top: y * 100, width: w * 100, height: h * 100 };
  };

  const roiOverlayStyle = (): { left: string; top: string; width: string; height: string } | null => {
    if (!roiNorm) return null;
    return {
      left: `${roiNorm.x * 100}%`,
      top: `${roiNorm.y * 100}%`,
      width: `${roiNorm.w * 100}%`,
      height: `${roiNorm.h * 100}%`,
    };
  };

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

          <div className="rounded-[2rem] overflow-hidden border border-border/70 bg-black/5 mb-4 relative h-[420px] w-full">
            <video
              ref={videoRef}
              className={`absolute inset-0 z-0 h-full w-full object-contain bg-black pointer-events-none transition-opacity ${
                !cameraActive ? "opacity-0" : annotatedImage && showAnnotated ? "opacity-0" : "opacity-100"
              }`}
              muted
              playsInline
            />
            {annotatedImage && showAnnotated && (
              <img
                src={annotatedImage}
                alt="YOLO detections"
                className="relative z-20 h-full w-full object-contain bg-black"
              />
            )}
            {cameraActive && !(annotatedImage && showAnnotated) && (
              <div
                className={`absolute inset-0 z-10 ${queueZoneDraw ? "cursor-crosshair touch-none" : "pointer-events-none"}`}
                onMouseDown={queueZoneDraw ? onZonePointerDown : undefined}
                onMouseMove={queueZoneDraw ? onZonePointerMove : undefined}
                onMouseUp={queueZoneDraw ? finishZoneDrag : undefined}
                onMouseLeave={queueZoneDraw ? finishZoneDrag : undefined}
              >
                {queueZoneDraw && previewRect() && (
                  <div
                    className="absolute border-2 border-amber-400/90 bg-amber-400/15 pointer-events-none"
                    style={{
                      left: `${previewRect()!.left}%`,
                      top: `${previewRect()!.top}%`,
                      width: `${previewRect()!.width}%`,
                      height: `${previewRect()!.height}%`,
                    }}
                  />
                )}
                {roiOverlayStyle() && !zoneDragStart && (
                  <div
                    className="absolute border-2 border-cyan-400/90 bg-cyan-400/10 pointer-events-none"
                    style={roiOverlayStyle()!}
                  />
                )}
              </div>
            )}
            {!cameraActive && !annotatedImage && (
              <div className="absolute inset-0 flex flex-col items-center justify-center gap-3 bg-black/40 text-center px-6">
                <p className="text-base font-semibold text-white">Camera preview will appear here</p>
                <p className="text-sm text-muted-foreground">Click start to grant browser camera access.</p>
              </div>
            )}
          </div>

          {cameraActive && (
            <div className="mb-4 flex flex-wrap items-center gap-3 rounded-xl border border-border/70 bg-background px-4 py-3">
              <SquareDashed className="w-4 h-4 text-muted-foreground shrink-0" />
              <button
                type="button"
                onClick={() => setQueueZoneDraw((v) => !v)}
                className={`rounded-lg px-3 py-1.5 text-xs font-semibold transition ${
                  queueZoneDraw ? "bg-primary text-primary-foreground" : "bg-secondary text-foreground"
                }`}
              >
                {queueZoneDraw ? "Drawing zone…" : "Draw queue zone"}
              </button>
              <button
                type="button"
                onClick={() => {
                  setRoiNorm(null);
                  setZoneDragStart(null);
                  setZoneDragCurrent(null);
                  setQueueZoneDraw(false);
                }}
                className="rounded-lg px-3 py-1.5 text-xs font-semibold border border-border text-foreground hover:bg-secondary/80"
              >
                Clear zone
              </button>
              {roiNorm && (
                <p className="text-xs text-muted-foreground max-w-[14rem] sm:max-w-none">
                  Cyan box = queue area. Count uses people whose box center is inside it.
                </p>
              )}
            </div>
          )}

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
            <p className="text-sm text-muted-foreground mt-3">
              {queueZoneAppliedLast
                ? "People inside your drawn queue zone (box center must be inside the zone)."
                : "Detections across the full frame (draw a queue zone on live camera to count only that area)."}
            </p>
            {queueZoneAppliedLast && framePersonTotal !== null && (
              <p className="text-xs text-muted-foreground mt-2">
                Full frame detections: {framePersonTotal} — displayed count is in-zone only.
              </p>
            )}
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
