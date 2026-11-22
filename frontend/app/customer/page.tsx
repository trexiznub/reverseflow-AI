"use client";
import clsx from "clsx";
import { Camera, Check, ChevronLeft, ChevronRight, Package, Repeat2, Truck, Wallet } from "lucide-react";
import { useEffect, useState } from "react";
import { useSession, useToast } from "@/components/providers";
import { Badge, Button, Card, Empty, ErrorState, Field, inputCls, Loading, Skeleton } from "@/components/ui";
import { api, useApi } from "@/lib/api";
import { day, inr } from "@/lib/format";

function SwitchToCustomer() {
  const { users, switchUser } = useSession();
  const customers = users.filter((u) => u.role === "customer");
  return (
    <div className="mx-auto max-w-xl py-10">
      <Card>
        <div className="label">Customer portal</div>
        <h2 className="mt-1 text-lg font-semibold">This view belongs to a customer account</h2>
        <p className="mt-1 text-[13px] text-ink-500">Customers only see their own orders and returns, never vendor risk scores or operational data. Pick a demo customer to continue.</p>
        <div className="mt-4 space-y-2">
          {customers.map((c) => (
            <button key={c.id} onClick={() => switchUser(c.id)} className="flex w-full items-center justify-between rounded border border-line px-3 py-2.5 text-left hover:border-blue-500 hover:bg-blue-50">
              <span><span className="block text-[13px] font-medium">{c.name}</span><span className="text-[11.5px] text-ink-500">{c.scope_id}</span></span>
              <ChevronRight className="h-4 w-4 text-ink-400" />
            </button>
          ))}
        </div>
      </Card>
    </div>
  );
}

function Timeline({ steps }: { steps: any[] }) {
  return (
    <ol className="relative mt-3 space-y-0">
      {steps.map((s, i) => (
        <li key={i} className="relative flex gap-3 pb-3 last:pb-0">
          {i < steps.length - 1 && <span className={clsx("absolute left-[9px] top-5 h-full w-px", s.done ? "bg-blue-500" : "bg-line-strong")} />}
          <span className={clsx("relative z-10 mt-0.5 flex h-[19px] w-[19px] shrink-0 items-center justify-center rounded-full border",
            s.done ? "border-blue-500 bg-blue-500 text-white" : "border-line-strong bg-white")}>{s.done && <Check className="h-3 w-3" />}</span>
          <div className="text-[12.5px]">
            <div className={clsx("font-medium", !s.done && "text-ink-500")}>{s.label}</div>
            {(s.date || s.note) && <div className="text-[11.5px] text-ink-500">{s.date ? day(s.date) : ""}{s.note ? ` ${s.note}` : ""}</div>}
          </div>
        </li>
      ))}
    </ol>
  );
}

