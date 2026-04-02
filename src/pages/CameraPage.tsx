import { useEffect, useRef, useState } from "react";
import LiveClock from "@/components/LiveClock";
import { Camera, Zap } from "lucide-react";
import { crowdApi } from "@/lib/api";

const CameraPage = () => {
  const [cameraActive, setCameraActive] = useState(false);
  const [cameraError, setCameraError] = useState<string | null>(null);
  const [analysisCount, setAnalysisCount] = useState<number | null>(null);
  const [isAnalyzing, setIsAnalyzing] = useState(false);
  const videoRef = useRef<HTMLVideoElement | null>(null);
  const streamRef = useRef<MediaStream | null>(null);

  const stopCamera = () => {
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
    canvas.width = video.videoWidth || 640;
    canvas.height = video.videoHeight || 480;
    const ctx = canvas.getContext("2d");
    if (!ctx) return null;
    ctx.drawImage(video, 0, 0, canvas.width, canvas.height);

    return await new Promise((resolve) => {
      canvas.toBlob((blob) => resolve(blob), "image/jpeg", 0.8);
    });
  };

  const captureAndAnalyze = async () => {
    if (!cameraActive) {
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
      setCameraError(null);
    } catch (error) {
      console.error("YOLO analysis failed", error);
      setCameraError("Unable to analyze the camera frame. Try again.");
    } finally {
      setIsAnalyzing(false);
    }
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

          <div className="rounded-[2rem] overflow-hidden border border-border/70 bg-black/5 mb-4 relative">
            <video ref={videoRef} className="w-full h-[420px] object-cover bg-black" muted playsInline />
            {!cameraActive && (
              <div className="absolute inset-0 flex flex-col items-center justify-center gap-3 bg-black/40 text-center px-6">
                <p className="text-base font-semibold text-white">Camera preview will appear here</p>
                <p className="text-sm text-muted-foreground">Click start to grant browser camera access.</p>
              </div>
            )}
          </div>

          {cameraError && <p className="mb-4 text-sm text-destructive">{cameraError}</p>}

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
        </div>

        <div className="rounded-[2rem] border border-border bg-surface/80 p-6 shadow-sm">
          <div className="mb-6">
            <p className="text-sm text-muted-foreground uppercase tracking-[0.24em]">Analysis results</p>
            <h2 className="text-2xl font-bold mt-2">People detected</h2>
          </div>

          <div className="rounded-[2rem] border border-border/70 bg-background p-6 text-center">
            <p className="text-sm text-muted-foreground uppercase tracking-[0.24em] mb-3">Last captured frame</p>
            <p className="text-6xl font-black text-primary">{analysisCount ?? "--"}</p>
            <p className="text-sm text-muted-foreground mt-3">The YOLO model counts people from the current camera image.</p>
          </div>

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
