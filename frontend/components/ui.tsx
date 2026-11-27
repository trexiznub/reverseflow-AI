"use client";
import clsx from "clsx";
import { AlertTriangle, ChevronDown, HelpCircle, Inbox, Loader2, RefreshCw, X } from "lucide-react";
import { ReactNode, useEffect, useId, useState } from "react";
import { AnimatePresence, motion } from "framer-motion";
import { usePathname } from "next/navigation";
import { useSession } from "./providers";
import { IS_HOSTED } from "@/lib/api";
import { navFor } from "@/lib/nav";
import { CountUp, EASE, itemVariants } from "./motion";

export function Card({ children, className, pad = true }: { children: ReactNode; className?: string; pad?: boolean }) {
  return (
    <motion.div initial={{ opacity: 0, y: 12 }} whileInView={{ opacity: 1, y: 0 }} viewport={{ once: true, margin: "-30px" }}
      transition={{ duration: 0.45, ease: EASE }}
      className={clsx("card rounded-lg border border-line bg-white transition-colors duration-300 hover:border-line-strong", pad && "p-5", className)}>
      {children}
    </motion.div>
  );
}

/** Small square icon tile used next to headings. */
export function IconTile({ icon: Icon, tone = "neutral", size = "md" }: { icon: any; tone?: "neutral" | "ok" | "warn" | "bad" | "light"; size?: "sm" | "md" | "lg" }) {
  return (
    <span className={clsx("inline-flex shrink-0 items-center justify-center rounded-md border",
      size === "sm" ? "h-7 w-7" : size === "lg" ? "h-11 w-11" : "h-9 w-9",
      { neutral: "border-line-strong bg-canvas text-ink-700", ok: "border-[#1D3D2B] bg-ok-50 text-ok-700", warn: "border-[#4A3A17] bg-warn-50 text-warn-700",
        bad: "border-[#4A2620] bg-bad-50 text-bad-700", light: "border-paper bg-paper text-black" }[tone])}>
      <Icon className={size === "sm" ? "h-3.5 w-3.5" : size === "lg" ? "h-5 w-5" : "h-4 w-4"} strokeWidth={1.75} />
    </span>
  );
}

export function CardHead({ title, sub, right, label, icon }: { title: ReactNode; sub?: ReactNode; right?: ReactNode; label?: string; icon?: any }) {
  return (
    <div className="mb-4 flex items-start justify-between gap-3">
      {icon && <IconTile icon={icon} size="sm" />}
      <div className="min-w-0 flex-1">
        {label && <div className="label mb-1.5">{label}</div>}
        <div className="text-[15px] font-semibold tracking-tight text-ink-900">{title}</div>
        {sub && <div className="mt-1 text-[12.5px] leading-relaxed text-ink-500">{sub}</div>}
      </div>
      {right && <div className="shrink-0">{right}</div>}
    </div>
  );
}

/** Big, bold page title in the display face, with a short plain-language intro. */
export function PageHeader({ eyebrow, title, sub, right, icon }: { eyebrow?: string; title: string; sub?: ReactNode; right?: ReactNode; icon?: any }) {
  const path = usePathname();
  const Icon = icon || navFor(path)?.icon;
  return (
    <div className="relative mb-9 overflow-hidden rounded-xl border border-line bg-[#070707] px-6 pb-8 pt-6 sm:px-8">
      <div className="grid-paper pointer-events-none absolute inset-0 [mask-image:radial-gradient(ellipse_at_top_right,black,transparent_70%)]" />
      <div className="relative">
        <motion.div initial={{ opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.4, ease: EASE }}
          className="mb-5 flex items-center gap-3">
          {Icon && <IconTile icon={Icon} />}
          {eyebrow && <div className="label">{eyebrow}</div>}
        </motion.div>
        <div className="flex flex-wrap items-end justify-between gap-5">
          <div className="max-w-3xl">
            <motion.h1 initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.5, ease: EASE, delay: 0.05 }}
              className="display text-[36px] text-ink-900 sm:text-[52px]">{title}</motion.h1>
            {sub && <motion.p initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ duration: 0.5, delay: 0.15 }}
              className="mt-4 max-w-2xl text-[15px] leading-relaxed text-ink-500">{sub}</motion.p>}
          </div>
          {right && <motion.div initial={{ opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.4, delay: 0.2, ease: EASE }}>{right}</motion.div>}
        </div>
      </div>
    </div>
  );
}

