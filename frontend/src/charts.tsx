import { useEffect, useMemo, useRef, useState } from "react";

export interface Series { id: string; label: string; color: string; dashed?: boolean; values: (number | null)[] }

interface LineChartProps {
  series: Series[];
  xLabels: string[];
  xTitles?: string[];
  yMax?: number;
  yTicks?: number[];
  yFormat?: (v: number) => string;
  marker?: { index: number; label: string } | null;
  height?: number;
  directLabels?: boolean;
  ariaLabel: string;
  highlight?: string | null;
}

const PAD = { l: 44, r: 92, t: 14, b: 30 };

/** Track a container's pixel width so SVG text renders at its true size. */
function useWidth(fallback = 720) {
  const ref = useRef<HTMLDivElement>(null);
  const [w, setW] = useState(fallback);
  useEffect(() => {
    const el = ref.current;
    if (!el || typeof ResizeObserver === "undefined") return;
    const ro = new ResizeObserver(([e]) => setW(Math.max(300, Math.round(e.contentRect.width))));
    ro.observe(el);
    return () => ro.disconnect();
  }, []);
  return [ref, w] as const;
}

export function LineChart({ series, xLabels, xTitles, yMax = 1, yTicks = [0, 0.25, 0.5, 0.75, 1], yFormat = (v) => `${Math.round(v * 100)}%`,
  marker, height = 300, directLabels = true, ariaLabel, highlight }: LineChartProps) {
  const ref = useRef<SVGSVGElement>(null);
  const [box, W] = useWidth();
  const [hover, setHover] = useState<number | null>(null);
  const H = height;
  const n = xLabels.length;
  const x = (i: number) => PAD.l + (n <= 1 ? 0 : (i * (W - PAD.l - PAD.r)) / (n - 1));
  const y = (v: number) => PAD.t + (1 - v / yMax) * (H - PAD.t - PAD.b);
  const paths = useMemo(() => series.map((s) => {
    let d = "";
    s.values.forEach((v, i) => { if (v === null) return; d += `${d && s.values[i - 1] !== null ? "L" : "M"}${x(i).toFixed(1)},${y(v).toFixed(1)}`; });
    return d;
  }), [series, n, H, yMax, W]);

  // Direct labels at line ends, nudged apart so they never collide.
  const labels = useMemo(() => {
    if (!directLabels) return [];
    const ends = series.map((s) => {
      let i = s.values.length - 1;
      while (i >= 0 && s.values[i] === null) i--;
      return { s, i, y: i >= 0 ? y(s.values[i] as number) : 0 };
    }).filter((e) => e.i >= 0).sort((a, b) => a.y - b.y);
    for (let k = 1; k < ends.length; k++) if (ends[k].y - ends[k - 1].y < 14) ends[k].y = ends[k - 1].y + 14;
    const bottom = H - PAD.b - 4;
    if (ends.length && ends[ends.length - 1].y > bottom) {
      ends[ends.length - 1].y = bottom;
      for (let k = ends.length - 2; k >= 0; k--) if (ends[k + 1].y - ends[k].y < 14) ends[k].y = ends[k + 1].y - 14;
    }
    return ends;
  }, [series, directLabels, H, W]);

  const onMove = (e: React.PointerEvent) => {
    const svg = ref.current;
    if (!svg || n === 0) return;
    const r = svg.getBoundingClientRect();
    const px = ((e.clientX - r.left) / r.width) * W;
    const i = Math.round(((px - PAD.l) / (W - PAD.l - PAD.r)) * (n - 1));
    setHover(Math.max(0, Math.min(n - 1, i)));
  };
  const step = Math.max(1, Math.ceil(n / Math.max(3, Math.floor((W - PAD.l - PAD.r) / 56))));
  const hx = hover !== null ? x(hover) : 0;
  const tipLeft = hover !== null && hx > W * 0.6;

  return (
    <div className="chart" ref={box}>
      <svg ref={ref} viewBox={`0 0 ${W} ${H}`} role="img" aria-label={ariaLabel} onPointerMove={onMove} onPointerLeave={() => setHover(null)}>
        {yTicks.map((t) => (
          <g key={t}>
            <line x1={PAD.l} x2={W - PAD.r} y1={y(t)} y2={y(t)} className="grid" />
            <text x={PAD.l - 8} y={y(t)} className="tick" textAnchor="end" dominantBaseline="middle">{yFormat(t)}</text>
          </g>
        ))}
        {xLabels.map((l, i) => (i % step === 0 || i === n - 1) && (
          <text key={i} x={x(i)} y={H - 8} className="tick" textAnchor="middle">{l}</text>
        ))}
        {marker && marker.index >= 0 && (
          <g>
            <line x1={x(marker.index)} x2={x(marker.index)} y1={PAD.t} y2={H - PAD.b} className="marker-line" />
            <text x={x(marker.index) - 6} y={PAD.t + 10} className="marker-text" textAnchor="end">{marker.label}</text>
          </g>
        )}
        {series.map((s, k) => (
          <path key={s.id} d={paths[k]} fill="none" stroke={s.color} strokeWidth={highlight === s.id ? 3 : 2}
            strokeDasharray={s.dashed ? "6 4" : undefined} strokeLinejoin="round" strokeLinecap="round"
            opacity={highlight && highlight !== s.id ? 0.35 : 1} />
        ))}
        {series.map((s) => {
          const last = s.values.length - 1;
          const v = s.values[last];
          return v === null || v === undefined ? null : (
            <circle key={s.id} cx={x(last)} cy={y(v)} r={4} fill={s.color} className="end-dot" />
          );
        })}
        {labels.map(({ s, y: ly }) => (
          <text key={s.id} x={W - PAD.r + 10} y={ly} className="direct-label" dominantBaseline="middle">{s.label}</text>
        ))}
        {hover !== null && (
          <g>
            <line x1={hx} x2={hx} y1={PAD.t} y2={H - PAD.b} className="crosshair" />
            {series.map((s) => s.values[hover] === null || s.values[hover] === undefined ? null : (
              <circle key={s.id} cx={hx} cy={y(s.values[hover] as number)} r={4.5} fill={s.color} className="hover-dot" />
            ))}
          </g>
        )}
      </svg>
      {hover !== null && (
        <div className="tooltip" style={{ left: `${(hx / W) * 100}%`, transform: tipLeft ? "translateX(calc(-100% - 12px))" : "translateX(12px)" }}>
          <div className="tooltip-title">{xTitles?.[hover] ?? xLabels[hover]}</div>
          {[...series].filter((s) => s.values[hover] !== null && s.values[hover] !== undefined)
            .sort((a, b) => (b.values[hover] as number) - (a.values[hover] as number)).slice(0, 8).map((s) => (
              <div key={s.id} className="tooltip-row">
                <span className="swatch" style={{ background: s.color }} />
                <span>{s.label}</span>
                <b>{yFormat(s.values[hover] as number)}</b>
              </div>
            ))}
        </div>
      )}
    </div>
  );
}

