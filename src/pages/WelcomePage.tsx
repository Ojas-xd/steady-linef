import { Link } from "react-router-dom";
import { motion } from "framer-motion";
import { LayoutDashboard, Ticket, Monitor, BarChart3, Zap, ArrowRight, Users, Clock, Shield, Scan } from "lucide-react";

const features = [
  {
    icon: LayoutDashboard,
    title: "Staff Dashboard",
    description: "Real-time crowd monitoring, token management, and AI-powered forecasting.",
    to: "/dashboard",
    color: "text-primary",
    bgColor: "bg-primary/10",
    borderColor: "border-primary/20",
  },
  {
    icon: Scan,
    title: "QR Scan Entry",
    description: "Display QR code for customers to scan and join queue instantly.",
    to: "/qr",
    color: "text-primary",
    bgColor: "bg-primary/10",
    borderColor: "border-primary/20",
  },
  {
    icon: Ticket,
    title: "Customer Token",
    description: "Mobile-friendly token status with live queue position and estimated wait time.",
    to: "/token",
    color: "text-accent",
    bgColor: "bg-accent/10",
    borderColor: "border-accent/20",
  },
  {
    icon: Monitor,
    title: "Queue Display",
    description: "Full-screen TV display for waiting areas with live queue and announcements.",
    to: "/display",
    color: "text-warning",
    bgColor: "bg-warning/10",
    borderColor: "border-warning/20",
  },
  {
    icon: BarChart3,
    title: "Analytics",
    description: "Detailed insights, crowd trends, hourly distributions, and exportable reports.",
    to: "/analytics",
    color: "text-destructive",
    bgColor: "bg-destructive/10",
    borderColor: "border-destructive/20",
  },
];

const stats = [
  { icon: Users, value: "10K+", label: "Tokens Managed Daily" },
  { icon: Clock, value: "40%", label: "Wait Time Reduced" },
  { icon: Shield, value: "99.9%", label: "System Uptime" },
];

const WelcomePage = () => {
  return (
    <div className="min-h-screen relative overflow-hidden">
      {/* Animated background */}
      <div className="absolute inset-0 bg-grid-pattern opacity-30" />
      <div className="absolute top-1/4 -left-32 w-96 h-96 rounded-full bg-primary/5 blur-3xl animate-pulse-slow" />
      <div className="absolute bottom-1/4 -right-32 w-96 h-96 rounded-full bg-accent/5 blur-3xl animate-pulse-slow" style={{ animationDelay: "1s" }} />

      <div className="relative z-10">
        {/* Header */}
        <header className="flex items-center justify-between px-6 lg:px-16 py-6">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-xl hero-gradient-bg flex items-center justify-center">
              <Zap className="w-5 h-5 text-primary-foreground" />
            </div>
            <span className="text-lg font-bold text-foreground">AI Queue</span>
          </div>
          <Link
            to="/dashboard"
            className="px-5 py-2.5 rounded-xl hero-gradient-bg text-primary-foreground text-sm font-semibold hover:opacity-90 transition-opacity"
          >
            Open Dashboard
          </Link>
        </header>

        {/* Hero */}
        <section className="px-6 lg:px-16 pt-12 lg:pt-24 pb-16 max-w-6xl mx-auto text-center">
          <motion.div
            initial={{ opacity: 0, y: 30 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.6 }}
          >
            <div className="inline-flex items-center gap-2 px-4 py-1.5 rounded-full bg-primary/10 border border-primary/20 text-primary text-xs font-semibold mb-6">
              <span className="w-2 h-2 rounded-full bg-accent animate-pulse-slow" />
              AI-Powered Queue Intelligence
            </div>

            <h1 className="text-4xl lg:text-7xl font-black text-foreground leading-tight">
              Smart Queue
              <br />
              <span className="hero-gradient-text">Management</span>
            </h1>

            <p className="text-muted-foreground text-base lg:text-lg max-w-2xl mx-auto mt-6 leading-relaxed">
              Eliminate long waits with AI-driven crowd prediction, real-time monitoring,
              and intelligent token management. Built for modern service environments.
            </p>

            <div className="flex flex-col sm:flex-row items-center justify-center gap-4 mt-10">
              <Link
                to="/dashboard"
                className="flex items-center gap-2 px-8 py-3.5 rounded-xl hero-gradient-bg text-primary-foreground font-semibold hover:opacity-90 transition-opacity shadow-lg"
              >
                Get Started <ArrowRight className="w-4 h-4" />
              </Link>
              <Link
                to="/display"
                className="flex items-center gap-2 px-8 py-3.5 rounded-xl bg-secondary border border-border text-foreground font-semibold hover:bg-secondary/80 transition-colors"
              >
                <Monitor className="w-4 h-4" /> View Live Display
              </Link>
            </div>
          </motion.div>

          {/* Stats row */}
          <motion.div
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.3, duration: 0.5 }}
            className="grid grid-cols-3 gap-4 lg:gap-8 max-w-xl mx-auto mt-16"
          >
            {stats.map((stat, i) => (
              <div key={i} className="text-center">
                <stat.icon className="w-5 h-5 text-primary mx-auto mb-2" />
                <p className="text-2xl lg:text-3xl font-bold text-foreground font-mono">{stat.value}</p>
                <p className="text-[11px] text-muted-foreground mt-1">{stat.label}</p>
              </div>
            ))}
          </motion.div>
        </section>

        {/* Feature cards */}
        <section className="px-6 lg:px-16 pb-24 max-w-6xl mx-auto">
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-5">
            {features.map((feature, i) => (
              <motion.div
                key={feature.to}
                initial={{ opacity: 0, y: 20 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ delay: 0.4 + i * 0.1 }}
              >
                <Link
                  to={feature.to}
                  className={`block glass-card-hover rounded-2xl p-6 lg:p-8 group border ${feature.borderColor}`}
                >
                  <div className={`w-12 h-12 rounded-xl ${feature.bgColor} flex items-center justify-center mb-4`}>
                    <feature.icon className={`w-6 h-6 ${feature.color}`} />
                  </div>
                  <h3 className="text-lg font-bold text-foreground mb-2">{feature.title}</h3>
                  <p className="text-sm text-muted-foreground leading-relaxed">{feature.description}</p>
                  <div className={`flex items-center gap-1 mt-4 text-sm font-semibold ${feature.color} opacity-0 group-hover:opacity-100 transition-opacity`}>
                    Open <ArrowRight className="w-4 h-4" />
                  </div>
                </Link>
              </motion.div>
            ))}
          </div>
        </section>

        {/* Footer */}
        <footer className="border-t border-border px-6 lg:px-16 py-8 text-center">
          <p className="text-xs text-muted-foreground">
            AI-Enabled Queue Management System • Built with Real-Time Intelligence
          </p>
        </footer>
      </div>
    </div>
  );
};

export default WelcomePage;
