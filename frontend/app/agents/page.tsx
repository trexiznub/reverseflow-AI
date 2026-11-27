"use client";
import "@xyflow/react/dist/style.css";
import { Background, Edge, Handle, Node, Position, ReactFlow } from "@xyflow/react";
import clsx from "clsx";
import { AlertTriangle, ArrowRight, CheckCircle2, CircleDashed, Loader2, RotateCw, User, XCircle } from "lucide-react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { Suspense, useEffect, useMemo, useState } from "react";
import { useToast } from "@/components/providers";
import { Badge, Button, Card, CardHead, DetailOnly, Empty, ErrorState, JsonBlock, Loading, More, PageHeader, Segmented, selectCls, statusText, statusTone } from "@/components/ui";
import { post, useApi } from "@/lib/api";
import { AGENT_JOB, AGENT_LABEL, AGENT_NO, AGENT_SHORT, dayTime, titleCase } from "@/lib/format";

const TRIGGER_LABEL: Record<string, string> = { full_cycle: "Full analysis", return_created: "A new return was booked", pickup_completed: "A pickup was completed", inspection_completed: "An item was inspected" };
const trig = (t: string) => TRIGGER_LABEL[t] || titleCase(t);

const POS: Record<string, { x: number; y: number }> = {
  orchestrator: { x: 330, y: 0 },
  prediction: { x: 0, y: 150 }, intelligence: { x: 220, y: 150 }, prevention: { x: 440, y: 150 },
  logistics: { x: 110, y: 300 }, recovery: { x: 330, y: 300 },
  governance: { x: 600, y: 300 }, human: { x: 600, y: 440 },
};
const GROUP: Record<string, string> = { prediction: "Spots", intelligence: "Spots", prevention: "Spots", logistics: "Plans", recovery: "Plans", governance: "Checks" };

function AgentNode({ data }: any) {
  const s = data.status as string;
  const Icon = s === "completed" ? CheckCircle2 : s === "running" ? Loader2 : s === "failed" ? XCircle : CircleDashed;
  return (
    <div className={clsx("w-[190px] rounded-md border bg-white px-3 py-2.5 text-left transition-shadow",
      data.selected ? "border-paper" : "border-line-strong", s === "running" && "shadow-[0_0_0_3px_rgba(255,255,255,.12)]")}>
      <Handle type="target" position={Position.Top} />
      <div className="flex items-center justify-between">
        <span className="num text-[10.5px] text-ink-400">{data.no}</span>
        <Icon className={clsx("h-3.5 w-3.5", s === "completed" && "text-ok-600", s === "running" && "animate-spin text-blue-500", s === "failed" && "text-bad-600", (!s || s === "queued" || s === "skipped") && "text-ink-300")} />
      </div>
      <div className="mt-0.5 text-[12px] font-semibold leading-tight text-ink-900">{data.label}</div>
      <div className="mt-1 flex items-center justify-between text-[10.5px] text-ink-500">
        <span>{data.group}</span>
        <span className="num">{s ? statusText(s) : "idle"}{data.attempts > 1 ? ` · ${data.attempts} tries` : ""}</span>
      </div>
      <Handle type="source" position={Position.Bottom} />
    </div>
  );
}
function HubNode({ data }: any) {
  return (
    <div className={clsx("w-[220px] rounded px-3 py-2.5 text-black", data.kind === "human" ? "bg-warn-500" : "bg-paper")}>
      <Handle type="target" position={Position.Top} />
      <div className="flex items-center gap-1.5 font-mono text-[10px] uppercase tracking-wider text-black/60">{data.kind === "human" ? <User className="h-3 w-3" /> : null}{data.kind === "human" ? "People approve" : "Coordinator"}</div>
      <div className="mt-0.5 text-[12px] font-semibold">{data.label}</div>
      <div className="text-[10.5px] text-black/70">{data.sub}</div>
      <Handle type="source" position={Position.Bottom} />
    </div>
  );
}
const nodeTypes = { agent: AgentNode, hub: HubNode };

