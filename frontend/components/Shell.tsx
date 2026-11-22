"use client";
import clsx from "clsx";
import {
  ArrowUp, BarChart3, Boxes, ChevronDown, CornerDownLeft, Handshake, LayoutGrid, Menu, Network, PackageOpen, RotateCcw, Search,
  Settings2, ShieldCheck, TrendingUp, Workflow, X,
} from "lucide-react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { ReactNode, useEffect, useMemo, useRef, useState } from "react";
import { day, ROLE_LABEL } from "@/lib/format";
import { Wordmark } from "./Logo";
import { useSession } from "./providers";

// Plain names for every page. `primary` items sit in the top bar; the rest live under "More".
export const NAV = [
  { id: "overview", href: "/", label: "Today", icon: LayoutGrid, primary: true, desc: "What's happening and what needs you" },
  { id: "governance", href: "/governance", label: "Decisions", icon: ShieldCheck, primary: true, desc: "Approve or decline suggested actions" },
  { id: "forecasting", href: "/forecasting", label: "Forecast", icon: TrendingUp, primary: true, desc: "How many returns are coming, and where" },
  { id: "root-cause", href: "/root-cause", label: "Product issues", icon: Network, primary: true, desc: "Why items come back, by product and seller" },
  { id: "twin", href: "/twin", label: "Planner", icon: Boxes, primary: true, desc: "Try plans before you commit to one" },
  { id: "recovery", href: "/recovery", label: "Resale", icon: RotateCcw, primary: true, desc: "Get returned items back on sale" },
  { id: "analytics", href: "/analytics", label: "Reports", icon: BarChart3, primary: false, desc: "Key numbers and downloads" },
  { id: "agents", href: "/agents", label: "How it works", icon: Workflow, primary: false, desc: "See what each AI agent did" },
  { id: "customer", href: "/customer", label: "Customer app", icon: PackageOpen, primary: false, desc: "What a shopper sees" },
  { id: "partners", href: "/partners", label: "Partner app", icon: Handshake, primary: false, desc: "Sellers, delivery partners, warehouses" },
  { id: "settings", href: "/settings", label: "Settings", icon: Settings2, primary: false, desc: "Assumptions, limits and demo reset" },
];

function useOutside(ref: React.RefObject<HTMLElement | null>, close: () => void) {
  useEffect(() => {
    const h = (e: MouseEvent) => ref.current && !ref.current.contains(e.target as Node) && close();
    document.addEventListener("mousedown", h);
    return () => document.removeEventListener("mousedown", h);
  }, [ref, close]);
}

