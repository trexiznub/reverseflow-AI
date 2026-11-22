"use client";
import clsx from "clsx";
import { Database, RefreshCw } from "lucide-react";
import { useEffect, useState } from "react";
import { useSession, useToast } from "@/components/providers";
import { Badge, Button, Card, CardHead, ErrorState, Field, inputCls, JsonBlock, KV, Loading, More, PageHeader } from "@/components/ui";
import { post, put, useApi } from "@/lib/api";
import { inr, ROLE_LABEL } from "@/lib/format";

const STATUS_TONE: Record<string, any> = { implemented: "ok", "implemented locally": "ok", "implemented (offline template)": "ok", proposed: "neutral" };

export default function Settings() {
  const { meta, refreshMeta } = useSession();
  const toast = useToast();
  const s = useApi<any>("/settings");
  const integ = useApi<any[]>("/integrations");
  const [resale, setResale] = useState<any>(null);
  const [gov, setGov] = useState<any>(null);
  const [fault, setFault] = useState<any>({ agent: "", failures: 1 });
  const [llm, setLlm] = useState("template");
  const [busy, setBusy] = useState<string | null>(null);
  const canEdit = meta?.user?.role === "ops_manager";
  useEffect(() => {
    if (s.data) {
      setResale(s.data.resale); setGov(s.data.governance); setLlm(s.data.llm?.provider || "template");
      setFault({ agent: s.data.fault_injection?.agent || "", failures: s.data.fault_injection?.failures || 1 });
    }
  }, [s.data]);
  const save = async (key: string, value: any) => {
    setBusy(key);
    try { await put(`/settings/${key}`, { value }); toast("ok", "Saved. The change is recorded in the history."); s.reload(true); }
    catch (e: any) { toast("err", e.message); } finally { setBusy(null); }
  };
  const reset = async () => {
    if (!confirm("Reset the demo? This rebuilds the demo data and clears every decision and test return. It only takes a few seconds.")) return;
    setBusy("reset");
    try { const r = await post("/admin/reset"); toast("info", r.detail); setTimeout(refreshMeta, 1500); }
    catch (e: any) { toast("err", e.message); } finally { setBusy(null); }
  };
  if (s.error) return <ErrorState error={s.error} onRetry={s.reload} />;
  if (s.loading || !s.data || !resale) return <Loading />;
  const numIn = (v: number, on: (x: number) => void, step = 0.01) => <input type="number" step={step} value={v} disabled={!canEdit} onChange={(e) => on(Number(e.target.value))} className={inputCls} />;
  return (
    <div className="space-y-5">
      <PageHeader eyebrow="Settings" title="Settings"
        sub={canEdit ? "Change the assumptions behind the numbers, approval limits, or reset the demo. Every change is recorded." : "Only the Operations Manager can change these. You can still look."} />
      <div className="grid grid-cols-1 gap-4 xl:grid-cols-3">
        <Card>
          <CardHead label="You" title={meta?.user?.name} sub={meta?.user?.title} />
          <KV k="Role" v={ROLE_LABEL[meta?.user?.role]} />
          <KV k="Can see" v={meta?.user?.scope_id || "Everything"} />
          <KV k="Can approve up to" v={inr(meta?.user?.approval_limit)} />
          <KV k="Demo date" v={meta?.scenario_date} />
          <div className="mt-3 rounded bg-canvas p-3 text-[12px] leading-relaxed text-ink-500">{meta?.disclaimer}</div>
        </Card>
        <Card className="xl:col-span-2">
          <CardHead label="Resale" title="What returned items are worth" sub="Used to estimate resale value and which items to check first." right={canEdit && <Button size="sm" variant="primary" loading={busy === "resale"} onClick={() => save("resale", resale)}>Save</Button>} />
          <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
            <Field label="Storage cost per item per day (₹)">{numIn(resale.storage_cost_per_day, (v) => setResale({ ...resale, storage_cost_per_day: v }), 0.5)}</Field>
            <Field label="Repair cost (share of price, 0–1)">{numIn(resale.refurb_cost_pct, (v) => setResale({ ...resale, refurb_cost_pct: v }))}</Field>
            <Field label="Inspection cost per item (₹)">{numIn(resale.inspection_cost, (v) => setResale({ ...resale, inspection_cost: v }), 1)}</Field>
            <Field label="Lowest sale price (share of price)">{numIn(resale.markdown_floor, (v) => setResale({ ...resale, markdown_floor: v }))}</Field>
            {Object.keys(resale.grade_factor).map((g) => (
              <Field key={g} label={`${({ A: "Like new", B: "Needs repair", C: "Damaged" } as any)[g] || g}: share of price`}>{numIn(resale.grade_factor[g], (v) => setResale({ ...resale, grade_factor: { ...resale.grade_factor, [g]: v } }))}</Field>
            ))}
          </div>
        </Card>
      </div>
      <div className="grid grid-cols-1 gap-4 xl:grid-cols-3">
        <Card>
          <CardHead label="Approvals" title="What can go ahead without a person" right={canEdit && <Button size="sm" variant="primary" loading={busy === "governance"} onClick={() => save("governance", gov)}>Save</Button>} />
          <div className="space-y-3">
            <Field label="Logistics spending limit (₹)" hint="Pickup and routing actions that cost this much or less go ahead on their own, unless two agents disagree. Anything else waits for a person.">{numIn(gov.auto_approve_logistics_limit_inr, (v) => setGov({ ...gov, auto_approve_logistics_limit_inr: v }), 1000)}</Field>
          </div>
        </Card>
        <Card className="xl:col-span-2">
          <CardHead label="Demo" title="Start the demo again" sub="Puts every number, decision and test return back to how it was at the start, so you can run the demo again." />
          {canEdit ? <Button variant="danger" onClick={reset} loading={busy === "reset"}><RefreshCw className="h-3.5 w-3.5" />Reset the demo</Button> : <div className="text-[12.5px] text-ink-500">Switch to Rahul Mehta (Operations Manager) to reset.</div>}
        </Card>
      </div>

      <More title="Technical settings" sub="Explanation provider, failure testing, SAP integration status and raw data">
      <div className="grid grid-cols-1 gap-4 xl:grid-cols-2">
        <Card>
          <CardHead label="Explanations" title="LLM provider" right={canEdit && <Button size="sm" variant="primary" loading={busy === "llm"} onClick={() => save("llm", { provider: llm })}>Save</Button>} />
          <div className="space-y-2">
            {s.data.llm_providers.map((p: any) => (
              <label key={p.id} className={clsx("flex items-start gap-2 rounded border p-2.5", llm === p.id ? "border-ink-500 bg-canvas" : "border-line", (!p.configured || !canEdit) && "opacity-60")}>
                <input type="radio" disabled={!p.configured || !canEdit} checked={llm === p.id} onChange={() => setLlm(p.id)} className="mt-0.5" />
                <span className="text-[12.5px]"><span className="font-medium">{p.label}</span><br />
                  <span className="text-[11px] text-ink-500">{p.configured ? "Configured" : p.implemented ? "Set LLM_BASE_URL and LLM_API_KEY in backend/.env" : "Proposed integration, not connected"}</span></span>
              </label>
            ))}
          </div>
          <div className="mt-2 text-[11px] text-ink-500">Decisions never depend on an LLM. The provider only phrases explanations; failures fall back to the evidence template.</div>
        </Card>
        <Card>
          <CardHead label="Resilience test" title="Fault injection" right={canEdit && <Button size="sm" variant="primary" loading={busy === "fault_injection"} onClick={() => save("fault_injection", { agent: fault.agent || null, failures: fault.agent ? fault.failures : 0 })}>Arm</Button>} />
          <div className="space-y-3">
            <Field label="Agent to fail transiently">
              <select className={inputCls} value={fault.agent} disabled={!canEdit} onChange={(e) => setFault({ ...fault, agent: e.target.value })}>
                <option value="">None</option>{["prediction", "intelligence", "prevention", "logistics", "recovery", "governance"].map((a) => <option key={a}>{a}</option>)}
              </select>
            </Field>
            <Field label="Failures before recovery" hint="The orchestrator retries up to 3 attempts; 3+ failures mark the agent failed and skip dependants">{numIn(fault.failures, (v) => setFault({ ...fault, failures: v }), 1)}</Field>
            <div className="text-[11px] text-ink-500">Armed: {s.data.fault_injection?.agent ? `${s.data.fault_injection.agent} × ${s.data.fault_injection.failures}` : "nothing"}</div>
          </div>
        </Card>
      </div>
      <Card>
        <CardHead label="SAP ecosystem" title="Integration status" sub="Implemented capabilities are distinguished from proposed pathways. Nothing here is presented as connected unless it is." />
        {integ.error ? <ErrorState error={integ.error} /> : !integ.data ? <Loading rows={1} /> : (
          <div className="overflow-x-auto">
            <table className="w-full min-w-[820px] text-[12.5px]">
              <thead><tr className="label text-left"><th className="pb-2 font-semibold">Capability</th><th className="pb-2 font-semibold">Status</th><th className="pb-2 font-semibold">What exists in this prototype</th><th className="pb-2 font-semibold">SAP target</th><th className="pb-2 font-semibold">Pathway</th></tr></thead>
              <tbody>
                {integ.data.map((i) => (
                  <tr key={i.system} className="border-t border-line align-top">
                    <td className="py-2 font-medium">{i.system}</td>
                    <td className="py-2"><Badge tone={STATUS_TONE[i.status] || "neutral"} dot>{i.status}</Badge></td>
                    <td className="max-w-[280px] py-2 text-ink-700">{i.detail}</td>
                    <td className="py-2 font-medium">{i.sap_target}</td>
                    <td className="max-w-[280px] py-2 text-ink-500">{i.pathway}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>
      <div className="grid grid-cols-1 gap-4 xl:grid-cols-2">
        <Card>
          <CardHead label="Shared state" title="Approved routing and capacity changes" sub="Written when someone approves a suggestion; read by agents, the partner app and the planner" />
          <JsonBlock value={{ routing_overrides: s.data.routing_overrides || {}, capacity_overrides: s.data.capacity_overrides || {} }} max={220} />
        </Card>
        <Card>
          <CardHead label="Demo data" title="Synthetic dataset" sub="Deterministic seed; regenerating restores the exact starting state for a repeat demonstration." />
          <div className="flex items-start gap-3">
            <Database className="mt-0.5 h-5 w-5 text-ink-400" />
            <div className="flex-1 text-[12.5px] text-ink-700">Network scale factors (marketplace returns represented by one sample record): <span className="font-mono text-[11.5px]">{JSON.stringify(s.data.scenario?.network_scale)}</span></div>
          </div>
          
        </Card>
      </div>
      </More>
    </div>
  );
}
