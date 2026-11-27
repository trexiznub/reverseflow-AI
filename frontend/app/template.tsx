"use client";
// Re-mounts on every navigation, so each page enters with the same short fade and lift.
import { motion } from "framer-motion";
import { EASE } from "@/components/motion";

export default function Template({ children }: { children: React.ReactNode }) {
  return (
    <motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.38, ease: EASE }}>
      {children}
    </motion.div>
  );
}
