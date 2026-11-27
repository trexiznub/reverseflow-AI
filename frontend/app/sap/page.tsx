"use client";
import clsx from "clsx";
import { Send } from "lucide-react";
import { useState } from "react";
import { useSession, useToast } from "@/components/providers";
import { Badge, BigStats, Button, Card, Drawer, Empty, ErrorState, JsonBlock, KV, Loading, More, PageHeader, Section, Tabs } from "@/components/ui";
import { post, useApi } from "@/lib/api";
import { dayTime } from "@/lib/format";

const STATE: Record<string, { label: string; tone: any }> = {
  in_use: { label: "In use", tone: "ok" },
  connected: { label: "Connected", tone: "ok" },
  ready: { label: "Built, not connected", tone: "warn" },
  planned: { label: "Planned", tone: "neutral" },
};
const MSG: Record<string, { label: string; tone: any }> = {
  waiting: { label: "Waiting for SAP", tone: "warn" },
  sent: { label: "Sent", tone: "ok" },
  failed: { label: "Failed", tone: "bad" },
};
const GROUPS = ["Build and run", "Data", "Run the business", "Connect", "Report"];
const SYS = { ibp: "IBP", tm: "TM", ariba: "Ariba" } as Record<string, string>;

function ServiceCard({ s }: { s: any }) {
  const st = STATE[s.state] || STATE.planned;
  return (
    <Card className="flex flex-col">
      <div className="flex items-start justify-between gap-3">
        <div className="text-[15px] font-semibold leading-snug tracking-tight">{s.product}</div>
        <Badge tone={st.tone} dot>{st.label}</Badge>
      </div>
      <p className="mt-2 text-[13px] leading-relaxed text-ink-700">{s.does}</p>
      <p className="mt-3 border-t border-dashed border-line pt-3 text-[12.5px] leading-relaxed text-ink-500">{s.today}</p>
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

  return (
    <div className="space-y-10">
      <PageHeader eyebrow="SAP" title="SAP connections"
        sub="What each SAP product does for ReverseFlow, and whether it is switched on. Nothing is shown as connected unless it really is."
        right={canPublish && (
          <Button variant="primary" loading={busy === "fc"} onClick={() => act("fc", () => post("/sap/ibp/forecast"),
            (r) => r.status === "sent" ? "Forecast sent to SAP IBP." : "Forecast prepared for SAP IBP. It waits in the outbox until IBP is connected.")}>
            <Send className="h-3.5 w-3.5" />Send forecast to IBP
          </Button>
        )} />

      <BigStats items={[
        { label: "In use", value: d.counts.in_use, sub: "SAP products the app runs on today" },
        { label: "Connected", value: d.counts.connected, sub: "SAP systems switched on in this setup" },
        { label: "Built, not connected", value: d.counts.ready, sub: "Working code that switches on when the SAP service is added", tone: d.counts.ready ? "warn" : undefined },
        { label: "Messages waiting", value: waiting, sub: "Prepared for IBP, TM and Ariba, not sent yet" },
      ]} />

      {GROUPS.map((g) => {
        const items = d.services.filter((s: any) => s.group === g);
        if (!items.length) return null;
        return (
          <Section key={g} label={g}>
            <div className="grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-3">{items.map((s: any) => <ServiceCard key={s.id} s={s} />)}</div>
          </Section>
        );
      })}

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
