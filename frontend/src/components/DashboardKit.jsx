// Shared visual building blocks for AdminDashboard/LecturerDashboard: animated
// KPI counters, gradient chart fills, a styled tooltip, and glass-style cards.
// Pulled into a shared file so both dashboards render with the same modern
// look instead of duplicating the same chart chrome twice.
import { useEffect, useRef, useState } from 'react';

// ── Palette (matches the app's existing brand colors) ─────────────────────────

export const COLOR = {
  teal:   '#2E6E8E',
  navy:   '#1A2E40',
  light:  '#4A9BC4',
  green:  '#1D9E75',
  red:    '#E24B4A',
  amber:  '#EF9F27',
  slate:  '#94A3B8',
};

// ── One-time global keyframes for this kit's animations ────────────────────────

export function DashboardKeyframes() {
  return (
    <style>{`
      @keyframes dkCardIn {
        from { opacity: 0; transform: translateY(10px); }
        to   { opacity: 1; transform: translateY(0); }
      }
      @keyframes dkPulse {
        0%, 100% { opacity: 1; }
        50%      { opacity: 0.55; }
      }
      .dk-card {
        animation: dkCardIn 0.45s cubic-bezier(0.34, 1.56, 0.64, 1) both;
        transition: box-shadow 0.25s ease, transform 0.25s ease, border-color 0.25s ease;
      }
      .dk-card:hover {
        box-shadow: 0 8px 24px rgba(26,46,64,0.10);
        transform: translateY(-2px);
        border-color: #C5D2DC;
      }
      .dk-kpi::before {
        content: '';
        position: absolute; inset: 0;
        background: linear-gradient(135deg, rgba(46,110,142,0.05), transparent 60%);
        opacity: 0; transition: opacity 0.25s ease;
      }
      .dk-kpi:hover::before { opacity: 1; }
    `}</style>
  );
}

// ── Animated count-up for KPI numbers ──────────────────────────────────────────

export function useCountUp(target, duration = 900) {
  const [display, setDisplay] = useState(0);
  const prevRef = useRef(0);
  const rafRef = useRef(null);

  useEffect(() => {
    if (target == null || Number.isNaN(Number(target))) return undefined;
    const from = prevRef.current;
    const to = Number(target);
    const start = performance.now();
    const tick = (now) => {
      const p = Math.min(1, (now - start) / duration);
      const eased = 1 - Math.pow(1 - p, 3);
      setDisplay(from + (to - from) * eased);
      if (p < 1) rafRef.current = requestAnimationFrame(tick);
      else prevRef.current = to;
    };
    rafRef.current = requestAnimationFrame(tick);
    return () => rafRef.current && cancelAnimationFrame(rafRef.current);
  }, [target, duration]);

  return display;
}

// ── KPI card with animated value, delta badge, and hover accent ───────────────

export function DeltaBadge({ value }) {
  if (value === null || value === undefined) return null;
  const pos = value >= 0;
  return (
    <span style={{
      display: 'inline-flex', alignItems: 'center', gap: 3,
      fontSize: 12, fontWeight: 600, marginTop: 6,
      color: pos ? COLOR.green : COLOR.red,
    }}>
      {pos ? '▲' : '▼'} {pos ? '+' : ''}{value}%
    </span>
  );
}

export function KpiCard({ label, value, decimals = 0, suffix = '', sub, delta, accent, warn, icon, index = 0 }) {
  const numeric = value === null || value === undefined || value === '—' ? null : Number(value);
  const display = useCountUp(numeric);
  const color = warn ? COLOR.red : (accent || COLOR.navy);
  const shown = numeric === null
    ? '—'
    : decimals > 0
      ? `${display.toFixed(decimals)}${suffix}`
      : `${Math.round(display).toLocaleString()}${suffix}`;

  return (
    <div
      className="dk-card dk-kpi"
      style={{ ...kpiStyle.card, borderTop: `3px solid ${accent || '#DDE4EA'}`, animationDelay: `${index * 45}ms`, position: 'relative', overflow: 'hidden' }}
    >
      <div style={kpiStyle.top}>
        {icon && <span style={kpiStyle.icon}>{icon}</span>}
        <p style={kpiStyle.label}>{label}</p>
      </div>
      <p style={{ ...kpiStyle.value, color }}>{shown}</p>
      {sub && <p style={kpiStyle.sub}>{sub}</p>}
      <DeltaBadge value={delta} />
    </div>
  );
}

const kpiStyle = {
  card: { background: '#fff', border: '0.5px solid #DDE4EA', borderRadius: 12, padding: '18px 18px 16px' },
  top:  { display: 'flex', alignItems: 'center', gap: 6, marginBottom: 8 },
  icon: { fontSize: 15, lineHeight: 1 },
  label:{ margin: 0, fontSize: 11, fontWeight: 600, color: '#8BA5B8', textTransform: 'uppercase', letterSpacing: 0.5 },
  value:{ margin: '0 0 2px', fontSize: 27, fontWeight: 600, letterSpacing: -0.5 },
  sub:  { margin: 0, fontSize: 11, color: '#8BA5B8' },
};

