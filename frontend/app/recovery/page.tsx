"use client";
import clsx from "clsx";
import Link from "next/link";
import { useState } from "react";
import { useSession } from "@/components/providers";
import { CartesianGrid, Line, LineChart, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { axis, C, ChartTooltip } from "@/components/charts";
import { Badge, BigStats, Card, CardHead, DetailOnly, ErrorState, Loading, More, PageHeader, Segmented, selectCls, statusText, statusTone, SyntheticTag } from "@/components/ui";
import { KIND_LABEL } from "@/lib/format";
import { useApi } from "@/lib/api";
import { day, inr, num, pct } from "@/lib/format";

const CATS = ["Lehenga", "Indo-western", "Festive dress", "Saree", "Kurta set"];

export default function Recovery() {
  const [cat, setCat] = useState("Lehenga");
  const [price, setPrice] = useState(7999);
  const [sort, setSort] = useState<"value" | "fifo">("value");
  const { detail } = useSession();
  const q = useApi<any>("/recovery/queue");
  const curve = useApi<any>(`/recovery/curve?price=${price}&category=${encodeURIComponent(cat)}&days=120`, { deps: [cat, price] });
  const recs = useApi<any>("/approvals");
  if (q.error) return <ErrorState error={q.error} onRetry={q.reload} />;
  if (q.loading || !q.data) return <Loading />;
  const d = q.data;
  const items = sort === "value" ? d.items : [...d.items].sort((a: any, b: any) => b.age_days - a.age_days);
  const series = curve.data ? curve.data.curves.A.map((p: any, i: number) => ({
    day: day(p.day), A: p.value, B: curve.data.curves.B[i].value, C: curve.data.curves.C[i].value, demand: p.demand30,
  })) : [];
  const recRows = (recs.data?.items || []).filter((r: any) => r.agent === "recovery");
  const saved = d.comparison.value_priority_protected - d.comparison.fifo_protected;

  return (
    <div className="space-y-5">
      <PageHeader eyebrow="Resale" title="Get the value back"
        sub="Festive clothes lose value every day they sit in a warehouse. Instead of checking returns in the order they arrive, the system checks the ones that would lose the most money first."
        right={<SyntheticTag />} />

      <BigStats items={[
        { label: "Returned items on their way", value: num(d.total), sub: "Being collected, travelling or at a warehouse" },
        { label: "Worth, if resold quickly", value: inr(d.totals.value_if_fast, true), sub: "Demo sample of items" },
        { label: "Lost if they wait a week", value: inr(d.totals.value_at_risk_7d, true), tone: "bad" },
        { label: "Saved by checking the right ones first", value: `+${inr(saved, true)}`, tone: "ok", sub: `In the first ${d.comparison.first_n} items, compared with first-come-first-served`, hint: "Checking the items that lose value fastest first, instead of in arrival order." },
      ]} />

      <div className="grid grid-cols-1 gap-4 xl:grid-cols-3">
        <Card className="xl:col-span-2">
          <CardHead label="How fast value drops" title={`What a returned ${cat.toLowerCase()} is worth, by the day it's back on sale`}
            sub="Festive wear sells well for a few weeks, then demand falls away. The longer an item waits, the less it can be sold for."
            right={
              <div className="flex items-center gap-2">
                <select value={cat} onChange={(e) => setCat(e.target.value)} className={selectCls}>{CATS.map((c) => <option key={c}>{c}</option>)}</select>
                <select value={price} onChange={(e) => setPrice(Number(e.target.value))} className={selectCls}>
                  {[2999, 4999, 7999, 12999].map((p) => <option key={p} value={p}>{inr(p)}</option>)}
                </select>
              </div>
            } />
          <div className="h-[280px]">
            {curve.error ? <ErrorState error={curve.error} /> : (
              <ResponsiveContainer>
                <LineChart data={series} margin={{ left: 6, right: 10, top: 8 }}>
                  <CartesianGrid stroke={C.grid} vertical={false} />
                  <XAxis dataKey="day" {...axis} interval={7} />
                  <YAxis {...axis} tickFormatter={(v) => inr(v, true)} />
                  <Tooltip content={<ChartTooltip fmt={(v: number) => inr(v)} />} />
                  <ReferenceLine y={0} stroke="#363636" />
                  <ReferenceLine x={series[15]?.day} stroke={C.amber} strokeDasharray="3 3" label={{ value: "+30 days", fontSize: 10, fill: C.amber, position: "top" }} />
                  <Line dataKey="A" name="Like new" stroke={C.blue} strokeWidth={2.2} dot={false} isAnimationActive={false} />
                  <Line dataKey="B" name="Needs a small repair" stroke={C.navy} strokeWidth={1.6} dot={false} isAnimationActive={false} />
                  <Line dataKey="C" name="Damaged" stroke={C.slate} strokeWidth={1.4} dot={false} strokeDasharray="4 3" isAnimationActive={false} />
                </LineChart>
              </ResponsiveContainer>
            )}
          </div>
          {curve.data && (
            <div className="mt-3 grid grid-cols-3 gap-3 border-t border-line pt-3 text-[12px]">
              {(["A", "B", "C"] as const).map((g) => {
                const c = curve.data.curves[g];
                const drop = c[0].value - c[15].value;
                return <div key={g}><div className="label">{({ A: "Like new", B: "Needs repair", C: "Damaged" } as any)[g]}</div><div className="mt-1"><span className="num">{inr(c[0].value)}</span> today → <span className="num">{inr(c[15].value)}</span> in 30 days</div><div className="num text-bad-700">−{inr(drop)}</div></div>;
              })}
            </div>
          )}
        </Card>
        <Card>
          <CardHead label="Condition" title="What shape the returns are in" sub="Expected, based on why customers returned them. Confirmed at inspection." />
          <div className="space-y-4">
            {(["A", "B", "C"] as const).map((g, i) => (
              <div key={g}>
                <div className="flex justify-between text-[13px]"><span>{({ A: "Like new, resell as is", B: "Needs a small repair", C: "Damaged" } as any)[g]}</span><span className="num">{d.grade_mix[g]}</span></div>
                <div className="mt-1.5 h-2 rounded-full bg-canvas"><div className="h-full rounded-full" style={{ width: `${(d.grade_mix[g] / Math.max(d.total, 1)) * 100}%`, background: [C.blue, C.navy, C.red][i] }} /></div>
              </div>
            ))}
          </div>
        </Card>
      </div>

      <Card pad={false}>
        <div className="flex flex-wrap items-center justify-between gap-2 border-b border-line px-4 py-2.5">
          <div>
            <div className="text-[15px] font-semibold">Which items to check first</div>
            <div className="text-[12.5px] text-ink-500">Top of the list loses the most money per day. Switch to see the old first-come-first-served order.</div>
          </div>
          <Segmented value={sort} onChange={setSort} items={[{ id: "value", label: "Most value first" }, { id: "fifo", label: "Arrival order" }]} />
        </div>
        <div className="max-h-[480px] overflow-auto">
          <table className="w-full min-w-[760px] text-[12.5px]">
            <thead className="sticky top-0 bg-white"><tr className="label border-b border-line text-left">
              <th className="px-4 py-2.5 font-normal">#</th><th className="py-2.5 font-normal">Item</th><th className="py-2.5 font-normal">Where</th>
              <th className="py-2.5 text-center font-normal">Condition</th>{detail && <th className="py-2.5 text-right font-normal">P(A)</th>}<th className="py-2.5 text-right font-normal">Worth now</th>
              <th className="py-2.5 text-right font-normal">Loses per day</th><th className="py-2.5 pr-4 text-right font-normal">Lost in a week</th></tr></thead>
            <tbody>
              {items.slice(0, 120).map((it: any, i: number) => (
                <tr key={it.return_id} className="border-b border-line hover:bg-canvas">
                  <td className="num px-4 py-2 text-ink-400">{i + 1}</td>
                  <td className="py-2"><div className="font-medium">{it.name}</div><div className="text-[11px] text-ink-400">returned {it.age_days} days ago{detail && <span className="font-mono"> · {it.return_id} · {it.sku}</span>}</div></td>
                  <td className="py-2 text-ink-700">{it.facility_id?.replace("FAC-", "")} <span className="text-[11px] text-ink-500">· {it.status.replace("_", " ")}</span>{it.fast_track && <Badge tone="ok" className="ml-1">fast-tracked</Badge>}</td>
                  <td className="py-2 text-center"><span className={clsx("inline-block rounded-sm px-1.5 py-0.5 text-[11px]", it.expected_grade === "A" ? "bg-paper text-black" : it.expected_grade === "B" ? "bg-canvas text-ink-900" : "bg-bad-50 text-bad-700", !it.grade_known && "border border-dashed border-current")} title={it.grade_known ? "Confirmed at inspection" : "Expected, not yet inspected"}>{({ A: "like new", B: "repair", C: "damaged" } as any)[it.expected_grade]}</span></td>
                  {detail && <td className="num py-2 text-right">{pct(it.p_grade_a)}</td>}
                  <td className="num py-2 text-right">{inr(it.value_if_fast)}</td>
                  <td className="num py-2 text-right">{inr(it.decay_per_day)}</td>
                  <td className="num py-2 pr-4 text-right font-semibold text-bad-700">{inr(it.value_at_risk_7d)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Card>

      <Card>
        <CardHead label="Suggested actions" title="Restock, repair, or move stock to where it sells" right={<Link href="/governance" className="text-xs font-medium text-blue-600">Decide on these</Link>} />
        <div className="grid grid-cols-1 gap-3 md:grid-cols-3">
          {recRows.map((r: any) => (
            <div key={r.id} className="rounded border border-line p-4">
              <div className="label mb-1.5">{KIND_LABEL[r.kind] || r.kind}</div><div className="flex items-start justify-between gap-2"><div className="text-[14px] font-semibold leading-snug">{r.title}</div><Badge tone={statusTone(r.status)}>{statusText(r.status)}</Badge></div>
              <div className="mt-2 text-[12.5px] leading-relaxed text-ink-500">{r.rationale}</div>
              <div className="mt-3 flex gap-4 text-[12px] text-ink-500"><span>Protects <b className="num text-ink-900">{inr(r.impact_inr, true)}</b></span><span>Costs <b className="num text-ink-900">{inr(r.cost_inr, true)}</b></span></div>
              {r.evidence?.moves && <div className="mt-2 space-y-0.5 text-[11px] text-ink-700">{r.evidence.moves.slice(0, 4).map((m: any, i: number) => <div key={i}>{m.units} × {m.category}: {m.from_cluster} → {m.to_cluster}</div>)}</div>}
            </div>
          ))}
        </div>
      </Card>
      <More title="How the value is worked out" sub="The assumptions behind every price">
        <div className="text-[12.5px] leading-relaxed text-ink-500">Value on day t = price × condition factor × demand on day t − repair − inspection − storage × days waited. Demand follows last year's orders for the category.</div>
        <Card>
          <CardHead label="Assumptions" title="The numbers behind the value estimate" sub="Every figure here can be changed in Settings." right={<Link href="/settings" className="text-xs font-medium text-blue-600">Change</Link>} />
          <div className="space-y-1 text-[12px]">
            {Object.entries(d.config.grade_factor).map(([g, v]: any) => <div key={g} className="flex justify-between"><span className="text-ink-500">Grade {g} price factor</span><span className="num">{pct(v)}</span></div>)}
            <div className="flex justify-between"><span className="text-ink-500">Markdown floor</span><span className="num">{pct(d.config.markdown_floor)}</span></div>
            <div className="flex justify-between"><span className="text-ink-500">Storage / day</span><span className="num">{inr(d.config.storage_cost_per_day)}</span></div>
            <div className="flex justify-between"><span className="text-ink-500">Refurbishment</span><span className="num">{pct(d.config.refurb_cost_pct)} of price</span></div>
            <div className="flex justify-between"><span className="text-ink-500">Inspection</span><span className="num">{inr(d.config.inspection_cost)}</span></div>
            {Object.entries(d.config.obsolescence_per_day || {}).map(([k, v]: any) => <div key={k} className="flex justify-between"><span className="text-ink-500">{k} obsolescence</span><span className="num">{(v * 100).toFixed(2)}%/day</span></div>)}
          </div>
          <div className="mt-3 rounded bg-canvas p-2.5 text-[11px] leading-relaxed text-ink-500">No market prices are claimed. Seasonality comes from the synthetic order history; every factor above is an editable assumption.</div>
        </Card>
      </More>
    </div>
  );
}
