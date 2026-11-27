"use client";
import clsx from "clsx";
import { useState } from "react";
import { mult, num } from "@/lib/format";

import { GEO, INDIA_PATH, STATE_PATHS } from "./india-geo";

// Boundaries: DataMeet India (CC BY 4.0), following the Survey of India boundary.
const LEFT_LABEL = new Set(["BOM", "PNQ", "AMD"]);
const project = (lon: number, lat: number) => [(lon - GEO.lon0) * GEO.k, (GEO.lat0 - lat) * GEO.k * GEO.ky] as const;

export type MapCluster = { id: string; city: string; lat: number; lon: number; risk?: string; avg_multiplier?: number; expected_network_7d?: number };
export type MapFacility = { id: string; name: string; city: string; lat: number; lon: number; kind: string; inspection_capacity: number };
export type MapFlow = { from: [number, number]; to: [number, number]; label?: string };

export function IndiaMap({ clusters, facilities = [], flows = [], height = 420, onSelect, selected }:
  { clusters: MapCluster[]; facilities?: MapFacility[]; flows?: MapFlow[]; height?: number; onSelect?: (id: string) => void; selected?: string | null }) {
  const [hover, setHover] = useState<MapCluster | null>(null);
  const maxVol = Math.max(1, ...clusters.map((c) => c.expected_network_7d || 0));
  const W = GEO.width, H = GEO.height;
  const color = (r?: string) => (r === "high" ? "#F0583E" : r === "elevated" ? "#E3A33B" : "#BDBDBD");
  return (
    <div className="relative" style={{ height }}>
      <svg viewBox={`0 0 ${W} ${H}`} className="h-full w-full" role="img" aria-label="Regional return risk map">
        <path d={INDIA_PATH} fill="#1A1A1A" />
        <g fill="none" stroke="#333" strokeWidth={0.5} strokeLinejoin="round">
          {STATE_PATHS.map((s) => <path key={s.name} d={s.d}><title>{s.name}</title></path>)}
        </g>
        <path d={INDIA_PATH} fill="none" stroke="#5A5A5A" strokeWidth={0.8} strokeLinejoin="round" />
        {flows.map((f, i) => {
          const [x1, y1] = project(f.from[0], f.from[1]);
          const [x2, y2] = project(f.to[0], f.to[1]);
          // Bend each flow to one side, with a minimum bulge so short hops (Pune → Nashik) stay visible,
          // and put its label clear of the arc on the outer side, away from the city circles.
          const len = Math.hypot(x2 - x1, y2 - y1) || 1;
          const nx = -(y2 - y1) / len, ny = (x2 - x1) / len;
          const bulge = Math.max(0.3 * len, 16);
          const mx = (x1 + x2) / 2 + nx * bulge, my = (y1 + y2) / 2 + ny * bulge;
          const ax = 0.25 * x1 + 0.5 * mx + 0.25 * x2, ay = 0.25 * y1 + 0.5 * my + 0.25 * y2;
          const lx = ax + nx * 6, ly = ay + ny * 6 + 3;
          return (
            <g key={i}>
              <path d={`M${x1},${y1} Q${mx},${my} ${x2},${y2}`} fill="none" stroke="#F2F2F2" strokeWidth={1.2} strokeDasharray="4 4" className="animate-dash" />
              {f.label && <text x={lx} y={ly} fontSize={8} fill="#F2F2F2" textAnchor={nx >= 0 ? "start" : "end"} fontFamily="var(--font-mono)" fontWeight={600}
                paintOrder="stroke" stroke="#000" strokeWidth={2.5}>{f.label}</text>}
            </g>
          );
        })}
        {facilities.map((f) => {
          const [x, y] = project(f.lon, f.lat);
          return (
            <g key={f.id}>
              <rect x={x - 3} y={y - 3} width={6} height={6} fill="#000" stroke="#F2F2F2" strokeWidth={1.3} transform={`rotate(45 ${x} ${y})`} />
            </g>
          );
        })}
        {clusters.map((c) => {
          const [x, y] = project(c.lon, c.lat);
          const r = 4.5 + 10 * Math.sqrt((c.expected_network_7d || 0) / maxVol);
          const col = color(c.risk);
          const isSel = selected === c.id;
          return (
            <g key={c.id} className="cursor-pointer" onMouseEnter={() => setHover(c)} onMouseLeave={() => setHover(null)} onClick={() => onSelect?.(c.id)}>
              {c.risk === "high" && <circle cx={x} cy={y} r={r} fill={col} opacity={0.35} className="animate-ring" style={{ transformOrigin: `${x}px ${y}px` }} />}
              <circle cx={x} cy={y} r={r} fill={col} fillOpacity={0.18} stroke={col} strokeWidth={isSel ? 2.2 : 1.2} />
              <circle cx={x} cy={y} r={2.2} fill={col} />
              {(() => {
                const left = LEFT_LABEL.has(c.id);
                const lx = left ? x - r - 3 : x + r + 3;
                const dy = c.id === "PNQ" ? 8 : c.id === "BOM" ? -4 : 3;
                return (
                  <>
                    <text x={lx} y={y + dy} fontSize={9.5} fill="#F4F4F4" fontWeight={600} textAnchor={left ? "end" : "start"}>{c.city}</text>
                    {c.avg_multiplier && <text x={lx} y={y + dy + 10} fontSize={8.5} fill="#8C8C8C" fontFamily="var(--font-mono)" textAnchor={left ? "end" : "start"}>{mult(c.avg_multiplier)}</text>}
                  </>
                );
              })()}
            </g>
          );
        })}
      </svg>
      {hover && (
        <div className="pointer-events-none absolute left-3 top-3 rounded border border-line-strong bg-[#111] px-3 py-2 text-xs shadow-pop">
          <div className="font-semibold">{hover.city} </div>
          <div className="mt-1 text-ink-700">Next 7 days: <span className="num font-medium">{num(hover.expected_network_7d)}</span> returns</div>
          <div className="text-ink-700"><span className="num font-medium">{mult(hover.avg_multiplier)}</span> a normal week</div>
        </div>
      )}
      <div className="absolute bottom-1 left-1 flex flex-wrap gap-3 text-[10.5px] text-ink-500">
        {[["high", "Big surge"], ["elevated", "Rising"], ["normal", "Normal"]].map(([k, l]) => (
          <span key={k} className="flex items-center gap-1"><span className={clsx("h-2 w-2 rounded-full")} style={{ background: color(k) }} />{l}</span>
        ))}
        {facilities.length > 0 && <span className="flex items-center gap-1"><span className="h-2 w-2 rotate-45 border border-navy-900 bg-white" />Warehouse</span>}
        <span>Bigger circle = more returns</span>
        <span className="text-ink-400">Boundaries: DataMeet, CC BY 4.0</span>
      </div>
    </div>
  );
}
