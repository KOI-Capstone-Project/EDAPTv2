import { useState, useEffect, useCallback, useRef } from 'react';
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, Legend, Cell,
  LineChart, Line, PieChart, Pie, ResponsiveContainer,
} from 'recharts';
import api from '../services/api';
import { getUserName } from '../utils/auth';

const ALL_PERIODS   = ['23.1','23.2','23.3','24.1','24.2','24.3','25.1','25.2','25.3'];
const YEAR_PERIODS  = { '2023':['23.1','23.2','23.3'], '2024':['24.1','24.2','24.3'], '2025':['25.1','25.2','25.3'] };

// ── Tiny helpers ──────────────────────────────────────────────────────────────

const NoData = ({ h = 220 }) => (
  <div style={{ height: h, display: 'flex', alignItems: 'center', justifyContent: 'center', color: '#94A3B8', fontSize: 13 }}>
    No data available
  </div>
);

const ChartCard = ({ title, children }) => (
  <div style={s.chartCard}>
    <h3 style={s.chartTitle}>{title}</h3>
    {children}
  </div>
);

const RADIAN = Math.PI / 180;
const PieLabel = ({ cx, cy, midAngle, innerRadius, outerRadius, percent }) => {
  const r = innerRadius + (outerRadius - innerRadius) * 0.55;
  const x = cx + r * Math.cos(-midAngle * RADIAN);
  const y = cy + r * Math.sin(-midAngle * RADIAN);
  return percent > 0.04 ? (
    <text x={x} y={y} fill="#fff" textAnchor="middle" dominantBaseline="central" fontSize={12} fontWeight={700}>
      {(percent * 100).toFixed(1)}%
    </text>
  ) : null;
};

const delta = (curr, prev) =>
  curr != null && prev != null ? +(curr - prev).toFixed(1) : null;

// ── Summary card ──────────────────────────────────────────────────────────────

function SummaryCard({ label, value, sub, change, warn, green }) {
  const d = change;
  return (
    <div style={s.kpiCard}>
      <p style={s.kpiLabel}>{label}</p>
      <p style={{ ...s.kpiValue, color: warn ? '#DC2626' : green ? '#059669' : '#1E293B' }}>
        {value ?? '—'}
      </p>
      {sub  && <p style={s.kpiSub}>{sub}</p>}
      {d !== null && d !== undefined && (
        <p style={{ fontSize: 12, marginTop: 4, color: d >= 0 ? '#059669' : '#DC2626', fontWeight: 500 }}>
          {d >= 0 ? '↑' : '↓'} {d >= 0 ? '+' : ''}{d}%
        </p>
      )}
    </div>
  );
}

// ── Searchable subject dropdown ───────────────────────────────────────────────

