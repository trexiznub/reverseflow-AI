"use client";
import "@xyflow/react/dist/style.css";
import { Background, Controls, Edge, Handle, Node, Position, ReactFlow } from "@xyflow/react";
import clsx from "clsx";
import { useEffect, useMemo, useRef, useState } from "react";
import { Bar, BarChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { axis, ChartTooltip, SERIES } from "@/components/charts";
import { Badge, Button, Card, CardHead, DetailOnly, Empty, ErrorState, inputCls, KV, Loading, More, PageHeader, selectCls, statusText, statusTone, SyntheticTag } from "@/components/ui";
import { post, useApi } from "@/lib/api";
import { inr, num, pct, reasonLabel } from "@/lib/format";

const COLS = ["customer", "return", "sku", "size", "vendor", "defect", "intervention"];
const COL_LABEL: Record<string, string> = { customer: "Customer", return: "Return", sku: "Product", size: "Size", vendor: "Seller", defect: "Problem", intervention: "Fix" };
const TONE: Record<string, string> = {
  customer: "border-line-strong bg-black", return: "border-line-strong bg-canvas", sku: "border-ink-400 bg-black", size: "border-line-strong bg-black",
  vendor: "border-paper bg-paper text-black", defect: "border-[#6A3428] bg-bad-50", intervention: "border-[#1D3D2B] bg-ok-50",
};

function GNode({ data }: any) {
  return (
    <div className={clsx("rounded border px-2 py-1.5 text-left", TONE[data.type], data.dim && "opacity-20", data.active && "ring-2 ring-ink-900 ring-offset-2 ring-offset-black")} style={{ width: data.w }}>
      <Handle type="target" position={Position.Left} />
      <div className={clsx("truncate text-[11px] font-semibold leading-tight", data.type === "vendor" ? "text-black" : "text-ink-900")}>{data.label}</div>
      {data.sub && <div className={clsx("num truncate text-[10px]", data.type === "vendor" ? "text-black/60" : "text-ink-500")}>{data.sub}</div>}
      <Handle type="source" position={Position.Right} />
    </div>
  );
}
function HdrNode({ data }: any) {
  return <div className="label w-[150px] border-b border-line-strong pb-1 text-center">{data.label}</div>;
}
const nodeTypes = { g: GNode, hdr: HdrNode };

export default function RootCause() {
  const [vendor, setVendor] = useState("");
  const [sku, setSku] = useState("");
  const [selected, setSelected] = useState<any>(null);
  const summary = useApi<any>("/intelligence/summary");
  const [ready, setReady] = useState(false);
  const graph = useApi<any>(ready ? `/intelligence/graph?${vendor ? `vendor_id=${vendor}` : ""}${sku ? `sku=${sku}` : ""}` : null, { deps: [vendor, sku, ready] });
  const skuDetail = useApi<any>(selected?.type === "sku" ? `/intelligence/sku/${selected.data.sku}` : null, { deps: [selected?.id] });
  const [text, setText] = useState("Choli is very tight, size chart seems wrong");
  useEffect(() => {
    if (summary.data && !ready) {
      setVendor(summary.data.vendor_findings[0]?.vendor_id || "");
      setReady(true);
    }
  }, [summary.data, ready]);
  const [cls, setCls] = useState<any>(null);
  // Fit the graph to its box once nodes are measured, and again if the box changes size.
  const flowRef = useRef<any>(null);
  const boxRef = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const fit = () => flowRef.current?.fitView({ padding: 0.06 });
    const timers = [80, 350, 900].map((t) => setTimeout(fit, t));
    const ro = typeof ResizeObserver !== "undefined" && boxRef.current ? new ResizeObserver(() => fit()) : null;
    if (ro && boxRef.current) ro.observe(boxRef.current);
    return () => { timers.forEach(clearTimeout); ro?.disconnect(); };
  }, [graph.data]);

  const { nodes, edges } = useMemo(() => {
    const g = graph.data;
    if (!g) return { nodes: [], edges: [] };
    const linked = new Set<string>();
    if (selected) {
      // walk both directions from the selected node
      const adjF: Record<string, string[]> = {}, adjB: Record<string, string[]> = {};
      g.edges.forEach((e: any) => { (adjF[e.source] ||= []).push(e.target); (adjB[e.target] ||= []).push(e.source); });
      const walk = (start: string, adj: Record<string, string[]>) => {
        const seen = new Set<string>();
        const st = [start];
        while (st.length) {
          const n = st.pop()!;
          if (seen.has(n)) continue;
          seen.add(n);
          linked.add(n);
          (adj[n] || []).forEach((x) => st.push(x));
        }
      };
      walk(selected.id, adjF); walk(selected.id, adjB);
    }
    const byCol: Record<string, any[]> = {};
    g.nodes.forEach((n: any) => (byCol[n.type] ||= []).push(n));
    const ns: Node[] = [];
    const tallest = Math.max(...COLS.map((c) => (byCol[c] || []).length * (c === "customer" || c === "return" ? 34 : c === "size" ? 32 : 58)));
    COLS.forEach((c, ci) => ns.push({ id: `hdr-${c}`, type: "hdr", position: { x: ci * 175, y: -tallest / 2 - 44 }, data: { label: COL_LABEL[c] }, selectable: false }));
    COLS.forEach((c, ci) => {
      const list = (byCol[c] || []).sort((a: any, b: any) => (b.data.returns || 0) - (a.data.returns || 0));
      const gap = c === "customer" || c === "return" ? 34 : c === "size" ? 32 : 58;
      const h = list.length * gap;
      list.forEach((n: any, i: number) => {
        const sub = n.type === "return" ? n.data.reason : n.data.returns ? `${n.data.returns} returns` : n.type === "customer" ? n.data.cluster : n.type === "intervention" ? `${(n.data.recommendations || []).length} recs` : "";
        ns.push({ id: n.id, type: "g", position: { x: ci * 175, y: i * gap - h / 2 }, data: { ...n, label: n.label, sub, w: 150, dim: selected && !linked.has(n.id), active: selected?.id === n.id } });
      });
    });
    const maxW = Math.max(1, ...g.edges.map((e: any) => e.weight));
    const es: Edge[] = g.edges.map((e: any) => ({
      id: e.id, source: e.source, target: e.target,
      style: { stroke: selected && !(linked.has(e.source) && linked.has(e.target)) ? "#1C1C1C" : e.target.startsWith("defect") || e.target.startsWith("intervention") ? "#F0583E" : "#555555",
               strokeWidth: 0.8 + 3.5 * (e.weight / maxW), opacity: 0.75 },
    }));
    return { nodes: ns, edges: es };
  }, [graph.data, selected]);

  const classify = async () => {
    try { setCls(await post("/intelligence/classify", { text })); } catch (e: any) { setCls({ error: e.message }); }
  };

  if (summary.error) return <ErrorState error={summary.error} onRetry={summary.reload} />;
  if (summary.loading || !summary.data) return <Loading />;
  const s = summary.data;
  const rc = s.model_metrics?.reason_classifier;

  return (
    <div className="space-y-5">
      <PageHeader eyebrow={`Product issues · last ${s.window_days} days · ${num(s.total_returns)} returns`} title="Why items come back"
        sub="The system reads what customers write when they return something, sorts it into reasons, and checks which products and sellers have far more of one problem than everyone else. Fix those, and the returns stop."
        right={<SyntheticTag />} />

      <div className="grid grid-cols-1 gap-3 md:grid-cols-2 xl:grid-cols-3">
        {s.recurring_feedback.slice(0, 3).map((f: any) => (
          <Card key={f.sku}>
            <div className="label">Customers keep saying</div>
            <div className="mt-1 text-[13px] font-semibold leading-tight">{f.customers} customers returned {f.name}</div>
            <div className="text-[11.5px] text-ink-500">Sold by {f.vendor_name}<DetailOnly> · <span className="font-mono">{f.sku}</span></DetailOnly></div>
            <div className="mt-2 flex h-2 overflow-hidden rounded-full">
              {f.breakdown.map((b: any, i: number) => <div key={b.reason} style={{ width: `${(b.count / f.returns) * 100}%`, background: SERIES[i % SERIES.length] }} title={`${b.label}: ${b.count}`} />)}
            </div>
            <div className="mt-2 space-y-0.5">
              {f.breakdown.slice(0, 3).map((b: any, i: number) => (
                <div key={b.reason} className="flex justify-between text-[11.5px]"><span className="flex items-center gap-1.5"><span className="h-2 w-2 rounded-sm" style={{ background: SERIES[i] }} />{b.label}</span><span className="num">{b.count}</span></div>
              ))}
            </div>
          </Card>
        ))}
      </div>

      <div className="grid grid-cols-1 gap-4 xl:grid-cols-[1fr_340px]">
        <Card pad={false}>
          <div className="flex flex-wrap items-center gap-2 border-b border-line px-4 py-2.5">
            <span className="text-[14px] font-semibold">Trace a problem</span>
            <select value={vendor} onChange={(e) => { setVendor(e.target.value); setSku(""); setSelected(null); }} className={selectCls}>
              <option value="">All sellers with a problem</option>
              {s.vendor_rankings.map((v: any) => <option key={v.vendor_id} value={v.vendor_id}>{v.name}</option>)}
            </select>
            <select value={sku} onChange={(e) => { setSku(e.target.value); setVendor(""); setSelected(null); }} className={clsx(selectCls, "max-w-[240px]")}>
              <option value="">Any product</option>
              {s.sku_findings.map((f: any) => <option key={f.sku + f.reason} value={f.sku}>{f.name || f.sku} · {f.reason_label}</option>)}
            </select>
            {selected && <Button size="sm" variant="ghost" onClick={() => setSelected(null)}>Show everything</Button>}
            <span className="ml-auto text-[12px] text-ink-500">Click any box to follow it. Thicker lines mean more returns.</span>
          </div>
          <div className="h-[620px]" ref={boxRef}>
            {graph.error ? <div className="p-4"><ErrorState error={graph.error} /></div> : graph.loading && !graph.data ? <div className="p-4"><Loading rows={1} /></div> : (
              <ReactFlow nodes={nodes} edges={edges} nodeTypes={nodeTypes} fitView fitViewOptions={{ padding: 0.06 }} nodesDraggable={false} nodesConnectable={false}
                onNodeClick={(_, n) => n.type === "g" && setSelected(n.data)} onPaneClick={() => setSelected(null)} proOptions={{ hideAttribution: true }} minZoom={0.2} colorMode="dark"
                onInit={(inst) => { flowRef.current = inst; [30, 250, 700].forEach((t) => setTimeout(() => inst.fitView({ padding: 0.06 }), t)); }}>
                <Background gap={22} color="#1C1C1C" />
                <Controls showInteractive={false} position="bottom-right" />
              </ReactFlow>
            )}
          </div>
          {graph.data && <DetailOnly><div className="border-t border-line px-4 py-2 text-[11px] text-ink-500">{graph.data.note}</div></DetailOnly>}
        </Card>

        <Card className="h-fit">
          {!selected ? (
            <>
              <CardHead label="Sellers with a clear problem" title="Pick one to trace it" sub="Each has far more of one kind of return than other sellers. The gap is too big to be chance." />
              <div className="space-y-2">
                {s.vendor_findings.map((v: any) => (
                  <button key={v.vendor_id + v.reason} onClick={() => setVendor(v.vendor_id)} className={clsx("w-full rounded border p-3 text-left hover:border-ink-500", vendor === v.vendor_id ? "border-ink-500" : "border-line")}>
                    <div className="flex justify-between text-[13px] font-semibold"><span>{v.vendor_name}</span><span className="num text-bad-700">{pct(v.share)}</span></div>
                    <div className="mt-0.5 text-[12px] text-ink-500">of their returns: “{v.reason_label}” (others: {pct(v.network_share)})<DetailOnly> · z {v.z}</DetailOnly></div>
                    <div className="mt-1.5 text-[12px] text-ink-900">Suggested fix: {v.intervention}</div>
                  </button>
                ))}
              </div>
            </>
          ) : (
            <>
              <CardHead label={COL_LABEL[selected.type]} title={selected.label} />
              {selected.type === "vendor" && (
                <div>
                  <KV k="Returns shown" v={num(selected.data.returns)} />
                  {(selected.data.findings || []).map((f: any) => (
                    <div key={f.reason} className="mt-2 rounded bg-bad-50 p-3 text-[12.5px] leading-relaxed"><b>{reasonLabel(f.reason)}</b>: {pct(f.share)} of this seller's returns, against {pct(f.network_share)} for other sellers. That gap is far too big to be chance.<DetailOnly> (z = {f.z})</DetailOnly></div>
                  ))}
                  {!selected.data.flagged && <div className="mt-2 text-xs text-ink-500">No clear problem for this seller.</div>}
                </div>
              )}
              {selected.type === "sku" && (
                <div>
                  <KV k="Product code" v={<span className="font-mono">{selected.data.sku}</span>} />
                  <KV k="Returns that could be avoided" v={num(selected.data.returns)} />
                  <div className="mt-2 h-40">
                    <ResponsiveContainer>
                      <BarChart data={Object.entries(selected.data.by_reason).map(([k, v]) => ({ k: reasonLabel(k), v }))} layout="vertical" margin={{ left: 20 }}>
                        <XAxis type="number" {...axis} /><YAxis type="category" dataKey="k" {...axis} width={90} />
                        <Tooltip content={<ChartTooltip />} />
                        <Bar dataKey="v" name="Returns" fill="#8C8C8C" barSize={10} />
                      </BarChart>
                    </ResponsiveContainer>
                  </div>
                  {skuDetail.data && (
                    <div className="mt-2 space-y-2 text-[12px]">
                      <div className="flex flex-wrap gap-1">
                        <Badge>Size chart version {skuDetail.data.product.size_chart_version}</Badge>
                        {skuDetail.data.product.pre_dispatch_qc && <Badge tone="ok">Checked before shipping</Badge>}
                        {skuDetail.data.product.exchange_first && <Badge tone="ok">Size swap offered first</Badge>}
                        <Badge>{inr(skuDetail.data.product.price)}</Badge>
                      </div>
                      <div className="label mt-3">In customers' words (names hidden)</div>
                      {skuDetail.data.samples.slice(0, 5).map((x: any) => (
                        <div key={x.id} className="border-l-2 border-line-strong pl-2 text-ink-700">“{x.reason_text}” <span className="text-[10.5px] text-ink-400">· {reasonLabel(x.reason)} · size {x.size}</span></div>
                      ))}
                    </div>
                  )}
                </div>
              )}
              {selected.type === "size" && <div><KV k="Product code" v={selected.data.sku} /><KV k="Size" v={selected.data.size} /><KV k="Returns" v={selected.data.returns} />
                {Object.entries(selected.data.by_reason).map(([k, v]: any) => <KV key={k} k={reasonLabel(k)} v={v} />)}</div>}
              {selected.type === "return" && (
                <div>
                  <div className="rounded bg-canvas p-2.5 text-[12.5px] italic">“{selected.data.text}”</div>
                  <KV k="Read as" v={reasonLabel(selected.data.reason)} />
                  <KV k="How sure" v={pct(selected.data.confidence)} />
                  <KV k="Confirmed at the warehouse" v={selected.data.verified ? "Yes" : "Not yet"} />
                  <KV k="Size" v={selected.data.size} />
                </div>
              )}
              {selected.type === "customer" && <div className="text-[13px] leading-relaxed text-ink-700">Names are hidden. City: {selected.data.cluster}. This view is about fixing products and sellers; it is never used to penalise customers.</div>}
              {selected.type === "defect" && <div><KV k="Returns with this problem" v={num(selected.data.returns)} /><div className="mt-2 text-xs text-ink-500">Lines to the left show which products and sizes cause it. The line to the right shows the suggested fix.</div></div>}
              {selected.type === "intervention" && (
                <div className="space-y-1.5">
                  {(selected.data.recommendations || []).map((r: any, i: number) => (
                    <div key={i} className="flex items-start justify-between gap-2 text-[12.5px]"><span>{r.title}</span><Badge tone={statusTone(r.status)}>{statusText(r.status)}</Badge></div>
                  ))}
                  {!(selected.data.recommendations || []).length && <Empty title="No suggestion of this kind yet" />}
                </div>
              )}
            </>
          )}
        </Card>
      </div>

      <div className="grid grid-cols-1 gap-4 xl:grid-cols-3">
        <Card>
          <CardHead label="Try it" title="Type what a customer might write" sub="See how the system reads a return comment." />
          <textarea value={text} onChange={(e) => setText(e.target.value)} rows={2} className={clsx(inputCls, "h-auto py-1.5")} />
          <Button variant="primary" className="mt-2" onClick={classify}>Read it</Button>
          {cls && (cls.error ? <div className="mt-2 text-xs text-bad-700">{cls.error}</div> : (
            <div className="mt-2 space-y-1">
              {cls.distribution.map((d: any) => (
                <div key={d.reason} className="flex items-center gap-2 text-[11.5px]">
                  <span className="w-36 truncate">{reasonLabel(d.reason)}</span>
                  <div className="h-1.5 flex-1 rounded-full bg-canvas"><div className="h-full rounded-full bg-ink-900" style={{ width: `${d.p * 100}%` }} /></div>
                  <span className="num w-10 text-right">{pct(d.p)}</span>
                </div>
              ))}
              <div className="text-[12px] text-ink-500">Tone: {cls.sentiment < -0.3 ? "unhappy" : cls.sentiment > 0.3 ? "happy" : "neutral"}<DetailOnly> ({cls.sentiment.toFixed(2)})</DetailOnly></div>
            </div>
          ))}
        </Card>
        <Card className="xl:col-span-2">
          <CardHead label="The pattern in numbers" title="What the most-returned products have in common" />
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
            {s.vendor_findings.slice(0, 3).map((v: any) => (
              <div key={v.vendor_id + v.reason} className="border-l border-line-strong pl-4">
                <div className="display-num text-[36px] text-bad-700">{(v.share / Math.max(v.network_share, 0.001)).toFixed(1)}×</div>
                <div className="mt-2 text-[13px] font-medium">{v.vendor_name}</div>
                <div className="text-[12px] text-ink-500">as many “{v.reason_label}” returns as other sellers</div>
              </div>
            ))}
          </div>
        </Card>
      </div>
      <More title="Seller scorecard and model accuracy" sub="Every seller ranked, and how accurate the reason-reading model is">
      <div className="grid grid-cols-1 gap-4 xl:grid-cols-3">
        <Card className="xl:col-span-2">
          <CardHead label="Seller scorecard" title="All sellers, worst first" sub="Score out of 100 from return rate, quality problems, size problems, damaged returns and review tone, last 90 days" />
          <div className="overflow-x-auto">
            <table className="w-full min-w-[680px] text-[12.5px]">
              <thead><tr className="label text-left"><th className="pb-2 font-normal">Seller</th><th className="pb-2 text-right font-normal">Score</th><th className="pb-2 text-right font-normal">Return rate</th><th className="pb-2 text-right font-normal">Quality</th><th className="pb-2 text-right font-normal">Size</th><th className="pb-2 text-right font-normal">Damaged</th><th className="pb-2 text-right font-normal">Review tone</th><th className="pb-2 text-right font-normal">Status</th></tr></thead>
              <tbody>
                {s.vendor_rankings.map((v: any) => (
                  <tr key={v.vendor_id} className="cursor-pointer border-t border-line hover:bg-canvas" onClick={() => { setVendor(v.vendor_id); setSku(""); setSelected(null); window.scrollTo({ top: 500, behavior: "smooth" }); }}>
                    <td className="py-1.5"><div className="font-medium">{v.name}</div><div className="text-[10.5px] text-ink-500">{v.specialty} · {v.city}</div></td>
                    <td className="py-1.5 text-right"><span className={clsx("num rounded px-1.5 py-0.5 font-semibold", v.quality_score < 60 ? "bg-bad-50 text-bad-700" : v.quality_score < 75 ? "bg-warn-50 text-warn-700" : "bg-ok-50 text-ok-700")}>{v.quality_score}</span></td>
                    <td className="num py-1.5 text-right">{pct(v.return_rate, 1)}</td>
                    <td className="num py-1.5 text-right">{pct(v.defect_rate, 1)}</td>
                    <td className="num py-1.5 text-right">{pct(v.size_issue_rate, 1)}</td>
                    <td className="num py-1.5 text-right">{pct(v.grade_c_rate, 1)}</td>
                    <td className="num py-1.5 text-right">{v.review_sentiment.toFixed(2)}</td>
                    <td className="py-1.5 text-right">{v.qc_hold ? <Badge tone="bad">paused for checks</Badge> : <span className="text-ink-300">—</span>}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Card>
        <Card>
          <CardHead label="Reason-reading model" title="How accurate it is" sub={s.model_metrics?.method?.reason} />
          {rc && (
            <div className="grid grid-cols-3 gap-2 text-center">
              <div className="rounded bg-canvas py-2"><div className="num text-[17px] font-semibold">{pct(rc.accuracy, 1)}</div><div className="text-[10.5px] text-ink-500">right</div></div>
              <div className="rounded bg-canvas py-2"><div className="num text-[17px] font-semibold">{rc.macro_f1.toFixed(3)}</div><div className="text-[10.5px] text-ink-500">macro F1</div></div>
              <div className="rounded bg-canvas py-2"><div className="num text-[17px] font-semibold">{num(rc.test_n)}</div><div className="text-[10.5px] text-ink-500">test comments</div></div>
            </div>
          )}
          <div className="mt-1.5 text-[11px] text-ink-500">Sentiment model accuracy {pct(s.model_metrics?.sentiment?.accuracy, 1)} on {num(s.model_metrics?.sentiment?.test_n)} held-out reviews. About 13% of customer texts are vague by design, which caps achievable accuracy.</div>
        </Card>
      </div>
      </More>
    </div>
  );
}