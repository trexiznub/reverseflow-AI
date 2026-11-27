"use client";
import clsx from "clsx";
import { PlugZap, Send } from "lucide-react";
import { useState } from "react";
import { useSession, useToast } from "@/components/providers";
import { Badge, BigStats, Button, Card, Drawer, Empty, ErrorState, JsonBlock, KV, Loading, More, PageHeader, Section, Tabs } from "@/components/ui";
import { post, useApi } from "@/lib/api";
import { dayTime } from "@/lib/format";

// Only "connected" means a test actually reached the service.
const STATE: Record<string, { label: string; tone: any }> = {
  connected: { label: "Connected", tone: "ok" },
  configured: { label: "Configured, not tested", tone: "warn" },
  not_configured: { label: "Not configured", tone: "neutral" },
  no_entitlement: { label: "Missing entitlement", tone: "warn" },
  failed: { label: "Connection failed", tone: "bad" },
};
const MSG: Record<string, { label: string; tone: any }> = {
  waiting: { label: "Waiting for SAP", tone: "warn" },
  sent: { label: "Sent", tone: "ok" },
  failed: { label: "Failed", tone: "bad" },
};
const SYS = { ibp: "IBP", tm: "TM", ariba: "Ariba" } as Record<string, string>;

function ServiceCard({ s }: { s: any }) {
  const st = STATE[s.state] || STATE.not_configured;
  return (
    <Card className="flex flex-col">
      <div className="flex items-start justify-between gap-3">
        <div className="text-[15px] font-semibold leading-snug tracking-tight">{s.product}</div>
        <Badge tone={st.tone} dot>{st.label}</Badge>
      </div>
      <p className="mt-2 text-[13px] leading-relaxed text-ink-700">{s.does}</p>
      <div className="mt-3 space-y-1.5 border-t border-dashed border-line pt-3 text-[12.5px] leading-relaxed text-ink-500">
        {s.detail && <p className={clsx(s.state === "failed" && "text-bad-700")}>{s.detail}</p>}
        {s.tested_at && <p className="label">Tested {dayTime(s.tested_at)}</p>}
        {s.sandbox && <p><Badge tone="warn">Sandbox</Badge> Not connected, so the S/4HANA view below shows synthetic data in the S/4HANA API format.</p>}
        {s.selected === false && s.state === "connected" && <p>Connected but not selected. Choose it under Settings to use it for explanations.</p>}
        {s.built && s.state !== "connected" && <p>{s.built} Messages wait in the outbox below until it is connected.</p>}
        {s.state === "not_configured" && !s.sandbox && <p>Needs: {s.needs}</p>}
        {s.state === "no_entitlement" && <p>Needs: {s.needs}</p>}
      </div>
      {s.messages && (
        <div className="label mt-3 flex gap-4">
          <span>{s.messages.waiting} waiting</span><span>{s.messages.sent} sent</span>{s.messages.failed > 0 && <span className="text-bad-700">{s.messages.failed} failed</span>}
        </div>
      )}
      <More title="How to connect">
        <div className="font-mono text-[11.5px] leading-relaxed text-ink-500">{s.connect}</div>
      </More>
    </Card>
  );
}

function S4Explorer() {
  const list = useApi<any>("/sap/s4");
  const [ent, setEnt] = useState<string>("customer_returns");
  const data = useApi<any>(`/sap/s4/${ent}?top=8`, { deps: [ent] });
  if (list.error) return <ErrorState error={list.error} />;
  if (!list.data) return <Loading rows={1} />;
  const recs: any[] = data.data?.records || [];
  const cols = recs.length ? Object.keys(recs[0]).filter((k) => !k.startsWith("__") && typeof recs[0][k] !== "object").slice(0, 7) : [];
  const fmt = (v: any) => (typeof v === "string" && v.startsWith("/Date(") ? new Date(Number(v.slice(6, -2))).toISOString().slice(0, 10) : String(v ?? ""));
  return (
    <div className="space-y-3">
      <Tabs value={ent} onChange={setEnt} items={list.data.entities.map((e: any) => ({ id: e.id, label: e.title }))} />
      {data.error ? <ErrorState error={data.error} /> : !data.data ? <Loading rows={1} /> : (
        <>
          <div className="flex flex-wrap items-center gap-2 text-[12.5px] text-ink-500">
            {data.data.source === "sandbox" ? <Badge tone="warn" dot>Sandbox, synthetic data</Badge> : data.data.ok ? <Badge tone="ok" dot>Live from S/4HANA</Badge> : <Badge tone="bad" dot>S/4HANA error</Badge>}
            <span className="font-mono text-[11.5px]">{data.data.api}</span>
          </div>
          {data.data.source === "sandbox" && <p className="text-[12.5px] text-ink-500">{data.data.label}</p>}
          {!data.data.ok && <p className="text-[12.5px] text-bad-700">{typeof data.data.error === "string" ? data.data.error : JSON.stringify(data.data.error)}</p>}
          {recs.length > 0 && (
            <Card pad={false} className="overflow-x-auto">
              <table className="w-full text-left text-[12px]">
                <thead><tr className="border-b border-line">{cols.map((c) => <th key={c} className="label whitespace-nowrap px-3 py-2 font-normal">{c}</th>)}</tr></thead>
                <tbody>{recs.map((r, i) => <tr key={i} className="border-b border-line last:border-0">{cols.map((c) => <td key={c} className="whitespace-nowrap px-3 py-2 font-mono text-[11.5px] text-ink-700">{fmt(r[c])}</td>)}</tr>)}</tbody>
              </table>
            </Card>
          )}
        </>
      )}
    </div>
  );
}