// ── Chart card shell — glass-ish, animates in, lifts on hover ─────────────────

export function ChartCard({ title, subtitle, children, index = 0, action }) {
  return (
    <div className="dk-card" style={{ ...cardStyle.card, animationDelay: `${index * 60}ms` }}>
      <div style={cardStyle.head}>
        <div>
          <h3 style={cardStyle.title}>{title}</h3>
          {subtitle && <p style={cardStyle.subtitle}>{subtitle}</p>}
        </div>
        {action}
      </div>
      {children}
    </div>
  );
}

const cardStyle = {
  card: { background: '#fff', border: '0.5px solid #DDE4EA', borderRadius: 14, padding: '20px' },
  head: { display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 14 },
  title:{ margin: 0, fontSize: 14, fontWeight: 600, color: '#1A2E40' },
  subtitle: { margin: '2px 0 0', fontSize: 11, color: '#8BA5B8' },
};

// ── Empty state ────────────────────────────────────────────────────────────────

export function NoData({ h = 240, icon = '📊', text = 'No data available' }) {
  return (
    <div style={{ height: h, display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', color: '#94A3B8', gap: 6 }}>
      <div style={{ fontSize: 26, opacity: 0.7 }}>{icon}</div>
      <div style={{ fontSize: 13 }}>{text}</div>
    </div>
  );
}

// ── Shared gradient defs — drop as the first child inside any recharts chart ──

export function ChartGradients() {
  return (
    <defs>
      <linearGradient id="dkTeal" x1="0" y1="0" x2="0" y2="1">
        <stop offset="0%"  stopColor={COLOR.teal}  stopOpacity={0.95} />
        <stop offset="100%" stopColor={COLOR.teal} stopOpacity={0.35} />
      </linearGradient>
      <linearGradient id="dkTealArea" x1="0" y1="0" x2="0" y2="1">
        <stop offset="0%"  stopColor={COLOR.teal}  stopOpacity={0.35} />
        <stop offset="100%" stopColor={COLOR.teal} stopOpacity={0} />
      </linearGradient>
      <linearGradient id="dkSlateArea" x1="0" y1="0" x2="0" y2="1">
        <stop offset="0%"  stopColor={COLOR.slate} stopOpacity={0.25} />
        <stop offset="100%" stopColor={COLOR.slate} stopOpacity={0} />
      </linearGradient>
      <linearGradient id="dkGreen" x1="0" y1="0" x2="0" y2="1">
        <stop offset="0%"  stopColor={COLOR.green} stopOpacity={0.95} />
        <stop offset="100%" stopColor={COLOR.green} stopOpacity={0.45} />
      </linearGradient>
      <linearGradient id="dkRed" x1="0" y1="0" x2="0" y2="1">
        <stop offset="0%"  stopColor={COLOR.red} stopOpacity={0.95} />
        <stop offset="100%" stopColor={COLOR.red} stopOpacity={0.45} />
      </linearGradient>
      <linearGradient id="dkNavy" x1="0" y1="0" x2="0" y2="1">
        <stop offset="0%"  stopColor={COLOR.navy} stopOpacity={0.95} />
        <stop offset="100%" stopColor={COLOR.navy} stopOpacity={0.45} />
      </linearGradient>
      <linearGradient id="dkTealH" x1="0" y1="0" x2="1" y2="0">
        <stop offset="0%"  stopColor={COLOR.light} stopOpacity={0.9} />
        <stop offset="100%" stopColor={COLOR.teal}  stopOpacity={0.95} />
      </linearGradient>
    </defs>
  );
}

// ── Custom tooltip — replaces recharts' plain default box ──────────────────────

export function CustomTooltip({ active, payload, label, formatter, labelFormatter }) {
  if (!active || !payload || !payload.length) return null;
  return (
    <div style={tt.box}>
      {label !== undefined && label !== null && (
        <div style={tt.label}>{labelFormatter ? labelFormatter(label) : label}</div>
      )}
      {payload.map((p, i) => (
        <div key={i} style={tt.row}>
          <span style={{ ...tt.dot, background: p.color || p.fill || COLOR.teal }} />
          <span style={tt.name}>{p.name}</span>
          <span style={tt.value}>{formatter ? formatter(p.value, p.name, p) : p.value}</span>
        </div>
      ))}
    </div>
  );
}

const tt = {
  box: {
    background: 'rgba(26,46,64,0.94)', borderRadius: 10, padding: '10px 12px',
    boxShadow: '0 8px 24px rgba(0,0,0,0.18)', minWidth: 120,
  },
  label: { fontSize: 11, fontWeight: 600, color: '#93c5fd', marginBottom: 6, letterSpacing: 0.3 },
  row:   { display: 'flex', alignItems: 'center', gap: 7, fontSize: 12, color: '#fff', padding: '2px 0' },
  dot:   { width: 8, height: 8, borderRadius: '50%', flexShrink: 0 },
  name:  { color: '#CBD5E1', marginRight: 'auto' },
  value: { fontWeight: 700, color: '#fff', marginLeft: 10 },
};
