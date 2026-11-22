"use client";
import clsx from "clsx";
import { useMemo, useState } from "react";
import { mult, num } from "@/lib/format";

// Simplified outline of India (lon, lat). Rendered as a dot matrix, so the
// coarse geometry reads as a stylised map rather than a survey boundary.
const OUTLINE: [number, number][] = [
  [68.2, 23.7], [68.9, 22.4], [70.1, 20.9], [71.6, 20.7], [72.6, 21.3], [72.9, 20.2], [72.8, 19.0], [73.2, 17.4], [73.6, 16.2], [74.0, 15.0],
  [74.6, 13.6], [74.9, 12.6], [75.6, 11.5], [76.1, 10.3], [76.6, 8.9], [77.5, 8.1], [78.2, 8.9], [79.0, 9.3], [79.3, 10.3], [79.8, 11.6],
  [80.2, 13.0], [80.1, 14.6], [80.5, 15.7], [81.3, 16.3], [82.3, 16.7], [83.4, 17.9], [84.8, 19.2], [86.3, 19.9], [86.9, 21.0], [87.6, 21.6],
  [88.6, 21.7], [89.0, 22.2], [88.8, 23.4], [88.5, 24.4], [88.1, 24.8], [88.6, 25.8], [89.8, 25.9], [92.2, 25.1], [92.6, 23.0], [93.3, 23.3],
  [93.9, 24.5], [94.6, 25.8], [95.2, 26.6], [96.2, 27.3], [97.3, 28.1], [96.4, 28.9], [95.3, 29.1], [94.2, 28.7], [92.6, 27.9], [91.6, 27.8],
  [90.3, 26.9], [89.0, 26.9], [88.8, 27.3], [88.2, 27.9], [88.0, 26.5], [86.1, 26.5], [85.0, 26.9], [84.1, 27.4], [83.3, 27.4], [81.9, 27.9],
  [80.9, 28.6], [80.1, 28.9], [80.6, 29.9], [81.0, 30.3], [79.4, 31.0], [78.8, 31.7], [78.8, 32.5], [79.5, 32.7], [79.5, 34.0], [78.5, 35.0],
  [77.8, 35.5], [76.3, 35.8], [75.4, 36.6], [74.7, 36.9], [73.8, 36.0], [74.0, 34.9], [73.9, 34.0], [74.3, 33.0], [74.6, 32.5], [75.2, 32.2],
  [74.6, 31.1], [74.0, 30.3], [73.4, 29.9], [72.9, 29.0], [72.1, 28.2], [71.0, 27.9], [70.2, 27.6], [69.6, 27.0], [70.1, 26.3], [70.6, 25.7],
  [70.9, 25.1], [70.1, 24.4], [69.2, 24.3], [68.7, 23.9],
];

const LEFT_LABEL = new Set(["BOM", "PNQ", "AMD"]);
const LON0 = 65.6, LAT0 = 37.5, K = 9.2;
const project = (lon: number, lat: number) => [(lon - LON0) * K, (LAT0 - lat) * K * 1.05] as const;

function inside(lon: number, lat: number) {
  let c = false;
  for (let i = 0, j = OUTLINE.length - 1; i < OUTLINE.length; j = i++) {
    const [xi, yi] = OUTLINE[i], [xj, yj] = OUTLINE[j];
    if (yi > lat !== yj > lat && lon < ((xj - xi) * (lat - yi)) / (yj - yi) + xi) c = !c;
  }
  return c;
}

export type MapCluster = { id: string; city: string; lat: number; lon: number; risk?: string; avg_multiplier?: number; expected_network_7d?: number };
export type MapFacility = { id: string; name: string; city: string; lat: number; lon: number; kind: string; inspection_capacity: number };
export type MapFlow = { from: [number, number]; to: [number, number]; label?: string };

export function IndiaMap({ clusters, facilities = [], flows = [], height = 420, onSelect, selected }:
  { clusters: MapCluster[]; facilities?: MapFacility[]; flows?: MapFlow[]; height?: number; onSelect?: (id: string) => void; selected?: string | null }) {
  const [hover, setHover] = useState<MapCluster | null>(null);
  const dots = useMemo(() => {
    const out: [number, number][] = [];
    for (let lat = 37; lat >= 6.5; lat -= 0.42) for (let lon = 68; lon <= 97.5; lon += 0.42) if (inside(lon, lat)) out.push([lon, lat]);
    return out;
  }, []);
  const maxVol = Math.max(1, ...clusters.map((c) => c.expected_network_7d || 0));
  const W = (97.8 - LON0) * K, H = (LAT0 - 6.2) * K * 1.05;
  const color = (r?: string) => (r === "high" ? "#F0583E" : r === "elevated" ? "#E3A33B" : "#BDBDBD");
  return (
    <div className="relative" style={{ height }}>
      <svg viewBox={`0 0 ${W} ${H}`} className="h-full w-full" role="img" aria-label="Regional return risk map">
        {dots.map(([lon, lat], i) => {
          const [x, y] = project(lon, lat);
          return <circle key={i} cx={x} cy={y} r={1.25} fill="#2B2B2B" />;
        })}
        {flows.map((f, i) => {
          const [x1, y1] = project(f.from[0], f.from[1]);
          const [x2, y2] = project(f.to[0], f.to[1]);
          const mx = (x1 + x2) / 2 - (y2 - y1) * 0.3, my = (y1 + y2) / 2 + (x2 - x1) * 0.3;
          return (
            <g key={i}>
              <path d={`M${x1},${y1} Q${mx},${my} ${x2},${y2}`} fill="none" stroke="#F2F2F2" strokeWidth={1.2} strokeDasharray="4 4" className="animate-dash" />
              {f.label && <text x={mx} y={my - 3} fontSize={8} fill="#F2F2F2" textAnchor="middle" fontFamily="var(--font-mono)" fontWeight={600}>{f.label}</text>}
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
      </div>
    </div>
  );
}