/** Section divider used between groups of content on a page. */
export function Section({ label, title, right, children, className, icon: Icon }: { label?: string; title?: ReactNode; right?: ReactNode; children: ReactNode; className?: string; icon?: any }) {
  return (
    <section className={clsx("space-y-4", className)}>
      {(label || title) && (
        <div className="flex flex-wrap items-end justify-between gap-3">
          <div>
            {label && <div className="label mb-1.5 flex items-center gap-1.5">{Icon && <Icon className="h-3.5 w-3.5" strokeWidth={1.75} />}{label}</div>}
            {title && <h2 className="text-[20px] font-semibold tracking-tight text-ink-900">{title}</h2>}
          </div>
          {right}
        </div>
      )}
      {children}
    </section>
  );
}

type Tone = "neutral" | "blue" | "ok" | "warn" | "bad" | "navy";
const toneCls: Record<Tone, string> = {
  neutral: "bg-canvas text-ink-700 border-line-strong",
  blue: "bg-canvas text-ink-900 border-line-strong",
  ok: "bg-ok-50 text-ok-700 border-[#1D3D2B]",
  warn: "bg-warn-50 text-warn-700 border-[#4A3A17]",
  bad: "bg-bad-50 text-bad-700 border-[#4A2620]",
  navy: "bg-navy-900 text-black border-navy-900",
};
export function Badge({ children, tone = "neutral", className, dot }: { children: ReactNode; tone?: Tone; className?: string; dot?: boolean }) {
  return (
    <span className={clsx("inline-flex items-center gap-1.5 whitespace-nowrap rounded-sm border px-1.5 py-[1px] text-[11px] font-medium", toneCls[tone], className)}>
      {dot && <span className={clsx("h-1.5 w-1.5 rounded-full", { neutral: "bg-ink-400", blue: "bg-ink-900", ok: "bg-ok-600", warn: "bg-warn-500", bad: "bg-bad-600", navy: "bg-black" }[tone])} />}
      {children}
    </span>
  );
}

export const statusTone = (s?: string): Tone =>
  ({ pending: "warn", escalated: "bad", approved: "ok", rejected: "neutral", completed: "ok", running: "blue", queued: "neutral", failed: "bad", skipped: "neutral",
     partial: "warn", high: "bad", elevated: "warn", normal: "ok", medium: "warn", low: "neutral" } as Record<string, Tone>)[s || ""] || "neutral";

/** Plain-language wording for workflow statuses shown to people. */
export const STATUS_TEXT: Record<string, string> = {
  pending: "waiting", escalated: "sent to senior", approved: "approved", rejected: "declined", completed: "done", running: "working",
  queued: "queued", failed: "failed", skipped: "skipped", high: "high", elevated: "rising", normal: "normal",
};
export const statusText = (s?: string) => STATUS_TEXT[s || ""] || (s || "").replace(/_/g, " ");

