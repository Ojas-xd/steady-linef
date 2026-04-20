import { QRCodeSVG } from "qrcode.react";
import { motion } from "framer-motion";
import { Scan, Smartphone, Clock, Users, ArrowRight } from "lucide-react";
import { Link } from "react-router-dom";

const QRScanPage = () => {
  const tokenUrl = `${window.location.origin}/token`;

  return (
    <div className="min-h-screen bg-background flex flex-col items-center justify-center p-4 relative overflow-hidden">
      {/* Background effects */}
      <div className="absolute inset-0 bg-grid-pattern opacity-20" />
      <div className="absolute top-1/4 left-1/2 -translate-x-1/2 w-[600px] h-[600px] rounded-full bg-primary/5 blur-3xl" />
      <div className="absolute bottom-1/4 left-1/4 w-[400px] h-[400px] rounded-full bg-accent/5 blur-3xl" />

      <div className="relative z-10 w-full max-w-md">
        {/* Header */}
        <motion.div
          initial={{ opacity: 0, y: -20 }}
          animate={{ opacity: 1, y: 0 }}
          className="text-center mb-8"
        >
          <div className="inline-flex items-center gap-2 px-4 py-2 rounded-full bg-primary/10 border border-primary/20 text-primary text-sm font-semibold mb-4">
            <Scan className="w-4 h-4" />
            Quick Queue Entry
          </div>
          <h1 className="text-3xl font-black text-foreground">Join the Queue</h1>
          <p className="text-muted-foreground mt-2">Scan the QR code with your phone to get your token</p>
        </motion.div>

        {/* QR Code Card */}
        <motion.div
          initial={{ opacity: 0, scale: 0.95 }}
          animate={{ opacity: 1, scale: 1 }}
          transition={{ delay: 0.1 }}
          className="glass-card rounded-3xl p-8 text-center mb-6"
        >
          <div className="bg-white rounded-2xl p-6 inline-block shadow-lg">
            <QRCodeSVG
              value={tokenUrl}
              size={200}
              bgColor="#ffffff"
              fgColor="#1e293b"
              level="H"
              includeMargin={false}
            />
          </div>
          <p className="text-sm text-muted-foreground mt-4">
            Point your camera at this code
          </p>
        </motion.div>

        {/* Instructions */}
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.2 }}
          className="space-y-3 mb-6"
        >
          <div className="flex items-center gap-4 p-4 rounded-xl bg-secondary/50">
            <div className="w-10 h-10 rounded-lg bg-primary/10 flex items-center justify-center flex-shrink-0">
              <Smartphone className="w-5 h-5 text-primary" />
            </div>
            <div className="text-left">
              <p className="font-semibold text-foreground">1. Scan with your phone</p>
              <p className="text-sm text-muted-foreground">Use your camera or QR scanner app</p>
            </div>
          </div>

          <div className="flex items-center gap-4 p-4 rounded-xl bg-secondary/50">
            <div className="w-10 h-10 rounded-lg bg-accent/10 flex items-center justify-center flex-shrink-0">
              <Users className="w-5 h-5 text-accent" />
            </div>
            <div className="text-left">
              <p className="font-semibold text-foreground">2. Enter your details</p>
              <p className="text-sm text-muted-foreground">Name and phone number required</p>
            </div>
          </div>

          <div className="flex items-center gap-4 p-4 rounded-xl bg-secondary/50">
            <div className="w-10 h-10 rounded-lg bg-warning/10 flex items-center justify-center flex-shrink-0">
              <Clock className="w-5 h-5 text-warning" />
            </div>
            <div className="text-left">
              <p className="font-semibold text-foreground">3. Get real-time updates</p>
              <p className="text-sm text-muted-foreground">Track your position in queue</p>
            </div>
          </div>
        </motion.div>

        {/* Direct link option */}
        <motion.div
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          transition={{ delay: 0.3 }}
          className="text-center"
        >
          <p className="text-sm text-muted-foreground mb-3">Can&apos;t scan the code?</p>
          <Link
            to="/token"
            className="inline-flex items-center gap-2 px-6 py-3 rounded-xl bg-secondary border border-border text-foreground font-semibold hover:bg-secondary/80 transition-colors"
          >
            Click here to join <ArrowRight className="w-4 h-4" />
          </Link>
        </motion.div>

        {/* Footer */}
        <motion.p
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          transition={{ delay: 0.4 }}
          className="text-center text-xs text-muted-foreground mt-8"
        >
          AI-Powered Queue Management System
        </motion.p>
      </div>
    </div>
  );
};

export default QRScanPage;
