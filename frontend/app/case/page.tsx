"use client";
import { ArrowUpRight } from "lucide-react";
import Link from "next/link";
import { ReactNode, useEffect, useMemo, useState } from "react";
import { Badge, BigStats, Card, ErrorState, Hint, Loading, More, PageHeader, Section } from "@/components/ui";
import { useApi } from "@/lib/api";
import { inr, mult, num, pct } from "@/lib/format";

const OBJECTIVES = [
  { t: "Forecast the wave", d: "Predict returns for each city about a week ahead.", href: "/forecasting", page: "Forecast" },
  { t: "Find the cause", d: "Spot sellers, products and sizes that cause avoidable returns.", href: "/root-cause", page: "Product issues" },
  { t: "Plan capacity early", d: "Vans, warehouse routing and inspection shifts, before the peak.", href: "/twin", page: "Planner" },
  { t: "Recover more value", d: "Inspect and resell the most valuable items first.", href: "/recovery", page: "Resale" },
  { t: "Keep people in charge", d: "Anything that costs money or affects a seller or customer needs a named person's approval.", href: "/governance", page: "Decisions" },
  { t: "Work inside SAP", d: "Hand each approved decision to the SAP system that carries it out.", href: "/sap", page: "SAP" },
];

const TERMS = [
  { t: "Return wave", d: "Returns per day compared with a normal week. 2× means twice the usual number." },
  { t: "Reverse capacity", d: "Pickups a day (vans × pickups per van) and inspections a day (staff × shift ÷ minutes per item)." },
  { t: "Value at risk", d: "Resale value lost if returned items wait longer before going back on sale." },
  { t: "Avoidable return", d: "Caused by size, quality or listing errors that a fix at the source would prevent. Changing your mind is not avoidable." },
];

const MEASURES = ["Forecast accuracy and days of warning", "Pickups made within 2 days", "Days from return to back on sale", "Cost per return",
  "Value recovered as a share of the original price", "Avoidable return rate"];

function Num({ n, children }: { n: string; children: ReactNode }) {
  return (
    <div className="grid grid-cols-1 gap-6 border-t border-line pt-8 lg:grid-cols-[120px_1fr]">
      <div className="display-num text-[44px] text-ink-300">{n}</div>
      <div className="min-w-0 space-y-6">{children}</div>
    </div>
  );
}

function H({ children, sub }: { children: ReactNode; sub?: ReactNode }) {
  return (
    <div>
      <h2 className="display text-[30px] text-ink-900 sm:text-[40px]">{children}</h2>
      {sub && <p className="mt-3 max-w-3xl text-[15px] leading-relaxed text-ink-500">{sub}</p>}
    </div>
  );
}

function Src({ ids, sources }: { ids: string[]; sources: Record<string, any> }) {
  if (!ids?.length) return <span className="text-ink-400">our assumption</span>;
  return (
    <span className="space-x-2">
      {ids.map((id) => <a key={id} href={sources[id]?.url} target="_blank" rel="noreferrer" className="text-blue-600">[{Object.keys(sources).indexOf(id) + 1}]</a>)}
    </span>
  );
}

function Slider({ a, v, on }: { a: any; v: number; on: (x: number) => void }) {
  const show = a.unit === "pct" ? pct(v, a.step < 0.01 ? 1 : 0) : `₹${num(v)} cr`;
  return (
    <label className="block">
      <div className="flex items-baseline justify-between gap-3">
        <span className="text-[13px] text-ink-700">{a.label}</span>
        <span className="num text-[14px] text-ink-900">{show}</span>
      </div>
      <input type="range" min={a.min} max={a.max} step={a.step} value={v} onChange={(e) => on(Number(e.target.value))} className="mt-2 w-full" />
      <div className="label mt-1 text-ink-400">{a.kind}</div>
    </label>
  );
}