function ReturnFlow({ order, onDone, onCancel }: { order: any; onDone: (r: any) => void; onCancel: () => void }) {
  const toast = useToast();
  const [opts, setOpts] = useState<any>(null);
  const [err, setErr] = useState<any>(null);
  const [step, setStep] = useState(0);
  const [form, setForm] = useState<any>({ reason_category: "", reason_text: "", resolution: "refund", exchange_size: "", pickup_date: "", pickup_slot: "" });
  const [files, setFiles] = useState<File[]>([]);
  const [busy, setBusy] = useState(false);
  useEffect(() => { api(`/customer/orders/${order.id}/return-options`).then(setOpts).catch(setErr); }, [order.id]);
  useEffect(() => {
    if (opts?.exchange_first && form.reason_category === "Size & fit" && form.resolution === "refund" && !form._suggested) {
      const i = ["XS", "S", "M", "L", "XL", "XXL"].indexOf(order.size);
      setForm((f: any) => ({ ...f, resolution: "exchange", exchange_size: ["XS", "S", "M", "L", "XL", "XXL"][Math.min(i + 1, 5)] || "", _suggested: true }));
    }
  }, [form.reason_category]); // eslint-disable-line react-hooks/exhaustive-deps
  if (err) return <ErrorState error={err} />;
  if (!opts) return <Skeleton className="h-72" />;
  const steps = ["Reason", "Refund or exchange", "Photos", "Pickup", "Review"];
  const canNext = [form.reason_category && form.reason_text.trim().length >= 5, form.resolution === "refund" || form.exchange_size, true, form.pickup_date && form.pickup_slot, true][step];
  const submit = async () => {
    setBusy(true);
    try {
      const { _suggested, ...body } = form;
      const res = await api("/customer/returns", { method: "POST", body: JSON.stringify({ ...body, order_id: order.id, exchange_size: body.exchange_size || null }) });
      for (const f of files) {
        const fd = new FormData();
        fd.append("file", f);
        await api(`/customer/returns/${res.return.id}/images`, { method: "POST", body: fd });
      }
      toast("ok", `Return ${res.return.id} booked. Pickup ${day(form.pickup_date)}, ${form.pickup_slot}.`);
      onDone(res);
    } catch (e: any) { toast("err", e.message); } finally { setBusy(false); }
  };
  const dates = Array.from(new Set(opts.slots.map((s: any) => s.date))) as string[];
  return (
    <Card className="border-blue-200">
      <div className="flex items-start justify-between">
        <div><div className="label">Return or exchange</div><div className="text-[15px] font-semibold">{opts.product}</div><div className="text-[12px] text-ink-500">Size {opts.size} · order {order.id}</div></div>
        <button onClick={onCancel} className="text-[12px] text-ink-500 hover:text-ink-900">Cancel</button>
      </div>
      <div className="mt-4 flex gap-1">
        {steps.map((s, i) => (
          <div key={s} className="flex-1">
            <div className={clsx("h-1 rounded-full", i <= step ? "bg-blue-500" : "bg-line")} />
            <div className={clsx("mt-1 text-[10.5px]", i === step ? "font-semibold text-ink-900" : "text-ink-500")}>{s}</div>
          </div>
        ))}
      </div>
      <div className="mt-5 min-h-[180px]">
        {step === 0 && (
          <div className="space-y-3">
            <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
              {opts.reasons.map((r: any) => (
                <button key={r.category} onClick={() => setForm({ ...form, reason_category: r.category })}
                  className={clsx("rounded border px-3 py-2.5 text-left", form.reason_category === r.category ? "border-blue-500 bg-blue-50" : "border-line hover:border-line-strong")}>
                  <div className="text-[13px] font-medium">{r.category}</div><div className="text-[11.5px] text-ink-500">{r.hint}</div>
                </button>
              ))}
            </div>
            <Field label="Tell us what happened" hint="Your words help the seller fix the product. Please don't include personal details.">
              <textarea rows={3} value={form.reason_text} onChange={(e) => setForm({ ...form, reason_text: e.target.value })} className={clsx(inputCls, "h-auto py-2")} placeholder="e.g. The blouse is tight at the bust even though I ordered my usual size" />
            </Field>
          </div>
        )}
        {step === 1 && (
          <div className="space-y-3">
            {opts.exchange_message && form.reason_category === "Size & fit" && (
              <div className="flex gap-2 rounded border border-blue-200 bg-blue-50 p-3 text-[12.5px] text-blue-700"><Repeat2 className="mt-0.5 h-4 w-4 shrink-0" />{opts.exchange_message}</div>
            )}
            <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
              {[{ id: "refund", t: "Refund", d: "To your original payment method after the quality check", I: Wallet }, { id: "exchange", t: "Exchange for another size", d: "New size delivered when we collect this one", I: Repeat2 }].map((o) => (
                <button key={o.id} onClick={() => setForm({ ...form, resolution: o.id })} className={clsx("flex gap-3 rounded border px-3 py-3 text-left", form.resolution === o.id ? "border-blue-500 bg-blue-50" : "border-line hover:border-line-strong")}>
                  <o.I className="mt-0.5 h-4 w-4 text-blue-600" /><span><span className="block text-[13px] font-medium">{o.t}</span><span className="text-[11.5px] text-ink-500">{o.d}</span></span>
                </button>
              ))}
            </div>
            {form.resolution === "exchange" && (
              <div>
                <div className="mb-1.5 text-xs font-medium text-ink-700">New size</div>
                <div className="flex flex-wrap gap-1.5">
                  {opts.exchange_sizes.map((s: string) => (
                    <button key={s} onClick={() => setForm({ ...form, exchange_size: s })} className={clsx("h-9 w-12 rounded border text-[13px] font-medium", form.exchange_size === s ? "border-navy-900 bg-navy-900 text-white" : "border-line-strong hover:border-ink-500")}>{s}</button>
                  ))}
                </div>
                {opts.size_chart && Object.keys(opts.size_chart).length > 0 && (
                  <table className="mt-3 w-full max-w-sm text-[11.5px]"><thead><tr className="text-ink-500"><th className="text-left font-medium">Size</th><th className="text-right font-medium">Bust (in)</th><th className="text-right font-medium">Waist (in)</th></tr></thead>
                    <tbody>{Object.entries(opts.size_chart).map(([s, v]: any) => <tr key={s} className={clsx("border-t border-line", s === form.exchange_size && "bg-blue-50")}><td>{s}</td><td className="num text-right">{v.bust_in}</td><td className="num text-right">{v.waist_in}</td></tr>)}</tbody></table>
                )}
                {opts.size_chart_version > 1 && <div className="mt-1 text-[11px] text-ok-700">Size chart updated (v{opts.size_chart_version}) based on recent customer feedback.</div>}
              </div>
            )}
          </div>
        )}
        {step === 2 && (
          <div>
            <label className="flex cursor-pointer flex-col items-center justify-center rounded border border-dashed border-line-strong px-4 py-8 text-center hover:bg-canvas">
              <Camera className="h-5 w-5 text-ink-400" />
              <span className="mt-1.5 text-[13px] font-medium">Add photos (optional, up to {opts.max_images})</span>
              <span className="text-[11.5px] text-ink-500">Photos of the label and the issue speed up the quality check. JPG or PNG, max 5 MB each.</span>
              <input type="file" accept="image/*" multiple className="hidden" onChange={(e) => setFiles(Array.from(e.target.files || []).filter((f) => f.size <= 5 * 1024 * 1024).slice(0, opts.max_images))} />
            </label>
            {files.length > 0 && (
              <div className="mt-3 flex flex-wrap gap-2">
                {files.map((f) => (
                  // eslint-disable-next-line @next/next/no-img-element
                  <img key={f.name} src={URL.createObjectURL(f)} alt={f.name} className="h-20 w-20 rounded border border-line object-cover" />
                ))}
              </div>
            )}
          </div>
        )}
        {step === 3 && (
          <div className="space-y-3">
            {dates.map((d) => (
              <div key={d}>
                <div className="mb-1.5 text-xs font-medium text-ink-700">{new Date(d + "T00:00:00").toLocaleDateString("en-GB", { weekday: "long", day: "numeric", month: "short" })}</div>
                <div className="grid grid-cols-3 gap-2">
                  {opts.slots.filter((s: any) => s.date === d).map((s: any) => (
                    <button key={s.slot} onClick={() => setForm({ ...form, pickup_date: s.date, pickup_slot: s.slot })}
                      className={clsx("rounded border px-2 py-2 text-[12.5px]", form.pickup_date === s.date && form.pickup_slot === s.slot ? "border-blue-500 bg-blue-50 font-medium" : "border-line hover:border-line-strong")}>
                      {s.slot}{s.availability === "limited" && <span className="block text-[10.5px] text-warn-700">limited slots</span>}
                    </button>
                  ))}
                </div>
              </div>
            ))}
            <div className="text-[11.5px] text-ink-500">Slots marked limited are in high demand after the festival; your pickup is still guaranteed.</div>
          </div>
        )}
        {step === 4 && (
          <div className="space-y-1.5 text-[13px]">
            <div className="flex justify-between border-b border-line py-1.5"><span className="text-ink-500">Reason</span><span>{form.reason_category}</span></div>
            <div className="border-b border-line py-1.5 text-ink-700">“{form.reason_text}”</div>
            <div className="flex justify-between border-b border-line py-1.5"><span className="text-ink-500">Resolution</span><span>{form.resolution === "exchange" ? `Exchange for size ${form.exchange_size}` : `Refund ${inr(order.price)}`}</span></div>
            <div className="flex justify-between border-b border-line py-1.5"><span className="text-ink-500">Photos</span><span>{files.length}</span></div>
            <div className="flex justify-between py-1.5"><span className="text-ink-500">Pickup</span><span>{day(form.pickup_date)} · {form.pickup_slot}</span></div>
            <div className="rounded bg-canvas p-2.5 text-[11.5px] text-ink-500">Keep the brand tag attached. Refunds start after a standard quality check at our returns centre.</div>
          </div>
        )}
      </div>
      <div className="mt-4 flex justify-between border-t border-line pt-3">
        <Button onClick={() => setStep((s) => s - 1)} disabled={step === 0}><ChevronLeft className="h-3.5 w-3.5" />Back</Button>
        {step < 4 ? <Button variant="primary" onClick={() => setStep((s) => s + 1)} disabled={!canNext}>Continue<ChevronRight className="h-3.5 w-3.5" /></Button>
          : <Button variant="primary" onClick={submit} loading={busy}>Confirm return</Button>}
      </div>
    </Card>
  );
}

