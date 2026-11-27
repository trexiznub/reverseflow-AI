"use client";
// The start screen: what ReverseFlow is, who uses it, and how it sits on SAP.
// Picking a person opens the app the way that person sees it.
import clsx from "clsx";
import { motion } from "framer-motion";
import { ArrowRight, ArrowUpRight, Network, Plug, RotateCcw, ShieldCheck, Sparkles, TrendingUp } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { Wordmark } from "@/components/Logo";
import { EASE, itemVariants } from "@/components/motion";
import { useSession } from "@/components/providers";
import { Badge, IconTile, Skeleton } from "@/components/ui";
import { useApi } from "@/lib/api";
import { ROLE_LABEL } from "@/lib/format";
import { homeFor, PERSON_GROUPS, ROLE_DOES, ROLE_ICON } from "@/lib/nav";

const FEATURES = [
  { icon: TrendingUp, t: "Forecast the wave", d: "Returns per city, about a week before they arrive." },
  { icon: Network, t: "Find the cause", d: "The sellers, sizes and listings behind avoidable returns." },
  { icon: RotateCcw, t: "Recover the value", d: "The most valuable items go back on sale first." },
  { icon: ShieldCheck, t: "People decide", d: "Anything that costs money needs a named person's approval." },
];

const STATE: Record<string, { label: string; tone: any }> = {
  connected: { label: "Connected", tone: "ok" },
  configured: { label: "Set up, not tested", tone: "warn" },
  not_configured: { label: "Ready to connect", tone: "neutral" },
  no_entitlement: { label: "No entitlement", tone: "warn" },
  failed: { label: "Failed", tone: "bad" },
};
const SHOWN = ["s4", "hana", "cap", "genai", "xsuaa", "ibp", "tm", "ariba", "sac", "workzone"];

function SapPanel() {
  const { data } = useApi<any>("/sap/overview");
  const items = data ? SHOWN.map((id) => data.services.find((s: any) => s.id === id)).filter(Boolean) : [];
  return (
    <motion.div variants={itemVariants} className="rounded-xl border border-line bg-[#080808]/90 p-5 backdrop-blur">
      <div className="mb-4 flex items-center gap-3">
        <IconTile icon={Plug} size="sm" />
        <div className="min-w-0 flex-1">
          <div className="text-[14px] font-semibold text-ink-900">Built for SAP BTP</div>
          <div className="text-[12px] text-ink-500">Live state of each connection in this demo</div>
        </div>
        {data && <span className="label">{data.counts.connected} connected</span>}
      </div>
      <div className="divide-y divide-line">
        {!data ? [0, 1, 2, 3, 4].map((i) => <Skeleton key={i} className="my-2 h-6" />) : items.map((s: any) => {
          const st = STATE[s.state] || STATE.not_configured;
          return (
            <div key={s.id} className="flex items-center justify-between gap-3 py-2">
              <span className="truncate text-[12.5px] text-ink-700">{s.product.replace(/ \(.*\)$/, "")}</span>
              <span className="flex shrink-0 items-center gap-1.5">
                {s.sandbox && <Badge tone="warn">sandbox data</Badge>}
                <Badge tone={st.tone} dot>{st.label}</Badge>
              </span>
            </div>
          );
        })}
      </div>
      <p className="mt-3 text-[11.5px] leading-relaxed text-ink-400">
        Nothing is shown as connected unless a test actually reached it. Each one switches on when its SAP service is bound.
      </p>
    </motion.div>
  );
}

function PersonCard({ u, current, onPick, busy }: { u: any; current: boolean; onPick: () => void; busy: boolean }) {
  const Icon = ROLE_ICON[u.role];
  return (
    <motion.button variants={itemVariants} onClick={onPick} whileHover={{ y: -3 }} whileTap={{ scale: 0.985 }} transition={{ type: "spring", stiffness: 400, damping: 30 }}
      className={clsx("group relative flex w-full items-start gap-3.5 overflow-hidden rounded-xl border bg-[#0A0A0A] p-4 text-left transition-colors duration-300",
        current ? "border-ink-500" : "border-line hover:border-line-strong")}>
      <span className="pointer-events-none absolute -right-12 -top-12 h-32 w-32 rounded-full bg-white/[0.05] opacity-0 blur-2xl transition-opacity duration-500 group-hover:opacity-100" />
      <span className="relative flex h-10 w-10 shrink-0 items-center justify-center rounded-lg border border-line-strong bg-canvas text-ink-700 transition-colors duration-300 group-hover:border-paper group-hover:bg-paper group-hover:text-black">
        {Icon && <Icon className="h-[18px] w-[18px]" strokeWidth={1.75} />}
      </span>
      <span className="relative min-w-0 flex-1">
        <span className="flex items-center gap-2">
          <span className="text-[14px] font-semibold text-ink-900">{u.name}</span>
          {current && <Badge tone="ok" dot>current</Badge>}
        </span>
        <span className="label mt-0.5 block text-ink-500">{ROLE_LABEL[u.role]}</span>
        <span className="mt-1.5 block text-[12.5px] leading-snug text-ink-500">{ROLE_DOES[u.role]}</span>
      </span>
      <ArrowRight className={clsx("relative mt-1 h-4 w-4 shrink-0 text-ink-400 transition-transform duration-300 group-hover:translate-x-1 group-hover:text-ink-900", busy && "animate-pulse")} />
    </motion.button>
  );
}

