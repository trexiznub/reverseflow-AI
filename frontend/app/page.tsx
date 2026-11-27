"use client";
import clsx from "clsx";
import { AlertTriangle, ArrowRight, ArrowUpRight, Bell, Bot, Check, Gauge, Inbox, MapPinned, RefreshCw, SearchCheck, Store, TrendingUp, Truck } from "lucide-react";
import { KIND_ICON } from "@/lib/nav";
import { IconTile } from "@/components/ui";
import Link from "next/link";
import { useState } from "react";
import { motion } from "framer-motion";
import { EASE } from "@/components/motion";
import { useToast } from "@/components/providers";
import { Badge, BigStats, btnCls, Button, Card, CardHead, Empty, ErrorState, Loading, More, Section, statusText, statusTone } from "@/components/ui";
import { IndiaMap } from "@/components/IndiaMap";
import { post, useApi } from "@/lib/api";
import { AGENT_LABEL, AGENT_NO, day, dayTime, inr, KIND_LABEL, mult, num, pct } from "@/lib/format";

const AGENT_HREF: Record<string, string> = {
  prediction: "/forecasting", intelligence: "/root-cause", prevention: "/governance", logistics: "/governance", recovery: "/recovery", governance: "/governance",
};

function Timeline({ items }: { items: any[] }) {
  return (
    <Card pad={false} className="overflow-hidden">
      <div className="border-b border-line px-5 py-4">
        <div className="label">Day by day</div>
        <div className="mt-1 text-[15px] font-semibold">What the agents did in the week before the peak</div>
      </div>
      <div className="grid grid-cols-1 divide-y divide-line md:grid-cols-7 md:divide-x md:divide-y-0">
        {items.map((s, i) => (
          <Link key={i} href={AGENT_HREF[s.agent] || "/"} className="group relative px-4 py-4 hover:bg-canvas">
            <div className="flex items-center justify-between">
              <span className="num rounded-sm bg-paper px-1.5 py-[1px] text-[11px] font-medium text-black">{s.t}</span>
              <ArrowUpRight className="h-3.5 w-3.5 text-ink-300 group-hover:text-ink-900" />
            </div>
            <div className="mt-3 text-[12.5px] font-semibold leading-tight text-ink-900">{s.title}</div>
            <div className="mt-1.5 text-[11.5px] leading-snug text-ink-500">{s.text}</div>
          </Link>
        ))}
      </div>
    </Card>
  );
}

function Lifecycle({ steps }: { steps: any[] }) {
  if (!steps?.length) return null;
  return (
    <Card>
      <CardHead label="Following one problem through" title="A return doesn't end at the refund"
        sub="How the biggest stitching problem moved from customer complaints to a fix." right={<Link href="/root-cause" className="text-xs font-medium text-blue-600">See the product</Link>} />
      <div className="relative grid grid-cols-2 gap-x-4 gap-y-5 md:grid-cols-4 xl:grid-cols-8">
        {steps.map((s, i) => (
          <div key={s.step} className="relative">
            <div className="flex items-center gap-2">
              <span className={clsx("flex h-6 w-6 shrink-0 items-center justify-center rounded-full border text-[11px] font-semibold",
                s.done ? "border-paper bg-paper text-black" : "border-line-strong text-ink-500")}>
                {s.done ? <Check className="h-3.5 w-3.5" /> : s.step}
              </span>
              {i < steps.length - 1 && <span className={clsx("hidden h-px flex-1 xl:block", s.done ? "bg-ink-500" : "bg-line-strong")} />}
            </div>
            <div className="mt-2.5 text-[12.5px] font-semibold leading-tight">{s.title}</div>
            <div className="num mt-1 text-[12.5px] text-ink-900">{s.metric}</div>
            <div className="mt-0.5 text-[11.5px] leading-snug text-ink-500">{s.detail}</div>
          </div>
        ))}
      </div>
    </Card>
  );
}

