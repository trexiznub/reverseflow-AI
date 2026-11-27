"use client";
import clsx from "clsx";
import { ArrowRight, Check, CornerUpRight, ShieldAlert, X } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { useSession, useToast } from "@/components/providers";
import { Badge, Button, Card, CardHead, DetailOnly, Drawer, Empty, ErrorState, Field, Hint, inputCls, JsonBlock, KV, Loading, More, PageHeader, selectCls, statusText, statusTone, Tabs } from "@/components/ui";
import { post, useApi } from "@/lib/api";
import { AGENT_LABEL, dayTime, inr, KIND_LABEL, num, pct, ROLE_LABEL, titleCase } from "@/lib/format";

const QUICK_REASONS: Record<string, string[]> = {
  approve: ["The evidence is clear", "Worth the cost for the festive peak", "Agreed with the seller"],
  reject: ["Cost is too high right now", "Need more evidence first", "Already handled another way"],
  escalate: ["Needs a senior decision", "Affects another team"],
};

const confidenceWords = (c?: number) => (c === undefined || c === null ? "—" : c >= 0.85 ? "Very sure" : c >= 0.7 ? "Fairly sure" : "Not very sure");

function Evidence({ r }: { r: any }) {
  const e = r.evidence || {};
  if (r.kind === "integrity_inspection" && e.case) {
    const c = e.case;
    return (
      <div className="space-y-4">
        <div className="rounded border border-[#4A3A17] bg-warn-50 p-3.5 text-[13px] leading-relaxed text-warn-700"><b>Something doesn't match, but that isn't proof of wrongdoing.</b> {e.customer_impact}</div>
        <div>
          <div className="label mb-2">What doesn't match</div>
          <ul className="space-y-1.5 text-[13.5px]">{c.evidence.map((x: string) => <li key={x} className="flex gap-2"><span className="text-ink-400">—</span>{x}</li>)}</ul>
          {!c.evidence.length && <div className="text-[13px] text-ink-500">No physical mismatch. The return pattern itself is unusual.</div>}
        </div>
        <More title="How unusual is it?" sub="Breakdown of the score">
          {Object.entries(c.components).map(([k, v]: any) => (
            <div key={k} className="flex items-center gap-2 text-[12px]">
              <span className="w-40 text-ink-700">{titleCase(k)}</span>
              <div className="h-1.5 flex-1 rounded-full bg-canvas"><div className="h-full rounded-full bg-warn-500" style={{ width: `${(v / 0.4) * 100}%` }} /></div>
              <span className="num w-10 text-right">{v.toFixed(2)}</span>
            </div>
          ))}
        </More>
      </div>
    );
  }
  const f = e.finding;
  return (
    <div className="space-y-3">
      {f && <div className="rounded bg-canvas p-3.5 text-[13.5px] leading-relaxed"><b>{f.vendor_name}</b>: {num(f.returns)} of {num(f.vendor_returns)} returns are for {f.reason_label.toLowerCase()}. That's {pct(f.share)}, compared with {pct(f.network_share)} for other sellers.
        {f.top_skus && <div className="mt-1.5 text-[12.5px] text-ink-500">Mostly these products: {f.top_skus.map((s: any) => `${s.sku} (${s.returns})`).join(", ")}</div>}</div>}
      {e.gap && <div className="rounded bg-canvas p-3.5 text-[13.5px] leading-relaxed">{e.gap.city} needs to collect about <span className="num">{num(e.gap.planning_volume)}</span> returns a day at the peak, but its vans carry <span className="num">{num(e.gap.pickup_capacity)}</span>. It is over capacity on {e.gap.days_over_pickup_capacity} of the next 7 days.</div>}
      {e.allocation && <div className="rounded bg-canvas p-3.5 text-[13.5px] leading-relaxed">Send <span className="num">{num(e.allocation.units)}</span> returns a day ({pct(e.allocation.share)}) on a {e.allocation.km} km trip at ₹{e.allocation.unit_cost} each, for {e.days} days.</div>}
      {e.skus && <div className="text-[13px] text-ink-700">Products: <span className="font-mono text-[12px]">{e.skus.join(", ")}</span></div>}
      {e.avoidable_returns_per_month !== undefined && <KV k="Returns this could prevent each month" v={num(e.avoidable_returns_per_month)} />}
      <More title="Raw data"><JsonBlock value={e} max={260} /></More>
    </div>
  );
}