export default function Start() {
  const { users, meta, switchUser } = useSession();
  const router = useRouter();
  const [busy, setBusy] = useState<string | null>(null);

  const pick = (u: any) => {
    setBusy(u.id);
    try { localStorage.setItem("rf.started", "1"); } catch {}
    switchUser(u.id);
    router.push(homeFor(u.role));
  };

  return (
    <div className="relative min-h-screen overflow-hidden bg-black">
      {/* quiet background: a faint grid that fades out, and one soft light */}
      <div className="grid-paper pointer-events-none absolute inset-0 [mask-image:radial-gradient(ellipse_80%_60%_at_20%_10%,black,transparent)]" />
      <motion.div className="pointer-events-none absolute -left-40 -top-40 h-[520px] w-[520px] rounded-full bg-white/[0.06] blur-3xl"
        animate={{ x: [0, 40, 0], y: [0, 30, 0] }} transition={{ duration: 18, repeat: Infinity, ease: "easeInOut" }} />

      <div className="relative mx-auto max-w-[1280px] px-5 py-6 lg:px-10">
        <header className="flex items-center justify-between">
          <Wordmark />
          <div className="flex items-center gap-4">
            <span className="label hidden sm:inline">SAP Hackfest 2026 · Team BugFixers</span>
            <Link href="/" onClick={() => { try { localStorage.setItem("rf.started", "1"); } catch {} }}
              className="flex items-center gap-1 text-[12.5px] text-ink-500 transition-colors hover:text-ink-900">
              Continue as {meta?.user?.name?.split(" ")[0] || "Rahul"} <ArrowUpRight className="h-3.5 w-3.5" />
            </Link>
          </div>
        </header>

        <div className="mt-12 grid grid-cols-1 gap-12 lg:mt-16 lg:grid-cols-[minmax(0,5fr)_minmax(0,7fr)] lg:gap-14">
          {/* Left: what it is */}
          <motion.div initial="hidden" animate="show" variants={{ hidden: {}, show: { transition: { staggerChildren: 0.08 } } }} className="space-y-8">
            <motion.div variants={itemVariants}>
              <span className="inline-flex items-center gap-2 rounded-full border border-line-strong bg-canvas px-3 py-1 text-[12px] text-ink-700">
                <Sparkles className="h-3.5 w-3.5" strokeWidth={1.75} /> Six AI agents · one control tower for returns
              </span>
            </motion.div>
            <motion.h1 variants={itemVariants} className="display text-[48px] text-ink-900 sm:text-[68px]">
              Festive returns,<br />handled before<br />they land.
            </motion.h1>
            <motion.p variants={itemVariants} className="max-w-md text-[15.5px] leading-relaxed text-ink-500">
              After Navratri, fashion returns arrive in a wave. ReverseFlow sees it coming, finds why items come back,
              and gets them back on sale, with a person approving every decision that costs money.
            </motion.p>
            <motion.div variants={itemVariants} className="grid grid-cols-1 gap-3 sm:grid-cols-2">
              {FEATURES.map((f) => (
                <div key={f.t} className="flex items-start gap-3 rounded-lg border border-line bg-[#080808]/80 p-3.5">
                  <IconTile icon={f.icon} size="sm" />
                  <div>
                    <div className="text-[13px] font-semibold text-ink-900">{f.t}</div>
                    <div className="mt-0.5 text-[12px] leading-snug text-ink-500">{f.d}</div>
                  </div>
                </div>
              ))}
            </motion.div>
            <SapPanel />
          </motion.div>

          {/* Right: who are you */}
          <motion.div initial={{ opacity: 0, y: 16 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.6, ease: EASE, delay: 0.15 }}>
            <div className="mb-6">
              <div className="label mb-2">Step in</div>
              <h2 className="text-[26px] font-semibold tracking-tight text-ink-900">Who are you today?</h2>
              <p className="mt-1.5 text-[13.5px] text-ink-500">Each person sees only what their job needs. You can switch at any time from the menu.</p>
            </div>
            {meta?.auth_mode === "xsuaa" ? (
              <div className="rounded-xl border border-line bg-[#0A0A0A] p-5">
                <div className="text-[14px] text-ink-700">You are signed in with SAP as <b className="text-ink-900">{meta.user?.name}</b> ({ROLE_LABEL[meta.user?.role]}). Your role comes from your SAP role collection.</div>
                <Link href={homeFor(meta.user?.role)} className="mt-4 inline-flex items-center gap-1.5 rounded-md bg-paper px-4 py-2 text-[13px] font-medium text-black">Continue <ArrowRight className="h-4 w-4" /></Link>
              </div>
            ) : (
            <div className="space-y-7">
              {PERSON_GROUPS.map((g) => {
                const list = users.filter((u) => g.roles.includes(u.role));
                return (
                  <div key={g.label}>
                    <div className="label mb-2.5">{g.label}</div>
                    {!users.length ? (
                      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">{[0, 1].map((i) => <Skeleton key={i} className="h-[104px] rounded-xl" />)}</div>
                    ) : (
                      <motion.div initial="hidden" animate="show" variants={{ hidden: {}, show: { transition: { staggerChildren: 0.05, delayChildren: 0.2 } } }}
                        className="grid grid-cols-1 gap-3 sm:grid-cols-2">
                        {list.map((u) => <PersonCard key={u.id} u={u} current={u.id === meta?.user?.id} busy={busy === u.id} onPick={() => pick(u)} />)}
                      </motion.div>
                    )}
                  </div>
                );
              })}
            </div>
            )}
          </motion.div>
        </div>

        <footer className="label mt-16 flex flex-wrap items-center gap-x-6 gap-y-2 border-t border-line pt-5 text-ink-400">
          <span className="flex items-center gap-2"><span className="h-1.5 w-1.5 rounded-full bg-warn-500" />All data is synthetic; numbers are illustrative</span>
          <span>Next.js · FastAPI · SAP CAP · SAP BTP</span>
        </footer>
      </div>
    </div>
  );
}
