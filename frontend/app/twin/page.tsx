"use client";
import clsx from "clsx";
import { Download, RotateCcw } from "lucide-react";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Bar, BarChart, CartesianGrid, Legend, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { axis, C, ChartTooltip } from "@/components/charts";
import { useSession, useToast } from "@/components/providers";
import { Badge, Button, Card, CardHead, DetailOnly, ErrorState, Loading, More, PageHeader, Segmented, SyntheticTag } from "@/components/ui";
import { api, post } from "@/lib/api";
import { inr, num, pct } from "@/lib/format";

const SC = ["baseline", "A", "B", "C"] as const;
const SC_LABEL: Record<string, string> = { baseline: "Do nothing", A: "More pickup vans", B: "Use other warehouses", C: "Both, best items first" };
const SC_DESC: Record<string, string> = {
  baseline: "Keep today's vans and warehouses.",
  A: "Hire extra pickup vans in the busy cities.",
  B: "Send part of Pune's returns to Nashik, which has spare room.",
  C: "Extra vans, Nashik, an extra inspection shift, and check the most valuable items first.",
};
const SC_COLOR: Record<string, string> = { baseline: C.slate, A: C.amber, B: C.navy, C: C.blue };

const KPIS: { k: string; label: string; f: (v: number) => string; better: "low" | "high"; key?: boolean }[] = [
  { k: "pickup_sla_pct", label: "Picked up within 2 days", f: (v) => pct(v, 0), better: "high", key: true },
  { k: "avg_pickup_wait_days", label: "Average wait for pickup", f: (v) => `${num(v, 1)} days`, better: "low", key: true },
  { k: "avg_return_to_restock_days", label: "Days until back on sale", f: (v) => `${num(v, 1)} days`, better: "low", key: true },
  { k: "value_at_risk", label: "Value lost to waiting", f: (v) => inr(v, true), better: "low", key: true },
  { k: "cost_per_return", label: "Cost per return", f: (v) => inr(v), better: "low", key: true },
  { k: "total_returns", label: "Returns in the 14 days", f: (v) => num(v), better: "low" },
  { k: "peak_pickup_backlog", label: "Most returns waiting for pickup", f: (v) => num(v), better: "low" },
  { k: "peak_warehouse_congestion_pct", label: "Busiest warehouse, how full", f: (v) => pct(v, 0), better: "low" },
  { k: "avg_inspection_wait_days", label: "Average wait for inspection", f: (v) => `${num(v, 1)} days`, better: "low" },
  { k: "units_unprocessed_at_horizon", label: "Still not processed on day 14", f: (v) => num(v), better: "low" },
];

function Slider({ label, value, min, max, step = 1, onChange, fmt = (v: number) => String(v), hint }:
  { label: string; value: number; min: number; max: number; step?: number; onChange: (v: number) => void; fmt?: (v: number) => string; hint?: string }) {
  return (
    <div className="py-2">
      <div className="flex items-baseline justify-between text-[13px]">
        <span className="text-ink-700" title={hint}>{label}</span>
        <span className="num font-medium text-ink-900">{fmt(value)}</span>
      </div>
      <input type="range" min={min} max={max} step={step} value={value} onChange={(e) => onChange(Number(e.target.value))} className="mt-1 w-full" />
    </div>
  );
}