export function Legend({ series }: { series: Series[] }) {
  return (
    <ul className="legend">
      {series.map((s) => (
        <li key={s.id}>
          <svg width="22" height="10" aria-hidden="true"><line x1="1" x2="21" y1="5" y2="5" stroke={s.color} strokeWidth="2.5" strokeDasharray={s.dashed ? "5 3" : undefined} /></svg>
          {s.label}
        </li>
      ))}
    </ul>
  );
}

export function ProbBar({ p, color, ghost }: { p: number; color: string; ghost?: number }) {
  return (
    <div className="probbar" aria-hidden="true">
      {ghost !== undefined && <div className="probbar-ghost" style={{ width: `${Math.min(100, ghost * 100)}%` }} />}
      <div className="probbar-fill" style={{ width: `${Math.min(100, p * 100)}%`, background: color }} />
    </div>
  );
}

export function CalibrationChart({ bins }: { bins: { bin: string; predicted: number; observed: number; n: number }[] }) {
  const S = 260, P = 34;
  const sc = (v: number) => P + v * (S - 2 * P);
  const [hover, setHover] = useState<number | null>(null);
  return (
    <div className="chart calib">
      <svg viewBox={`0 0 ${S} ${S}`} role="img" aria-label="Podium probability calibration: predicted versus observed frequency">
        {[0, 0.25, 0.5, 0.75, 1].map((t) => (
          <g key={t}>
            <line x1={sc(0)} x2={sc(1)} y1={S - sc(t)} y2={S - sc(t)} className="grid" />
            <text x={P - 6} y={S - sc(t)} className="tick" textAnchor="end" dominantBaseline="middle">{t * 100}%</text>
            <text x={sc(t)} y={S - P + 16} className="tick" textAnchor="middle">{t * 100}%</text>
          </g>
        ))}
        <line x1={sc(0)} y1={S - sc(0)} x2={sc(1)} y2={S - sc(1)} className="diag" />
        {bins.map((b, i) => (
          <circle key={b.bin} cx={sc(b.predicted)} cy={S - sc(b.observed)} r={Math.max(4.5, Math.min(11, Math.sqrt(b.n) * 0.8))}
            className="calib-dot" onPointerEnter={() => setHover(i)} onPointerLeave={() => setHover(null)} />
        ))}
      </svg>
      <p className="chart-caption">
        {hover !== null
          ? `${bins[hover].bin} bin: predicted ${(bins[hover].predicted * 100).toFixed(1)}%, observed ${(bins[hover].observed * 100).toFixed(1)}% across ${bins[hover].n} driver-races.`
          : "Each dot is a bin of forecasts. On the diagonal = calibrated. Dot size reflects the number of forecasts."}
      </p>
    </div>
  );
}
