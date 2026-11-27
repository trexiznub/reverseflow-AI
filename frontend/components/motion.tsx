"use client";
// Shared motion: one easing curve and a few building blocks, so every
// transition in the app feels the same. Respects "reduce motion" through the
// MotionConfig in providers.tsx.
import { animate, motion, useInView, useReducedMotion } from "framer-motion";
import { ReactNode, useEffect, useRef, useState } from "react";

export const EASE = [0.22, 1, 0.36, 1] as const;

/** Fades and lifts its content in when it scrolls into view. */
export function Reveal({ children, delay = 0, className, y = 14 }: { children: ReactNode; delay?: number; className?: string; y?: number }) {
  return (
    <motion.div className={className} initial={{ opacity: 0, y }} whileInView={{ opacity: 1, y: 0 }}
      viewport={{ once: true, margin: "-40px" }} transition={{ duration: 0.5, ease: EASE, delay }}>
      {children}
    </motion.div>
  );
}

/** Children appear one after another. Wrap each child in <StaggerItem>. */
export function Stagger({ children, className, gap = 0.05, delay = 0 }: { children: ReactNode; className?: string; gap?: number; delay?: number }) {
  return (
    <motion.div className={className} initial="hidden" whileInView="show" viewport={{ once: true, margin: "-30px" }}
      variants={{ hidden: {}, show: { transition: { staggerChildren: gap, delayChildren: delay } } }}>
      {children}
    </motion.div>
  );
}

export const itemVariants = {
  hidden: { opacity: 0, y: 12 },
  show: { opacity: 1, y: 0, transition: { duration: 0.45, ease: EASE } },
};

export function StaggerItem({ children, className }: { children: ReactNode; className?: string }) {
  return <motion.div className={className} variants={itemVariants}>{children}</motion.div>;
}

/**
 * Counts up to a figure the first time it is seen. Takes the already formatted
 * text ("1,24,185", "2.34×", "₹4.2 L", "38") and keeps its format; anything
 * that isn't a plain number is shown as it is.
 */
export function CountUp({ value, duration = 1.1 }: { value: ReactNode; duration?: number }) {
  const ref = useRef<HTMLSpanElement>(null);
  const seen = useInView(ref, { once: true });
  const reduce = useReducedMotion();
  const text = typeof value === "string" || typeof value === "number" ? String(value) : null;
  const m = text?.match(/^([^\d-]*)(-?[\d,]*\.?\d+)(.*)$/);
  const [shown, setShown] = useState<string | null>(m ? m[1] + "0" + m[3] : null);

  useEffect(() => {
    if (!m || !seen) return;
    const [, pre, numText, post] = m;
    const target = Number(numText.replace(/,/g, ""));
    const decimals = (numText.split(".")[1] || "").length;
    const indian = /,\d\d,/.test(numText);  // 1,24,185 is grouped the Indian way
    const fmt = (v: number) => {
      const s = v.toFixed(decimals);
      if (!numText.includes(",")) return s;
      const [i, d] = s.split(".");
      const n = Number(i).toLocaleString(indian ? "en-IN" : "en-US");
      return d ? `${n}.${d}` : n;
    };
    if (reduce) { setShown(pre + fmt(target) + post); return; }
    const c = animate(0, target, { duration, ease: EASE, onUpdate: (v) => setShown(pre + fmt(v) + post) });
    return () => c.stop();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [seen, text]);

  if (!m) return <>{value}</>;
  return <span ref={ref}>{shown}</span>;
}