export default function CustomerPortal() {
  const { meta } = useSession();
  const isCustomer = meta?.user?.role === "customer";
  const { data, error, loading, reload } = useApi<any>(isCustomer ? "/customer/me" : null, { deps: [meta?.user?.id] });
  const [active, setActive] = useState<any>(null);
  const [justCreated, setJustCreated] = useState<string | null>(null);
  if (!meta) return <Loading rows={1} />;
  if (!isCustomer) return <SwitchToCustomer />;
  if (error) return <ErrorState error={error} onRetry={reload} />;
  if (loading || !data) return <Loading rows={2} />;
  return (
    <div className="mx-auto max-w-5xl space-y-8">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <div className="label">Your orders</div>
          <h1 className="display mt-2 text-[44px] sm:text-[64px]">Hello, {data.customer.name.split(" ")[0]}.</h1>
          <p className="mt-3 text-[14px] text-ink-500">Returns are free within {data.return_window_days} days of delivery. Today is {day(data.scenario_date)} (demo date).</p>
        </div>
        <div className="text-right text-[11.5px] text-ink-500">Delivering to PIN <span className="num text-ink-900">{data.customer.pin}</span></div>
      </div>
      {active && <ReturnFlow order={active} onCancel={() => setActive(null)} onDone={(r) => { setActive(null); setJustCreated(r.return.id); reload(); }} />}
      <div className="grid grid-cols-1 gap-5 lg:grid-cols-[1fr_1fr]">
        <div className="space-y-3">
          <div className="label">Orders</div>
          {data.orders.map((o: any) => (
            <Card key={o.id} className="flex gap-3">
              <div className="flex h-16 w-14 shrink-0 items-center justify-center rounded bg-gradient-to-b from-canvas to-[#1F1F1F]"><Package className="h-5 w-5 text-ink-300" /></div>
              <div className="min-w-0 flex-1">
                <div className="text-[13px] font-medium leading-snug">{o.product}</div>
                <div className="text-[11.5px] text-ink-500">Size {o.size} · {inr(o.price)} · delivered {day(o.delivered_date)}</div>
                <div className="mt-2 flex items-center gap-2">
                  {o.return_id ? <Badge tone="blue">Return {o.return_id}</Badge> : o.eligible ? (
                    <>
                      <Button size="sm" variant="dark" onClick={() => setActive(o)} disabled={!!active}>Return or exchange</Button>
                      <span className="text-[11px] text-ink-500">until {day(o.return_by)}</span>
                    </>
                  ) : <span className="text-[11.5px] text-ink-400">Return window closed</span>}
                </div>
              </div>
            </Card>
          ))}
        </div>
        <div className="space-y-3">
          <div className="label">Returns</div>
          {data.returns.length === 0 && <Empty title="No returns yet" icon={<Truck className="h-5 w-5" />} />}
          {data.returns.map((r: any) => (
            <Card key={r.id} className={clsx(justCreated === r.id && "border-blue-500 ring-2 ring-blue-100")}>
              <div className="flex items-start justify-between gap-2">
                <div>
                  <div className="text-[13px] font-medium">{r.product}</div>
                  <div className="font-mono text-[11px] text-ink-500">{r.id} · requested {day(r.request_date)}</div>
                </div>
                <Badge tone={r.status === "recovered" ? "ok" : "blue"}>{r.status_text}</Badge>
              </div>
              <div className="mt-2 rounded bg-canvas p-2.5 text-[12px] leading-relaxed text-ink-700">{r.explanation}</div>
              <Timeline steps={r.timeline} />
              <div className="mt-2 flex flex-wrap gap-3 border-t border-line pt-2 text-[11.5px] text-ink-500">
                <span>{r.resolution === "exchange" ? `Exchange → size ${r.exchange_size}` : `Refund ${inr(r.price)}`}</span>
                {r.pickup_date && <span>Pickup {day(r.pickup_date)} · {r.pickup_slot}</span>}
                {r.images.length > 0 && <span>{r.images.length} photo{r.images.length > 1 ? "s" : ""}</span>}
              </div>
            </Card>
          ))}
        </div>
      </div>
    </div>
  );
}