export default function Governance() {
  const { meta } = useSession();
  const toast = useToast();
  const [tab, setTab] = useState<"queue" | "integrity" | "decided" | "audit" | "policy">("queue");
  const [open, setOpen] = useState<any>(null);
  const [openId, setOpenId] = useState<string | null>(null);
  const [reason, setReason] = useState("");
  const [busy, setBusy] = useState<string | null>(null);
  const [kindFilter, setKindFilter] = useState("");
  const ap = useApi<any>("/approvals");
  const integ = useApi<any>(tab === "integrity" ? "/integrity/cases" : null, { deps: [tab] });
  const audit = useApi<any[]>(tab === "audit" ? "/audit?limit=200" : null, { deps: [tab] });
  const pol = useApi<any>(tab === "policy" ? "/governance/policy" : null, { deps: [tab] });

  // Deep links from the Today page: ?open=<id> or ?tab=integrity
  useEffect(() => {
    const q = new URLSearchParams(window.location.search);
    if (q.get("open")) setOpenId(q.get("open"));
    const t = q.get("tab");
    if (t && ["queue", "integrity", "decided", "audit", "policy"].includes(t)) setTab(t as any);
  }, []);
  useEffect(() => {
    if (openId && ap.data) {
      const r = ap.data.items.find((i: any) => i.id === openId);
      if (r) { setOpen(r); setReason(""); }
      setOpenId(null);
    }
  }, [openId, ap.data]);

  const items = ap.data?.items || [];
  const pending = useMemo(() => items.filter((i: any) => ["pending", "escalated"].includes(i.status) && (!kindFilter || i.kind === kindFilter))
    .sort((a: any, b: any) => Number(b.can_decide) - Number(a.can_decide) || (b.priority === "high" ? 1 : 0) - (a.priority === "high" ? 1 : 0)), [items, kindFilter]);
  const mine = pending.filter((i: any) => i.can_decide).length;
  const decided = items.filter((i: any) => ["approved", "rejected"].includes(i.status));
  const kinds = Array.from(new Set(items.map((i: any) => i.kind))) as string[];

  const decide = async (r: any, action: string) => {
    setBusy(action);
    try {
      const res = await post(`/approvals/${r.id}/decision`, { action, reason });
      toast("ok", `${action === "approve" ? "Approved" : action === "reject" ? "Declined" : "Sent to a senior approver"}: ${r.title}`);
      void res;
      setOpen(null);
      setReason("");
      ap.reload(true);
    } catch (e: any) { toast("err", e.message); } finally { setBusy(null); }
  };

  if (ap.error) return <ErrorState error={ap.error} onRetry={ap.reload} />;
  if (ap.loading || !ap.data) return <Loading />;
  const c = ap.data.counts;

  return (
    <div className="space-y-8">
      <PageHeader eyebrow={`Decisions · ${meta?.user?.name || ""}`} title={mine ? `${mine} waiting for you` : "You're all caught up"}
        sub="The system suggests actions. Nothing that costs money or affects a seller or customer happens until a person approves it. Customers are never refused, and sellers are never penalised, automatically."
        right={<div className="text-right text-[12.5px] text-ink-500">You can approve up to<div className="display-num mt-1 text-[28px] text-ink-900">{inr(meta?.user?.approval_limit, true)}</div></div>} />

      <div className="grid grid-cols-2 border-y border-line md:grid-cols-4">
        {[["Waiting for a person", (c.pending || 0) + (c.escalated || 0), "warn", c.escalated ? `${c.escalated} escalated to the Operations Manager` : "Nothing happens until someone decides"],
          ["Approved by a person", (c.approved_by_person || 0), "ok", "A named person approved, with a reason"],
          ["Pre-authorised", (c.pre_authorised || 0), "", "Within the policy spending limit. No person approved these"],
          ["Declined", (c.rejected || 0), "", "Turned down by a person, with a reason"]].map(([l, v, t, sub], i) => (
          <div key={l as string} className={clsx("px-1 py-5 sm:px-5", i > 0 && "md:border-l border-line", i % 2 === 1 && "border-l", i >= 2 && "border-t md:border-t-0")}>
            <div className={clsx("display-num text-[40px]", t === "warn" && "text-warn-700", t === "bad" && "text-bad-700", t === "ok" && "text-ok-700")}>{num(v as number)}</div>
            <div className="label mt-3">{l}</div>
            <div className="mt-1 text-[11.5px] leading-snug text-ink-500">{sub}</div>
          </div>
        ))}
      </div>

      <Tabs value={tab} onChange={setTab} items={[
        { id: "queue", label: "To decide", count: (c.pending || 0) + (c.escalated || 0) }, { id: "integrity", label: "Returns to double-check" },
        { id: "decided", label: "Already decided", count: decided.length }, { id: "audit", label: "History" }, { id: "policy", label: "Who decides what" },
      ]} />

      {tab === "queue" && (
        <div>
          <div className="mb-3 flex flex-wrap items-center gap-3">
            <select value={kindFilter} onChange={(e) => setKindFilter(e.target.value)} className={selectCls}>
              <option value="">All kinds of action</option>{kinds.map((k) => <option key={k} value={k}>{KIND_LABEL[k] || k}</option>)}
            </select>
            <span className="text-[12.5px] text-ink-500">Yours are listed first. Click one to see why it was suggested.</span>
          </div>
          {pending.length === 0 ? <Empty title="Nothing to decide" sub="New suggestions appear here after the next analysis." /> : (
            <div className="border-t border-line">
              {pending.map((r: any) => (
                <button key={r.id} onClick={() => { setOpen(r); setReason(""); }} className="group grid w-full grid-cols-[1fr_auto] items-center gap-4 border-b border-line py-4 text-left md:grid-cols-[1fr_200px_auto]">
                  <div className="min-w-0">
                    <div className="flex flex-wrap items-center gap-2">
                      <span className="label">{KIND_LABEL[r.kind] || r.kind}</span>
                      {r.priority === "high" && <Badge tone="bad">urgent</Badge>}
                      {r.status === "escalated" && <Badge tone="bad">sent to senior</Badge>}
                      {r.can_decide ? <Badge tone="navy">yours</Badge> : <span className="text-[11.5px] text-ink-400">for {ROLE_LABEL[r.approver_role]}</span>}
                    </div>
                    <div className="mt-1.5 text-[15px] font-semibold leading-snug group-hover:underline group-hover:decoration-ink-500 group-hover:underline-offset-4">{r.title}</div>
                  </div>
                  <div className="hidden text-[12.5px] text-ink-500 md:block">
                    <div>Benefit <span className="num text-ink-900">{r.impact_inr ? inr(r.impact_inr, true) : "—"}</span> · Cost <span className="num text-ink-900">{r.cost_inr ? inr(r.cost_inr, true) : "₹0"}</span></div>
                    {(r.impact_inr || r.cost_inr) ? <div>Net <span className={clsx("num font-medium", r.net_inr >= 0 ? "text-ok-700" : "text-bad-700")}>{r.net_inr >= 0 ? "+" : "−"}{inr(Math.abs(r.net_inr), true)}</span></div> : <div>No money involved</div>}
                  </div>
                  <ArrowRight className="h-4 w-4 text-ink-400 group-hover:text-ink-900" />
                </button>
              ))}
            </div>
          )}
        </div>
      )}

      {tab === "integrity" && (integ.error ? <ErrorState error={integ.error} /> : !integ.data ? <Loading rows={1} /> : (
        <div className="space-y-4">
          <div className="flex items-start gap-3 rounded border border-[#4A3A17] bg-warn-50 px-4 py-3 text-[13px] leading-relaxed text-warn-700">
            <ShieldAlert className="mt-0.5 h-4 w-4 shrink-0" />
            <span>These returns had something that didn't match, such as a different serial number or a missing tag. The only thing that happens is a closer look at the warehouse. Refunds are not blocked and customers' names are hidden from reviewers.</span>
          </div>
          <div className="grid grid-cols-1 gap-3 md:grid-cols-2 xl:grid-cols-3">
            {integ.data.cases.map((x: any) => (
              <Card key={x.return_id}>
                <div className="flex items-start justify-between gap-2">
                  <div><div className="font-mono text-[12.5px] font-medium">{x.return_id}</div><div className="text-[11.5px] text-ink-500">{x.cluster_id} · {x.status.replace("_", " ")}</div></div>
                  {x.recommendation ? <button onClick={() => setOpen(items.find((i: any) => i.id === x.recommendation.id) || x.recommendation)}><Badge tone={statusTone(x.recommendation.status)}>{statusText(x.recommendation.status)}</Badge></button> : null}
                </div>
                <ul className="mt-3 space-y-1 text-[13px]">{x.evidence.map((e: string) => <li key={e} className="flex gap-2"><span className="text-ink-400">—</span>{e}</li>)}</ul>
                {!x.evidence.length && <div className="mt-3 text-[13px] text-ink-500">Unusual return pattern only</div>}
                <div className="mt-3 border-t border-line pt-3 text-[12px] text-ink-500">Next step: {x.recommended_inspection}</div>
                <DetailOnly><div className="num mt-2 text-[11px] text-ink-400">score {x.score.toFixed(2)}</div></DetailOnly>
              </Card>
            ))}
          </div>
        </div>
      ))}

      {tab === "decided" && (
        decided.length === 0 ? <Empty title="No decisions yet" /> : (
          <div className="border-t border-line">
            {decided.map((r: any) => {
              const last = r.decisions[r.decisions.length - 1];
              return (
                <button key={r.id} onClick={() => setOpen(r)} className="grid w-full grid-cols-[1fr_auto] gap-4 border-b border-line py-4 text-left hover:bg-canvas md:grid-cols-[1fr_1fr_auto]">
                  <div><div className="label">{KIND_LABEL[r.kind]}</div><div className="mt-1 text-[14px] font-medium">{r.title}</div></div>
                  <div className="hidden text-[12.5px] text-ink-500 md:block">“{last?.reason}”<div className="mt-0.5 text-[11.5px] text-ink-400">{last?.user} · {dayTime(last?.ts)}</div></div>
                  <div className="flex flex-col items-end gap-1"><Badge tone={r.status === "approved" && !r.requires_approval ? "warn" : statusTone(r.status)}>{r.status === "approved" && !r.requires_approval ? "pre-authorised" : statusText(r.status)}</Badge>{r.applied && <span className="text-[11px] text-ok-700">applied in ReverseFlow</span>}</div>
                </button>
              );
            })}
          </div>
        )
      )}

      {tab === "audit" && (audit.error ? <ErrorState error={audit.error} /> : !audit.data ? <Loading rows={1} /> : (
        <Card pad={false}>
          <div className="border-b border-line px-5 py-3 text-[12.5px] text-ink-500">Every action by a person or an agent is recorded here and can't be edited.</div>
          <div className="max-h-[620px] overflow-auto">
            <table className="w-full min-w-[760px] text-[12.5px]">
              <thead className="sticky top-0 bg-white"><tr className="label border-b border-line text-left"><th className="px-5 py-2.5 font-normal">When</th><th className="py-2.5 font-normal">Who</th><th className="py-2.5 font-normal">What</th><th className="py-2.5 pr-5 font-normal">On</th></tr></thead>
              <tbody>
                {audit.data.map((a) => (
                  <tr key={a.id} className="border-b border-line align-top">
                    <td className="num whitespace-nowrap px-5 py-2 text-ink-500">{dayTime(a.ts)}</td>
                    <td className="py-2"><span className="font-medium">{a.actor}</span> <span className="text-[11px] text-ink-400">{a.actor_type === "agent" ? "agent" : a.actor_type === "user" ? "" : a.actor_type}</span></td>
                    <td className="py-2">{titleCase(a.action)}</td>
                    <td className="py-2 pr-5 font-mono text-[11.5px] text-ink-500" title={JSON.stringify(a.detail)}>{a.entity_id}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Card>
      ))}

      {tab === "policy" && (pol.error ? <ErrorState error={pol.error} /> : !pol.data ? <Loading rows={1} /> : (
        <div className="grid grid-cols-1 gap-4 xl:grid-cols-3">
          <Card className="xl:col-span-2">
            <CardHead title="Who approves each kind of action" sub={`Small logistics actions up to ${inr(pol.data.auto_approve_limit_inr)} are pre-authorised by policy, unless two agents disagree. Everything else needs a person from the team that owns it; only escalations go to the Operations Manager.`} />
            <table className="w-full text-[13px]">
              <thead><tr className="label text-left"><th className="pb-2 font-normal">Action</th><th className="pb-2 font-normal">Needs a person?</th><th className="pb-2 font-normal">Who</th></tr></thead>
              <tbody>{pol.data.rules.map((r: any) => (
                <tr key={r.kind} className="border-t border-line"><td className="py-2 font-medium">{KIND_LABEL[r.kind] || r.kind}</td>
                  <td className="py-2"><Badge tone={r.rule === "always" ? "warn" : "neutral"}>{r.rule === "always" ? "always" : "only above the limit"}</Badge></td><td className="py-2 text-ink-700">{ROLE_LABEL[r.approver_role]}</td></tr>
              ))}</tbody>
            </table>
          </Card>
          <div className="space-y-4">
            <Card>
              <CardHead title="Never done automatically" />
              <ul className="space-y-2 text-[13px]">{pol.data.forbidden.map((f: string) => <li key={f} className="flex items-center gap-2"><X className="h-3.5 w-3.5 text-bad-600" />{titleCase(f)}</li>)}</ul>
            </Card>
            <Card>
              <CardHead title="Approval limits" />
              {pol.data.approvers.map((u: any) => <KV key={u.name} k={<>{u.name}<div className="text-[11px]">{ROLE_LABEL[u.role]}</div></>} v={inr(u.approval_limit, true)} />)}
            </Card>
          </div>
        </div>
      ))}

      <Drawer open={!!open} onClose={() => setOpen(null)} width={620}
        title={open && <div><div className="label mb-1">{KIND_LABEL[open.kind] || open.kind}</div><div className="text-[17px] leading-snug">{open.title}</div></div>}>
        {open && (
          <div className="space-y-6">
            <div className="flex flex-wrap gap-1.5">
              <Badge tone={open.status === "approved" && !open.requires_approval ? "warn" : statusTone(open.status)}>{open.status === "approved" && !open.requires_approval ? "pre-authorised by policy" : statusText(open.status)}</Badge>
              <Badge>Suggested by the {AGENT_LABEL[open.agent]}</Badge>
              <Badge>Approver: {ROLE_LABEL[open.approver_role]}</Badge>
            </div>
            <div>
              <div className="label mb-2">Why this is suggested</div>
              <p className="text-[14.5px] leading-relaxed text-ink-900">{open.rationale}</p>
            </div>
            {open.stages && (
              <div className="grid grid-cols-1 gap-2 sm:grid-cols-3">
                {[["1 · Suggestion", open.stages.recommendation], ["2 · Approval", open.stages.approval], ["3 · Carried out", open.stages.execution]].map(([l, st]: any) => (
                  <div key={l} className={clsx("rounded-md border p-2.5", st.state === "approved" || st.state === "applied" || st.state === "sap_sent" ? "border-[#1D3D2B]" : st.state === "pre_authorised" || st.state === "sap_waiting" ? "border-[#4A3A17]" : st.state === "sap_failed" || st.state === "rejected" ? "border-[#4A2620]" : "border-line")}>
                    <div className="label">{l}</div>
                    <div className="mt-1 text-[12px] leading-snug text-ink-700">{st.text}</div>
                  </div>
                ))}
              </div>
            )}
            <div className="grid grid-cols-4 border-y border-line">
              <div className="py-3 pr-3"><div className="label">Benefit</div><div className="display-num mt-2 text-[22px]">{open.impact_inr ? inr(open.impact_inr, true) : "—"}</div></div>
              <div className="border-l border-line py-3 pl-3 pr-3"><div className="label">Cost</div><div className="display-num mt-2 text-[22px]">{open.cost_inr ? inr(open.cost_inr, true) : "₹0"}</div></div>
              <div className="border-l border-line py-3 pl-3 pr-3"><div className="label">Net</div><div className={clsx("display-num mt-2 text-[22px]", open.net_inr >= 0 ? "text-ok-700" : "text-bad-700")}>{(open.impact_inr || open.cost_inr) ? `${open.net_inr >= 0 ? "+" : "−"}${inr(Math.abs(open.net_inr), true)}` : "—"}</div></div>
              <div className="border-l border-line py-3 pl-3"><div className="label flex items-center gap-1">How sure <Hint text="How confident the agent is, based on how much data supports this and how consistent it is." /></div><div className="mt-2 text-[15px] font-semibold">{confidenceWords(open.confidence)}</div><DetailOnly><div className="num text-[11px] text-ink-500">{pct(open.confidence)}</div></DetailOnly></div>
            </div>
            <div><div className="label mb-2">The evidence</div><Evidence r={open} /></div>

            {["pending", "escalated"].includes(open.status) && (
              <div className="rounded border border-line-strong p-4">
                {open.can_decide === false && <div className="mb-3 text-[13px] text-warn-700">{open.decide_reason || "This one needs a different approver."} Each team approves its own kind of action. In the demo, switch person from the menu.</div>}
                <Field label="Your reason" hint="Saved with your decision so others can see why.">
                  <textarea value={reason} onChange={(e) => setReason(e.target.value)} rows={2} className={clsx(inputCls, "h-auto py-2")} placeholder="Type a reason, or pick one below" />
                </Field>
                <div className="mt-2 flex flex-wrap gap-1.5">
                  {[...QUICK_REASONS.approve, ...QUICK_REASONS.reject].map((q) => (
                    <button key={q} onClick={() => setReason(q)} className={clsx("rounded-full border px-2.5 py-1 text-[11.5px]", reason === q ? "border-paper bg-paper text-black" : "border-line-strong text-ink-500 hover:text-ink-900")}>{q}</button>
                  ))}
                </div>
                <div className="mt-4 flex flex-wrap gap-2">
                  <Button variant="primary" size="lg" onClick={() => decide(open, "approve")} loading={busy === "approve"} disabled={!reason.trim() || open.can_decide === false}><Check className="h-4 w-4" />Approve</Button>
                  <Button variant="danger" size="lg" onClick={() => decide(open, "reject")} loading={busy === "reject"} disabled={!reason.trim() || open.can_decide === false}><X className="h-4 w-4" />Decline</Button>
                  <Button size="lg" variant="ghost" onClick={() => decide(open, "escalate")} loading={busy === "escalate"} disabled={!reason.trim() || open.can_decide === false || open.status === "escalated"}><CornerUpRight className="h-4 w-4" />Ask a senior</Button>
                </div>
              </div>
            )}

            <div>
              <div className="label mb-2">History</div>
              {(open.decisions || []).length === 0 ? <div className="text-[13px] text-ink-500">No one has decided yet.</div> : (
                <ol className="space-y-2.5 border-l border-line-strong pl-4">
                  {open.decisions.map((d: any, i: number) => (
                    <li key={i} className="text-[13px]"><div><b>{d.user}</b> <span className="text-ink-500">({ROLE_LABEL[d.role] || d.role})</span> {d.action === "approve" ? "approved" : d.action === "reject" ? "declined" : d.action === "escalate" ? "sent it to a senior" : d.action === "auto_approve" ? "pre-authorised it under the spending-limit policy (no person approved)" : d.action}</div>
                      <div className="text-[12px] text-ink-500">{dayTime(d.ts)} · “{d.reason}”</div></li>
                  ))}
                </ol>
              )}
            </div>
            <DetailOnly><div className="font-mono text-[11px] text-ink-400">{open.id} · explanation: {open.explanation_source === "template" ? "evidence template (no LLM)" : open.explanation_source}</div></DetailOnly>
          </div>
        )}
      </Drawer>
    </div>
  );
}