type BtnVariant = "primary" | "secondary" | "ghost" | "danger" | "dark";
type BtnSize = "sm" | "md" | "lg";
export const btnCls = (variant: BtnVariant = "secondary", size: BtnSize = "md") => clsx(
  "inline-flex items-center justify-center gap-1.5 rounded-md font-medium transition-[background-color,border-color,color,transform] duration-200 active:scale-[0.97] disabled:cursor-not-allowed disabled:opacity-40 disabled:active:scale-100",
  size === "sm" ? "h-7 px-2.5 text-xs" : size === "lg" ? "h-11 px-5 text-[14px]" : "h-9 px-3.5 text-[13px]",
  { primary: "bg-paper text-black hover:bg-[#DADADA]", secondary: "border border-line-strong bg-transparent text-ink-900 hover:border-ink-500",
    ghost: "text-ink-700 hover:bg-canvas hover:text-ink-900", danger: "border border-[#5A2A22] bg-transparent text-bad-700 hover:bg-bad-50", dark: "bg-paper text-black hover:bg-[#DADADA]" }[variant]);

export function Button({ children, onClick, variant = "secondary", size = "md", disabled, loading, className, type = "button", title }:
  { children: ReactNode; onClick?: () => void; variant?: BtnVariant; size?: BtnSize; disabled?: boolean; loading?: boolean; className?: string; type?: "button" | "submit"; title?: string }) {
  return (
    <button type={type} title={title} onClick={onClick} disabled={disabled || loading} className={clsx(btnCls(variant, size), className)}>
      {loading && <Loader2 className="h-3.5 w-3.5 animate-spin" />}
      {children}
    </button>
  );
}

export function Stat({ label, value, sub, tone, children, hint }: { label: string; value: ReactNode; sub?: ReactNode; tone?: "bad" | "ok" | "warn"; children?: ReactNode; hint?: string }) {
  return (
    <Card className="flex flex-col justify-between">
      <div className="label flex items-center gap-1.5">{label}{hint && <Hint text={hint} />}</div>
      <div className="mt-4 flex items-end justify-between gap-2">
        <div>
          <div className={clsx("display-num text-[30px]", tone === "bad" && "text-bad-700", tone === "ok" && "text-ok-700", tone === "warn" && "text-warn-700")}>{value}</div>
          {sub && <div className="mt-2 text-[12px] text-ink-500">{sub}</div>}
        </div>
        {children}
      </div>
    </Card>
  );
}

/** Row of very large figures separated by hairlines. */
export function BigStats({ items }: { items: { label: string; value: ReactNode; sub?: ReactNode; tone?: "bad" | "ok" | "warn"; hint?: string; icon?: any }[] }) {
  return (
    <motion.div initial="hidden" whileInView="show" viewport={{ once: true, margin: "-30px" }}
      variants={{ hidden: {}, show: { transition: { staggerChildren: 0.07 } } }}
      className={clsx("grid grid-cols-2 gap-3", items.length >= 4 ? "xl:grid-cols-4" : "lg:grid-cols-3")}>
      {items.map((it, i) => {
        const Icon = it.icon;
        return (
          <motion.div key={i} variants={itemVariants}
            className="group relative min-w-0 overflow-hidden rounded-xl border border-line bg-white px-4 py-5 transition-colors duration-300 hover:border-line-strong sm:px-5">
            <div className={clsx("pointer-events-none absolute -right-10 -top-10 h-32 w-32 rounded-full opacity-0 blur-2xl transition-opacity duration-500 group-hover:opacity-100",
              it.tone === "bad" ? "bg-bad-600/15" : it.tone === "warn" ? "bg-warn-500/15" : it.tone === "ok" ? "bg-ok-600/15" : "bg-white/[0.06]")} />
            <div className="relative flex items-start justify-between gap-2">
              <div className="label flex items-center gap-1.5 text-ink-500">{it.label}{it.hint && <Hint text={it.hint} />}</div>
              {Icon && <Icon className={clsx("h-4 w-4 shrink-0", it.tone === "bad" ? "text-bad-600" : it.tone === "warn" ? "text-warn-500" : it.tone === "ok" ? "text-ok-600" : "text-ink-400")} strokeWidth={1.75} />}
            </div>
            <div className={clsx("relative mt-5 truncate pb-1 display-num text-[30px] sm:text-[44px] 2xl:text-[54px]", it.tone === "bad" && "text-bad-700", it.tone === "warn" && "text-warn-700", it.tone === "ok" && "text-ok-700")}>
              <CountUp value={it.value} />
            </div>
            {it.sub && <div className="relative mt-2 text-[12.5px] leading-snug text-ink-500">{it.sub}</div>}
          </motion.div>
        );
      })}
    </motion.div>
  );
}

