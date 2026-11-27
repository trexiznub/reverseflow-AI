"use client";
import clsx from "clsx";
import { AlertTriangle } from "lucide-react";
import { useMemo, useState } from "react";
import { Area, Bar, BarChart, CartesianGrid, ComposedChart, Line, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { axis, C, ChartTooltip } from "@/components/charts";
import { IndiaMap } from "@/components/IndiaMap";
import { Badge, Card, CardHead, DetailOnly, ErrorState, Loading, More, PageHeader, Segmented, statusText, statusTone, SyntheticTag } from "@/components/ui";
import { useApi } from "@/lib/api";
import { day, mult, num, pct } from "@/lib/format";

function heat(m: number) {
  // dark grey for normal, amber to red as the day gets busier
  if (m < 1.15) return { bg: "#141414", fg: "#8C8C8C" };
  if (m < 1.5) return { bg: "#2A2110", fg: "#F2C26E" };
  if (m < 2) return { bg: "#3A2412", fg: "#F6A266" };
  if (m < 2.5) return { bg: "#5A2418", fg: "#FFB09E" };
  return { bg: "#F0583E", fg: "#000" };
}

export default function Forecasting() {
  const { data, error, loading, reload } = useApi<any>("/forecast");
  const [sel, setSel] = useState("PNQ");
  const [scale, setScale] = useState<"network" | "sample">("network");
  const [evalIdx, setEvalIdx] = useState(0);

  const cluster = data?.clusters.find((c: any) => c.cluster_id === sel);
  const series = useMemo(() => {
    if (!cluster) return [];
    const s = scale === "network" ? cluster.network_scale : 1;
    const hist = cluster.history.map((h: any, i: number, arr: any[]) => {
      const win = arr.slice(Math.max(0, i - 6), i + 1);
      return { day: day(h.day), actual: +(h.actual * s).toFixed(1), avg7: +((win.reduce((a: number, x: any) => a + x.actual, 0) / win.length) * s).toFixed(1) };
    });
    const last = hist[hist.length - 1];
    const fc = cluster.forecast.map((f: any) => ({ day: day(f.day), forecast: +(f.forecast * s).toFixed(1), band: [+(f.lo * s).toFixed(1), +(f.hi * s).toFixed(1)] }));
    if (last) fc.unshift({ day: last.day, forecast: last.actual, band: [last.actual, last.actual] } as any);
    const merged: any[] = hist.slice(0, -1);
    merged.push({ ...last, ...fc[0] });
    return merged.concat(fc.slice(1));
  }, [cluster, scale]);

  if (error) return <ErrorState error={error} onRetry={reload} />;
  if (loading || !data) return <Loading />;
  const ev = data.evaluations[evalIdx];
  const evSeries = ev.series.filter((p: any) => p.cluster_id === (["PNQ", "AMD", "JAI", "BOM"].includes(sel) ? sel : "PNQ"))
    .map((p: any) => ({ ...p, d: day(p.day), band: [p.lo, p.hi] }));
  const rows = [
    ["Average miss (returns/day)", "mae", 2], ["Miss, big errors weighted (RMSE)", "rmse", 2], ["Miss as % of volume (WAPE)", "wape", "pct"], ["Leans high or low (bias)", "bias", "pct"],
  ] as const;
  const fmt = (v: number, f: any) => (f === "pct" ? pct(v, 1) : num(v, f));
  const days = data.clusters[0].forecast.map((f: any) => f.day);

  return (
    <div className="space-y-5">
      <PageHeader eyebrow="Forecast · next 7 days" title="How many returns are coming"
        sub={<>A prediction of returns for each city, day by day, based on past festive seasons and this year's orders. Pick a city to see its curve. Tested on last year's festive season (synthetic history): its daily error was {pct(data.evaluations[0].daily_cluster.ml.wape, 1)} (WAPE) against {pct(data.evaluations[0].daily_cluster.baseline.wape, 1)} for a simple baseline, and {pct(data.evaluations[0].weekly_cluster.ml.wape, 1)} against {pct(data.evaluations[0].weekly_cluster.baseline.wape, 1)} on weekly totals. Lower is better.</>}
        right={<SyntheticTag text="Synthetic history" />} />

      {data.surge_alerts.length > 0 && (
        <Card className="border-[#4A2620] bg-bad-50/40">
          <div className="flex items-start gap-3">
            <AlertTriangle className="mt-0.5 h-4 w-4 text-bad-600" />
            <div className="flex-1">
              <div className="text-[14px] font-semibold">{data.surge_alerts.length} cities will get at least 1.5× their normal returns</div>
              <div className="mt-0.5 text-[12.5px] text-ink-500">Click a city to see its forecast.</div>
              <div className="mt-2 flex flex-wrap gap-2">
                {data.surge_alerts.map((a: any) => (
                  <button key={a.cluster_id} onClick={() => setSel(a.cluster_id)}
                    className={clsx("rounded border bg-black px-3 py-2 text-left text-[12px] hover:border-bad-600", sel === a.cluster_id ? "border-bad-600" : "border-line-strong")}>
                    <div className="font-semibold">{a.city} <span className="num text-bad-700">{mult(a.avg_multiplier)}</span></div>
                    <div className="text-ink-500">busiest on {day(a.peak_day)} · {num(a.additional_network_at_peak)} extra a day</div>
                  </button>
                ))}
              </div>
            </div>
          </div>
        </Card>
      )}

      <div className="grid grid-cols-1 gap-4 xl:grid-cols-3">
        <Card className="xl:col-span-2">
          <CardHead label="Returns per day" title={`${cluster?.city}: the last few weeks and the next ${data.horizon_days} days`}
            sub="Solid line: what actually came back. Dashed line: the forecast. Shaded band: the likely range."
            right={<DetailOnly><Segmented value={scale} onChange={setScale} items={[{ id: "network", label: "Network" }, { id: "sample", label: "Sample" }]} /></DetailOnly>} />
          <div className="mb-3 flex flex-wrap gap-1.5">
            {data.clusters.map((c: any) => (
              <button key={c.cluster_id} onClick={() => setSel(c.cluster_id)}
                className={clsx("rounded-full border px-3 py-1 text-[12px]", sel === c.cluster_id ? "border-paper bg-paper text-black" : "border-line-strong text-ink-700 hover:border-ink-500")}>
                {c.city} <span className="num opacity-70">{mult(c.avg_multiplier)}</span>
              </button>
            ))}
          </div>
          <div className="h-[300px]">
            <ResponsiveContainer>
              <ComposedChart data={series} margin={{ left: -10, right: 8, top: 6 }}>
                <CartesianGrid stroke={C.grid} vertical={false} />
                <XAxis dataKey="day" {...axis} interval={5} />
                <YAxis {...axis} />
                <Tooltip content={<ChartTooltip />} />
                <Area dataKey="band" name="Likely range" fill={C.band} stroke="none" fillOpacity={0.9} isAnimationActive={false} />
                <Line dataKey="actual" name="Actual" stroke={C.slate} strokeWidth={1} dot={false} isAnimationActive={false} />
                <Line dataKey="avg7" name="Weekly average" stroke={C.navy} strokeWidth={2} dot={false} isAnimationActive={false} />
                <Line dataKey="forecast" name="Forecast" stroke={C.blue} strokeWidth={2} strokeDasharray="5 3" dot={{ r: 2.5 }} isAnimationActive={false} />
                <ReferenceLine y={(scale === "network" ? cluster.network_scale : 1) * cluster.normal_sample_daily} stroke={C.slate} strokeDasharray="2 3"
                  label={{ value: "normal level", position: "insideTopLeft", fontSize: 10, fill: C.slate }} />
              </ComposedChart>
            </ResponsiveContainer>
          </div>
          <div className="mt-4 grid grid-cols-2 gap-4 border-t border-line pt-4 md:grid-cols-4">
            <div><div className="label">vs a normal week</div><div className="display-num mt-2 text-[26px]">{mult(cluster.avg_multiplier)}</div></div>
            <div><div className="label">Busiest day</div><div className="display-num mt-2 text-[26px]">{day(cluster.peak_day)}</div></div>
            <div><div className="label">Returns on busiest day</div><div className="display-num mt-2 text-[26px]">{num(cluster.peak_network)}</div></div>
            <div><div className="label">Total next 7 days</div><div className="display-num mt-2 text-[26px]">{num(cluster.expected_network_7d)}</div></div>
          </div>
        </Card>
        <Card>
          <CardHead label="Map" title="All cities" sub="Click a city to see its forecast" />
          <IndiaMap height={340} clusters={data.clusters.map((c: any) => ({ id: c.cluster_id, city: c.city, lat: c.lat, lon: c.lon, risk: c.risk, avg_multiplier: c.avg_multiplier, expected_network_7d: c.expected_network_7d }))}
            onSelect={setSel} selected={sel} />
        </Card>
      </div>

      <Card>
        <CardHead label="Day by day" title="How busy each day will be, compared with normal" sub="1.0× is a normal day. The redder the box, the busier the day." />
        <div className="overflow-x-auto">
          <table className="w-full min-w-[720px] border-separate border-spacing-[3px] text-[12px]">
            <thead><tr><th className="label w-36 text-left font-normal">City</th>{days.map((d: string) => <th key={d} className="label text-center">{day(d)}</th>)}<th className="label text-right font-normal">Overall</th></tr></thead>
            <tbody>
              {data.clusters.map((c: any) => (
                <tr key={c.cluster_id} className="cursor-pointer" onClick={() => setSel(c.cluster_id)}>
                  <td className={clsx("pr-2 font-medium", sel === c.cluster_id ? "text-ink-900 underline underline-offset-4" : "text-ink-700")}>{c.city} <DetailOnly><span className="font-mono text-[10.5px] text-ink-400">{c.pin_prefix}xxx</span></DetailOnly></td>
                  {c.forecast.map((f: any) => {
                    const h = heat(f.multiplier);
                    return <td key={f.day} className="num rounded-[3px] py-2 text-center font-medium" style={{ background: h.bg, color: h.fg }} title={`${num(f.network_forecast)} returns`}>{f.multiplier.toFixed(2)}</td>;
                  })}
                  <td className="text-right"><Badge tone={statusTone(c.risk)} dot>{statusText(c.risk)}</Badge></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Card>

      <More title="How accurate is it?" sub="Tested on last year's festive season, plus breakdowns by seller and size">
      <div className="grid grid-cols-1 gap-4 xl:grid-cols-3">
        <Card className="xl:col-span-2">
          <CardHead label="Tested on past data the model hadn't seen" title={ev.label}
            sub={`Trained on data before ${day(ev.train_end)}; tested ${day(ev.test_start)} to ${day(ev.test_end)} · showing ${["PNQ", "AMD", "JAI", "BOM"].includes(sel) ? cluster.city : "Pune"}`}
            right={<Segmented value={String(evalIdx) as any} onChange={(v: any) => setEvalIdx(Number(v))} items={data.evaluations.map((e: any, i: number) => ({ id: String(i), label: i === 0 ? "Festive 2025" : "Recent 2026" }))} />} />
          <div className="h-[260px]">
            <ResponsiveContainer>
              <ComposedChart data={evSeries} margin={{ left: -14, right: 8, top: 6 }}>
                <CartesianGrid stroke={C.grid} vertical={false} />
                <XAxis dataKey="d" {...axis} interval={9} />
                <YAxis {...axis} />
                <Tooltip content={<ChartTooltip />} />
                <Area dataKey="band" name="Likely range" fill={C.band} stroke="none" isAnimationActive={false} />
                <Line dataKey="actual" name="Actual" stroke={C.navy} strokeWidth={1.4} dot={false} isAnimationActive={false} />
                <Line dataKey="baseline" name="Simple baseline (same weekday, last 4 weeks)" stroke={C.amber} strokeWidth={1.3} dot={false} isAnimationActive={false} />
                <Line dataKey="ml" name="Our forecast" stroke={C.blue} strokeWidth={1.8} dot={false} isAnimationActive={false} />
              </ComposedChart>
            </ResponsiveContainer>
          </div>
        </Card>
        <Card>
          <CardHead label="Accuracy" title="Our forecast vs a simple baseline" sub="Baseline: average of the same weekday over the last 4 weeks. Lower is better, except the last row." />
          <table className="w-full text-[12.5px]">
            <thead><tr className="label"><th className="pb-1.5 text-left font-normal">Measure</th><th className="pb-1.5 text-right font-normal">Baseline</th><th className="pb-1.5 text-right font-normal">Ours</th></tr></thead>
            <tbody>
              {rows.map(([l, k, f]) => (
                <tr key={k} className="border-t border-line">
                  <td className="py-1.5 text-ink-700">{l}</td>
                  <td className="num py-1.5 text-right">{fmt(ev.daily_cluster.baseline[k], f)}</td>
                  <td className={clsx("num py-1.5 text-right font-semibold", Math.abs(ev.daily_cluster.ml[k]) < Math.abs(ev.daily_cluster.baseline[k]) && "text-ok-700")}>{fmt(ev.daily_cluster.ml[k], f)}</td>
                </tr>
              ))}
              {ev.surge_window && (
                <tr className="border-t border-line"><td className="py-1.5 text-ink-700">Miss %, during the surge</td>
                  <td className="num py-1.5 text-right">{pct(ev.surge_window.baseline.wape, 1)}</td>
                  <td className="num py-1.5 text-right font-semibold text-ok-700">{pct(ev.surge_window.ml.wape, 1)}</td></tr>
              )}
              <tr className="border-t border-line"><td className="py-1.5 text-ink-700">Miss %, weekly totals</td>
                <td className="num py-1.5 text-right">{pct(ev.weekly_cluster.baseline.wape, 1)}</td>
                <td className="num py-1.5 text-right font-semibold">{pct(ev.weekly_cluster.ml.wape, 1)}</td></tr>
              <tr className="border-t border-line"><td className="py-1.5 text-ink-700">Actual fell inside the range</td><td className="py-1.5 text-right text-ink-400">—</td>
                <td className="num py-1.5 text-right font-semibold">{pct(ev.interval_coverage_p10_p90, 1)}</td></tr>
            </tbody>
          </table>
          <div className="mt-3 text-[11px] leading-relaxed text-ink-500">
            Day-level numbers in the demo data are small (2–8 returns per city per day), so daily misses include random noise no model can remove. Weekly totals show planning accuracy better. Tested on <span className="num">{num(ev.rows_test)}</span> city-days; model trained on {num(data.model.training_rows)} city-days.
          </div>
          {ev.surge_lead_time?.length > 0 && (
            <div className="mt-3 border-t border-line pt-3">
              <div className="label mb-1.5">How early the surge was spotted</div>
              {ev.surge_lead_time.map((l: any) => (
                <div key={l.cluster_id} className="flex justify-between text-[12px]"><span>{l.cluster_id} · peak {day(l.peak)}</span><span className="num">alert {day(l.alert_issued)} · <b>{l.lead_days} days</b></span></div>
              ))}
            </div>
          )}
        </Card>
      </div>

      {data.breakdown && (
        <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
          <Card>
            <CardHead label="Breakdown" title="Expected returns by seller" sub="Next 7 days" />
            <div className="h-[260px]">
              <ResponsiveContainer>
                <BarChart data={data.breakdown.vendors.slice(0, 8)} layout="vertical" margin={{ left: 40, right: 10 }}>
                  <XAxis type="number" {...axis} />
                  <YAxis type="category" dataKey="name" {...axis} width={110} tick={{ fontSize: 10.5, fill: "#BDBDBD" }} />
                  <Tooltip content={<ChartTooltip />} />
                  <Bar dataKey="expected_network_7d" name="7-day returns" fill={C.navy} radius={[0, 3, 3, 0]} barSize={12} />
                </BarChart>
              </ResponsiveContainer>
            </div>
          </Card>
          <Card>
            <CardHead label="Breakdown" title="Products expected back most" sub="Next 7 days" />
            <div className="space-y-1.5">
              {data.breakdown.skus.slice(0, 9).map((s: any) => (
                <div key={s.sku} className="flex items-center justify-between gap-2 text-[12px]">
                  <div className="min-w-0"><div className="truncate font-medium">{s.name}</div><div className="font-mono text-[10.5px] text-ink-400">{s.sku}</div></div>
                  <span className="num shrink-0">{num(s.expected_network_7d)}</span>
                </div>
              ))}
            </div>
          </Card>
          <Card>
            <CardHead label="Breakdown" title="By size" sub="Next 7 days" />
            <div className="h-[260px]">
              <ResponsiveContainer>
                <BarChart data={["XS", "S", "M", "L", "XL", "XXL", "Free"].map((s) => data.breakdown.sizes.find((x: any) => x.size === s)).filter(Boolean)} margin={{ left: -10 }}>
                  <CartesianGrid stroke={C.grid} vertical={false} />
                  <XAxis dataKey="size" {...axis} />
                  <YAxis {...axis} />
                  <Tooltip content={<ChartTooltip />} />
                  <Bar dataKey="expected_network_7d" name="Returns" fill={C.blue} radius={[3, 3, 0, 0]} barSize={22} />
                </BarChart>
              </ResponsiveContainer>
            </div>
          </Card>
        </div>
      )}
      </More>
    </div>
  );
}
