"use client";
import { Area, AreaChart, ResponsiveContainer } from "recharts";

// Monochrome chart palette: white for the main series, greys for context,
// status colours only where the value is good or bad.
export const C = {
  blue: "#F2F2F2", navy: "#8C8C8C", slate: "#555555", amber: "#E3A33B", red: "#F0583E", green: "#3FBF7F", grid: "#1C1C1C", band: "#262626",
};
export const SERIES = ["#F2F2F2", "#8C8C8C", "#E3A33B", "#3FBF7F", "#555555", "#F0583E", "#C4C4C4", "#6E6E6E"];

export const axis = { tick: { fontSize: 10.5, fill: "#7A7A7A", fontFamily: "var(--font-mono)" }, tickLine: false, axisLine: { stroke: "#2A2A2A" } } as const;

export function Sparkline({ data, k = "value", color = C.blue, height = 34, width = 96 }: { data: any[]; k?: string; color?: string; height?: number; width?: number }) {
  if (!data?.length) return null;
  const id = "sg" + Math.abs(color.split("").reduce((a, c) => a + c.charCodeAt(0), 0));
  return (
    <div style={{ width, height }}>
      <ResponsiveContainer>
        <AreaChart data={data} margin={{ top: 2, bottom: 0, left: 0, right: 0 }}>
          <defs>
            <linearGradient id={id} x1="0" x2="0" y1="0" y2="1">
              <stop offset="0%" stopColor={color} stopOpacity={0.18} />
              <stop offset="100%" stopColor={color} stopOpacity={0} />
            </linearGradient>
          </defs>
          <Area dataKey={k} stroke={color} strokeWidth={1.4} fill={`url(#${id})`} isAnimationActive={false} dot={false} />
        </AreaChart>
      </ResponsiveContainer>
    </div>
  );
}

export function ChartTooltip({ active, payload, label, fmt }: any) {
  if (!active || !payload?.length) return null;
  return (
    <div className="rounded border border-line-strong bg-[#111] px-2.5 py-2 text-[11.5px] shadow-pop">
      <div className="mb-1 font-medium text-ink-900">{label}</div>
      {payload.filter((p: any) => p.value !== null && p.value !== undefined && !String(p.dataKey).startsWith("_")).map((p: any) => (
        <div key={p.dataKey} className="flex items-center justify-between gap-4">
          <span className="flex items-center gap-1.5 text-ink-500"><span className="h-2 w-2 rounded-sm" style={{ background: p.color || p.stroke }} />{p.name}</span>
          <span className="num font-medium text-ink-900">{fmt ? fmt(p.value) : typeof p.value === "number" ? p.value.toLocaleString("en-IN", { maximumFractionDigits: 2 }) : Array.isArray(p.value) ? p.value.map((x: number) => x.toFixed(1)).join("–") : p.value}</span>
        </div>
      ))}
    </div>
  );
}
