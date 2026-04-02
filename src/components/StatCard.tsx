import { motion } from "framer-motion";
import { LucideIcon } from "lucide-react";

interface StatCardProps {
  title: string;
  value: string | number;
  subtitle?: string;
  icon: LucideIcon;
  glowClass?: string;
  iconColorClass?: string;
  trend?: { value: string; positive: boolean };
}

const StatCard = ({ title, value, subtitle, icon: Icon, glowClass = "", iconColorClass = "text-primary", trend }: StatCardProps) => (
  <motion.div
    initial={{ opacity: 0, y: 20 }}
    animate={{ opacity: 1, y: 0 }}
    whileHover={{ y: -2, transition: { duration: 0.2 } }}
    className={`glass-card-hover rounded-xl p-5 lg:p-6 ${glowClass}`}
  >
    <div className="flex items-start justify-between">
      <div>
        <p className="text-xs lg:text-sm text-muted-foreground font-medium">{title}</p>
        <p className="text-2xl lg:text-3xl font-bold text-foreground mt-1.5 font-mono">{value}</p>
        <div className="flex items-center gap-2 mt-1">
          {subtitle && <p className="text-[11px] text-muted-foreground">{subtitle}</p>}
          {trend && (
            <span className={`text-[11px] font-semibold ${trend.positive ? "text-accent" : "text-destructive"}`}>
              {trend.positive ? "↑" : "↓"} {trend.value}
            </span>
          )}
        </div>
      </div>
      <div className={`w-10 h-10 rounded-xl bg-secondary flex items-center justify-center ${iconColorClass}`}>
        <Icon className="w-5 h-5" />
      </div>
    </div>
  </motion.div>
);

export default StatCard;