function PersonaSwitcher() {
  const { meta, users, switchUser } = useSession();
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);
  const router = useRouter();
  useOutside(ref, () => setOpen(false));
  const groups = useMemo(() => {
    const g: Record<string, any[]> = { "Marketplace team": [], Partners: [], Customers: [] };
    users.forEach((u) => (u.role === "customer" ? g.Customers : ["vendor", "logistics", "warehouse"].includes(u.role) ? g.Partners : g["Marketplace team"]).push(u));
    return g;
  }, [users]);
  const u = meta?.user;
  const initials = (u?.name || "··").split(" ").map((s: string) => s[0]).join("").slice(0, 2);
  return (
    <div className="relative" ref={ref}>
      <button onClick={() => setOpen((o) => !o)} className="flex items-center gap-2 rounded border border-line-strong py-1 pl-1 pr-2 hover:border-ink-500">
        <span className="flex h-7 w-7 items-center justify-center rounded-sm bg-paper text-[11px] font-semibold text-black">{initials}</span>
        <span className="hidden text-left leading-tight md:block">
          <span className="block text-[12.5px] font-medium text-ink-900">{u?.name || "Loading"}</span>
          <span className="block text-[10.5px] text-ink-500">{ROLE_LABEL[u?.role] || ""}</span>
        </span>
        <ChevronDown className="h-3.5 w-3.5 text-ink-400" />
      </button>
      {open && (
        <div className="absolute right-0 top-11 z-50 max-h-[75vh] w-[330px] overflow-y-auto rounded border border-line-strong bg-[#0B0B0B] p-1 shadow-pop">
          <div className="px-3 pb-2 pt-2.5 text-[12px] leading-snug text-ink-500">Switch person to see the app the way they do. Each person only sees what their job needs.</div>
          {Object.entries(groups).map(([g, list]) => (
            <div key={g} className="py-1">
              <div className="label px-3 py-1">{g}</div>
              {list.map((x) => (
                <button key={x.id} onClick={() => {
                  switchUser(x.id); setOpen(false);
                  router.push(x.role === "customer" ? "/customer" : ["vendor", "logistics", "warehouse"].includes(x.role) ? "/partners" : x.role === "dispute_reviewer" ? "/governance" : "/");
                }}
                  className={clsx("flex w-full items-start gap-2 rounded-sm px-3 py-2 text-left hover:bg-canvas", x.id === u?.id && "bg-canvas")}>
                  <div className="min-w-0 flex-1">
                    <div className="text-[13px] font-medium text-ink-900">{x.name}</div>
                    <div className="truncate text-[11.5px] text-ink-500">{x.title}</div>
                  </div>
                  {x.id === u?.id && <span className="label mt-0.5 text-ink-900">current</span>}
                </button>
              ))}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

function DetailSwitch() {
  const { detail, setDetail } = useSession();
  return (
    <button onClick={() => setDetail(!detail)} title="Show or hide technical details such as model accuracy and raw data"
      className="hidden items-center gap-2 rounded px-2 py-1.5 text-[12px] text-ink-500 hover:text-ink-900 md:flex">
      <span className={clsx("relative h-4 w-7 rounded-full border transition-colors", detail ? "border-paper bg-paper" : "border-line-strong bg-transparent")}>
        <span className={clsx("absolute top-[1px] h-3 w-3 rounded-full transition-all", detail ? "left-[13px] bg-black" : "left-[1px] bg-ink-500")} />
      </span>
      <span className="label text-inherit">Details</span>
    </button>
  );
}

function CommandPalette({ open, onClose, allowed }: { open: boolean; onClose: () => void; allowed: string[] }) {
  const [q, setQ] = useState("");
  const [i, setI] = useState(0);
  const router = useRouter();
  const items = NAV.filter((n) => allowed.includes(n.id) && (n.label + " " + n.desc).toLowerCase().includes(q.toLowerCase()));
  useEffect(() => { setI(0); }, [q]);
  useEffect(() => { if (!open) setQ(""); }, [open]);
  if (!open) return null;
  const go = (href: string) => { router.push(href); onClose(); };
  return (
    <div className="fixed inset-0 z-[70] flex items-start justify-center bg-black/70 px-4 pt-[14vh]" onClick={onClose}>
      <div className="w-full max-w-lg rounded border border-line-strong bg-[#0B0B0B] shadow-pop" onClick={(e) => e.stopPropagation()}>
        <div className="flex items-center gap-2 border-b border-line px-4">
          <Search className="h-4 w-4 text-ink-400" />
          <input autoFocus value={q} onChange={(e) => setQ(e.target.value)} placeholder="Where do you want to go?"
            onKeyDown={(e) => {
              if (e.key === "ArrowDown") setI((x) => Math.min(x + 1, items.length - 1));
              if (e.key === "ArrowUp") setI((x) => Math.max(x - 1, 0));
              if (e.key === "Enter" && items[i]) go(items[i].href);
              if (e.key === "Escape") onClose();
            }}
            className="h-12 flex-1 bg-transparent text-[14px] text-ink-900 outline-none" />
          <kbd className="label rounded-sm border border-line-strong px-1.5">esc</kbd>
        </div>
        <div className="max-h-96 overflow-y-auto p-1">
          {items.map((n, k) => (
            <button key={n.id} onMouseEnter={() => setI(k)} onClick={() => go(n.href)}
              className={clsx("flex w-full items-center gap-3 rounded-sm px-3 py-2.5 text-left", k === i ? "bg-canvas text-ink-900" : "text-ink-700")}>
              <n.icon className="h-4 w-4 text-ink-400" />
              <span className="flex-1"><span className="block text-[13.5px] font-medium">{n.label}</span><span className="block text-[11.5px] text-ink-500">{n.desc}</span></span>
              {k === i && <CornerDownLeft className="h-3.5 w-3.5 text-ink-400" />}
            </button>
          ))}
          {!items.length && <div className="px-3 py-6 text-center text-xs text-ink-500">Nothing matches.</div>}
        </div>
      </div>
    </div>
  );
}

function MoreMenu({ items, path }: { items: typeof NAV; path: string }) {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);
  useOutside(ref, () => setOpen(false));
  useEffect(() => setOpen(false), [path]);
  if (!items.length) return null;
  const active = items.some((n) => path.startsWith(n.href));
  return (
    <div className="relative" ref={ref}>
      <button onClick={() => setOpen((o) => !o)} className={clsx("flex items-center gap-1 px-2.5 py-1.5 text-[13px] transition-colors", active || open ? "text-ink-900" : "text-ink-500 hover:text-ink-900")}>
        More <ChevronDown className="h-3.5 w-3.5" />
      </button>
      {open && (
        <div className="absolute left-0 top-10 z-50 w-[300px] rounded border border-line-strong bg-[#0B0B0B] p-1 shadow-pop">
          {items.map((n) => (
            <Link key={n.id} href={n.href} className={clsx("flex items-start gap-3 rounded-sm px-3 py-2.5 hover:bg-canvas", path.startsWith(n.href) && "bg-canvas")}>
              <n.icon className="mt-0.5 h-4 w-4 text-ink-400" />
              <span><span className="block text-[13px] font-medium text-ink-900">{n.label}</span><span className="block text-[11.5px] text-ink-500">{n.desc}</span></span>
            </Link>
          ))}
        </div>
      )}
    </div>
  );
}

export function Shell({ children }: { children: ReactNode }) {
  const path = usePathname();
  const { meta, metaError } = useSession();
  const [palette, setPalette] = useState(false);
  const [mobile, setMobile] = useState(false);
  const allowed = meta?.pages || [];
  const navItems = NAV.filter((n) => allowed.includes(n.id));
  // Small roles (customers, partners) have one or two pages: show them all in the bar.
  const primary = navItems.length <= 4 ? navItems : navItems.filter((n) => n.primary);
  const more = navItems.length <= 4 ? [] : navItems.filter((n) => !n.primary);

  useEffect(() => {
    const k = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") { e.preventDefault(); setPalette((p) => !p); }
    };
    window.addEventListener("keydown", k);
    return () => window.removeEventListener("keydown", k);
  }, []);
  useEffect(() => setMobile(false), [path]);

  const isActive = (href: string) => (href === "/" ? path === "/" : path.startsWith(href));

  return (
    <div className="flex min-h-screen flex-col">
      <header className="sticky top-0 z-30 border-b border-line bg-black/90 backdrop-blur">
        <div className="mx-auto flex h-[60px] max-w-[1440px] items-center gap-4 px-4 lg:px-10">
          <button className="-ml-1 rounded p-1.5 text-ink-700 hover:bg-canvas lg:hidden" onClick={() => setMobile(true)} aria-label="Open menu"><Menu className="h-5 w-5" /></button>
          <Link href={allowed.includes("overview") ? "/" : navItems[0]?.href || "/"} className="shrink-0"><Wordmark /></Link>
          <nav className="ml-4 hidden items-center lg:flex">
            {primary.map((n) => (
              <Link key={n.id} href={n.href} className={clsx("relative px-2.5 py-1.5 text-[13px] transition-colors", isActive(n.href) ? "text-ink-900" : "text-ink-500 hover:text-ink-900")}>
                {n.label}
                {isActive(n.href) && <span className="absolute inset-x-2.5 -bottom-[13px] h-px bg-ink-900" />}
              </Link>
            ))}
            <MoreMenu items={more} path={path} />
          </nav>
          <div className="ml-auto flex items-center gap-1.5 sm:gap-2">
            <span className="label hidden items-center gap-2 xl:flex" title={meta?.disclaimer}>
              <span className="h-1.5 w-1.5 animate-blink rounded-full bg-warn-500" />
              Demo · {meta ? new Date(meta.scenario_date + "T00:00:00").toLocaleDateString("en-GB", { day: "2-digit", month: "short", year: "numeric" }) : "—"}
            </span>
            {meta?.user?.role !== "customer" && <DetailSwitch />}
            <button onClick={() => setPalette(true)} className="rounded p-2 text-ink-500 hover:bg-canvas hover:text-ink-900" aria-label="Search pages" title="Search pages (⌘K)"><Search className="h-4 w-4" /></button>
            <PersonaSwitcher />
          </div>
        </div>
      </header>

      {mobile && (
        <div className="fixed inset-0 z-50 bg-black lg:hidden">
          <div className="flex h-[60px] items-center justify-between border-b border-line px-4">
            <Wordmark />
            <button onClick={() => setMobile(false)} className="rounded p-1.5 text-ink-700 hover:bg-canvas" aria-label="Close menu"><X className="h-5 w-5" /></button>
          </div>
          <div className="overflow-y-auto px-4 py-4">
            {navItems.map((n) => (
              <Link key={n.id} href={n.href} className={clsx("flex items-baseline justify-between border-b border-line py-3.5", isActive(n.href) ? "text-ink-900" : "text-ink-500")}>
                <span className="text-[22px] font-semibold tracking-tight">{n.label}</span>
                <span className="ml-3 text-right text-[11.5px] text-ink-500">{n.desc}</span>
              </Link>
            ))}
            <div className="mt-5 flex items-center justify-between">
              <span className="label">Show technical details</span>
              <MobileDetailSwitch />
            </div>
          </div>
        </div>
      )}

      {metaError && (
        <div className="border-b border-[#4A2620] bg-bad-50 px-6 py-2.5 text-[13px] text-bad-700">
          Can't reach the data service. Start it with <span className="font-mono">cd backend && .venv/bin/uvicorn app.main:app --port 8040</span>
        </div>
      )}
      {meta && meta.status && !meta.status.ready && (
        <div className="border-b border-line bg-canvas px-6 py-2.5 text-[13px] text-ink-700">Getting the demo ready: {meta.status.detail || meta.status.state}…</div>
      )}
      <main className="mx-auto w-full max-w-[1440px] flex-1 px-4 py-8 lg:px-10 lg:py-10">{children}</main>
      <footer className="border-t border-line">
        <div className="label mx-auto flex max-w-[1440px] flex-wrap items-center gap-x-6 gap-y-2 px-4 py-5 lg:px-10">
          <span>© 2026 ReverseFlow</span>
          <span className="flex items-center gap-2"><span className="h-1.5 w-1.5 rounded-full bg-warn-500" />Demo data · numbers are illustrative</span>
          {meta && <span>Scenario date {day(meta.scenario_date)} 2026</span>}
          <span>SAP Hackfest 2026 · Team BugFixers</span>
          <button onClick={() => window.scrollTo({ top: 0, behavior: "smooth" })} className="ml-auto flex items-center gap-1.5 hover:text-ink-900">Back to top <ArrowUp className="h-3 w-3" /></button>
        </div>
      </footer>
      <CommandPalette open={palette} onClose={() => setPalette(false)} allowed={allowed} />
    </div>
  );
}

function MobileDetailSwitch() {
  const { detail, setDetail } = useSession();
  return (
    <button onClick={() => setDetail(!detail)} className={clsx("relative h-6 w-11 rounded-full border transition-colors", detail ? "border-paper bg-paper" : "border-line-strong")} aria-label="Show technical details">
      <span className={clsx("absolute top-[2px] h-[18px] w-[18px] rounded-full transition-all", detail ? "left-[21px] bg-black" : "left-[2px] bg-ink-500")} />
    </button>
  );
}
