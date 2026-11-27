"use client";
import clsx from "clsx";
import { AlertTriangle, Bell, Check, Gauge, Lock, PackageX, Ruler, ScanLine, Smile, Star, Store, Target, Undo2 } from "lucide-react";
import { motion } from "framer-motion";
import { CountUp, EASE, itemVariants } from "@/components/motion";
import { useEffect, useState } from "react";
import { Area, AreaChart, Bar, BarChart, CartesianGrid, ComposedChart, Legend, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { axis, C, ChartTooltip, SERIES } from "@/components/charts";
import { useSession, useToast } from "@/components/providers";
import { Badge, Button, Card, CardHead, IconTile, Drawer, Empty, ErrorState, Field, inputCls, Loading, PageHeader, selectCls, Stat, statusText, statusTone, Tabs } from "@/components/ui";
import { post, useApi } from "@/lib/api";
import { day, inr, num, pct } from "@/lib/format";

const REASONS = ["SIZE_SMALL", "SIZE_LARGE", "STITCHING", "COLOUR_MISMATCH", "FABRIC_QUALITY", "NOT_AS_DESCRIBED", "DAMAGED_IN_TRANSIT", "CHANGED_MIND", "LATE_DELIVERY"];

// Bands of the quality score, for reading it at a glance. The score itself comes from the backend.
const band = (q: number) => q >= 80 ? { t: "Trusted", tone: "ok" as const } : q >= 60 ? { t: "Good", tone: "ok" as const } : q >= 40 ? { t: "Watch", tone: "warn" as const } : { t: "At risk", tone: "bad" as const };

function ScoreRing({ value }: { value: number }) {
  const r = 34, c = 2 * Math.PI * r, b = band(value);
  const col = b.tone === "ok" ? "#3FBF7F" : b.tone === "warn" ? "#E3A33B" : "#F0583E";
  return (
    <div className="relative h-[92px] w-[92px] shrink-0">
      <svg viewBox="0 0 80 80" className="h-full w-full -rotate-90">
        <circle cx="40" cy="40" r={r} fill="none" stroke="#1E1E1E" strokeWidth="6" />
        <motion.circle cx="40" cy="40" r={r} fill="none" stroke={col} strokeWidth="6" strokeLinecap="round" strokeDasharray={c}
          initial={{ strokeDashoffset: c }} whileInView={{ strokeDashoffset: c * (1 - value / 100) }} viewport={{ once: true }} transition={{ duration: 1.2, ease: EASE }} />
      </svg>
      <div className="absolute inset-0 flex flex-col items-center justify-center">
        <span className="display-num text-[26px] text-ink-900"><CountUp value={String(Math.round(value))} /></span>
        <span className="label -mt-0.5 text-[9px]">of 100</span>
      </div>
    </div>
  );
}

/** One measure: your figure as a bar, other sellers' average as a tick. Lower is better unless "higher". */
function ScoreBar({ icon: Icon, label, value, others, max = 1, higher, fmt }: { icon: any; label: string; value: number; others?: number; max?: number; higher?: boolean; fmt: (v: number) => string }) {
  const worse = others !== undefined && (higher ? value < others * 0.9 : value > others * 1.2);
  const better = others !== undefined && (higher ? value > others * 1.05 : value < others * 0.85);
  return (
    <motion.div variants={itemVariants} className="rounded-lg border border-line bg-[#090909] p-3.5 transition-colors duration-300 hover:border-line-strong">
      <div className="flex items-center justify-between gap-2">
        <span className="flex min-w-0 items-center gap-2 text-[12.5px] text-ink-700"><Icon className="h-3.5 w-3.5 shrink-0 text-ink-400" strokeWidth={1.75} /><span className="truncate">{label}</span></span>
        <span className={clsx("num text-[14px] font-medium", worse ? "text-bad-700" : better ? "text-ok-700" : "text-ink-900")}>{fmt(value)}</span>
      </div>
      <div className="relative mt-3 h-1.5 rounded-full bg-canvas">
        <motion.div className={clsx("absolute inset-y-0 left-0 rounded-full", worse ? "bg-bad-600" : better ? "bg-ok-600" : "bg-ink-700")}
          initial={{ width: 0 }} whileInView={{ width: `${Math.min(1, value / max) * 100}%` }} viewport={{ once: true }} transition={{ duration: 0.9, ease: EASE }} />
        {others !== undefined && <span className="absolute -top-1 h-3.5 w-[2px] rounded bg-paper/80" style={{ left: `${Math.min(1, others / max) * 100}%` }} title="Other sellers" />}
      </div>
      <div className="mt-2 text-[11px] text-ink-500">{others !== undefined ? <>Other sellers {fmt(others)}{worse ? " · worse" : better ? " · better" : ""}</> : higher ? "Higher is better" : "Lower is better"}</div>
    </motion.div>
  );
}

function SellerScorecard({ vendor, m, n }: { vendor: any; m: any; n: any }) {
  const b = band(m.quality_score);
  const p1 = (v: number) => pct(v, 1);
  return (
    <Card pad={false} className={clsx("overflow-hidden", vendor.qc_hold && "!border-[#4A2620]")}>
      <div className="relative flex flex-wrap items-center gap-5 border-b border-line p-5">
        <div className="grid-paper pointer-events-none absolute inset-0 [mask-image:linear-gradient(to_right,black,transparent_60%)]" />
        <span className="relative"><IconTile icon={Store} size="lg" /></span>
        <div className="relative min-w-0 flex-1">
          <div className="label">Seller account · {vendor.id}</div>
          <div className="mt-1 text-[20px] font-semibold tracking-tight">{vendor.name}</div>
          <div className="mt-1 flex flex-wrap items-center gap-2 text-[12.5px] text-ink-500">
            <span>{vendor.specialty} · {vendor.city}</span>
            {vendor.qc_hold ? <Badge tone="bad"><Lock className="h-3 w-3" />Paused: shipments need a stitching check first</Badge> : <Badge tone="ok" dot>No restrictions</Badge>}
          </div>
        </div>
        <div className="relative flex items-center gap-4">
          <div className="text-right">
            <div className="label">Quality score</div>
            <div className="mt-1"><Badge tone={b.tone} dot>{b.t}</Badge></div>
            <div className="mt-1.5 text-[11.5px] text-ink-500">{m.returns} returns · {num(m.orders)} orders</div>
          </div>
          <ScoreRing value={m.quality_score} />
        </div>
      </div>
      <div className="p-5">
        <div className="mb-3 flex flex-wrap items-baseline justify-between gap-2">
          <div className="text-[14px] font-semibold">Your scorecard, last 90 days</div>
          <div className="text-[11.5px] text-ink-500">Worked out by ReverseFlow from returns, inspections and reviews. The tick shows other sellers.</div>
        </div>
        <motion.div initial="hidden" whileInView="show" viewport={{ once: true }} variants={{ hidden: {}, show: { transition: { staggerChildren: 0.05 } } }}
          className="grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-4">
          <ScoreBar icon={Undo2} label="Return rate" value={m.return_rate} others={n.return_rate} max={0.5} fmt={p1} />
          <ScoreBar icon={AlertTriangle} label="Returned for quality" value={m.defect_rate} others={n.defect_rate} max={0.6} fmt={p1} />
          <ScoreBar icon={Ruler} label="Returned for size" value={m.size_issue_rate} others={n.size_issue_rate} max={0.6} fmt={p1} />
          <ScoreBar icon={Target} label="Avoidable returns" value={m.avoidable_rate} others={n.avoidable_rate} max={1} fmt={p1} />
          <ScoreBar icon={PackageX} label="Graded C at inspection" value={m.grade_c_rate} max={0.5} fmt={p1} />
          <ScoreBar icon={Star} label="Average review" value={m.avg_rating ?? 0} max={5} higher fmt={(v) => v ? v.toFixed(2) + " / 5" : "—"} />
          <ScoreBar icon={Smile} label="Review mood" value={(m.review_sentiment + 1) / 2} max={1} higher fmt={(v) => `${Math.round(v * 100)} / 100`} />
          <ScoreBar icon={Gauge} label="Quality score" value={m.quality_score} max={100} higher fmt={(v) => `${Math.round(v)} / 100`} />
        </motion.div>
      </div>
    </Card>
  );
}

function AlertList({ alerts, onAck }: { alerts: any[]; onAck: (id: number) => void }) {
  if (!alerts.length) return <Empty title="No alerts" icon={<Bell className="h-5 w-5" />} />;
  return (
    <div className="space-y-2">
      {alerts.map((a) => (
        <div key={a.id} className={clsx("rounded border p-2.5", a.acknowledged ? "border-line bg-white" : "border-[#4A3A17] bg-warn-50")}>
          <div className="flex items-start justify-between gap-2">
            <div className="text-[12.5px] font-medium leading-snug">{a.title}</div>
            {a.acknowledged ? <Badge tone="ok"><Check className="h-3 w-3" />seen</Badge> : <Button size="sm" onClick={() => onAck(a.id)}>Mark as seen</Button>}
          </div>
          <div className="mt-1 text-[11.5px] leading-snug text-ink-500">{a.body}</div>
        </div>
      ))}
    </div>
  );
}

function VendorView({ vendorId }: { vendorId?: string }) {
  const toast = useToast();
  const { meta } = useSession();
  const { data, error, loading, reload } = useApi<any>(`/partners/vendor${vendorId ? `?vendor_id=${vendorId}` : ""}`, { deps: [vendorId] });
  const [respond, setRespond] = useState<any>(null);
  const [note, setNote] = useState("");
  if (error) return <ErrorState error={error} onRetry={reload} />;
  if (loading || !data) return <Loading />;
  const m = data.metrics, n = data.network;
  const ack = async (id: number) => { try { await post(`/alerts/${id}/ack`); reload(true); toast("ok", "Alert acknowledged"); } catch (e: any) { toast("err", e.message); } };
  const send = async () => {
    try { await post("/partners/vendor/response", { recommendation_id: respond.id, note }); toast("ok", "Response sent to the marketplace quality team"); setRespond(null); setNote(""); }
    catch (e: any) { toast("err", e.message); }
  };
  const isVendor = meta?.user?.role === "vendor";
  return (
    <div className="space-y-4">
      <SellerScorecard vendor={data.vendor} m={m} n={n} />
      <div className="grid grid-cols-1 gap-4 xl:grid-cols-3">
        <Card className="xl:col-span-2">
          <CardHead label="By product" title="Where your returns come from" sub="Last 90 days. Reasons come from warehouse checks and what customers wrote." />
          <div className="overflow-x-auto">
            <table className="w-full min-w-[600px] text-[12px]">
              <thead><tr className="label text-left"><th className="pb-2 font-normal">Product</th><th className="pb-2 text-right font-semibold">Returns</th><th className="pb-2 font-normal pl-4">Top reason</th><th className="pb-2 font-normal">By size</th></tr></thead>
              <tbody>
                {data.sku_patterns.map((s: any) => (
                  <tr key={s.sku} className="border-t border-line align-top">
                    <td className="py-1.5"><div className="font-medium">{s.name}</div><div className="font-mono text-[10.5px] text-ink-400">{s.sku}</div></td>
                    <td className="num py-1.5 text-right">{s.returns}</td>
                    <td className="py-1.5 pl-4">{s.top_reason} <span className="num text-ink-500">{pct(s.top_share)}</span></td>
                    <td className="py-1.5"><div className="flex gap-1">{Object.entries(s.by_size).map(([k, v]: any) => <span key={k} className="num rounded bg-canvas px-1 text-[10.5px]">{k}:{v}</span>)}</div></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Card>
        <Card>
          <CardHead label="Alerts" title="Messages about quality" />
          <AlertList alerts={data.alerts} onAck={ack} />
        </Card>
      </div>
      <div className="grid grid-cols-1 gap-4 xl:grid-cols-3">
        <Card>
          <CardHead label="Why customers return" title="Reasons" />
          <div className="h-56">
            <ResponsiveContainer>
              <BarChart data={Object.entries(data.reason_mix).map(([k, v]) => ({ k, v }))} layout="vertical" margin={{ left: 40 }}>
                <XAxis type="number" {...axis} /><YAxis type="category" dataKey="k" {...axis} width={130} />
                <Tooltip content={<ChartTooltip />} /><Bar dataKey="v" name="Returns" fill={C.navy} barSize={10} radius={[0, 3, 3, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </div>
        </Card>
        <Card>
          <CardHead label="Customer comments" title="In their words" sub={data.privacy} />
          <div className="max-h-56 space-y-2 overflow-y-auto">
            {data.complaints.map((c: any, i: number) => <div key={i} className="border-l-2 border-line-strong pl-2 text-[12px] text-ink-700">“{c.text}”<div className="text-[10.5px] text-ink-400">{c.reason} · size {c.size} · {day(c.date)}</div></div>)}
          </div>
        </Card>
        <Card>
          <CardHead label="Over time" title="Return rate by month" />
          <div className="h-56">
            <ResponsiveContainer>
              <LineChart data={data.trend} margin={{ left: -14, right: 6 }}>
                <CartesianGrid stroke={C.grid} vertical={false} /><XAxis dataKey="month" {...axis} interval={2} /><YAxis {...axis} tickFormatter={(v) => pct(v)} />
                <Tooltip content={<ChartTooltip fmt={(v: number) => pct(v, 1)} />} /><Line dataKey="return_rate" name="Return rate" stroke={C.blue} strokeWidth={2} dot={false} />
              </LineChart>
            </ResponsiveContainer>
          </div>
        </Card>
      </div>
      <Card>
        <CardHead label="Requests from the marketplace" title="Changes asked of your shop" sub="Decided by the marketplace quality team. Tell them what you have fixed." />
        {data.recommendations.length === 0 ? <Empty title="Nothing asked of you right now" /> : (
          <div className="space-y-2">
            {data.recommendations.map((r: any) => (
              <div key={r.id} className="flex flex-wrap items-start justify-between gap-3 rounded border border-line p-3">
                <div className="min-w-0 flex-1"><div className="text-[13px] font-medium">{r.title}</div><div className="mt-0.5 text-[12px] leading-snug text-ink-500">{r.rationale}</div></div>
                <div className="flex items-center gap-2"><Badge tone={statusTone(r.status)}>{statusText(r.status)}</Badge>{isVendor && <Button size="sm" onClick={() => setRespond(r)}>Respond</Button>}</div>
              </div>
            ))}
          </div>
        )}
        <div className="mt-3 flex flex-wrap gap-1.5">
          {data.products.map((p: any) => (
            <span key={p.sku} className="rounded border border-line px-2 py-1 text-[11px]"><span className="font-mono">{p.sku}</span>{p.pre_dispatch_qc && <span className="ml-1 text-ok-700">· checked</span>}{p.exchange_first && <span className="ml-1 text-ok-700">· size swap first</span>}{p.size_chart_version > 1 && <span className="ml-1 text-ok-700">· new size chart</span>}</span>
          ))}
        </div>
      </Card>
      <Drawer open={!!respond} onClose={() => setRespond(null)} title="Reply to the marketplace">
        {respond && (
          <div className="space-y-3">
            <div className="text-[13px] font-medium">{respond.title}</div>
            <Field label="What you have changed"><textarea rows={4} value={note} onChange={(e) => setNote(e.target.value)} className={clsx(inputCls, "h-auto py-2")} placeholder="e.g. Added a second stitching check at our Surat unit from 22 Oct; re-measured size charts for the affected SKUs." /></Field>
            <Button variant="primary" onClick={send} disabled={note.trim().length < 5}>Send to marketplace</Button>
          </div>
        )}
      </Drawer>
    </div>
  );
}

function LogisticsView({ providerId }: { providerId?: string }) {
  const toast = useToast();
  const { data, error, loading, reload } = useApi<any>(`/partners/logistics${providerId ? `?provider_id=${providerId}` : ""}`, { deps: [providerId] });
  const [pick, setPick] = useState<any>(null);
  const [ev, setEv] = useState({ tag_intact: true, serial_scanned: "", weight_delta_pct: 0 });
  const [busy, setBusy] = useState(false);
  useEffect(() => { if (pick) setEv({ tag_intact: true, serial_scanned: pick.expected_serial || "", weight_delta_pct: 0 }); }, [pick]);
  if (error) return <ErrorState error={error} onRetry={reload} />;
  if (loading || !data) return <Loading />;
  const ack = async (id: number) => { try { await post(`/alerts/${id}/ack`); reload(true); } catch (e: any) { toast("err", e.message); } };
  const complete = async () => {
    setBusy(true);
    try {
      const r = await post(`/partners/logistics/pickups/${pick.return_id}/complete`, ev);
      toast("ok", `Picked up ${pick.return_id}. Compliance agent checking evidence (${r.orchestrator_run_id}).`);
      setPick(null); reload(true);
    } catch (e: any) { toast("err", e.message); } finally { setBusy(false); }
  };
  return (
    <div className="space-y-4">
      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        <Stat label="Delivery partner" value={<span className="text-[16px]">{data.provider.name}</span>} sub={`${data.provider.pickups_per_vehicle} pickups per van per day`} />
        <Stat label="Picked up on time, 60 days" value={pct(data.sla.overall_60d, 1)} sub={`Target: within ${data.provider.sla_hours} hours`} tone={data.sla.overall_60d < 0.85 ? "warn" : "ok"} />
        <Stat label="Pickups to do" value={num(data.pickup_tasks.length)} sub="Demo sample" />
        <Stat label="Rate per pickup" value={inr(data.provider.cost_per_pickup)} sub="Example rate" />
      </div>
      <div className="grid grid-cols-1 gap-4 xl:grid-cols-2">
        {data.clusters.map((c: any) => (
          <Card key={c.cluster_id}>
            <CardHead label={`Geographic cluster · ${c.cluster_id}`} title={`${c.city}: expected pickups vs fleet capacity`} sub={data.note}
              right={<div className="text-right"><Badge tone={statusTone(c.risk)} dot>{c.risk}</Badge><div className="num mt-1 text-[11px] text-ink-500">{c.vehicles} vehicles{c.extra_vehicles_approved ? ` (+${c.extra_vehicles_approved} approved)` : ""}</div></div>} />
            <div className="h-52">
              <ResponsiveContainer>
                <ComposedChart data={c.forecast.map((f: any) => ({ ...f, d: day(f.day), cap: c.capacity }))} margin={{ left: -6, right: 6 }}>
                  <CartesianGrid stroke={C.grid} vertical={false} /><XAxis dataKey="d" {...axis} /><YAxis {...axis} />
                  <Tooltip content={<ChartTooltip />} />
                  <Bar dataKey="pickups" name="Forecast pickups" fill={C.blue} barSize={18} radius={[3, 3, 0, 0]} />
                  <Line dataKey="cap" name="Fleet capacity" stroke={C.red} strokeDasharray="4 3" dot={false} strokeWidth={1.6} />
                </ComposedChart>
              </ResponsiveContainer>
            </div>
          </Card>
        ))}
      </div>
      <div className="grid grid-cols-1 gap-4 xl:grid-cols-3">
        <Card pad={false} className="xl:col-span-2">
          <div className="border-b border-line px-4 py-2.5"><div className="text-[13px] font-semibold">Pickup allocation · today's tasks</div><div className="text-[11.5px] text-ink-500">Complete a pickup to capture tag, serial and weight evidence. Portal-created returns are marked.</div></div>
          <div className="max-h-[420px] overflow-auto">
            {data.pickup_tasks.length === 0 ? <div className="p-6"><Empty title="No pickups scheduled" /></div> : (
              <table className="w-full min-w-[640px] text-[12px]">
                <thead className="sticky top-0 bg-white"><tr className="label border-b border-line text-left"><th className="px-4 py-2.5 font-normal">Return</th><th className="py-2.5 font-normal">PIN code</th><th className="py-2.5 font-normal">When</th><th className="py-2.5 font-normal">Take to</th><th className="py-2 pr-4 text-right font-semibold" /></tr></thead>
                <tbody>
                  {data.pickup_tasks.map((t: any) => (
                    <tr key={t.return_id} className={clsx("border-b border-line", t.created_via === "portal" && "bg-canvas")}>
                      <td className="px-4 py-1.5"><span className="font-mono font-medium">{t.return_id}</span>{t.created_via === "portal" && <Badge tone="navy" className="ml-1.5">new</Badge>}<div className="font-mono text-[10.5px] text-ink-400">{t.sku}</div></td>
                      <td className="num py-1.5">{t.pin}</td>
                      <td className="py-1.5">{day(t.pickup_date)} · {t.slot}</td>
                      <td className="py-1.5">{t.facility_id.replace("FAC-", "")}</td>
                      <td className="py-1.5 pr-4 text-right"><Button size="sm" onClick={() => setPick(t)}><ScanLine className="h-3 w-3" />Complete pickup</Button></td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </div>
        </Card>
        <div className="space-y-4">
          <Card>
            <CardHead label="On time" title="Pickups on time, by week" />
            <div className="h-36">
              <ResponsiveContainer>
                <AreaChart data={data.sla.weekly} margin={{ left: -14, right: 6 }}>
                  <XAxis dataKey="week" {...axis} tickFormatter={(v) => day(v)} interval={2} /><YAxis {...axis} domain={[0, 1]} tickFormatter={(v) => pct(v)} />
                  <Tooltip content={<ChartTooltip fmt={(v: number) => pct(v, 1)} />} /><Area dataKey="sla" name="On time" stroke={C.blue} fill={C.band} />
                </AreaChart>
              </ResponsiveContainer>
            </div>
            <div className="mt-2 flex gap-3 text-[11.5px]">{Object.entries(data.sla.by_cluster).map(([k, v]: any) => <span key={k}>{k} <b className="num">{pct(v, 1)}</b></span>)}</div>
          </Card>
          <Card><CardHead label="Alerts" title="From the marketplace" /><AlertList alerts={data.alerts} onAck={ack} /></Card>
        </div>
      </div>
      <Drawer open={!!pick} onClose={() => setPick(null)} title={pick && <>Complete pickup · <span className="font-mono">{pick.return_id}</span></>}>
        {pick && (
          <div className="space-y-3">
            <div className="rounded bg-canvas p-3 text-[12px] text-ink-700">Doorstep checklist. If something doesn't match, the item just gets a closer look at the warehouse. The customer's refund is not held up.</div>
            <label className="flex items-center gap-2 text-[13px]"><input type="checkbox" checked={ev.tag_intact} onChange={(e) => setEv({ ...ev, tag_intact: e.target.checked })} />Brand tag attached</label>
            <Field label="Serial number on the label" hint={`Should be: ${pick.expected_serial}`}><input className={clsx(inputCls, "font-mono")} value={ev.serial_scanned} onChange={(e) => setEv({ ...ev, serial_scanned: e.target.value })} /></Field>
            <Field label="Weight difference from when it was sent (%)"><input type="number" step="0.5" className={inputCls} value={ev.weight_delta_pct} onChange={(e) => setEv({ ...ev, weight_delta_pct: Number(e.target.value) })} /></Field>
            <Button variant="primary" onClick={complete} loading={busy} disabled={!ev.serial_scanned.trim()}>Confirm pickup</Button>
          </div>
        )}
      </Drawer>
    </div>
  );
}

function WarehouseView({ facilityId }: { facilityId?: string }) {
  const toast = useToast();
  const { data, error, loading, reload } = useApi<any>(`/partners/warehouse${facilityId ? `?facility_id=${facilityId}` : ""}`, { deps: [facilityId] });
  const [insp, setInsp] = useState<any>(null);
  const [form, setForm] = useState({ grade: "A", verified_reason: "SIZE_SMALL", defects: "" });
  const [busy, setBusy] = useState<string | null>(null);
  if (error) return <ErrorState error={error} onRetry={reload} />;
  if (loading || !data) return <Loading />;
  const f = data.facility;
  const ack = async (id: number) => { try { await post(`/alerts/${id}/ack`); reload(true); } catch (e: any) { toast("err", e.message); } };
  const receive = async (id: string) => {
    setBusy(id);
    try { await post(`/partners/warehouse/receive/${id}`); toast("ok", `${id} received`); reload(true); } catch (e: any) { toast("err", e.message); } finally { setBusy(null); }
  };
  const inspect = async () => {
    setBusy("inspect");
    try {
      const r = await post(`/partners/warehouse/inspect/${insp.return_id}`, { ...form, defects: form.defects || null });
      toast("ok", `Saved. Next step: ${r.recovery_action.replace("_", " ")}, worth about ${inr(r.estimated_recovery_value)}.${r.nlp_agreed ? "" : " Your answer differed from the system's guess, so it will learn from it."}`);
      setInsp(null); reload(true);
    } catch (e: any) { toast("err", e.message); } finally { setBusy(null); }
  };
  const days = data.expected_inbound[0]?.forecast.map((x: any) => x.day) || [];
  const inbound = days.map((d: string, i: number) => {
    const row: any = { d: day(d) };
    data.expected_inbound.forEach((e: any) => (row[e.city + (e.diverted_in ? " (diverted)" : "")] = e.forecast[i].units));
    row.capacity = f.inspection_capacity;
    return row;
  });
  const keys = data.expected_inbound.map((e: any) => e.city + (e.diverted_in ? " (diverted)" : ""));
  return (
    <div className="space-y-4">
      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        <Stat label="Warehouse" value={<span className="text-[16px]">{f.name}</span>} sub={f.city} />
        <Stat label="Can inspect per day" value={num(f.inspection_capacity)} sub={f.extra_capacity_approved ? `including an approved extra shift of ${num(f.extra_capacity_approved)}` : "Full network"} />
        <Stat label="Waiting to be checked" value={num(data.queue_total)} sub="Demo sample" />
        <Stat label="Condition, last 30 days" value={<span className="text-[15px]">{["A", "B", "C"].map((g) => `${g} ${data.grade_mix_30d[g] || 0}`).join(" · ")}</span>} />
      </div>
      <div className="grid grid-cols-1 gap-4 xl:grid-cols-2">
        <Card>
          <CardHead label="Coming in" title="Expected returns vs what you can inspect" sub="Includes approved transfers to or from this warehouse" />
          <div className="h-60">
            {inbound.length === 0 ? <Empty title="No cities send returns here" /> : (
              <ResponsiveContainer>
                <ComposedChart data={inbound} margin={{ left: -6, right: 6 }}>
                  <CartesianGrid stroke={C.grid} vertical={false} /><XAxis dataKey="d" {...axis} /><YAxis {...axis} />
                  <Tooltip content={<ChartTooltip />} /><Legend wrapperStyle={{ fontSize: 11 }} />
                  {keys.map((k: string, i: number) => <Bar key={k} dataKey={k} stackId="a" fill={SERIES[i]} barSize={20} />)}
                  <Line dataKey="capacity" name="Capacity" stroke={C.red} strokeDasharray="4 3" dot={false} />
                </ComposedChart>
              </ResponsiveContainer>
            )}
          </div>
        </Card>
        <Card>
          <CardHead label="Last 45 days" title="Arrived, checked, and still waiting" />
          <div className="h-60">
            <ResponsiveContainer>
              <ComposedChart data={data.daily.map((x: any) => ({ ...x, d: day(x.day) }))} margin={{ left: -6, right: 6 }}>
                <CartesianGrid stroke={C.grid} vertical={false} /><XAxis dataKey="d" {...axis} interval={6} /><YAxis {...axis} />
                <Tooltip content={<ChartTooltip />} /><Legend wrapperStyle={{ fontSize: 11 }} />
                <Area dataKey="backlog" name="Backlog" fill="#3A2412" stroke={C.red} />
                <Line dataKey="inbound" name="Inbound" stroke={C.navy} dot={false} strokeWidth={1.4} />
                <Line dataKey="processed" name="Processed" stroke={C.blue} dot={false} strokeWidth={1.4} />
              </ComposedChart>
            </ResponsiveContainer>
          </div>
        </Card>
      </div>
      <div className="grid grid-cols-1 gap-4 xl:grid-cols-3">
        <Card pad={false} className="xl:col-span-2">
          <div className="border-b border-line px-4 py-2.5"><div className="text-[13px] font-semibold">Inspection queue · priority order</div><div className="text-[11.5px] text-ink-500">Ordered by resale-window value at risk. Receive in-transit parcels, then inspect and grade.</div></div>
          <div className="max-h-[440px] overflow-auto">
            {data.queue.length === 0 ? <div className="p-6"><Empty title="Nothing waiting" /></div> : (
              <table className="w-full min-w-[700px] text-[12px]">
                <thead className="sticky top-0 bg-white"><tr className="label border-b border-line text-left"><th className="px-4 py-2 font-normal">#</th><th className="py-2 font-normal">Item</th><th className="py-2 font-normal">Status</th><th className="py-2 text-center font-semibold">Exp. grade</th><th className="py-2 text-right font-semibold">At risk</th><th className="py-2 pr-4 text-right font-semibold">Action</th></tr></thead>
                <tbody>
                  {data.queue.map((q: any, i: number) => (
                    <tr key={q.return_id} className="border-b border-line">
                      <td className="num px-4 py-1.5 text-ink-400">{i + 1}</td>
                      <td className="py-1.5"><div className="font-medium">{q.name}</div><div className="font-mono text-[10.5px] text-ink-400">{q.return_id}</div></td>
                      <td className="py-1.5"><Badge>{q.status.replace("_", " ")}</Badge>{q.fast_track && <Badge tone="blue" className="ml-1">fast-track</Badge>}{q.integrity && <Badge tone="warn" className="ml-1">inspect tags</Badge>}</td>
                      <td className="num py-1.5 text-center">{q.expected_grade}</td>
                      <td className="num py-1.5 text-right">{inr(q.value_at_risk_7d)}</td>
                      <td className="py-1.5 pr-4 text-right">
                        {q.status === "in_transit" && <Button size="sm" onClick={() => receive(q.return_id)} loading={busy === q.return_id}>Receive</Button>}
                        {q.status === "received" && <Button size="sm" variant="dark" onClick={() => { setInsp(q); setForm({ grade: q.expected_grade, verified_reason: "SIZE_SMALL", defects: "" }); }}>Inspect</Button>}
                        {!["in_transit", "received"].includes(q.status) && <span className="text-[11px] text-ink-400">{q.status === "pickup_scheduled" ? "awaiting pickup" : "graded"}</span>}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </div>
        </Card>
        <Card><CardHead label="Alerts" title="For this warehouse" /><AlertList alerts={data.alerts} onAck={ack} /></Card>
      </div>
      <Drawer open={!!insp} onClose={() => setInsp(null)} title={insp && <>Inspect & grade · <span className="font-mono">{insp.return_id}</span></>}>
        {insp && (
          <div className="space-y-3">
            <div className="text-[13px] font-medium">{insp.name}</div>
            {insp.integrity && <div className="rounded border border-[#4A3A17] bg-warn-50 p-2.5 text-[12px] text-warn-700">Integrity check requested: verify brand tag and serial label against the dispatch record.</div>}
            <Field label="Condition (A like new, B needs repair, C damaged)">
              <div className="flex gap-2">{["A", "B", "C"].map((g) => <button key={g} onClick={() => setForm({ ...form, grade: g })} className={clsx("h-9 flex-1 rounded border text-[13px] font-semibold", form.grade === g ? "border-paper bg-paper text-white" : "border-line-strong")}>Grade {g}</button>)}</div>
            </Field>
            <Field label="Real reason for the return" hint="Your answer teaches the system to read return reasons better.">
              <select className={inputCls} value={form.verified_reason} onChange={(e) => setForm({ ...form, verified_reason: e.target.value })}>{REASONS.map((r) => <option key={r} value={r}>{r.replace(/_/g, " ").toLowerCase()}</option>)}</select>
            </Field>
            <Field label="Faults you can see"><input className={inputCls} value={form.defects} onChange={(e) => setForm({ ...form, defects: e.target.value })} placeholder="e.g. seam opening at side panel" /></Field>
            <Button variant="primary" onClick={inspect} loading={busy === "inspect"}>Record inspection</Button>
          </div>
        )}
      </Drawer>
    </div>
  );
}

export default function Partners() {
  const { meta } = useSession();
  const role = meta?.user?.role;
  const tabsFor: Record<string, ("vendor" | "logistics" | "warehouse")[]> = {
    vendor: ["vendor"], logistics: ["logistics"], warehouse: ["warehouse"], ops_manager: ["vendor", "logistics", "warehouse"],
    warehouse_manager: ["warehouse"], vendor_quality_manager: ["vendor"],
  };
  const tabs = tabsFor[role] || [];
  const [tab, setTab] = useState<"vendor" | "logistics" | "warehouse">("vendor");
  const [vendorId, setVendorId] = useState("V03");
  const [providerId, setProviderId] = useState("LP-SWR");
  const [facilityId, setFacilityId] = useState("FAC-PUN");
  useEffect(() => { if (tabs.length && !tabs.includes(tab)) setTab(tabs[0]); }, [role]); // eslint-disable-line react-hooks/exhaustive-deps
  if (!meta) return <Loading />;
  if (!tabs.length) return <ErrorState error={{ status: 403, message: "The partner app is for sellers, delivery partners, warehouse teams and marketplace managers." }} />;
  const internal = !["vendor", "logistics", "warehouse"].includes(role);
  return (
    <div className="space-y-6">
      <PageHeader eyebrow="Partner app" title={internal ? "Partners" : meta.user.title}
        sub={internal ? "What each seller, delivery partner and warehouse sees. Managers can look at any of them; partners only ever see their own data." : "Your returns, and what the marketplace needs from you. You only see your own data, and customers' names are hidden."}
        right={internal && (
          <div className="flex items-center gap-2 text-[12px]">
            <span className="text-ink-500">Looking at:</span>
            {tab === "vendor" && <select className={selectCls} value={vendorId} onChange={(e) => setVendorId(e.target.value)}>{["V01", "V02", "V03", "V04", "V05", "V06", "V07", "V08", "V09", "V10", "V11", "V12"].map((v) => <option key={v}>{v}</option>)}</select>}
            {tab === "logistics" && <select className={selectCls} value={providerId} onChange={(e) => setProviderId(e.target.value)}>{["LP-SWR", "LP-KSE", "LP-DKR", "LP-STH"].map((v) => <option key={v}>{v}</option>)}</select>}
            {tab === "warehouse" && <select className={selectCls} value={facilityId} onChange={(e) => setFacilityId(e.target.value)}>{["FAC-PUN", "FAC-NSK", "FAC-BHW", "FAC-AMD", "FAC-JAI", "FAC-GGN", "FAC-BLR", "FAC-HYD", "FAC-CCU"].map((v) => <option key={v}>{v}</option>)}</select>}
          </div>
        )} />
      {tabs.length > 1 && <Tabs value={tab} onChange={setTab} items={tabs.map((t) => ({ id: t, label: { vendor: "Seller", logistics: "Delivery partner", warehouse: "Warehouse" }[t] }))} />}
      {tab === "vendor" && <VendorView vendorId={internal ? vendorId : undefined} />}
      {tab === "logistics" && <LogisticsView providerId={internal ? providerId : undefined} />}
      {tab === "warehouse" && <WarehouseView facilityId={internal ? facilityId : undefined} />}
    </div>
  );
}