/** How a forecast becomes work: returns requested → pickups the vans can make → arrivals at the warehouse → inspections. */
function ForecastToWarehouse({ gaps, reroutes, facilities }: { gaps: any[]; reroutes: any[]; facilities: any[] }) {
  const west = ["PNQ", "BOM", "AMD", "JAI"].map((id) => gaps.find((g) => g.cluster_id === id)).filter(Boolean);
  const facName = (id: string) => (facilities.find((f) => f.id === id)?.name || id).replace(/ Returns (Centre|Hub)$/, "").replace(" West-zone", "");
  if (!west.length) return null;
  return (
    <Section label="From forecast to warehouse" icon={Truck} title="What the forecast means for vans and warehouses, per day at the peak">
      <p className="max-w-3xl text-[13px] leading-relaxed text-ink-500">
        Each forecast return is a pickup request. Vans collect what they can that day; the rest wait. Collected items reach the warehouse
        about a day later, split between warehouses as the routing plan says, and the warehouse inspects what it has capacity for.
        Figures are the average of the three busiest forecast days, before any extra vans or shifts are approved.
      </p>
      <div className="overflow-x-auto rounded-xl border border-line">
        <table className="w-full min-w-[760px] text-[12.5px]">
          <thead><tr className="label border-b border-line text-left">
            <th className="px-4 py-2.5 font-normal">City</th>
            <th className="py-2.5 text-right font-normal">1 · Returns requested</th>
            <th className="py-2.5 text-right font-normal">2 · Vans can collect</th>
            <th className="py-2.5 text-right font-normal">Left waiting</th>
            <th className="py-2.5 pl-6 font-normal">3 · Arrive next day at</th>
            <th className="py-2.5 pr-4 text-right font-normal">4 · Home warehouse inspects</th>
          </tr></thead>
          <tbody>
            {west.map((g: any) => {
              const picked = Math.min(g.planning_volume, g.pickup_capacity);
              const out = reroutes.filter((r) => r.cluster_id === g.cluster_id);
              const outShare = out.reduce((a, r) => a + r.share, 0);
              const home = Math.round(picked * (1 - outShare));
              return (
                <tr key={g.cluster_id} className="border-b border-line last:border-0">
                  <td className="px-4 py-3 font-medium">{g.city}</td>
                  <td className="num py-3 text-right">{num(g.planning_volume)}</td>
                  <td className="num py-3 text-right">{num(g.pickup_capacity)}</td>
                  <td className={clsx("num py-3 text-right", g.pickup_gap > 0 ? "text-bad-700" : "text-ink-500")}>{g.pickup_gap > 0 ? num(g.pickup_gap) : "0"}</td>
                  <td className="py-3 pl-6 text-ink-700">
                    <span className="num">{num(home)}</span> at home warehouse
                    {out.map((r) => <span key={r.facility_id} className="text-ink-500"> · <span className="num">{num(Math.round(picked * r.share))}</span> to {facName(r.facility_id)}</span>)}
                  </td>
                  <td className={clsx("num py-3 pr-4 text-right", home > g.inspection_capacity ? "text-bad-700" : "text-ok-700")}>{num(g.inspection_capacity)}{home > g.inspection_capacity ? " (short)" : ""}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
      <p className="text-[11.5px] text-ink-500">Network-scale figures from the forecast and the routing plan (demo data). Reroutes shown are suggestions until approved.</p>
    </Section>
  );
}

export default function Overview() {
  const toast = useToast();
  const { data, error, loading, reload } = useApi<any>("/overview", { poll: 15000 });
  const geo = useApi<any>("/geo");
  const ap = useApi<any>("/approvals");
  const [running, setRunning] = useState(false);

  if (error) return <ErrorState error={error} onRetry={reload} />;
  if (loading || !data) return <Loading rows={2} />;
  const k = data.kpis;
  const clusters = geo.data?.clusters || [];
  const fac = geo.data?.facilities || [];
  const facById = Object.fromEntries(fac.map((f: any) => [f.id, f]));
  const cluById = Object.fromEntries(clusters.map((c: any) => [c.id, c]));
  const flows = (data.reroutes || []).filter((r: any) => cluById[r.cluster_id] && facById[r.facility_id]).map((r: any) => ({
    from: [cluById[r.cluster_id].lon, cluById[r.cluster_id].lat], to: [facById[r.facility_id].lon, facById[r.facility_id].lat], label: pct(r.share),
  }));
  const run = data.last_run;
  const waiting = (ap.data?.items || [])
    .filter((i: any) => ["pending", "escalated"].includes(i.status))
    .sort((a: any, b: any) => Number(b.can_decide) - Number(a.can_decide) || (b.priority === "high" ? 1 : 0) - (a.priority === "high" ? 1 : 0) || (b.impact_inr || 0) - (a.impact_inr || 0));
  const top = waiting.slice(0, 4);
  const gaps = data.capacity_gaps || [];
  const short = gaps.filter((g: any) => g.planning_volume > g.pickup_capacity);
  const weekday = new Date(data.scenario_date + "T00:00:00").toLocaleDateString("en-GB", { weekday: "long", day: "numeric", month: "long", year: "numeric" });

  const refresh = async () => {
    setRunning(true);
    try {
      await post("/orchestrator/run", { trigger: "full_cycle" });
      toast("info", "Analysis is running. Numbers on this page will update in a few seconds.");
      setTimeout(() => { reload(true); ap.reload(true); }, 6000);
    } catch (e: any) { toast("err", e.message); } finally { setRunning(false); }
  };

  return (
    <div className="space-y-14">
      {/* Hero */}
      <section>
        <div className="label mb-5 flex flex-wrap items-center gap-x-3 gap-y-1">
          <span>{weekday}</span><span className="text-ink-300">/</span><span>Day after Navratri</span><span className="text-ink-300">/</span><span>West-zone returns hub</span>
        </div>
        <h1 className="display text-[44px] text-ink-900 sm:text-[68px] xl:text-[84px]">Returns peak<br />in 5 days.</h1>
        <div className="mt-7 grid grid-cols-1 gap-6 lg:grid-cols-[1fr_auto] lg:items-end">
          <p className="max-w-2xl text-[17px] leading-relaxed text-ink-500">
            Pune, Ahmedabad and Jaipur expect about <b className="font-semibold text-ink-900">{mult(k.west_surge_multiplier)} the usual returns</b> next week.
            {short.length > 0 && <> {short.length === gaps.length ? `None of the ${gaps.length} cities` : `${short.length} of ${gaps.length} cities`} {short.length === gaps.length ? "has" : "don't have"} enough pickup vans for the busiest days.</>}
            {" "}<b className="font-semibold text-ink-900">{num(k.pending_approvals)} decisions</b> are waiting for you.
          </p>
          <div className="flex flex-wrap gap-2">
            <Link href="/governance" className={btnCls("primary", "lg")}>Review decisions <ArrowRight className="h-4 w-4" /></Link>
            <Link href="/forecasting" className={btnCls("secondary", "lg")}>See the forecast</Link>
          </div>
        </div>
      </section>

      <BigStats items={[
        { label: "Returns vs a normal week", icon: TrendingUp, value: mult(k.west_surge_multiplier), sub: "Pune, Ahmedabad, Jaipur · next 7 days", tone: "bad", hint: "2× means twice as many returns as an ordinary week at this time of year." },
        { label: "Returns expected, next 7 days", icon: Gauge, value: num(k.network_expected_7d), sub: <>All 8 cities · {num(k.west_expected_7d)} in the west zone ({(k.west_zone_cities || []).join(", ")})</> },
        { label: "Decisions waiting", icon: Inbox, value: num(k.pending_approvals), sub: <Link href="/governance" className="text-blue-600">Open the list</Link>, tone: "warn" },
        { label: "Returns to double-check", icon: SearchCheck, value: num(k.integrity_flags), sub: <Link href="/governance?tab=integrity" className="text-blue-600">Look at them</Link>, hint: "Returns where something doesn't match, like a different serial number. They get a closer look at the warehouse. No customer is refused automatically." },
      ]} />

      {/* What needs you */}
      <Section label="Needs your attention" icon={Bell} title="Start here"
        right={<Link href="/governance" className="text-[13px] text-blue-600">All {waiting.length} decisions</Link>}>
        {ap.error ? <ErrorState error={ap.error} /> : !ap.data ? <Loading rows={0} /> : top.length === 0 ? <Empty title="Nothing waiting. You're all caught up." /> : (
          <div className="overflow-hidden rounded-xl border border-line">
            {top.map((r: any, i: number) => (
              <Link key={r.id} href={`/governance?open=${r.id}`} className="group grid grid-cols-[40px_1fr_auto] items-center gap-4 border-b border-line bg-white px-4 py-4 transition-colors duration-200 last:border-0 hover:bg-[#111] sm:grid-cols-[48px_1fr_220px_auto] sm:px-5">
                <IconTile icon={KIND_ICON[r.kind] || ArrowRight} tone={r.priority === "high" ? "bad" : "neutral"} />
                <div className="min-w-0">
                  <div className="flex flex-wrap items-center gap-2">
                    <span className="label text-ink-500">{KIND_LABEL[r.kind] || r.kind}</span>
                    {r.priority === "high" && <Badge tone="bad">urgent</Badge>}
                    {!r.can_decide && <Badge>needs another approver</Badge>}
                  </div>
                  <div className="mt-1.5 text-[17px] font-semibold leading-snug text-ink-900 group-hover:underline group-hover:decoration-ink-500 group-hover:underline-offset-4">{r.title}</div>
                </div>
                <div className="hidden text-[12.5px] text-ink-500 sm:block">
                  <div>Benefit <span className="num text-ink-900">{r.impact_inr ? inr(r.impact_inr, true) : "—"}</span> · Cost <span className="num text-ink-900">{r.cost_inr ? inr(r.cost_inr, true) : "₹0"}</span></div>
                  {(r.impact_inr || r.cost_inr) ? <div>Net <span className={clsx("num font-medium", r.net_inr >= 0 ? "text-ok-700" : "text-bad-700")}>{r.net_inr >= 0 ? "+" : "−"}{inr(Math.abs(r.net_inr), true)}</span></div> : null}
                </div>
                <span className="flex h-9 w-9 items-center justify-center rounded-full border border-line-strong text-ink-500 transition-all duration-300 group-hover:translate-x-0.5 group-hover:border-paper group-hover:bg-paper group-hover:text-black"><ArrowRight className="h-4 w-4" /></span>
              </Link>
            ))}
          </div>
        )}
      </Section>

      <ForecastToWarehouse gaps={gaps} reroutes={data.reroutes || []} facilities={fac} />

      {/* Where and can we cope */}
      <div className="grid grid-cols-1 gap-5 xl:grid-cols-5">
        <Card className="xl:col-span-3">
          <CardHead icon={MapPinned} label="Where" title="Where the returns will land" sub="Each circle is a city. Lines show returns being sent to a less busy warehouse."
            right={<Link href="/forecasting" className="text-xs font-medium text-blue-600">Forecast</Link>} />
          {geo.error ? <ErrorState error={geo.error} /> : <IndiaMap clusters={clusters} facilities={fac} flows={flows} height={440} />}
        </Card>
        <Card className="xl:col-span-2">
          <CardHead icon={Truck} label="Can we cope?" title="Pickup vans at the busiest days" sub="How many returns each city needs to collect per day, against what its vans can carry."
            right={<Link href="/governance" className="text-xs font-medium text-blue-600">Van decisions</Link>} />
          <div className="space-y-5">
            {[...gaps].sort((x: any, y: any) => (y.planning_volume - y.pickup_capacity) - (x.planning_volume - x.pickup_capacity)).slice(0, 4).map((g: any) => {
              const over = g.planning_volume - g.pickup_capacity;
              const covered = Math.min(1, g.pickup_capacity / g.planning_volume);
              return (
                <div key={g.cluster_id}>
                  <div className="flex items-baseline justify-between gap-2">
                    <span className="text-[14px] font-semibold">{g.city}</span>
                    {over > 0 ? <span className="text-[12px] text-bad-700">short by <span className="num">{num(over)}</span> a day</span> : <Badge tone="ok">enough vans</Badge>}
                  </div>
                  <div className="mt-2 flex h-2 overflow-hidden rounded-full bg-canvas">
                    <motion.div className="h-full bg-ink-900" initial={{ width: 0 }} whileInView={{ width: `${covered * 100}%` }} viewport={{ once: true }} transition={{ duration: 0.9, ease: EASE }} />
                    {over > 0 && <div className="hatch h-full flex-1 border-l border-black bg-bad-600/40" />}
                  </div>
                  <div className="mt-1.5 flex justify-between text-[11.5px] text-ink-500">
                    <span>Vans carry <span className="num text-ink-900">{num(g.pickup_capacity)}</span></span>
                    <span>Needed <span className="num text-ink-900">{num(g.planning_volume)}</span></span>
                  </div>
                </div>
              );
            })}
            {gaps.length > 4 && <div className="text-[12px] text-ink-500">{gaps.length - 4} more cities are tight too. <Link href="/governance" className="text-blue-600">See the suggested vans</Link></div>}
          </div>
        </Card>
      </div>

      {/* Product problems, in one line each */}
      {data.vendor_findings?.length > 0 && (
        <Section label="Why items come back" icon={Store} title="Sellers with a clear quality problem"
          right={<Link href="/root-cause" className="text-[13px] text-blue-600">See all product issues</Link>}>
          <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
            {data.vendor_findings.slice(0, 2).map((v: any) => (
              <Card key={v.vendor_id + v.reason}>
                <div className="flex items-center gap-2.5"><IconTile icon={AlertTriangle} tone="bad" size="sm" /><div className="label">{v.vendor_name}</div></div>
                <div className="mt-3 text-[18px] font-semibold leading-snug">
                  <span className="display-num text-[34px] text-bad-700">{pct(v.share)}</span> of their returns: <span className="text-ink-700">“{v.reason_label}”</span>
                </div>
                <div className="mt-2 text-[13px] text-ink-500">Other sellers: {pct(v.network_share)}. This is too big a gap to be chance.</div>
                <div className="mt-4 flex items-center gap-3">
                  <div className="relative h-2 flex-1 rounded-full bg-canvas">
                    <motion.div className="absolute inset-y-0 left-0 rounded-full bg-bad-600" initial={{ width: 0 }} whileInView={{ width: `${v.share * 100}%` }} viewport={{ once: true }} transition={{ duration: 0.9, ease: EASE }} />
                    <div className="absolute -top-1 h-4 w-[2px] bg-ink-900" style={{ left: `${v.network_share * 100}%` }} title="Other sellers" />
                  </div>
                </div>
              </Card>
            ))}
          </div>
        </Section>
      )}

      <More title="Alerts and the last analysis" sub="What the agents flagged. How they decided is on How it works; all key figures are under Reports.">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div className="text-[13px] text-ink-500">
            {run ? <>Last analysis {dayTime(run.finished_at || run.started_at)} · {run.summary?.recommendations?.created ?? 0} new suggestions · <Link href={`/agents?run=${run.id}`} className="text-blue-600">see how it decided</Link> · <Link href="/analytics" className="text-blue-600">all key figures</Link></> : "No analysis yet."}
          </div>
          <Button onClick={refresh} loading={running}><RefreshCw className="h-3.5 w-3.5" />Run the analysis again</Button>
        </div>
        <Card>
          <CardHead icon={Bell} label="Alerts" title="Things the agents flagged" right={<Badge>{data.alerts.length}</Badge>} />
          <div className="space-y-3">
            {data.alerts.map((a: any) => (
              <div key={a.id} className="flex gap-3 border-b border-dashed border-line pb-3 last:border-0">
                <span className={clsx("mt-1.5 h-1.5 w-1.5 shrink-0 rounded-full", a.severity === "high" ? "bg-bad-600" : "bg-warn-500")} />
                <div className="min-w-0">
                  <div className="text-[13px] font-medium leading-snug">{a.title}</div>
                  <div className="mt-0.5 text-[12px] leading-snug text-ink-500">{a.body}</div>
                  <div className="label mt-1">{AGENT_LABEL[a.agent] || a.agent}</div>
                </div>
              </div>
            ))}
          </div>
        </Card>
        <div className="text-[12px] text-ink-500">Scenario date {day(data.scenario_date)} 2026. All records are synthetic; city volumes are scaled up to illustrate a full marketplace.</div>
      </More>
    </div>
  );
}