export default function Twin() {
  const toast = useToast();
  const [params, setParams] = useState<any>(null);
  const [storagePct, setStoragePct] = useState(100);
  const [note, setNote] = useState("");
  const [res, setRes] = useState<any>(null);
  const [err, setErr] = useState<any>(null);
  const [busy, setBusy] = useState(false);
  const [view, setView] = useState<"backlog" | "queue" | "util">("backlog");
  const [utilSc, setUtilSc] = useState<string>("baseline");
  const timer = useRef<any>(null);
  const [moreInputs, setMoreInputs] = useState(false);
  const { detail } = useSession();

  const load = useCallback(async (source: "deck" | "forecast") => {
    try {
      const d = await api(`/twin/defaults?source=${source}`);
      setParams(d.params);
      setNote(d.note);
      setStoragePct(100);
    } catch (e) { setErr(e); }
  }, []);
  useEffect(() => { load("deck"); }, [load]);

  const effective = useMemo(() => {
    if (!params) return null;
    return { ...params, facilities: params.facilities.map((f: any) => ({ ...f, storage: Math.round(f.storage * storagePct / 100) })) };
  }, [params, storagePct]);

  useEffect(() => {
    if (!effective) return;
    clearTimeout(timer.current);
    timer.current = setTimeout(async () => {
      setBusy(true);
      try {
        setRes(await post("/twin/simulate", { params: effective }));
        setErr(null);
      } catch (e: any) { setErr(e); } finally { setBusy(false); }
    }, 350);
    return () => clearTimeout(timer.current);
  }, [effective]);

  const set = (path: (p: any) => void) => setParams((p: any) => { const q = structuredClone(p); path(q); return q; });

  if (err && !params) return <ErrorState error={err} onRetry={() => load("deck")} />;
  if (!params) return <Loading />;

  const series = res ? res.scenarios.baseline.series.map((_: any, i: number) => {
    const row: any = { day: `D${i + 1}` };
    SC.forEach((s) => {
      const r = res.scenarios[s].series[i];
      row[s] = view === "backlog" ? r.pickup_backlog : r.inspection_queue;
    });
    return row;
  }) : [];
  const facIds = params.facilities.map((f: any) => f.id);
  const utilSeries = res ? res.scenarios[utilSc].series.map((r: any, i: number) => {
    const row: any = { day: `D${i + 1}` };
    facIds.forEach((f: string) => (row[f] = +(r[`util_${f}`] * 100).toFixed(1)));
    return row;
  }) : [];
  const econ = res ? SC.map((s) => ({ s: SC_LABEL[s], cost: res.scenarios[s].kpis.total_cost.mean, risk: res.scenarios[s].kpis.value_at_risk.mean })) : [];
  const best = (k: string, better: "low" | "high") => {
    if (!res) return null;
    const vals = SC.map((s) => res.scenarios[s].kpis[k].mean);
    const t = better === "low" ? Math.min(...vals) : Math.max(...vals);
    return SC.find((s) => res.scenarios[s].kpis[k].mean === t);
  };
  const bestPlan = res ? SC.reduce((b, s) => (res.scenarios[s].kpis.value_at_risk.mean < res.scenarios[b].kpis.value_at_risk.mean ? s : b), "baseline" as (typeof SC)[number]) : null;
  const exportJson = () => {
    const blob = new Blob([JSON.stringify(res, null, 2)], { type: "application/json" });
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = "reverseflow_twin_results.json";
    a.click();
  };

  return (
    <div className="space-y-5">
      <PageHeader eyebrow="Planner · next 14 days" title="Try a plan before you pay for it"
        sub="This is a practice run of the next two weeks in Pune, Ahmedabad and Jaipur. Move the sliders and the four plans below update straight away, so you can see which one keeps returns moving for the least money."
        right={<div className="flex items-center gap-2"><SyntheticTag text="Example figures" />{res && <DetailOnly><Button size="sm" onClick={exportJson}><Download className="h-3 w-3" />Export</Button></DetailOnly>}</div>} />

      <div className="grid grid-cols-1 gap-4 xl:grid-cols-[320px_1fr]">
        <Card className="h-fit xl:sticky xl:top-[68px]">
          <div className="mb-3 flex items-center justify-between">
            <div className="text-[15px] font-semibold">Change the situation</div>
            {busy ? <Badge>updating…</Badge> : <Badge tone="ok" dot>up to date</Badge>}
          </div>
          <div className="mb-4 flex flex-wrap gap-1.5">
            <Button size="sm" onClick={() => load("deck")}><RotateCcw className="h-3 w-3" />Start over</Button>
            <Button size="sm" variant="primary" onClick={() => { load("forecast"); toast("info", "Loaded the busiest days from the latest forecast"); }}>Use the latest forecast</Button>
          </div>
          <Slider label="How big the wave is" value={params.surge_intensity} min={0.2} max={2.5} step={0.1} fmt={(v) => (v === 1 ? "as forecast" : `${v.toFixed(1)}× forecast`)} onChange={(v) => set((p) => (p.surge_intensity = v))} />
          <div className="label mt-4">Pickup vans per city</div>
          {params.clusters.map((c: any, i: number) => (
            <Slider key={c.id} label={c.name} value={c.vehicles} min={5} max={140} onChange={(v) => set((p) => (p.clusters[i].vehicles = v))} fmt={(v) => `${v} vans`} />
          ))}
          <div className="label mt-4">Warehouses</div>
          <Slider label="Inspection staff" value={params.inspection_capacity_pct} min={50} max={200} step={5} fmt={(v) => (v === 100 ? "today's level" : `${v}% of today`)} onChange={(v) => set((p) => (p.inspection_capacity_pct = v))} />
          <Slider label="Share of Pune's returns sent to Nashik" value={params.interventions.B_allocation.PNQ["FAC-NSK"]} min={0} max={0.6} step={0.05} fmt={(v) => pct(v)} onChange={(v) => set((p) => (p.interventions.B_allocation.PNQ["FAC-NSK"] = v))} />

          <button onClick={() => setMoreInputs((m) => !m)} className="label mt-4 w-full border-t border-dashed border-line-strong pt-3 text-left hover:text-ink-900">{moreInputs || detail ? "−" : "+"} More settings</button>
          {(moreInputs || detail) && (
            <div>
              {params.clusters.map((c: any, i: number) => (
                <Slider key={c.id} label={`${c.name}: extra returns a day at the peak`} value={c.additional} min={0} max={3000} step={50} fmt={(v) => `+${num(v)}`} onChange={(v) => set((p) => (p.clusters[i].additional = v))} />
              ))}
              <Slider label="Minutes to inspect one item" value={params.processing_minutes} min={6} max={25} step={0.5} fmt={(v) => `${v} min`} onChange={(v) => set((p) => (p.processing_minutes = v))} />
              <Slider label="Warehouse storage space" value={storagePct} min={20} max={150} step={5} fmt={(v) => `${v}%`} onChange={setStoragePct} />
              <Slider label="Items with a quality fault" value={params.vendor_defect_rate} min={0} max={0.5} step={0.01} fmt={(v) => pct(v)} onChange={(v) => set((p) => (p.vendor_defect_rate = v))} />
              <Slider label="Items that can be resold" value={params.recovery_rate} min={0.4} max={1} step={0.01} fmt={(v) => pct(v)} onChange={(v) => set((p) => (p.recovery_rate = v))} />
              <div className="label mt-3">Where returns go today</div>
              <Slider label="Pune → Nashik" value={params.allocation.PNQ?.["FAC-NSK"] || 0} min={0} max={0.6} step={0.05} fmt={(v) => pct(v)} onChange={(v) => set((p) => (p.allocation.PNQ = { "FAC-NSK": v }))} />
              <Slider label="Ahmedabad → Bhiwandi" value={params.allocation.AMD?.["FAC-BHW"] || 0} min={0} max={0.6} step={0.05} fmt={(v) => pct(v)} onChange={(v) => set((p) => (p.allocation.AMD = { "FAC-BHW": v }))} />
              <Slider label="Jaipur → Gurugram" value={params.allocation.JAI?.["FAC-GGN"] || 0} min={0} max={0.6} step={0.05} fmt={(v) => pct(v)} onChange={(v) => set((p) => (p.allocation.JAI = { "FAC-GGN": v }))} />
              <div className="label mt-3">Size of each plan</div>
              <Slider label="Extra vans in plan A" value={params.interventions.A_extra_vehicles_pct} min={0} max={120} step={5} fmt={(v) => `+${v}%`} onChange={(v) => set((p) => (p.interventions.A_extra_vehicles_pct = v))} />
              <Slider label="Extra inspection shift in plan C" value={params.interventions.C_extra_inspection_pct} min={0} max={60} step={5} fmt={(v) => `+${v}%`} onChange={(v) => set((p) => (p.interventions.C_extra_inspection_pct = v))} />
              {note && <div className="mt-2 text-[11.5px] text-ink-500">{note}</div>}
            </div>
          )}
        </Card>

        <div className="space-y-4">
          {err && <ErrorState error={err} />}
          {!res ? <Loading rows={2} /> : (
            <>
              {bestPlan && (
                <div className="rounded border border-line-strong bg-black p-5">
                  <div className="label">Our suggestion</div>
                  <div className="mt-2 text-[22px] font-semibold leading-snug tracking-tight">
                    {bestPlan === "baseline" ? "No change needed. Today's set-up copes." : <>Go with <span className="underline decoration-ink-500 underline-offset-4">{SC_LABEL[bestPlan]}</span>. It cuts the value lost to waiting from {inr(res.scenarios.baseline.kpis.value_at_risk.mean, true)} to {inr(res.scenarios[bestPlan].kpis.value_at_risk.mean, true)}.</>}
                  </div>
                  <div className="mt-2 text-[13px] text-ink-500">Approving the matching actions is done on the <a href="/governance" className="text-blue-600">Decisions</a> page.</div>
                </div>
              )}
              <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
                {SC.map((s) => {
                  const k = res.scenarios[s].kpis;
                  const dv = res.scenarios[s].vs_baseline;
                  return (
                    <Card key={s} className={clsx(s === bestPlan && "border-paper")}>
                      <div className="flex items-center justify-between">
                        <span className="label">{s === "baseline" ? "Today" : `Plan ${s}`}</span>
                        {s === bestPlan ? <Badge tone="navy">best</Badge> : <span className="h-2 w-2 rounded-full" style={{ background: SC_COLOR[s] }} />}
                      </div>
                      <div className="mt-2 text-[15px] font-semibold leading-tight">{SC_LABEL[s]}</div>
                      <div className="mt-1 min-h-[34px] text-[11.5px] leading-snug text-ink-500">{SC_DESC[s]}</div>
                      <div className="mt-3 label">Value lost to waiting</div>
                      <div className={clsx("display-num mt-1.5 text-[30px]", s === bestPlan && "text-ok-700")}>{inr(k.value_at_risk.mean, true)}</div>
                      <DetailOnly><div className="num mt-1 text-[10.5px] text-ink-500">P10–P90 {inr(k.value_at_risk.p10, true)} – {inr(k.value_at_risk.p90, true)}</div></DetailOnly>
                      {s !== "baseline" && (
                        <div className="mt-3 border-t border-line pt-2.5 text-[12px] text-ink-500">
                          {dv.value_at_risk < 0 ? <>Saves <span className="num font-semibold text-ok-700">{inr(Math.abs(dv.value_at_risk), true)}</span></> : <>Loses <span className="num font-semibold text-bad-700">{inr(Math.abs(dv.value_at_risk), true)}</span> more</>}
                          <span> · {dv.cost_per_return >= 0 ? "+" : "−"}<span className="num text-ink-900">{inr(Math.abs(dv.cost_per_return))}</span> per return</span>
                        </div>
                      )}
                    </Card>
                  );
                })}
              </div>

              <Card>
                <CardHead label="Side by side" title="How each plan plays out over 14 days" sub="The best result in each row is green." />
                <div className="overflow-x-auto">
                  <table className="w-full min-w-[640px] text-[12.5px]">
                    <thead><tr className="label text-left"><th className="pb-2 font-normal" />{SC.map((s) => <th key={s} className="pb-2 text-right font-normal">{SC_LABEL[s]}</th>)}</tr></thead>
                    <tbody>
                      {KPIS.filter((row) => row.key || detail).map((row) => {
                        const b = best(row.k, row.better);
                        return (
                          <tr key={row.k} className="border-t border-line">
                            <td className="py-2 text-ink-700">{row.label}</td>
                            {SC.map((s) => {
                              const v = res.scenarios[s].kpis[row.k];
                              return <td key={s} title={`P10 ${row.f(v.p10)} · P90 ${row.f(v.p90)}`} className={clsx("num py-2 text-right", b === s && row.k !== "total_returns" ? "font-semibold text-ok-700" : "text-ink-900")}>{row.f(v.mean)}</td>;
                            })}
                          </tr>
                        );
                      })}
                      {detail && <tr className="border-t border-line-strong">
                        <td className="py-2 font-medium">Effective setup</td>
                        {SC.map((s) => {
                          const e = res.scenarios[s].effective;
                          return <td key={s} className="py-2 text-right text-[11px] text-ink-500">{Object.values(e.vehicles).join("/")} veh · insp {Math.round(e.inspection_capacity_pct)}%{s === "C" && res.scenarios[s].value_priority ? " · value-priority" : ""}</td>;
                        })}
                      </tr>}
                    </tbody>
                  </table>
                </div>
              </Card>

              <div className="grid grid-cols-1 gap-4 2xl:grid-cols-2">
                <Card className="2xl:col-span-2">
                  <CardHead label="Day by day" title={view === "backlog" ? "Returns waiting to be picked up" : view === "queue" ? "Returns waiting to be inspected" : "How full each warehouse is"}
                    right={<Segmented value={view} onChange={setView} items={[{ id: "backlog", label: "Pickup" }, { id: "queue", label: "Inspection" }, { id: "util", label: "Warehouses" }]} />} />
                  {view === "util" && <div className="mb-2"><Segmented value={utilSc} onChange={setUtilSc} items={SC.map((s) => ({ id: s, label: s === "baseline" ? "Base" : s }))} /></div>}
                  <div className="h-[260px]">
                    <ResponsiveContainer>
                      {view === "util" ? (
                        <LineChart data={utilSeries} margin={{ left: -10, right: 8 }}>
                          <CartesianGrid stroke={C.grid} vertical={false} />
                          <XAxis dataKey="day" {...axis} /><YAxis {...axis} unit="%" />
                          <Tooltip content={<ChartTooltip fmt={(v: number) => `${v}%`} />} />
                          <Legend wrapperStyle={{ fontSize: 11 }} />
                          {facIds.map((f: string, i: number) => <Line key={f} dataKey={f} name={f.replace("FAC-", "")} stroke={["#F2F2F2", "#8C8C8C", "#E3A33B", "#3FBF7F", "#555555", "#F0583E"][i]} dot={false} strokeWidth={1.6} isAnimationActive={false} />)}
                        </LineChart>
                      ) : (
                        <LineChart data={series} margin={{ left: -4, right: 8 }}>
                          <CartesianGrid stroke={C.grid} vertical={false} />
                          <XAxis dataKey="day" {...axis} /><YAxis {...axis} />
                          <Tooltip content={<ChartTooltip />} />
                          <Legend wrapperStyle={{ fontSize: 11 }} />
                          {SC.map((s) => <Line key={s} dataKey={s} name={SC_LABEL[s]} stroke={SC_COLOR[s]} strokeWidth={s === "C" ? 2.2 : 1.5} dot={false} isAnimationActive={false} />)}
                        </LineChart>
                      )}
                    </ResponsiveContainer>
                  </div>
                </Card>
              </div>
              <More title="Costs and how the practice run works">
              <div className="grid grid-cols-1 gap-4">
                <Card>
                  <CardHead label="Money" title="What each plan costs vs what it saves" sub="A plan is worth it when the value it protects is bigger than what it costs." />
                  <div className="h-[260px]">
                    <ResponsiveContainer>
                      <BarChart data={econ} margin={{ left: 10, right: 8 }}>
                        <CartesianGrid stroke={C.grid} vertical={false} />
                        <XAxis dataKey="s" {...axis} /><YAxis {...axis} tickFormatter={(v) => inr(v, true)} />
                        <Tooltip content={<ChartTooltip fmt={(v: number) => inr(v, true)} />} />
                        <Legend wrapperStyle={{ fontSize: 11 }} />
                        <Bar dataKey="cost" name="Total cost" fill={C.navy} barSize={18} radius={[3, 3, 0, 0]} />
                        <Bar dataKey="risk" name="Value lost to waiting" fill={C.red} barSize={18} radius={[3, 3, 0, 0]} />
                      </BarChart>
                    </ResponsiveContainer>
                  </div>
                </Card>
              </div>
              <div className="text-[11.5px] leading-relaxed text-ink-500">
                Each plan is run {params.replications} times with random day-to-day variation and the results averaged. Model: arrivals = base + additional × surge intensity × triangular wave (peak day {params.peak_day + 1}); pickup capacity = vehicles × {params.pickups_per_vehicle}/day; inspection capacity = inspectors × {params.shift_minutes} min ÷ processing minutes × capacity %;
                diverted units add one transit day and ₹{params.transfer_fixed} + ₹{params.transfer_cost_per_km}/km. Value decays {params.value_decay_pct_per_day.priority}%/day for likely Grade-A festive stock and {params.value_decay_pct_per_day.other}%/day otherwise once restock exceeds {params.target_days_to_restock} days.
              </div>
              </More>
            </>
          )}
        </div>
      </div>
    </div>
  );
}
