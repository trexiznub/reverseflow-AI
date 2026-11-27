"use client";
import clsx from "clsx";
import { AnimatePresence, motion } from "framer-motion";
import {
  ArrowUp, ChevronsLeft, ChevronsRight, ChevronsUpDown, CornerDownLeft, LogIn, Menu, Search, Users, X,
} from "lucide-react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { ReactNode, useEffect, useMemo, useRef, useState } from "react";
import { day, ROLE_LABEL } from "@/lib/format";
import { IS_HOSTED } from "@/lib/api";
import { homeFor, NAV, NAV_GROUPS, navFor, PERSON_GROUPS, ROLE_ICON } from "@/lib/nav";
import { Wordmark, LogoMark } from "./Logo";
import { EASE } from "./motion";
import { useSession } from "./providers";

export { NAV } from "@/lib/nav";

function useOutside(ref: React.RefObject<HTMLElement | null>, close: () => void) {
  useEffect(() => {
    const h = (e: MouseEvent) => ref.current && !ref.current.contains(e.target as Node) && close();
    document.addEventListener("mousedown", h);
    return () => document.removeEventListener("mousedown", h);
  }, [ref, close]);
}

function Avatar({ name, role, size = 32 }: { name?: string; role?: string; size?: number }) {
  const Icon = ROLE_ICON[role || ""];
  const initials = (name || "··").split(" ").map((s) => s[0]).join("").slice(0, 2);
  return (
    <span className="relative inline-flex shrink-0 items-center justify-center rounded-md bg-paper text-[11px] font-semibold text-black" style={{ width: size, height: size }}>
      {initials}
      {Icon && (
        <span className="absolute -bottom-1 -right-1 flex h-4 w-4 items-center justify-center rounded-full border border-black bg-[#1A1A1A] text-ink-700">
          <Icon className="h-2.5 w-2.5" strokeWidth={2} />
        </span>
      )}
    </span>
  );
}