function SearchableSelect({ value, onChange, options, placeholder }) {
  const [open,  setOpen]  = useState(false);
  const [query, setQuery] = useState('');
  const ref = useRef(null);

  useEffect(() => {
    if (!open) return;
    const close = (e) => { if (ref.current && !ref.current.contains(e.target)) { setOpen(false); setQuery(''); } };
    document.addEventListener('mousedown', close);
    return () => document.removeEventListener('mousedown', close);
  }, [open]);

  const filtered = query
    ? options.filter(o => o.toLowerCase().includes(query.toLowerCase()))
    : options;

  return (
    <div ref={ref} style={{ position: 'relative' }}>
      <button
        type="button"
        onClick={() => { setOpen(v => !v); setQuery(''); }}
        style={{
          padding: '9px 32px 9px 12px', background: '#2E6E8E', color: '#fff',
          border: 'none', borderRadius: 8, fontSize: 13, fontWeight: 500,
          cursor: 'pointer', minWidth: 150, textAlign: 'left',
          backgroundImage: `url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='12' height='12' viewBox='0 0 24 24' fill='none' stroke='white' stroke-width='2.5'%3E%3Cpolyline points='6 9 12 15 18 9'/%3E%3C/svg%3E")`,
          backgroundRepeat: 'no-repeat', backgroundPosition: 'right 10px center',
        }}
      >
        {value || placeholder}
      </button>
      {open && (
        <div style={{
          position: 'absolute', top: 'calc(100% + 4px)', left: 0, zIndex: 200,
          background: '#fff', border: '1px solid #DDE4EA', borderRadius: 8,
          boxShadow: '0 4px 16px rgba(0,0,0,0.10)', minWidth: 180,
        }}>
          <div style={{ padding: '8px 8px 4px' }}>
            <input
              autoFocus
              value={query}
              onChange={e => setQuery(e.target.value)}
              placeholder="Search…"
              style={{
                width: '100%', padding: '6px 10px', border: '1px solid #E2E8F0',
                borderRadius: 6, fontSize: 12, color: '#1E293B', outline: 'none',
                boxSizing: 'border-box', background: '#F8FAFC',
              }}
            />
          </div>
          <div style={{ maxHeight: 200, overflowY: 'auto' }}>
            <div
              onClick={() => { onChange(''); setOpen(false); setQuery(''); }}
              style={{ padding: '8px 12px', fontSize: 13, cursor: 'pointer', color: '#64748B' }}
              onMouseEnter={e => e.currentTarget.style.background = '#F0F4F8'}
              onMouseLeave={e => e.currentTarget.style.background = 'transparent'}
            >
              {placeholder}
            </div>
            {filtered.map(opt => (
              <div
                key={opt}
                onClick={() => { onChange(opt); setOpen(false); setQuery(''); }}
                style={{
                  padding: '8px 12px', fontSize: 13, cursor: 'pointer',
                  color: '#1E293B', fontWeight: value === opt ? 600 : 400,
                  background: value === opt ? '#EFF6FF' : 'transparent',
                }}
                onMouseEnter={e => { if (value !== opt) e.currentTarget.style.background = '#F0F4F8'; }}
                onMouseLeave={e => { if (value !== opt) e.currentTarget.style.background = 'transparent'; }}
              >
                {opt}
              </div>
            ))}
            {filtered.length === 0 && (
              <div style={{ padding: '8px 12px', fontSize: 12, color: '#94A3B8' }}>No matches</div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}

// ── Main component ────────────────────────────────────────────────────────────

export default function AdminDashboard() {
  // Cause 5 — safe read (computed before hooks, no early return here)
  const _rawUser = (() => {
    try { return JSON.parse(localStorage.getItem('edapt_user') || 'null'); }
    catch { return null; }
  })();

  const userName = getUserName();

  // Filters
  const [yearF,  setYearF]  = useState('');
  const [trimeF, setTrimeF] = useState('');
  const [subjF,  setSubjF]  = useState('');
  const [cgF,    setCgF]    = useState('');

  // Reference data
  const [subjects,    setSubjects]    = useState([]);
  const [classgroups, setClassgroups] = useState([]);

  // Chart data
  const [summary,     setSummary]     = useState(null);
  const [gradeDist,   setGradeDist]   = useState([]);
  const [trend,       setTrend]       = useState([]);
  const [assessment,  setAssessment]  = useState([]);
  const [passFail,    setPassFail]    = useState(null);
  const [intl,        setIntl]        = useState([]);
  const [difficulty,  setDifficulty]  = useState([]);
  const [loading,     setLoading]     = useState(true);
  const [error,       setError]       = useState(null);

  // Trimesters available for the selected year
  const trimeOptions = yearF ? (YEAR_PERIODS[yearF] || []) : ALL_PERIODS;

  // Load subjects once
  useEffect(() => {
    api.get('/api/filters').then(r => setSubjects(r.data.subjects || [])).catch(() => {});
  }, []);

  // Reload classgroups when subject changes
  useEffect(() => {
    const params = subjF ? { subject: subjF } : {};
    api.get('/api/dashboard/classgroups', { params })
      .then(r => setClassgroups(r.data.classgroups || []))
      .catch(() => setClassgroups([]));
    setCgF('');
  }, [subjF]);

  // Main data fetch — refires whenever any filter changes
  const fetchAll = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const p = {};
      if (trimeF) p.trimester = trimeF;
      else if (yearF) p.year = yearF;
      if (subjF) p.subject    = subjF;
      if (cgF)   p.classgroup = cgF;

      const [sumR, grR, trR, asR, pfR, inR, diR] = await Promise.allSettled([
        api.get('/api/dashboard/summary',               { params: p }),
        api.get('/api/dashboard/grade-distribution',    { params: p }),
        api.get('/api/dashboard/performance-trend',     { params: { subject: subjF || undefined, classgroup: cgF || undefined } }),
        api.get('/api/dashboard/assessment-comparison', { params: p }),
        api.get('/api/dashboard/pass-fail',             { params: p }),
        api.get('/api/dashboard/international',         { params: { trimester: trimeF || undefined, year: yearF || undefined } }),
        api.get('/api/dashboard/difficulty-index'),
      ]);

      if (sumR.status === 'fulfilled') setSummary(sumR.value.data);
      if (grR.status  === 'fulfilled') setGradeDist(grR.value.data.data  || []);
      if (trR.status  === 'fulfilled') setTrend(trR.value.data.data      || []);
      if (asR.status  === 'fulfilled') setAssessment(asR.value.data.data || []);
      if (pfR.status  === 'fulfilled') setPassFail(pfR.value.data);
      if (inR.status  === 'fulfilled') setIntl(inR.value.data.data       || []);
      if (diR.status  === 'fulfilled') setDifficulty(diR.value.data.data || []);

      if ([sumR, grR, trR, asR, pfR, inR, diR].every(r => r.status === 'rejected')) {
        setError('Could not load dashboard data. Check that the backend is running.');
      }
    } catch (err) {
      console.error('Dashboard error:', err);
      setError('Failed to load dashboard data.');
    } finally {
      setLoading(false);
    }
  }, [trimeF, yearF, subjF, cgF]);

  useEffect(() => { fetchAll(); }, [fetchAll]);

  // Cause 5 — redirect after hooks if user is missing/corrupt
  useEffect(() => {
    if (!_rawUser) window.location.href = '/login';
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  // Build full trend array (all 9 periods, fill null for missing)
  const trendData = ALL_PERIODS.map(period => {
    const row = trend.find(d => String(d.period) === period);
    return { period, institution_avg: row?.institution_avg ?? null, subject_avg: row?.subject_avg ?? null };
  });

  const noData = !loading && summary?.total_students === 0;

  // Difficulty index — top 20, colour top-10 red
  const diffTop20 = difficulty.slice(0, 20);

  // Cause 6 — always return valid JSX; null guard after all hooks
  if (!_rawUser) return null;

  return (
    <div>

      {/* ── Welcome ─────────────────────────────────────────────── */}
      <div style={s.welcome}>
        <div style={s.badge}>Head of Technology</div>
        <p style={s.wSub}>Welcome back, {userName}</p>
        <p style={s.wDesc}>Here is your institution-wide performance overview.</p>
      </div>

      {/* ── Loading / error states ──────────────────────────────── */}
      {loading && (
        <div style={s.loadingBanner}>
          <div style={{ width: 32, height: 32, border: '3px solid #F0F4F8', borderTop: '3px solid #2E6E8E', borderRadius: '50%', animation: 'spin 0.8s linear infinite' }} />
        </div>
      )}
      {error && !loading && (
        <div style={s.errorBanner}>
          <span>⚠ {error}</span>
          <button style={s.retryBtn} onClick={fetchAll}>Retry</button>
        </div>
      )}

      {/* ── No data warning ─────────────────────────────────────── */}
      {!loading && !error && noData && (
        <div style={s.noBanner}>
          ⚠ No dataset loaded. Go to <strong>Data Ingestion</strong> to upload the CSV file.
        </div>
      )}

      {/* ── Scope selectors ─────────────────────────────────────── */}
      <div style={s.scopeRow}>
        <select style={s.select} value={yearF} onChange={e => { setYearF(e.target.value); setTrimeF(''); }}>
          <option value="">All Years</option>
          <option value="2023">2023</option>
          <option value="2024">2024</option>
          <option value="2025">2025</option>
        </select>

        <select style={s.select} value={trimeF} onChange={e => setTrimeF(e.target.value)}>
          <option value="">All Trimesters</option>
          {trimeOptions.map(t => <option key={t} value={t}>{t}</option>)}
        </select>

        <SearchableSelect
          value={subjF}
          onChange={setSubjF}
          options={subjects}
          placeholder="All Subjects"
        />

        <select style={s.select} value={cgF} onChange={e => setCgF(e.target.value)}>
          <option value="">All Lecturers</option>
          {classgroups.map(cg => <option key={cg} value={cg}>{cg}</option>)}
        </select>
      </div>

      {/* ── 6 Summary cards ─────────────────────────────────────── */}
      {!loading && !error && <div style={s.kpiRow}>
        <SummaryCard label="Total Students"       value={summary?.total_students?.toLocaleString()} sub="unique enrolments" />
        <SummaryCard label="Total Subjects"        value={summary?.total_subjects} sub="subject codes" />
        <SummaryCard label="Institution Avg Mark"  value={summary?.avg_mark != null ? `${summary.avg_mark}%` : '—'}
          change={delta(summary?.avg_mark, summary?.avg_mark_prev)} />
        <SummaryCard label="Institution Pass Rate" value={summary?.pass_rate != null ? `${summary.pass_rate}%` : '—'}
          change={delta(summary?.pass_rate, summary?.pass_rate_prev)} />
        <SummaryCard label="Total At Risk"         value={summary?.at_risk_count?.toLocaleString()} sub="below 50%" warn />
        <SummaryCard label="Countries"             value={summary?.countries_count} sub="represented" />
      </div>}

      {/* ── Charts (2-col grid) ──────────────────────────────────── */}
      {!loading && !error && <div style={s.chartGrid}>

        {/* Chart 1 — Grade Distribution */}
        <ChartCard title="Grade Distribution">
          {gradeDist.length === 0 ? <NoData /> : (
            <ResponsiveContainer width="100%" height={280}>
              <BarChart data={gradeDist} margin={{ top: 4, right: 12, left: 0, bottom: 0 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="#F1F5F9" />
                <XAxis dataKey="band" tick={{ fontSize: 11 }} />
                <YAxis tick={{ fontSize: 11 }} />
                <Tooltip />
                <Bar dataKey="count" name="Students" radius={[3,3,0,0]}>
                  {gradeDist.map((entry, i) => (
                    <Cell key={i} fill={parseInt(entry.band.split('-')[0]) < 50 ? '#E24B4A' : '#1D9E75'} />
                  ))}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          )}
        </ChartCard>

        {/* Chart 2 — Performance Trend */}
        <ChartCard title="Performance Trend">
          {trendData.every(d => d.institution_avg === null) ? <NoData /> : (
            <ResponsiveContainer width="100%" height={280}>
              <LineChart data={trendData} margin={{ top: 4, right: 12, left: 0, bottom: 0 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="#F1F5F9" />
                <XAxis dataKey="period" type="category" tick={{ fontSize: 11 }} />
                <YAxis domain={[0, 100]} unit="%" tick={{ fontSize: 11 }} />
                <Tooltip formatter={v => v !== null ? `${v}%` : 'No data'} />
                <Legend />
                <Line type="monotone" dataKey="institution_avg" name="Institution Avg" stroke="#2E6E8E" strokeWidth={2} dot={false} connectNulls />
                {(subjF || cgF) && (
                  <Line type="monotone" dataKey="subject_avg" name="Selected Avg" stroke="#1A2E40" strokeWidth={2} strokeDasharray="5 3" dot={false} connectNulls />
                )}
              </LineChart>
            </ResponsiveContainer>
          )}
        </ChartCard>

        {/* Chart 3 — Assessment Type Comparison */}
        <ChartCard title="Assessment Type Comparison">
          {assessment.length === 0 ? <NoData /> : (
            <ResponsiveContainer width="100%" height={280}>
              <BarChart data={assessment} margin={{ top: 4, right: 12, left: 0, bottom: 0 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="#F1F5F9" />
                <XAxis dataKey="type" tick={{ fontSize: 11 }} />
                <YAxis domain={[0, 100]} unit="%" tick={{ fontSize: 11 }} />
                <Tooltip formatter={v => `${v}%`} />
                <Bar dataKey="avg_mark" name="Avg Mark %" fill="#2E6E8E" radius={[3,3,0,0]} />
              </BarChart>
            </ResponsiveContainer>
          )}
        </ChartCard>

        {/* Chart 4 — Pass / Fail Donut */}
        <ChartCard title="Pass / Fail">
          {!passFail || (passFail.pass_count === 0 && passFail.fail_count === 0) ? <NoData /> : (
            <ResponsiveContainer width="100%" height={280}>
              <PieChart>
                <Pie
                  data={[{ name: 'Pass', value: passFail.pass_count }, { name: 'Fail', value: passFail.fail_count }]}
                  innerRadius="38%" outerRadius="62%"
                  dataKey="value" labelLine={false} label={PieLabel}
                >
                  <Cell fill="#1D9E75" />
                  <Cell fill="#E24B4A" />
                </Pie>
                <Tooltip formatter={(v, name) => [v.toLocaleString(), name]} />
                <Legend />
              </PieChart>
            </ResponsiveContainer>
          )}
        </ChartCard>

        {/* Chart 5 — International Performance (admin only, horizontal) */}
        <ChartCard title="International Performance">
          {intl.length === 0 ? <NoData /> : (
            <div style={{ overflowY: 'auto', maxHeight: 320 }}>
              <ResponsiveContainer width="100%" height={Math.max(260, intl.length * 22)}>
                <BarChart layout="vertical" data={intl} margin={{ top: 4, right: 40, left: 0, bottom: 0 }}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#F1F5F9" horizontal={false} />
                  <XAxis type="number" domain={[0, 100]} unit="%" tick={{ fontSize: 10 }} />
                  <YAxis type="category" dataKey="country" width={90} tick={{ fontSize: 10 }} />
                  <Tooltip formatter={v => `${v}%`} />
                  <Bar dataKey="avg_mark" name="Avg Mark %" fill="#2E6E8E" radius={[0,3,3,0]} />
                </BarChart>
              </ResponsiveContainer>
            </div>
          )}
        </ChartCard>

        {/* Chart 6 — Subject Difficulty Index (admin only) */}
        <ChartCard title="Subject Difficulty Index">
          {diffTop20.length === 0 ? <NoData /> : (
            <ResponsiveContainer width="100%" height={280}>
              <BarChart data={diffTop20} margin={{ top: 4, right: 12, left: 0, bottom: 50 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="#F1F5F9" />
                <XAxis dataKey="subject" tick={{ fontSize: 9 }} angle={-40} textAnchor="end" interval={0} />
                <YAxis domain={[0, 100]} unit="%" tick={{ fontSize: 11 }} />
                <Tooltip formatter={v => `${v}%`} />
                <Bar dataKey="failure_rate" name="Failure Rate %" radius={[3,3,0,0]}>
                  {diffTop20.map((_, i) => <Cell key={i} fill={i < 10 ? '#E24B4A' : '#1A2E40'} />)}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          )}
        </ChartCard>

      </div>}
    </div>
  );
}

// ── Styles ────────────────────────────────────────────────────────────────────

const s = {
  welcome: {
    background: 'linear-gradient(135deg, #1A2E40 0%, #2E6E8E 100%)',
    borderRadius: 12, padding: '22px 28px', marginBottom: 24, color: '#fff',
  },
  badge: {
    display: 'inline-block',
    background: 'rgba(79,142,247,0.22)', border: '1px solid rgba(79,142,247,0.35)',
    color: '#93c5fd', borderRadius: 20, padding: '3px 12px',
    fontSize: 11, fontWeight: 600, letterSpacing: 0.4, marginBottom: 8,
  },
  wSub:  { margin: '0 0 4px', fontSize: 18, fontWeight: 600, color: '#fff' },
  wDesc: { margin: 0, fontSize: 13, opacity: 0.70 },

  loadingBanner: {
    display: 'flex', alignItems: 'center', justifyContent: 'center', height: 200,
  },
  errorBanner: {
    display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 12,
    background: 'rgba(220,38,38,0.07)', border: '1px solid rgba(220,38,38,0.2)',
    color: '#DC2626', borderRadius: 8, padding: '12px 16px', fontSize: 13, marginBottom: 16,
  },
  retryBtn: {
    padding: '6px 14px', borderRadius: 6, border: '1px solid #DC2626',
    background: 'none', color: '#DC2626', fontSize: 12, fontWeight: 600, cursor: 'pointer',
  },

  noBanner: {
    background: '#FFFBEB', border: '1px solid #FDE68A', color: '#92400E',
    borderRadius: 8, padding: '10px 16px', fontSize: 13, marginBottom: 20,
  },

  scopeRow: { display: 'flex', gap: 10, marginBottom: 24, flexWrap: 'wrap' },
  select: {
    padding: '9px 32px 9px 12px', background: '#2E6E8E', color: '#fff',
    border: 'none', borderRadius: 8, fontSize: 13, fontWeight: 500, cursor: 'pointer',
    appearance: 'none', minWidth: 150,
    backgroundImage: `url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='12' height='12' viewBox='0 0 24 24' fill='none' stroke='white' stroke-width='2.5'%3E%3Cpolyline points='6 9 12 15 18 9'/%3E%3C/svg%3E")`,
    backgroundRepeat: 'no-repeat', backgroundPosition: 'right 10px center',
  },

  kpiRow: { display: 'grid', gridTemplateColumns: 'repeat(6, 1fr)', gap: 14, marginBottom: 28 },
  kpiCard: { background: '#fff', border: '0.5px solid #DDE4EA', borderRadius: 12, padding: '20px 18px', transition: 'box-shadow 0.2s' },
  kpiLabel: { margin: '0 0 8px', fontSize: 11, fontWeight: 600, color: '#8BA5B8', textTransform: 'uppercase', letterSpacing: 0.5 },
  kpiValue: { margin: '0 0 4px', fontSize: 28, fontWeight: 500, letterSpacing: -0.5 },
  kpiSub:   { margin: 0, fontSize: 11, color: '#8BA5B8' },

  chartGrid: { display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 20 },
  chartCard: { background: '#fff', border: '0.5px solid #DDE4EA', borderRadius: 12, padding: '20px' },
  chartTitle: { margin: '0 0 14px', fontSize: 14, fontWeight: 500, color: '#1A2E40' },
};