function CommandCentre() {
  const params = useSearchParams();
  const toast = useToast();
  const runs = useApi<any[]>("/orchestrator/runs?limit=25", { poll: 4000 });
  const registry = useApi<any>("/agents");
  const [runId, setRunId] = useState<string | null>(params.get("run"));
  const [sel, setSel] = useState<string>("prediction");
  const [tab, setTab] = useState<"outputs" | "inputs">("outputs");
  const [trigger, setTrigger] = useState("full_cycle");
  const [starting, setStarting] = useState(false);
  useEffect(() => { if (!runId && runs.data?.length) setRunId(runs.data[0].id); }, [runs.data, runId]);
  const runStatus = runs.data?.find((r) => r.id === runId)?.status;
  const live = runStatus === "running" || runStatus === "queued";
  const detail = useApi<any>(runId ? `/orchestrator/runs/${runId}` : null, { poll: live ? 900 : 0, deps: [runId] });

  const d = detail.data;
  const byAgent = Object.fromEntries((d?.agents || []).map((a: any) => [a.agent, a]));
  const { nodes, edges } = useMemo(() => {
    const ns: Node[] = [
      { id: "orchestrator", type: "hub", position: POS.orchestrator, data: { label: d ? trig(d.trigger) : "Idle", sub: d ? `${d.plan.length} agents · ${statusText(d.status)}` : "" } },
      { id: "human", type: "hub", position: POS.human, data: { kind: "human", label: `${d?.human_requests?.length ?? 0} decisions sent to people`, sub: "Operations, quality, warehouse, return checks" } },
    ];
    Object.keys(AGENT_NO).forEach((a) => {
      const r = byAgent[a];
      ns.push({ id: a, type: "agent", position: POS[a], data: { no: AGENT_NO[a], label: AGENT_LABEL[a], group: GROUP[a], status: r?.status || (d ? "not in plan" : ""), duration: r?.duration_ms, attempts: r?.attempts, selected: sel === a } });
    });
    const topics = new Map<string, string[]>();
    (d?.messages || []).forEach((m: any) => {
      const k = `${m.sender}->${m.receiver}`;
      topics.set(k, [...(topics.get(k) || []), m.topic]);
    });
    const es: Edge[] = [];
    Object.keys(AGENT_NO).forEach((a) => es.push({ id: `o-${a}`, source: "orchestrator", target: a, style: { stroke: "#2A2A2A", strokeDasharray: "3 5" } }));
    topics.forEach((t, k) => {
      const [s, r] = k.split("->");
      if (s === "orchestrator") return;
      const focus = s === sel || r === sel;
      es.push({ id: k, source: s, target: r, label: focus ? t.map((x) => x.replace(/_/g, " ")).join(", ") : `${t.length}`, animated: true,
        style: { stroke: focus ? "#F2F2F2" : "#3A3A3A", strokeWidth: focus ? 1.8 : 1 }, zIndex: focus ? 10 : 0,
        labelStyle: { fontSize: 9.5, fill: "#F2F2F2", fontWeight: 600 }, labelBgStyle: { fill: "#151515" }, labelBgPadding: [3, 1] as any });
    });
    es.push({ id: "gov-human", source: "governance", target: "human", animated: true, style: { stroke: "#E3A33B", strokeWidth: 1.6 }, label: "asks a person", labelStyle: { fontSize: 9.5, fill: "#E3A33B" } });
    return { nodes: ns, edges: es };
  }, [d, sel, live]); // eslint-disable-line react-hooks/exhaustive-deps

  const start = async () => {
    setStarting(true);
    try {
      const r = await post("/orchestrator/run", { trigger });
      setRunId(r.run_id);
      runs.reload(true);
      toast("info", `Started: ${trig(trigger)}`);
    } catch (e: any) { toast("err", e.message); } finally { setStarting(false); }
  };

  if (runs.error) return <ErrorState error={runs.error} onRetry={runs.reload} />;
  if (runs.loading || !runs.data) return <Loading />;
  const selAgent = byAgent[sel];
  const reg = registry.data?.agents?.find((a: any) => a.id === sel);

  return (
    <div className="space-y-5">
      <PageHeader eyebrow="How it works" title="Six agents, one plan"
        sub="Six AI agents each do one job and pass what they find to each other. A coordinator runs them in the right order. The last one checks every suggestion against the rules and sends anything important to a person."
        right={
          <div className="flex items-center gap-2">
            <select value={trigger} onChange={(e) => setTrigger(e.target.value)} className={clsx(selectCls, "h-9")}>
              {Object.keys(registry.data?.plans || { full_cycle: 1 }).map((p) => <option key={p} value={p}>{trig(p)}</option>)}
            </select>
            <Button variant="primary" onClick={start} loading={starting}><RotateCw className="h-3.5 w-3.5" />Run it now</Button>
          </div>
        } />

      <div className="grid grid-cols-1 gap-4 xl:grid-cols-[1fr_320px]">
        <Card pad={false}>
          <div className="flex items-center justify-between border-b border-line px-4 py-2.5">
            <div className="flex items-center gap-2">
              <span className="text-[14px] font-semibold">Who passed what to whom</span>
              {d && <Badge tone={statusTone(d.status)} dot>{statusText(d.status)}</Badge>}
              {live && <span className="text-[11.5px] text-ink-500">updating live</span>}
            </div>
            <span className="hidden text-[12px] text-ink-500 sm:inline">Click an agent to see what it did</span>
          </div>
          <div className="h-[540px]">
            <ReactFlow nodes={nodes} edges={edges} nodeTypes={nodeTypes} fitView fitViewOptions={{ padding: 0.12 }} nodesDraggable={false} nodesConnectable={false}
              onNodeClick={(_, n) => AGENT_NO[n.id] && setSel(n.id)} proOptions={{ hideAttribution: true }} minZoom={0.5} maxZoom={1.5} colorMode="dark">
              <Background gap={22} color="#1C1C1C" />
            </ReactFlow>
          </div>
          <div className="flex flex-wrap items-center gap-x-5 gap-y-1 border-t border-line px-4 py-2 text-[11.5px] text-ink-500">
            <span className="flex items-center gap-1.5"><span className="h-px w-5 border-t border-dashed border-ink-400" />coordinator starts each agent</span>
            <span className="flex items-center gap-1.5"><span className="h-[2px] w-5 bg-ink-700" />agent passes findings (number = messages)</span>
            <span className="flex items-center gap-1.5"><span className="h-[2px] w-5 bg-warn-500" />sent to a person to decide</span>
            <span>Click an agent to name its messages.</span>
          </div>
        </Card>
        <Card pad={false} className="flex flex-col">
          <div className="border-b border-line px-4 py-2.5 text-[14px] font-semibold">Recent runs</div>
          <div className="max-h-[540px] flex-1 overflow-y-auto">
            {runs.data.map((r) => (
              <button key={r.id} onClick={() => setRunId(r.id)} className={clsx("block w-full border-b border-line px-4 py-3 text-left hover:bg-canvas", r.id === runId && "bg-canvas")}>
                <div className="flex items-center justify-between">
                  <span className="text-[13px] font-medium">{trig(r.trigger)}</span>
                  <Badge tone={statusTone(r.status)} dot>{statusText(r.status)}</Badge>
                </div>
                <div className="mt-0.5 text-[11.5px] text-ink-500">{dayTime(r.started_at)} · {r.plan.length} agents{r.event?.return_id ? ` · ${r.event.return_id}` : ""}{r.summary?.recommendations ? ` · ${r.summary.recommendations.created} new suggestions` : ""}</div>
              </button>
            ))}
          </div>
        </Card>
      </div>

      {detail.error && <ErrorState error={detail.error} />}
      {d && (
        <div className="grid grid-cols-1 gap-4 xl:grid-cols-3">
          <Card className="xl:col-span-2">
            <CardHead label={`Agent ${AGENT_NO[sel]}`} title={AGENT_LABEL[sel]} sub={AGENT_JOB[sel] || reg?.purpose} />
            <div className="mb-3 flex flex-wrap gap-2 text-[11.5px]">
              <Badge tone={statusTone(selAgent?.status)} dot>{selAgent ? statusText(selAgent.status) : "not needed for this run"}</Badge>
              {selAgent?.attempts > 1 && <Badge tone="warn">needed {selAgent.attempts} tries</Badge>}
              <DetailOnly>
                {selAgent?.duration_ms !== undefined && selAgent?.duration_ms !== null && <Badge>{selAgent.duration_ms} ms</Badge>}
                {reg?.models?.map((mdl: string) => <Badge key={mdl}>{mdl}</Badge>)}
              </DetailOnly>
            </div>
            {selAgent?.error && (
              <div className={clsx("mb-3 flex items-start gap-2 rounded border px-3 py-2 text-[12px]", selAgent.status === "failed" ? "border-[#4A2620] bg-bad-50 text-bad-700" : "border-[#4A3A17] bg-warn-50 text-warn-700")}>
                <AlertTriangle className="mt-0.5 h-3.5 w-3.5" />{selAgent.error}
              </div>
            )}
            {!selAgent && <Empty title="This agent wasn't needed for this run" sub={`Agents used: ${d.plan.map((x: string) => AGENT_SHORT[x] || x).join(", ")}`} />}
            {selAgent && (
              <div className="space-y-3">
                {d.messages.filter((m: any) => m.sender === sel).length > 0 && (
                  <div>
                    <div className="label mb-2">What it passed on</div>
                    <ul className="space-y-1.5 text-[13px]">
                      {d.messages.filter((m: any) => m.sender === sel).map((m: any, i: number) => (
                        <li key={i} className="flex gap-2"><ArrowRight className="mt-0.5 h-3.5 w-3.5 shrink-0 text-ink-400" /><span><span className="capitalize">{m.topic.replace(/_/g, " ")}</span> <span className="text-ink-500">to the {AGENT_LABEL[m.receiver] || m.receiver}</span></span></li>
                      ))}
                    </ul>
                  </div>
                )}
                {reg && <div className="text-[12.5px] text-ink-500">{reg.depends_on.length ? <>Waits for: {reg.depends_on.map((x: string) => AGENT_SHORT[x]).join(", ")}</> : "Runs first; doesn't wait for other agents."}</div>}
                <More title="Raw inputs and outputs">
                  <Segmented value={tab} onChange={setTab} items={[{ id: "outputs", label: "Outputs" }, { id: "inputs", label: "Inputs" }]} />
                  <JsonBlock value={tab === "outputs" ? selAgent.outputs : selAgent.inputs} max={420} />
                  {reg && <div className="text-[11.5px] text-ink-500">Data used: {reg.inputs.join(" · ")}</div>}
                </More>
              </div>
            )}
          </Card>
          <div className="space-y-4">
            <Card>
              <CardHead label="In order" title="Who told whom what" sub="Every message the agents passed in this run, first to last." />
              <ol className="max-h-64 space-y-1.5 overflow-y-auto">
                {(d.messages || []).filter((m: any) => m.sender !== "orchestrator" && m.receiver !== "orchestrator").map((m: any, i: number) => (
                  <li key={i} className="flex items-baseline gap-2 text-[12px]">
                    <span className="num w-5 shrink-0 text-right text-ink-400">{i + 1}</span>
                    <span><b className="font-medium text-ink-900">{AGENT_SHORT[m.sender] || m.sender}</b> → <b className="font-medium text-ink-900">{AGENT_SHORT[m.receiver] || m.receiver}</b>: <span className="text-ink-500">{String(m.topic).replace(/_/g, " ")}</span></span>
                  </li>
                ))}
              </ol>
            </Card>
            <Card>
              <CardHead label="Disagreements" title={d.conflicts.length ? `${d.conflicts.length} times two agents disagreed` : "No disagreements"} sub="When two suggestions clash, the coordinator settles it, and the hard ones go to a person." />
              {d.conflicts.length === 0 ? <Empty title="Everyone agreed this time" /> : (
                <div className="space-y-3">
                  {d.conflicts.map((c: any, i: number) => (
                    <div key={i} className="overflow-hidden rounded-lg border border-[#4A3A17]">
                      <div className="bg-warn-50 px-3 py-2">
                        <div className="label text-warn-700">Disagreement {i + 1} · {c.agents.map((a: string) => AGENT_SHORT[a]).join(" vs ")}</div>
                        <div className="mt-1 text-[13px] font-semibold leading-snug">{c.title || c.description}</div>
                      </div>
                      <div className="space-y-2 px-3 py-2.5 text-[12px] leading-snug">
                        {c.a_wants && <div className="flex gap-2"><span className="label w-5 shrink-0 text-ink-400">A</span><span>{c.a_wants}</span></div>}
                        {c.b_wants && <div className="flex gap-2"><span className="label w-5 shrink-0 text-ink-400">B</span><span>{c.b_wants}</span></div>}
                        {c.why && <div className="flex gap-2"><span className="label w-5 shrink-0 text-ink-400">!</span><span className="text-ink-700">{c.why}</span></div>}
                        <div className="rounded-md bg-canvas px-2.5 py-2"><span className="font-semibold text-ink-900">Settled: </span><span className="text-ink-700">{c.resolution}</span></div>
                        {c.decided_by && <div className="text-[11.5px] text-ink-500">Final say: {c.decided_by}</div>}
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </Card>
            <Card>
              <CardHead label="For people" title={`${d.human_requests.length} decisions sent to people`} right={<Link href="/governance" className="text-xs font-medium text-blue-600">Decide</Link>} />
              <div className="max-h-56 space-y-1.5 overflow-y-auto">
                {d.human_requests.slice(0, 20).map((h: any) => (
                  <div key={h.id} className="flex items-center justify-between gap-2 text-[12px]">
                    <span className="truncate">{h.title}</span><Badge tone={statusTone(h.status)}>{statusText(h.status)}</Badge>
                  </div>
                ))}
                {!d.human_requests.length && <div className="text-xs text-ink-500">Nothing new for people from this run.</div>}
              </div>
            </Card>
          </div>
        </div>
      )}

      {d && (
        <More title="Every message between agents" sub={`${d.messages.length} messages, with the data each one carried`}>
        <Card>
          <CardHead label="Agent-to-agent communication" title={`${d.messages.length} messages`} sub="Recorded on the shared state as each agent completes" />
          <div className="overflow-x-auto">
            <table className="w-full min-w-[640px] text-[12px]">
              <thead><tr className="label text-left"><th className="pb-2 font-semibold">Time</th><th className="pb-2 font-semibold">From</th><th className="pb-2 font-semibold" /><th className="pb-2 font-semibold">To</th><th className="pb-2 font-semibold">Topic</th><th className="pb-2 font-semibold">Payload</th></tr></thead>
              <tbody>
                {d.messages.map((m: any, i: number) => (
                  <tr key={i} className="border-t border-line align-top">
                    <td className="num py-1.5 pr-3 text-ink-500">{new Date(m.ts).toLocaleTimeString("en-GB")}</td>
                    <td className="py-1.5 font-medium">{AGENT_SHORT[m.sender]}</td>
                    <td className="py-1.5 px-1 text-ink-300"><ArrowRight className="h-3 w-3" /></td>
                    <td className="py-1.5 font-medium">{AGENT_SHORT[m.receiver]}</td>
                    <td className="py-1.5"><Badge>{m.topic.replace(/_/g, " ")}</Badge></td>
                    <td className="max-w-[520px] truncate py-1.5 font-mono text-[11px] text-ink-500">{JSON.stringify(m.payload)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Card>
        </More>
      )}
    </div>
  );
}

export default function Page() {
  return <Suspense fallback={<Loading />}><CommandCentre /></Suspense>;
}