/** The person card at the foot of the sidebar; opens the list of people. */
function PersonMenu({ collapsed }: { collapsed: boolean }) {
  const { meta, users, switchUser } = useSession();
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);
  const router = useRouter();
  useOutside(ref, () => setOpen(false));
  const u = meta?.user;
  return (
    <div className="relative" ref={ref}>
      <button onClick={() => setOpen((o) => !o)} title="Switch person"
        className={clsx("flex w-full items-center gap-2.5 rounded-lg border border-line p-2 text-left transition-colors hover:border-line-strong hover:bg-canvas",
          collapsed && "justify-center border-transparent")}>
        <Avatar name={u?.name} role={u?.role} />
        {!collapsed && (
          <>
            <span className="min-w-0 flex-1 leading-tight">
              <span className="block truncate text-[12.5px] font-medium text-ink-900">{u?.name || "Loading"}</span>
              <span className="block truncate text-[11px] text-ink-500">{ROLE_LABEL[u?.role] || ""}</span>
            </span>
            <ChevronsUpDown className="h-3.5 w-3.5 text-ink-400" />
          </>
        )}
      </button>
      <AnimatePresence>
        {open && (
          <motion.div initial={{ opacity: 0, y: 8, scale: 0.98 }} animate={{ opacity: 1, y: 0, scale: 1 }} exit={{ opacity: 0, y: 8, scale: 0.98 }}
            transition={{ duration: 0.18, ease: EASE }}
            className="absolute bottom-[calc(100%+8px)] left-0 z-50 max-h-[70vh] w-[320px] origin-bottom-left overflow-y-auto rounded-lg border border-line-strong bg-[#0B0B0B] p-1 shadow-pop">
            <div className="px-3 pb-2 pt-2.5 text-[12px] leading-snug text-ink-500">See the app the way each person does. Everyone only sees what their job needs.</div>
            {PERSON_GROUPS.map((g) => (
              <div key={g.label} className="py-1">
                <div className="label px-3 py-1">{g.label}</div>
                {users.filter((x) => g.roles.includes(x.role)).map((x) => (
                  <button key={x.id} onClick={() => { switchUser(x.id); setOpen(false); router.push(homeFor(x.role)); }}
                    className={clsx("flex w-full items-center gap-2.5 rounded-md px-2.5 py-2 text-left transition-colors hover:bg-canvas", x.id === u?.id && "bg-canvas")}>
                    <Avatar name={x.name} role={x.role} size={28} />
                    <span className="min-w-0 flex-1">
                      <span className="block text-[13px] font-medium text-ink-900">{x.name}</span>
                      <span className="block truncate text-[11.5px] text-ink-500">{x.title}</span>
                    </span>
                    {x.id === u?.id && <span className="h-1.5 w-1.5 rounded-full bg-ok-600" />}
                  </button>
                ))}
              </div>
            ))}
            <Link href="/start" onClick={() => setOpen(false)} className="mt-1 flex items-center gap-2 border-t border-line px-3 py-2.5 text-[12.5px] text-ink-500 hover:text-ink-900">
              <Users className="h-3.5 w-3.5" /> Open the start screen
            </Link>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}

function NavList({ items, collapsed, path, onNavigate }: { items: typeof NAV; collapsed: boolean; path: string; onNavigate?: () => void }) {
  const active = navFor(path)?.id;
  return (
    <nav className="space-y-5">
      {NAV_GROUPS.map((g) => {
        const list = items.filter((n) => n.group === g);
        if (!list.length) return null;
        return (
          <div key={g}>
            {!collapsed ? <div className="label mb-1.5 px-3 text-ink-400">{g}</div> : <div className="mx-auto mb-2 h-px w-6 bg-line" />}
            <div className="space-y-0.5">
              {list.map((n) => {
                const on = n.id === active;
                return (
                  <Link key={n.id} href={n.href} onClick={onNavigate} title={collapsed ? n.label : undefined}
                    className={clsx("group relative flex items-center gap-3 rounded-md px-3 py-2 text-[13.5px] transition-colors",
                      collapsed && "justify-center px-0", on ? "text-ink-900" : "text-ink-500 hover:text-ink-900")}>
                    {on && <motion.span layoutId="nav-active" className="absolute inset-0 rounded-md border border-line-strong bg-canvas"
                      transition={{ type: "spring", stiffness: 500, damping: 40 }} />}
                    {on && <motion.span layoutId="nav-bar" className="absolute -left-3 top-1/2 h-4 w-[3px] -translate-y-1/2 rounded-r bg-paper"
                      transition={{ type: "spring", stiffness: 500, damping: 40 }} />}
                    <n.icon className={clsx("relative h-[17px] w-[17px] shrink-0 transition-transform duration-200 group-hover:scale-110", on ? "text-ink-900" : "text-ink-400 group-hover:text-ink-700")} strokeWidth={1.75} />
                    {!collapsed && <span className="relative truncate">{n.label}</span>}
                  </Link>
                );
              })}
            </div>
          </div>
        );
      })}
    </nav>
  );
}

function DetailSwitch() {
  const { detail, setDetail } = useSession();
  return (
    <button onClick={() => setDetail(!detail)} title="Show or hide technical details such as model accuracy and raw data"
      className="hidden items-center gap-2 rounded-md px-2 py-1.5 text-[12px] text-ink-500 transition-colors hover:text-ink-900 md:flex">
      <span className={clsx("relative h-4 w-7 rounded-full border transition-colors duration-300", detail ? "border-paper bg-paper" : "border-line-strong bg-transparent")}>
        <motion.span layout transition={{ type: "spring", stiffness: 600, damping: 35 }}
          className={clsx("absolute top-[1px] h-3 w-3 rounded-full", detail ? "right-[1px] bg-black" : "left-[1px] bg-ink-500")} />
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
  const go = (href: string) => { router.push(href); onClose(); };
  return (
    <AnimatePresence>
      {open && (
        <motion.div className="fixed inset-0 z-[70] flex items-start justify-center bg-black/70 px-4 pt-[14vh] backdrop-blur-sm" onClick={onClose}
          initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}>
          <motion.div className="w-full max-w-lg overflow-hidden rounded-xl border border-line-strong bg-[#0B0B0B] shadow-pop" onClick={(e) => e.stopPropagation()}
            initial={{ opacity: 0, y: -10, scale: 0.98 }} animate={{ opacity: 1, y: 0, scale: 1 }} exit={{ opacity: 0, y: -10, scale: 0.98 }} transition={{ duration: 0.2, ease: EASE }}>
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
              <kbd className="label rounded border border-line-strong px-1.5">esc</kbd>
            </div>
            <div className="max-h-96 overflow-y-auto p-1.5">
              {items.map((n, k) => (
                <button key={n.id} onMouseEnter={() => setI(k)} onClick={() => go(n.href)}
                  className={clsx("relative flex w-full items-center gap-3 rounded-md px-3 py-2.5 text-left", k === i ? "text-ink-900" : "text-ink-700")}>
                  {k === i && <motion.span layoutId="palette-active" className="absolute inset-0 rounded-md bg-canvas" transition={{ type: "spring", stiffness: 600, damping: 40 }} />}
                  <span className="relative flex h-8 w-8 items-center justify-center rounded-md border border-line-strong bg-black"><n.icon className="h-4 w-4 text-ink-500" strokeWidth={1.75} /></span>
                  <span className="relative flex-1"><span className="block text-[13.5px] font-medium">{n.label}</span><span className="block text-[11.5px] text-ink-500">{n.desc}</span></span>
                  {k === i && <CornerDownLeft className="relative h-3.5 w-3.5 text-ink-400" />}
                </button>
              ))}
              {!items.length && <div className="px-3 py-6 text-center text-xs text-ink-500">Nothing matches.</div>}
            </div>
          </motion.div>
        </motion.div>
      )}
    </AnimatePresence>
  );
}

function SidebarBody({ collapsed, setCollapsed, items, path, onNavigate, mobile }:
  { collapsed: boolean; setCollapsed?: (v: boolean) => void; items: typeof NAV; path: string; onNavigate?: () => void; mobile?: boolean }) {
  const { meta } = useSession();
  return (
    <div className="flex h-full flex-col">
      <div className={clsx("flex h-[60px] shrink-0 items-center border-b border-line", collapsed ? "justify-center px-2" : "justify-between px-4")}>
        <Link href={items.some((n) => n.id === "overview") ? "/" : items[0]?.href || "/"} onClick={onNavigate}>{collapsed ? <LogoMark size={24} /> : <Wordmark />}</Link>
        {!collapsed && setCollapsed && !mobile && (
          <button onClick={() => setCollapsed(true)} className="rounded-md p-1.5 text-ink-400 transition-colors hover:bg-canvas hover:text-ink-900" aria-label="Collapse menu" title="Collapse menu">
            <ChevronsLeft className="h-4 w-4" />
          </button>
        )}
      </div>
      <div className={clsx("flex-1 overflow-y-auto py-5", collapsed ? "px-2" : "px-3")}>
        <NavList items={items} collapsed={collapsed} path={path} onNavigate={onNavigate} />
      </div>
      <div className={clsx("shrink-0 space-y-2 border-t border-line", collapsed ? "p-2" : "p-3")}>
        {collapsed && setCollapsed && (
          <button onClick={() => setCollapsed(false)} className="flex w-full justify-center rounded-md p-2 text-ink-400 hover:bg-canvas hover:text-ink-900" aria-label="Expand menu" title="Expand menu">
            <ChevronsRight className="h-4 w-4" />
          </button>
        )}
        {!collapsed && meta && (
          <div className="label flex items-center gap-2 px-1 text-ink-400" title={meta.disclaimer}>
            <span className="h-1.5 w-1.5 animate-blink rounded-full bg-warn-500" />
            Demo · {new Date(meta.scenario_date + "T00:00:00").toLocaleDateString("en-GB", { day: "2-digit", month: "short", year: "numeric" })}
          </div>
        )}
        <PersonMenu collapsed={collapsed} />
      </div>
    </div>
  );
}

export function Shell({ children }: { children: ReactNode }) {
  const path = usePathname();
  const router = useRouter();
  const { meta, metaError } = useSession();
  const [palette, setPalette] = useState(false);
  const [mobile, setMobile] = useState(false);
  const [collapsed, setCollapsedState] = useState(false);
  const allowed = meta?.pages || [];
  const navItems = useMemo(() => NAV.filter((n) => allowed.includes(n.id)), [allowed]);
  const here = navFor(path);
  const bare = path.startsWith("/start");

  useEffect(() => { try { setCollapsedState(localStorage.getItem("rf.nav") === "min"); } catch {} }, []);
  const setCollapsed = (v: boolean) => { setCollapsedState(v); try { localStorage.setItem("rf.nav", v ? "min" : "full"); } catch {} };

  // First visit: open on the start screen, where people pick who they are.
  useEffect(() => {
    try { if (path === "/" && !localStorage.getItem("rf.started")) router.replace("/start"); } catch {}
  }, [path, router]);

  useEffect(() => {
    const k = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") { e.preventDefault(); setPalette((p) => !p); }
    };
    window.addEventListener("keydown", k);
    return () => window.removeEventListener("keydown", k);
  }, []);
  useEffect(() => setMobile(false), [path]);

  if (bare) return <>{children}</>;

  // The server answers 503 while it prepares the demo (first start, or after a reset).
  const booting = metaError?.status === 503 || (!!meta?.status && !meta.status.ready);

  return (
    <div className="flex min-h-screen">
      {/* Sidebar (desktop) */}
      <motion.aside animate={{ width: collapsed ? 72 : 248 }} transition={{ duration: 0.3, ease: EASE }}
        className="sticky top-0 hidden h-screen shrink-0 border-r border-line bg-[#050505] lg:block">
        <SidebarBody collapsed={collapsed} setCollapsed={setCollapsed} items={navItems} path={path} />
      </motion.aside>

      {/* Sidebar (phones and tablets) */}
      <AnimatePresence>
        {mobile && (
          <>
            <motion.div className="fixed inset-0 z-50 bg-black/70 backdrop-blur-sm lg:hidden" onClick={() => setMobile(false)}
              initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} />
            <motion.aside className="fixed bottom-0 left-0 top-0 z-50 w-[280px] border-r border-line-strong bg-[#050505] lg:hidden"
              initial={{ x: "-100%" }} animate={{ x: 0 }} exit={{ x: "-100%" }} transition={{ type: "spring", stiffness: 380, damping: 40 }}>
              <button onClick={() => setMobile(false)} className="absolute right-3 top-3.5 z-10 rounded-md p-1.5 text-ink-500 hover:bg-canvas" aria-label="Close menu"><X className="h-5 w-5" /></button>
              <SidebarBody collapsed={false} items={navItems} path={path} onNavigate={() => setMobile(false)} mobile />
            </motion.aside>
          </>
        )}
      </AnimatePresence>

      <div className="flex min-w-0 flex-1 flex-col">
        <header className="sticky top-0 z-30 border-b border-line bg-black/80 backdrop-blur-md">
          <div className="mx-auto flex h-[60px] max-w-[1360px] items-center gap-3 px-4 lg:px-8">
            <button className="-ml-1 rounded-md p-1.5 text-ink-700 hover:bg-canvas lg:hidden" onClick={() => setMobile(true)} aria-label="Open menu"><Menu className="h-5 w-5" /></button>
            <div className="lg:hidden"><LogoMark size={22} /></div>
            <AnimatePresence mode="wait">
              <motion.div key={here?.id || path} initial={{ opacity: 0, y: 4 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: -4 }} transition={{ duration: 0.2 }}
                className="hidden min-w-0 items-center gap-2 text-[13px] sm:flex">
                <span className="text-ink-400">{here?.group || "ReverseFlow"}</span>
                <span className="text-ink-300">/</span>
                <span className="truncate font-medium text-ink-900">{here?.label || ""}</span>
              </motion.div>
            </AnimatePresence>
            <div className="ml-auto flex items-center gap-1.5 sm:gap-2">
              <button onClick={() => setPalette(true)} aria-label="Search pages"
                className="flex h-8 items-center gap-2 rounded-md border border-line-strong px-2.5 text-[12.5px] text-ink-500 transition-colors hover:border-ink-500 hover:text-ink-900">
                <Search className="h-3.5 w-3.5" />
                <span className="hidden md:inline">Jump to</span>
                <kbd className="label hidden rounded border border-line px-1 md:inline">⌘K</kbd>
              </button>
              {meta?.user?.role !== "customer" && <DetailSwitch />}
              <Link href="/start" title="Start screen" className="hidden rounded-md p-2 text-ink-500 transition-colors hover:bg-canvas hover:text-ink-900 sm:block"><LogIn className="h-4 w-4" /></Link>
            </div>
          </div>
        </header>

        {metaError && metaError.status !== 503 && (
          IS_HOSTED ? (
            <div className="border-b border-line bg-canvas px-6 py-2.5 text-[13px] text-ink-700">
              <span className="mr-2 inline-block h-1.5 w-1.5 animate-blink rounded-full bg-warn-500" />Waking up the demo server. This takes about a minute on the free plan; the page will load by itself.
            </div>
          ) : (
            <div className="border-b border-[#4A2620] bg-bad-50 px-6 py-2.5 text-[13px] text-bad-700">
              Can't reach the data service. Start it with <span className="font-mono">cd backend && .venv/bin/uvicorn app.main:app --port 8040</span>
            </div>
          )
        )}
        <main className="mx-auto w-full max-w-[1360px] flex-1 px-4 py-7 lg:px-8 lg:py-9">{booting ? <GettingReady /> : children}</main>
        <footer className="border-t border-line">
          <div className="label mx-auto flex max-w-[1360px] flex-wrap items-center gap-x-6 gap-y-2 px-4 py-5 lg:px-8">
            <span>© 2026 ReverseFlow</span>
            <span className="flex items-center gap-2"><span className="h-1.5 w-1.5 rounded-full bg-warn-500" />Demo data · numbers are illustrative</span>
            {meta && <span>Scenario date {day(meta.scenario_date)} 2026</span>}
            <span>SAP Hackfest 2026 · Team BugFixers</span>
            <button onClick={() => window.scrollTo({ top: 0, behavior: "smooth" })} className="ml-auto flex items-center gap-1.5 hover:text-ink-900">Back to top <ArrowUp className="h-3 w-3" /></button>
          </div>
        </footer>
      </div>
      <CommandPalette open={palette} onClose={() => setPalette(false)} allowed={allowed} />
    </div>
  );
}

function GettingReady() {
  return (
    <div className="py-10">
      <div className="label mb-5 flex items-center gap-2"><span className="h-1.5 w-1.5 animate-blink rounded-full bg-warn-500" />Starting up</div>
      <h1 className="display text-[44px] text-ink-900 sm:text-[72px]">Getting the<br />demo ready.</h1>
      <p className="mt-6 max-w-xl text-[16px] leading-relaxed text-ink-500">
        The server is building the demo data, training its models and running the six agents for the first time.
        {IS_HOSTED ? " On the free hosting plan this can take a few minutes." : " This takes about half a minute."} This page opens by itself when it's done.
      </p>
      <div className="mt-8 h-1 max-w-xl overflow-hidden rounded-full bg-canvas"><div className="h-full w-1/3 rounded-full bg-ink-900" style={{ animation: "slide 1.6s ease-in-out infinite" }} /></div>
    </div>
  );
}
