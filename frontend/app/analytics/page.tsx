"use client";
import { Download, Info } from "lucide-react";
import { useState } from "react";
import { Area, AreaChart, Bar, BarChart, CartesianGrid, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { axis, C, ChartTooltip, Sparkline } from "@/components/charts";
import { getUserId } from "@/lib/session";
import { Card, CardHead, DetailOnly, Drawer, ErrorState, Loading, PageHeader, SyntheticTag } from "@/components/ui";
import { API, useApi } from "@/lib/api";
import { inr, num, pct } from "@/lib/format";

const fmtV = (v: number | null, unit: string) =>
  v === null || v === undefined ? "—" : unit === "ratio" ? pct(v, 1) : unit === "INR" ? inr(v, v > 99999) : unit === "hours" ? `${num(v, 1)} h` : unit === "days" ? `${num(v, 1)} d` : num(v, 2);

export default function Analytics() {
  const { data, error, loading, reload } = useApi<any>("/analytics/kpis");
  const [open, setOpen] = useState<any>(null);
  const download = async (ds: string) => {
    const r = await fetch(`${API}/api/integrations/sac/${ds}.csv`, { headers: { "X-User-Id": getUserId() } });
    const b = await r.blob();
    const a = document.createElement("a");
    a.href = URL.createObjectURL(b);
    a.download = `reverseflow_${ds}.csv`;
    a.click();
  };
  if (error) return <ErrorState error={error} onRetry={reload} />;
  if (loading || !data) return <Loading rows={2} />;
  return (
    <div className="space-y-5">
      <PageHeader eyebrow="Reports" title="The numbers that matter"
        sub="Each figure is worked out from the app's own data. Click one to see what it means, how it has changed, and which city or seller drives it."
        right={<SyntheticTag />} />
      <div className="grid grid-cols-1 gap-3 md:grid-cols-2 xl:grid-cols-3">
        {data.kpis.map((k: any) => (
          <button key={k.key} onClick={() => setOpen(k)} className="text-left">
            <Card className="h-full transition-colors hover:border-ink-500">
              <div className="flex items-start justify-between gap-2">
                <div className="label">{k.name}</div>
                <Info className="h-3.5 w-3.5 shrink-0 text-ink-300" />
              </div>
              <div className="mt-2 flex items-end justify-between gap-3">
                <div>
                  <div className="display-num text-[34px]">{fmtV(k.value, k.unit)}</div>
                  {k.baseline_value !== undefined && <DetailOnly><div className="mt-1 text-[11px] text-ink-500">baseline model {pct(k.baseline_value, 1)} · weekly {pct(k.weekly_accuracy, 1)}</div></DetailOnly>}
                  {k.window && <div className="mt-1 text-[11px] text-ink-500">{k.window}</div>}
                  {k.key === "surge_lead_time" && <div className="mt-1 text-[11px] text-ink-500">warning given before last year's peak</div>}
                </div>
                {k.trend?.length > 1 && <Sparkline data={k.trend} width={110} height={38} color={k.key === "value_at_risk" ? C.red : C.blue} />}
              </div>
              <div className="mt-3 line-clamp-2 text-[11.5px] leading-snug text-ink-500">{k.definition}</div>
            </Card>
          </button>
        ))}
      </div>
      <Card>
        <CardHead label="Downloads" title="Take the data with you" sub="Spreadsheet files (CSV) you can open in Excel, or load into SAP Analytics Cloud." />
        <div className="flex flex-wrap gap-2">
          {[["returns_fact", "All returns"], ["forecast", "Forecast"], ["vendor_kpis", "Seller scorecard"], ["recovery_queue", "Resale list"]].map(([d, l]) => (
            <button key={d} onClick={() => download(d)} className="flex items-center gap-2 rounded border border-line-strong px-3.5 py-2 text-[13px] hover:border-ink-500"><Download className="h-3.5 w-3.5" />{l}</button>
          ))}
        </div>
      </Card>
      <Drawer open={!!open} onClose={() => setOpen(null)} title={open?.name} width={640}>
        {open && (
          <div className="space-y-4">
            <div className="display-num text-[48px]">{fmtV(open.value, open.unit)}</div>
            <div className="rounded bg-canvas p-3.5 text-[13px] leading-relaxed"><b>What it means.</b> {open.definition}</div>
            {open.trend?.length > 0 && (
              <div>
                <div className="label mb-2">Over time</div>
                <div className="h-56">
                  <ResponsiveContainer>
                    {open.key === "forecast_accuracy" ? (
                      <LineChart data={open.trend} margin={{ left: -10, right: 8 }}>
                        <CartesianGrid stroke={C.grid} vertical={false} /><XAxis dataKey="period" {...axis} /><YAxis {...axis} domain={[0, 1]} tickFormatter={(v) => pct(v)} />
                        <Tooltip content={<ChartTooltip fmt={(v: number) => pct(v, 1)} />} />
                        <Line dataKey="value" name="Our forecast" stroke={C.blue} strokeWidth={2} dot={false} /><Line dataKey="baseline" name="Simple guess" stroke={C.amber} dot={false} />
                      </LineChart>
                    ) : (
                      <AreaChart data={open.trend} margin={{ left: 0, right: 8 }}>
                        <CartesianGrid stroke={C.grid} vertical={false} /><XAxis dataKey="period" {...axis} interval="preserveStartEnd" />
                        <YAxis {...axis} tickFormatter={(v) => (open.unit === "ratio" ? pct(v) : open.unit === "INR" ? inr(v, true) : num(v))} />
                        <Tooltip content={<ChartTooltip fmt={(v: number) => fmtV(v, open.unit)} />} />
                        <Area dataKey="value" name={open.name} stroke={C.blue} fill={C.band} strokeWidth={1.8} />
                      </AreaChart>
                    )}
                  </ResponsiveContainer>
                </div>
              </div>
            )}
            {open.drilldown?.length > 0 && (
              <div>
                <div className="label mb-2">Broken down</div>
                {open.key === "surge_lead_time" ? (
                  <table className="w-full text-[12.5px]"><tbody>{open.drilldown.map((d: any) => (
                    <tr key={d.cluster_id} className="border-t border-line"><td className="py-1.5">{d.cluster_id}</td><td className="py-1.5">peak {d.peak}</td><td className="py-1.5">alert {d.alert_issued}</td><td className="num py-1.5 text-right font-semibold">{d.lead_days} days</td></tr>
                  ))}</tbody></table>
                ) : (
                  <div style={{ height: Math.max(160, open.drilldown.length * 26) }}>
                    <ResponsiveContainer>
                      <BarChart data={open.drilldown} layout="vertical" margin={{ left: 30, right: 20 }}>
                        <XAxis type="number" {...axis} tickFormatter={(v) => (open.unit === "ratio" || open.key === "vendor_defect_rate" ? pct(v) : open.unit === "INR" ? inr(v, true) : num(v))} />
                        <YAxis type="category" dataKey="label" {...axis} width={150} tick={{ fontSize: 10.5, fill: "#BDBDBD" }} />
                        <Tooltip content={<ChartTooltip fmt={(v: number) => (open.unit === "INR" ? inr(v) : open.unit === "ratio" ? pct(v, 1) : num(v, 1))} />} />
                        <Bar dataKey="value" name={open.name} fill={C.navy} barSize={12} radius={[0, 3, 3, 0]} />
                      </BarChart>
                    </ResponsiveContainer>
                  </div>
                )}
              </div>
            )}
          </div>
        )}
      </Drawer>
    </div>
  );
}