/** Small "?" with an explanation of a term, shown on hover or tap. */
export function Hint({ text }: { text: string }) {
  const [open, setOpen] = useState(false);
  return (
    <span className="relative inline-flex normal-case tracking-normal" onMouseEnter={() => setOpen(true)} onMouseLeave={() => setOpen(false)}>
      <button type="button" onClick={(e) => { e.preventDefault(); e.stopPropagation(); setOpen((o) => !o); }} aria-label="What does this mean?" className="text-ink-400 hover:text-ink-900">
        <HelpCircle className="h-3.5 w-3.5" />
      </button>
      <AnimatePresence>
        {open && (
          <motion.span initial={{ opacity: 0, y: -4 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: -4 }} transition={{ duration: 0.15 }}
            className="absolute left-1/2 top-5 z-50 w-64 -translate-x-1/2 rounded-md border border-line-strong bg-[#111] px-3 py-2 font-sans text-[12px] font-normal leading-snug text-ink-700 shadow-pop">{text}</motion.span>
        )}
      </AnimatePresence>
    </span>
  );
}

/**
 * Technical detail that most people do not need. Hidden behind a fold unless
 * the global "Show details" switch is on.
 */
export function More({ title = "Technical details", sub, children }: { title?: string; sub?: string; children: ReactNode }) {
  const { detail } = useSession();
  const [open, setOpen] = useState(false);
  const shown = detail || open;
  return (
    <div className="space-y-4">
      {!detail && (
        <button onClick={() => setOpen((o) => !o)} className="group flex w-full items-center gap-3 border-t border-dashed border-line-strong pt-3 text-left">
          <span className="label text-ink-500 group-hover:text-ink-900">{open ? "−" : "+"} {title}</span>
          {sub && <span className="hidden text-[12px] text-ink-400 sm:inline">{sub}</span>}
          <ChevronDown className={clsx("ml-auto h-4 w-4 text-ink-400 transition-transform", open && "rotate-180")} />
        </button>
      )}
      <AnimatePresence initial={false}>
        {shown && (
          <motion.div key="more" initial={{ opacity: 0, height: 0 }} animate={{ opacity: 1, height: "auto" }} exit={{ opacity: 0, height: 0 }}
            transition={{ duration: 0.3, ease: EASE }} className="space-y-4 overflow-hidden">{children}</motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}

/** Renders children only in details mode (for small inline bits). */
export function DetailOnly({ children }: { children: ReactNode }) {
  const { detail } = useSession();
  return detail ? <>{children}</> : null;
}

export function Skeleton({ className }: { className?: string }) {
  return <div className={clsx("skeleton rounded", className)} />;
}

export function Loading({ rows = 3, className }: { rows?: number; className?: string }) {
  return (
    <div className={clsx("space-y-3", className)}>
      <Skeleton className="h-24 w-2/3" />
      <div className="grid grid-cols-2 gap-3 md:grid-cols-4">{[0, 1, 2, 3].map((i) => <Skeleton key={i} className="h-[96px]" />)}</div>
      {Array.from({ length: rows }).map((_, i) => <Skeleton key={i} className="h-44" />)}
    </div>
  );
}

export function ErrorState({ error, onRetry }: { error: any; onRetry?: () => void }) {
  const offline = error?.status === 0;
  const forbidden = error?.status === 403;
  return (
    <Card className="flex items-start gap-3 !border-[#4A2620] bg-bad-50">
      <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0 text-bad-600" />
      <div className="flex-1 text-[13px]">
        <div className="font-semibold text-ink-900">{offline ? (IS_HOSTED ? "The server is waking up" : "Can't reach the server") : forbidden ? "This page isn't available for your role" : "Something went wrong"}</div>
        <div className="mt-0.5 text-ink-700">{offline ? (IS_HOSTED ? "The demo runs on a free server that sleeps when nobody is using it. It takes about a minute to start, then press Try again." : "The data service isn't running. Start it and this page will load.") : error?.message || String(error)}</div>
        {offline && !IS_HOSTED && <div className="mt-1 font-mono text-xs text-ink-500">cd backend &amp;&amp; .venv/bin/uvicorn app.main:app --port 8040</div>}
        {forbidden && <div className="mt-1 text-xs text-ink-500">Switch to another person from the menu in the top-right corner.</div>}
      </div>
      {onRetry && !forbidden && <Button size="sm" onClick={onRetry}><RefreshCw className="h-3 w-3" />Try again</Button>}
    </Card>
  );
}

export function Empty({ title, sub, icon }: { title: string; sub?: string; icon?: ReactNode }) {
  return (
    <motion.div initial={{ opacity: 0, scale: 0.98 }} animate={{ opacity: 1, scale: 1 }} transition={{ duration: 0.35, ease: EASE }}
      className="flex flex-col items-center justify-center rounded-lg border border-dashed border-line-strong px-4 py-12 text-center">
      <div className="mb-3 flex h-11 w-11 items-center justify-center rounded-full border border-line-strong bg-canvas text-ink-500">{icon || <Inbox className="h-5 w-5" strokeWidth={1.75} />}</div>
      <div className="text-[13.5px] font-medium text-ink-700">{title}</div>
      {sub && <div className="mt-1 max-w-sm text-xs text-ink-500">{sub}</div>}
    </motion.div>
  );
}

export function Tabs<T extends string>({ value, onChange, items }: { value: T; onChange: (v: T) => void; items: { id: T; label: ReactNode; count?: number; icon?: any }[] }) {
  const id = useId();
  return (
    <div className="flex gap-1 overflow-x-auto border-b border-line">
      {items.map((it) => (
        <button key={it.id} onClick={() => onChange(it.id)}
          className={clsx("relative flex items-center gap-2 whitespace-nowrap px-3 py-2.5 text-[13.5px] font-medium transition-colors",
            value === it.id ? "text-ink-900" : "text-ink-500 hover:text-ink-900")}>
          {it.icon && <it.icon className="h-3.5 w-3.5" strokeWidth={1.75} />}
          {it.label}
          {it.count !== undefined && <span className="num rounded-full bg-canvas px-1.5 text-[11px] text-ink-500">{it.count}</span>}
          {value === it.id && <motion.span layoutId={`tab-${id}`} className="absolute inset-x-1 -bottom-px h-[2px] rounded-full bg-ink-900" transition={{ type: "spring", stiffness: 500, damping: 38 }} />}
        </button>
      ))}
    </div>
  );
}

export function Segmented<T extends string>({ value, onChange, items }: { value: T; onChange: (v: T) => void; items: { id: T; label: ReactNode }[] }) {
  const id = useId();
  return (
    <div className="inline-flex rounded-md border border-line-strong p-0.5">
      {items.map((it) => (
        <button key={it.id} onClick={() => onChange(it.id)}
          className={clsx("relative rounded px-2.5 py-1 text-xs font-medium transition-colors", value === it.id ? "text-black" : "text-ink-500 hover:text-ink-900")}>
          {value === it.id && <motion.span layoutId={`seg-${id}`} className="absolute inset-0 rounded bg-paper" transition={{ type: "spring", stiffness: 500, damping: 38 }} />}
          <span className="relative">{it.label}</span>
        </button>
      ))}
    </div>
  );
}

export function Drawer({ open, onClose, title, children, width = 560 }: { open: boolean; onClose: () => void; title: ReactNode; children: ReactNode; width?: number }) {
  useEffect(() => {
    const k = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", k);
    return () => window.removeEventListener("keydown", k);
  }, [onClose]);
  return (
    <AnimatePresence>
      {open && (
        <>
          <motion.div className="fixed inset-0 z-40 bg-black/60 backdrop-blur-[2px]" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} onClick={onClose} />
          <motion.aside className="fixed bottom-0 right-0 top-0 z-50 flex w-full flex-col border-l border-line-strong bg-[#0B0B0B] shadow-pop" style={{ maxWidth: width }}
            initial={{ x: "100%" }} animate={{ x: 0 }} exit={{ x: "100%" }} transition={{ type: "spring", stiffness: 380, damping: 40 }}>
            <div className="flex items-center justify-between border-b border-line px-6 py-4">
              <div className="min-w-0 text-[15px] font-semibold">{title}</div>
              <button onClick={onClose} className="rounded p-1 text-ink-500 hover:bg-canvas hover:text-ink-900" aria-label="Close"><X className="h-4 w-4" /></button>
            </div>
            <div className="flex-1 overflow-y-auto p-6">{children}</div>
          </motion.aside>
        </>
      )}
    </AnimatePresence>
  );
}

export function Field({ label, children, hint }: { label: string; children: ReactNode; hint?: string }) {
  return (
    <label className="block">
      <div className="mb-1.5 text-[12.5px] font-medium text-ink-700">{label}</div>
      {children}
      {hint && <div className="mt-1 text-[11.5px] text-ink-500">{hint}</div>}
    </label>
  );
}

export const inputCls = "h-9 w-full rounded-md border border-line-strong bg-black px-3 text-[13.5px] text-ink-900 outline-none transition-[border-color,box-shadow] focus:border-ink-500 focus:ring-2 focus:ring-white/10";
export const selectCls = "h-8 rounded-md border border-line-strong bg-black px-2 text-[12.5px] text-ink-900 outline-none transition-[border-color,box-shadow] focus:border-ink-500 focus:ring-2 focus:ring-white/10";

export function Meter({ value, max = 1, tone, className }: { value: number; max?: number; tone?: "bad" | "warn" | "ok" | "blue"; className?: string }) {
  const p = Math.max(0, Math.min(1, value / (max || 1)));
  const t = tone || (p > 1 ? "bad" : p > 0.9 ? "warn" : "blue");
  return (
    <div className={clsx("h-1.5 w-full overflow-hidden rounded-full bg-canvas", className)}>
      <motion.div className={clsx("h-full rounded-full", { bad: "bg-bad-600", warn: "bg-warn-500", ok: "bg-ok-600", blue: "bg-ink-900" }[t])}
        initial={{ width: 0 }} whileInView={{ width: `${p * 100}%` }} viewport={{ once: true }} transition={{ duration: 0.8, ease: EASE }} />
    </div>
  );
}

export function SyntheticTag({ text = "Demo data" }: { text?: string }) {
  return <span className="label inline-flex items-center gap-1.5 rounded-sm border border-dashed border-line-strong px-2 py-1 text-ink-500"><span className="h-1.5 w-1.5 rounded-full bg-warn-500" />{text}</span>;
}

export function KV({ k, v }: { k: ReactNode; v: ReactNode }) {
  return (
    <div className="flex items-baseline justify-between gap-3 border-b border-dashed border-line py-2 text-[13px] last:border-0">
      <span className="text-ink-500">{k}</span>
      <span className="text-right font-medium text-ink-900">{v}</span>
    </div>
  );
}

export function JsonBlock({ value, max = 380 }: { value: any; max?: number }) {
  return (
    <pre className="overflow-auto rounded border border-line bg-black p-3 font-mono text-[11px] leading-[1.55] text-ink-700" style={{ maxHeight: max }}>
      {JSON.stringify(value, null, 2)}
    </pre>
  );
}