export default function SapPage() {
  const { meta } = useSession();
  const toast = useToast();
  const status = useApi<any>("/sap/status");
  const [tab, setTab] = useState<string>("all");
  const box = useApi<any[]>(`/sap/outbox${tab === "all" ? "" : `?system=${tab}`}`, { deps: [tab] });
  const [open, setOpen] = useState<string | null>(null);
  const msg = useApi<any>(open ? `/sap/outbox/${open}` : null, { deps: [open] });
  const [busy, setBusy] = useState<string | null>(null);
  const isOps = meta?.user?.role === "ops_manager";
  const isAdmin = !!meta?.user?.is_admin;
  const canPublish = ["ops_manager", "vendor_quality_manager", "warehouse_manager"].includes(meta?.user?.role);

  const refresh = () => { status.reload(true); box.reload(true); if (open) msg.reload(true); };
  const act = async (key: string, fn: () => Promise<any>, ok: (r: any) => string) => {
    setBusy(key);
    try { const r = await fn(); toast("ok", ok(r)); refresh(); } catch (e: any) { toast("err", e.message); } finally { setBusy(null); }
  };

  if (status.error) return <ErrorState error={status.error} onRetry={status.reload} />;
  if (!status.data) return <Loading />;
  const d = status.data;
  const ob = d.outbox as Record<string, any>;
  const waiting = Object.values(ob).reduce((a: number, x: any) => a + x.waiting, 0);
  const c = d.counts;

  return (
    <div className="space-y-10">
      <PageHeader eyebrow="SAP" title="SAP connections"
        sub="What each SAP service does for ReverseFlow and whether it works right now. A service only shows as connected after a test has reached it."
        right={<div className="flex flex-wrap gap-2">
          {isAdmin && (
            <Button loading={busy === "test"} onClick={() => act("test", () => post("/sap/status/test"),
              (r) => `Tested. ${r.counts.connected} connected, ${r.counts.failed} failed, ${r.counts.no_entitlement} missing an entitlement.`)}>
              <PlugZap className="h-3.5 w-3.5" />Test connections
            </Button>
          )}
          {canPublish && (
            <Button variant="primary" loading={busy === "fc"} onClick={() => act("fc", () => post("/sap/ibp/forecast"),
              (r) => r.status === "sent" ? "Forecast sent to SAP IBP." : "Forecast prepared for SAP IBP. It waits in the outbox until IBP is connected.")}>
              <Send className="h-3.5 w-3.5" />Send forecast to IBP
            </Button>
          )}
        </div>} />

      <BigStats items={[
        { label: "Connected", value: c.connected, sub: "Reached by the last connection test", tone: c.connected ? "ok" : undefined },
        { label: "Configured, not tested", value: c.configured, sub: "Set up; press Test connections to check", tone: c.configured ? "warn" : undefined },
        { label: "Failed or no entitlement", value: c.failed + c.no_entitlement, sub: "Set up, but the test did not get through", tone: c.failed + c.no_entitlement ? "bad" : undefined },
        { label: "Not configured", value: c.not_configured, sub: "Code is ready; the SAP service is not set up yet" },
      ]} />

      <p className="max-w-3xl text-[13px] leading-relaxed text-ink-500">
        Sign-in: {d.auth_mode === "xsuaa" ? "SAP XSUAA (roles from your SAP role collections)." : "demo person switcher. In production the app requires SAP sign-in."}
        {" "}Database: {d.database === "hana" ? "SAP HANA Cloud." : `${d.database} (local). HANA Cloud is used when bound.`}
        {" "}Development happens in SAP Business Application Studio.
      </p>

      {(d.groups as string[]).map((g) => {
        const items = d.services.filter((s: any) => s.group === g);
        if (!items.length) return null;
        return (
          <Section key={g} label={g}>
            <div className="grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-3">{items.map((s: any) => <ServiceCard key={s.id} s={s} />)}</div>
          </Section>
        );
      })}

      <Section label="SAP S/4HANA" title="Orders, returns and stock in S/4HANA format">
        <p className="max-w-3xl text-[13.5px] leading-relaxed text-ink-500">
          Read through SAP&apos;s published S/4HANA APIs. While no S/4HANA system is connected, the same requests are answered from the demo data and labelled as sandbox data.
        </p>
        <S4Explorer />
      </Section>

      <Section label="Outbox" title="Messages for SAP systems"
        right={isOps && waiting > 0 && (
          <Button size="sm" loading={busy === "all"} onClick={() => act("all", () => post("/sap/outbox/send-waiting"),
            (r) => r.sent ? `${r.sent} sent.` : "Nothing was sent: no SAP system is connected yet.")}>Try sending all waiting</Button>
        )}>
        <p className="max-w-3xl text-[13.5px] leading-relaxed text-ink-500">
          When someone approves a decision that another SAP system carries out, the app writes the message for that system here.
          Van bookings and warehouse changes go to TM, seller quality issues to Ariba, and forecasts and recovered stock to IBP.
          Each one is sent as soon as its system is connected.
        </p>
        <Tabs value={tab} onChange={setTab} items={[
          { id: "all", label: "All" },
          ...Object.keys(SYS).map((k) => ({ id: k, label: SYS[k], count: ob[k] ? ob[k].waiting + ob[k].sent + ob[k].failed : 0 })),
        ]} />
        {box.error ? <ErrorState error={box.error} /> : !box.data ? <Loading rows={1} /> : !box.data.length ? (
          <Empty title="No messages yet" sub="Approve a decision on the Decisions page, or send the forecast to IBP." />
        ) : (
          <Card pad={false} className="divide-y divide-line">
            {box.data.map((x) => (
              <button key={x.id} onClick={() => setOpen(x.id)} className="flex w-full flex-wrap items-center gap-x-4 gap-y-1 px-5 py-3.5 text-left hover:bg-canvas">
                <span className="label w-12 shrink-0 text-ink-900">{SYS[x.system]}</span>
                <span className="min-w-0 flex-1 text-[13.5px] font-medium text-ink-900">{x.title}</span>
                <span className="text-[12px] text-ink-500">{x.created_by} · {dayTime(x.created_at)}</span>
                <Badge tone={MSG[x.status]?.tone} dot>{MSG[x.status]?.label || x.status}</Badge>
              </button>
            ))}
          </Card>
        )}
      </Section>

      <Drawer open={!!open} onClose={() => setOpen(null)} title={msg.data?.title || "Message"} width={640}>
        {msg.error ? <ErrorState error={msg.error} /> : !msg.data ? <Loading rows={1} /> : (
          <div className="space-y-5">
            <div className="flex items-center gap-2">
              <Badge tone={MSG[msg.data.status]?.tone} dot>{MSG[msg.data.status]?.label}</Badge>
              <span className="text-[12.5px] text-ink-500">for {msg.data.system_label}</span>
            </div>
            <div>
              <KV k="Prepared by" v={msg.data.created_by} />
              <KV k="Prepared" v={dayTime(msg.data.created_at)} />
              <KV k="Because of" v={msg.data.source_type === "forecast" ? "The latest return forecast" : `Decision ${msg.data.source_id}`} />
              <KV k="Send attempts" v={msg.data.attempts} />
              {msg.data.target && <KV k="Sent to" v={<span className="font-mono text-[11.5px]">{msg.data.target}</span>} />}
            </div>
            {(msg.data.response?.note || msg.data.response?.error) && (
              <div className={clsx("rounded border p-3 text-[12.5px]", msg.data.status === "failed" ? "border-[#4A2620] bg-bad-50 text-bad-700" : "border-line bg-canvas text-ink-700")}>
                {msg.data.response.note || msg.data.response.error}
              </div>
            )}
            {isOps && msg.data.status !== "sent" && (
              <Button variant="primary" loading={busy === "one"} onClick={() => act("one", () => post(`/sap/outbox/${open}/send`),
                (r) => r.status === "sent" ? "Sent." : r.status === "failed" ? "Sending failed. See the reply below." : "Not sent: this SAP system isn't connected yet.")}>
                <Send className="h-3.5 w-3.5" />Send now
              </Button>
            )}
            <div>
              <div className="label mb-2">The message</div>
              <JsonBlock value={msg.data.payload} max={420} />
            </div>
            {msg.data.response?.http_status && (
              <div>
                <div className="label mb-2">Reply from SAP</div>
                <JsonBlock value={msg.data.response} max={200} />
              </div>
            )}
          </div>
        )}
      </Drawer>
    </div>
  );
}