export default function CasePage() {
  const c = useApi<any>("/case");
  const sap = useApi<any>("/sap/status");
  const [v, setV] = useState<Record<string, number>>({});
  useEffect(() => {
    if (c.data && !Object.keys(v).length) setV(Object.fromEntries(c.data.assumptions.map((a: any) => [a.id, a.value])));
  }, [c.data, v]);

  const d = c.data?.demo;
  const model = useMemo(() => {
    if (!d || !Object.keys(v).length) return null;
    const fashion = v.festive_gmv_cr * v.fashion_share;
    const returned = fashion * v.return_rate;
    const handling = returned * v.reverse_cost_pct;
    const waiting = returned * v.value_lost_pct;
    const timingSaving = waiting * d.planner.reduction;
    const prevented = returned * d.avoidable_share * v.prevented_share;
    const preventionSaving = prevented * (v.reverse_cost_pct + v.value_lost_pct);
    return { fashion, returned, handling, waiting, timingSaving, prevented, preventionSaving, total: timingSaving + preventionSaving };
  }, [d, v]);

  if (c.error) return <ErrorState error={c.error} onRetry={c.reload} />;
  if (!c.data || !model) return <Loading />;
  const S = c.data.sources;
  const fact = (id: string) => c.data.facts.find((f: any) => f.id === id);
  const p = d.planner;
  const surge = d.surge as any[];
  const avgPeak = surge.length ? surge.reduce((a, x) => a + x.peak_multiplier, 0) / surge.length : null;
  const cr = (x: number) => `₹${num(Math.round(x))} cr`;

  return (
    <div className="space-y-14">
      <PageHeader eyebrow="Why it matters" title="The festive return wave"
        sub="The problem ReverseFlow solves, what it sets out to do, a worked example from the demo, what it is worth, and where SAP fits." />

      {/* 1 */}
      <Num n="01">
        <H sub={<>After the festive sales (Navratri, Dussehra, Diwali), online fashion returns don't arrive steadily. They <b className="text-ink-900">arrive as a wave</b> in the week or two after the festival. The return chain, from pickup to inspection to resale, is sized for normal weeks and can't absorb it.</>}>
          Problem statement
        </H>
        <BigStats items={[
          { label: "Festive online sales, 2025", value: "₹1.15 lakh cr", sub: <>Redseer forecast, up 20–25% <Src ids={fact("festive_gmv").sources} sources={S} /></> },
          { label: "First 11 days vs normal", value: "3.5×", sub: <>Sales, so returns follow <Src ids={fact("first_days").sources} sources={S} /></> },
          { label: "Fashion orders returned", value: "17–25%", sub: <>Against 7.8% for all e-commerce <Src ids={fact("fashion_returns").sources} sources={S} /></> },
          { label: "Cost of a return", value: "1.5–2×", sub: <>A forward delivery <Src ids={fact("reverse_cost").sources} sources={S} /></> },
        ]} />
        <div className="grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-4">
          {[
            ["Pickups are missed", "Customers wait longer for their refund."],
            ["Stock waits for days", "Festive clothes lose resale value every day, because demand ends with the season."],
            ["The same faults repeat", "Returns are treated as a cost, not as information about stitching, size charts or photos."],
            ["Everyone acts alone and late", "The marketplace, sellers, couriers and warehouses each see one part, after the wave has hit."],
          ].map(([t, x]) => <Card key={t}><div className="text-[14px] font-semibold">{t}</div><div className="mt-1.5 text-[13px] leading-relaxed text-ink-500">{x}</div></Card>)}
        </div>
      </Num>

      {/* 2 */}
      <Num n="02">
        <H sub="An AI-assisted control tower for festive returns. Each objective is a page in this app.">Objective</H>
        <div className="grid grid-cols-1 gap-px overflow-hidden rounded border border-line bg-line md:grid-cols-2 xl:grid-cols-3">
          {OBJECTIVES.map((o, i) => (
            <Link key={o.t} href={o.href} className="group bg-black p-5 hover:bg-canvas">
              <div className="flex items-center justify-between">
                <span className="label">{String(i + 1).padStart(2, "0")} · {o.page}</span>
                <ArrowUpRight className="h-3.5 w-3.5 text-ink-300 group-hover:text-ink-900" />
              </div>
              <div className="mt-3 text-[15px] font-semibold">{o.t}</div>
              <div className="mt-1 text-[13px] leading-relaxed text-ink-500">{o.d}</div>
            </Link>
          ))}
        </div>
      </Num>

      {/* 3 */}
      <Num n="03">
        <H sub="Customer returns of fashion bought online during festive peaks, from the moment the return is booked until the item is back on sale, repaired, sold off cheaply or charged back to the seller.">
          Defining it properly
        </H>
        <div className="grid grid-cols-1 gap-4 xl:grid-cols-3">
          <Card className="xl:col-span-2">
            <div className="label mb-3">Key terms</div>
            <dl className="divide-y divide-line">
              {TERMS.map((t) => (
                <div key={t.t} className="grid grid-cols-1 gap-1 py-3 sm:grid-cols-[180px_1fr]">
                  <dt className="text-[13.5px] font-semibold">{t.t}</dt><dd className="text-[13px] leading-relaxed text-ink-500">{t.d}</dd>
                </div>
              ))}
            </dl>
          </Card>
          <div className="space-y-4">
            <Card>
              <div className="label mb-3">How we measure success</div>
              <ul className="space-y-2 text-[13px] text-ink-700">{MEASURES.map((x) => <li key={x} className="flex gap-2"><span className="text-ink-400">—</span>{x}</li>)}</ul>
              <Link href="/analytics" className="mt-4 inline-block text-xs font-medium text-blue-600">See them on Reports</Link>
            </Card>
            <Card>
              <div className="label mb-2">Out of scope, on purpose</div>
              <p className="text-[13px] leading-relaxed text-ink-500">Refusing a customer's return or penalising a seller automatically. The system can only ask for a closer look and send the decision to a person.</p>
            </Card>
          </div>
        </div>
      </Num>

      {/* 4 */}
      <Num n="04">
        <H sub="Priya in Pune buys a ₹7,999 bandhani lehenga in the pre-Navratri sale. The stitching opens at the waist during garba, and she books a return the day after Dussehra, along with thousands of shoppers in Pune, Ahmedabad and Jaipur.">
          A real-life example
        </H>
        <div className="grid grid-cols-1 gap-4 xl:grid-cols-2">
          <Card>
            <div className="label mb-3">Without coordination</div>
            <ul className="space-y-3 text-[13.5px] leading-relaxed text-ink-700">
              <li>Pune's vans collect <b className="num text-ink-900">{num(d.pickup.capacity_per_day)}</b> returns a day, but <b className="num text-ink-900">{num(d.pickup.needed_per_day)}</b> are booked. Her pickup slips.</li>
              <li>At the warehouse her lehenga waits in arrival order behind cheaper items, losing value as festive demand fades.</li>
              <li>Her refund is late.</li>
              <li>The seller, with the same fault on many lehengas, finds out weeks later, so next season repeats.</li>
            </ul>
          </Card>
          <Card>
            <div className="label mb-3">With ReverseFlow (from the live demo)</div>
            <ol className="space-y-3 text-[13.5px] leading-relaxed text-ink-700">
              <li><b className="text-ink-900">Five days early:</b> the forecast flags {surge.map((s) => s.city).join(", ")} at about <b className="num text-ink-900">{mult(avgPeak)}</b> normal returns at the peak. <Link href="/forecasting" className="text-blue-600">Forecast</Link></li>
              <li><b className="text-ink-900">The cause:</b> <b className="num text-ink-900">{pct(d.seller.share)}</b> of returns from {d.seller.name} are for "{d.seller.reason?.toLowerCase()}", against <b className="num text-ink-900">{pct(d.seller.others_share, 1)}</b> for other sellers. A quality check is suggested and sent to the quality manager. <Link href="/root-cause" className="text-blue-600">Product issues</Link></li>
              <li><b className="text-ink-900">The plan:</b> doing nothing loses about <b className="num text-ink-900">{inr(p.baseline.value_lost, true)}</b> of resale value over 14 days. Extra vans, sending <b className="num text-ink-900">{pct(d.reroute.share)}</b> of Pune's returns to Nashik, an extra shift and checking valuable items first cut that to <b className="num text-ink-900">{inr(p.C.value_lost, true)}</b>. <Link href="/twin" className="text-blue-600">Planner</Link></li>
              <li><b className="text-ink-900">The approval:</b> a named manager approves each change with a reason. <b className="num text-ink-900">{num(d.decisions_waiting)}</b> decisions are waiting for people right now. <Link href="/governance" className="text-blue-600">Decisions</Link></li>
              <li><b className="text-ink-900">The safety check:</b> <b className="num text-ink-900">{num(d.integrity_checks)}</b> returns get a closer look at the warehouse. No refund is blocked automatically.</li>
              <li><b className="text-ink-900">Into SAP:</b> approved van bookings go to SAP TM, the seller's quality notice to Ariba, and the forecast to IBP. <Link href="/sap" className="text-blue-600">SAP</Link></li>
            </ol>
          </Card>
        </div>
        <BigStats items={[
          { label: "Value lost, doing nothing", value: inr(p.baseline.value_lost, true), sub: "Planner, 14 days, three cities", tone: "bad" },
          { label: "Value lost, combined plan", value: inr(p.C.value_lost, true), sub: `${pct(p.reduction)} less`, tone: "ok" },
          { label: "Picked up on time", value: `${pct(p.baseline.pickup_on_time)} → ${pct(p.C.pickup_on_time)}`, sub: "Within 2 days" },
          { label: "Days to resale", value: `${num(p.baseline.days_to_resale, 1)} → ${num(p.C.days_to_resale, 1)}`, sub: "From pickup to back on sale" },
        ]} />
        <p className="text-[12px] text-ink-400">{p.scenario} All demo records are synthetic.</p>
      </Num>

      {/* 5 */}
      <Num n="05">
        <H sub="A rough model of the whole Indian market, built from published figures. Move the sliders to test the assumptions; the savings use the planner result and the avoidable share from the demo.">
          The economics
        </H>
        <div className="grid grid-cols-1 gap-4 xl:grid-cols-[380px_1fr]">
          <Card className="space-y-5">
            <div className="label">Assumptions</div>
            {c.data.assumptions.map((a: any) => <Slider key={a.id} a={a} v={v[a.id]} on={(x) => setV({ ...v, [a.id]: x })} />)}
          </Card>
          <div className="space-y-4">
            <BigStats items={[
              { label: "Festive fashion sales", value: cr(model.fashion), sub: `${pct(v.fashion_share)} of ₹${num(v.festive_gmv_cr)} cr` },
              { label: "Comes back as returns", value: cr(model.returned), sub: `${pct(v.return_rate)} of fashion sales, in one season` },
              { label: "Cost to handle them", value: cr(model.handling), sub: "Pickup, transport, inspection", tone: "bad" },
              { label: "Lost to waiting", value: cr(model.waiting), sub: "Resale value lost while stock waits", tone: "bad" },
            ]} />
            <Card>
              <div className="label mb-4">What better coordination could save, each festive season</div>
              <div className="grid grid-cols-1 gap-6 md:grid-cols-3">
                <div>
                  <div className="display-num text-[36px]">{cr(model.timingSaving)}</div>
                  <div className="mt-2 text-[12.5px] leading-relaxed text-ink-500">Less value lost to waiting: the planner's {pct(p.reduction)} reduction applied to {cr(model.waiting)}.</div>
                </div>
                <div>
                  <div className="display-num text-[36px]">{cr(model.preventionSaving)}</div>
                  <div className="mt-2 text-[12.5px] leading-relaxed text-ink-500">Returns that never happen: {pct(v.prevented_share)} of the avoidable {pct(d.avoidable_share)} prevented, saving their handling and lost value.</div>
                </div>
                <div>
                  <div className="display-num text-[36px] text-ok-700">{cr(model.total)}</div>
                  <div className="mt-2 text-[12.5px] leading-relaxed text-ink-500">Together. A rough estimate to discuss, not a forecast.</div>
                </div>
              </div>
            </Card>
            <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
              {[
                ["Marketplaces", "Reverse shipping, warehouse overtime, markdowns, and lost sales while customers wait for refunds."],
                ["Sellers", "Often small businesses: money tied up in returned stock, charge-backs and repeated faults."],
                ["Couriers and warehouses", "Unpredictable peaks, overtime and missed service targets."],
                ["Customers and the planet", "Late refunds, less trust, extra trips and clothes written off."],
              ].map(([t, x]) => <Card key={t}><div className="text-[14px] font-semibold">Who pays: {t}</div><div className="mt-1.5 text-[13px] leading-relaxed text-ink-500">{x}</div></Card>)}
            </div>
          </div>
        </div>
        <More title="Published figures and the formula">
          <Card pad={false}>
            <table className="w-full text-[13px]">
              <tbody>
                {c.data.facts.map((f: any) => (
                  <tr key={f.id} className="border-b border-line align-top last:border-0">
                    <td className="px-5 py-3 text-ink-700">{f.label}</td>
                    <td className="num px-5 py-3 text-ink-900">{f.value}</td>
                    <td className="px-5 py-3"><Badge tone={f.kind === "published" ? "ok" : "warn"}>{f.kind}</Badge></td>
                    <td className="px-5 py-3"><Src ids={f.sources} sources={S} /></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </Card>
          <div className="rounded border border-line bg-black p-4 font-mono text-[11.5px] leading-relaxed text-ink-500">
            returned = sales × fashion share × return rate<br />
            handling = returned × handling cost share · lost to waiting = returned × value lost share<br />
            timing saving = lost to waiting × planner reduction ({pct(p.reduction)})<br />
            prevention saving = returned × avoidable share ({pct(d.avoidable_share)}, demo data) × prevented share × (handling share + value lost share)
          </div>
        </More>
      </Num>

      {/* 6 */}
      <Num n="06">
        <H sub="A return touches orders, stock, transport, suppliers and finance, and in large retailers those already run on SAP. ReverseFlow is the layer that links them for the return wave, instead of another separate system.">
          Use of SAP
        </H>
        {sap.error ? <ErrorState error={sap.error} /> : !sap.data ? <Loading rows={1} /> : (
          <Card pad={false} className="divide-y divide-line">
            {sap.data.services.map((s: any) => (
              <div key={s.id} className="grid grid-cols-1 gap-2 px-5 py-4 md:grid-cols-[260px_1fr_170px] md:items-center">
                <div className="text-[13.5px] font-semibold">{s.product}</div>
                <div className="text-[13px] leading-relaxed text-ink-500">{s.does}</div>
                <div className="md:text-right">
                  <Badge tone={{ in_use: "ok", connected: "ok", ready: "warn", planned: "neutral" }[s.state as string] as any} dot>
                    {{ in_use: "In use", connected: "Connected", ready: "Built, not connected", planned: "Planned" }[s.state as string]}
                  </Badge>
                </div>
              </div>
            ))}
          </Card>
        )}
        <Link href="/sap" className="inline-flex items-center gap-1 text-[13px] font-medium text-blue-600">See connections and messages <ArrowUpRight className="h-3.5 w-3.5" /></Link>
      </Num>

      <Section label="Sources">
        <ol className="list-decimal space-y-1.5 pl-5 text-[12.5px] text-ink-500">
          {Object.entries(S).map(([id, s]: any) => <li key={id}><a href={s.url} target="_blank" rel="noreferrer" className="text-blue-600">{s.label}</a></li>)}
        </ol>
        <p className="flex items-center gap-1.5 text-[12px] text-ink-400">
          Many return and cost figures come from logistics companies' blogs rather than audited studies, so they are shown as ranges.
          <Hint text={c.data.note} />
        </p>
      </Section>
    </div>
  );
}
