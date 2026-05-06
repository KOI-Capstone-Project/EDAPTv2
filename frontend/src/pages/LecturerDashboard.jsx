import { useEffect, useState, useCallback } from 'react';
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip,
  ResponsiveContainer, Legend, LineChart, Line,
  PieChart, Pie, Cell,
} from 'recharts';
import api from '../services/api';
import { getUser, getUserName } from '../utils/auth';
import GeminiPanel from '../components/GeminiPanel';

// ── Constants ─────────────────────────────────────────────────────────────────

const ALL_PERIODS  = ['23.1','23.2','23.3','24.1','24.2','24.3','25.1','25.2','25.3'];
const YEAR_PERIODS = { '2023':['23.1','23.2','23.3'], '2024':['24.1','24.2','24.3'], '2025':['25.1','25.2','25.3'] };
const GRADE_COLORS = band => parseInt(band.split('-')[0], 10) < 50 ? '#E24B4A' : '#1D9E75';
const DONUT_COLORS = ['#1D9E75','#E24B4A'];

// ── Helpers ───────────────────────────────────────────────────────────────────

const fmtPct = v => v != null ? `${Number(v).toFixed(1)}%` : '—';

function Spinner() {
  return (
    <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', height: 200 }}>
      <div style={{ width: 32, height: 32, border: '3px solid #F0F4F8', borderTop: '3px solid #2E6E8E', borderRadius: '50%', animation: 'spin 0.8s linear infinite' }} />
    </div>
  );
}

function NoData() {
  return (
    <div style={{ textAlign: 'center', padding: '48px 20px', color: '#8BA5B8' }}>
      <div style={{ fontSize: 28, marginBottom: 10 }}>📊</div>
      <div style={{ fontSize: 13, fontWeight: 500, color: '#1A2E40', marginBottom: 4 }}>No data available</div>
      <div style={{ fontSize: 12 }}>Try adjusting your filters</div>
    </div>
  );
}

function Delta({ val }) {
  if (val == null) return null;
  const pos = val >= 0;
  return (
    <span style={{ fontSize: 12, fontWeight: 500, color: pos ? '#1D9E75' : '#E24B4A', marginLeft: 6 }}>
      {pos ? '↑' : '↓'} {Math.abs(val).toFixed(1)}%
    </span>
  );
}

function PieLabel({ cx, cy, midAngle, innerRadius, outerRadius, percent }) {
  if (percent < 0.05) return null;
  const RADIAN = Math.PI / 180;
  const r = innerRadius + (outerRadius - innerRadius) * 0.5;
  const x = cx + r * Math.cos(-midAngle * RADIAN);
  const y = cy + r * Math.sin(-midAngle * RADIAN);
  return (
    <text x={x} y={y} fill="#fff" textAnchor="middle" dominantBaseline="central" fontSize={12} fontWeight={700}>
      {`${(percent * 100).toFixed(0)}%`}
    </text>
  );
}

// ── KPI Card ─────────────────────────────────────────────────────────────────

function KpiCard({ label, value, sub, delta, accent }) {
  const [hovered, setHovered] = useState(false);
  return (
    <div
      style={{
        ...s.kpiCard,
        borderTop: `3px solid ${accent || '#DDE4EA'}`,
        boxShadow: hovered ? '0 2px 8px rgba(0,0,0,0.06)' : 'none',
        transition: 'box-shadow 0.2s',
      }}
      onMouseEnter={() => setHovered(true)}
      onMouseLeave={() => setHovered(false)}
    >
      <p style={s.kpiLabel}>{label}</p>
      <p style={{ ...s.kpiValue, color: accent || '#1A2E40' }}>
        {value}
        {delta !== undefined && <Delta val={delta} />}
      </p>
      {sub && <p style={s.kpiSub}>{sub}</p>}
    </div>
  );
}

// ── Chart Card ────────────────────────────────────────────────────────────────

function ChartCard({ title, children }) {
  return (
    <div style={s.chartCard}>
      <h3 style={s.chartTitle}>{title}</h3>
      {children}
    </div>
  );
}

// ── Main Component ────────────────────────────────────────────────────────────

export default function LecturerDashboard() {
  const user       = getUser();
  const userName   = getUserName();
  const mySubjects = user?.subjects || [];

  // Filters — use full period values to match backend STUDYPERIOD format
  const [yearF,  setYearF]  = useState('');
  const [trimeF, setTrimeF] = useState('');
  const [subjF,  setSubjF]  = useState('');

  const trimeOptions = yearF ? (YEAR_PERIODS[yearF] || []) : ALL_PERIODS;

  const [summary,    setSummary]    = useState(null);
  const [gradeDist,  setGradeDist]  = useState([]);
  const [trend,      setTrend]      = useState([]);
  const [assessment, setAssessment] = useState([]);
  const [passFail,   setPassFail]   = useState([]);
  const [loading,    setLoading]    = useState(true);
  const [error,      setError]      = useState(null);

  const fetchAll = useCallback(() => {
    setLoading(true);
    setError(null);
    const p = {};
    if (subjF)  p.subject   = subjF;
    if (trimeF) p.trimester = trimeF;
    else if (yearF) p.year  = yearF;

    Promise.allSettled([
      api.get('/api/dashboard/summary',               { params: p }),
      api.get('/api/dashboard/grade-distribution',    { params: p }),
      api.get('/api/dashboard/performance-trend',     { params: p }),
      api.get('/api/dashboard/assessment-comparison', { params: p }),
      api.get('/api/dashboard/pass-fail',             { params: p }),
    ]).then(([sumR, gradeR, trendR, assessR, pfR]) => {
      if (sumR.status   === 'fulfilled') setSummary(sumR.value.data);
      if (gradeR.status === 'fulfilled') setGradeDist(gradeR.value.data.data   ?? []);
      if (assessR.status=== 'fulfilled') setAssessment(assessR.value.data.data ?? []);
      if (pfR.status    === 'fulfilled') setPassFail(pfR.value.data.breakdown   ?? []);

      if (trendR.status === 'fulfilled') {
        const raw = trendR.value.data.data ?? [];
        const byPeriod = Object.fromEntries(raw.map(r => [r.period, r]));
        setTrend(ALL_PERIODS.map(p => ({
          period:          p,
          institution_avg: byPeriod[p]?.institution_avg ?? null,
          subject_avg:     byPeriod[p]?.subject_avg     ?? null,
        })));
      }

      if ([sumR, gradeR, trendR, assessR, pfR].every(r => r.status === 'rejected')) {
        setError('Could not load dashboard data. Please check the backend.');
      }
    }).finally(() => setLoading(false));
  }, [subjF, trimeF, yearF]);

  useEffect(() => { fetchAll(); }, [fetchAll]);

  const atRisk     = summary?.at_risk_count ?? 0;
  const atRiskSubj = subjF || (mySubjects[0] || 'your subject');
  const noData     = !loading && summary?.total_students === 0;

  const avgMarkDelta  = summary?.avg_mark != null && summary?.avg_mark_prev != null
    ? +(summary.avg_mark  - summary.avg_mark_prev ).toFixed(1) : null;
  const passRateDelta = summary?.pass_rate != null && summary?.pass_rate_prev != null
    ? +(summary.pass_rate - summary.pass_rate_prev).toFixed(1) : null;

  return (
    <div>

      {/* ── Welcome banner ─────────────────────────────────────────── */}
      <div style={s.welcome}>
        <div style={s.welcomeBadge}>Lecturer</div>
        <p style={s.welcomeName}>Welcome back, {userName}</p>
        <p style={s.welcomeSub}>Here is your teaching performance overview.</p>
      </div>

      {/* ── At-risk banner ─────────────────────────────────────────── */}
      {!loading && atRisk > 0 && (
        <div style={s.riskBanner}>
          <span style={{ fontSize: 16 }}>⚠</span>
          <span>
            <strong>{atRisk} student{atRisk !== 1 ? 's' : ''}</strong> in{' '}
            <strong>{atRiskSubj}</strong> are currently below 50%. Consider early intervention.
          </span>
        </div>
      )}

      {/* ── Page header ────────────────────────────────────────────── */}
      <div style={s.pageHeader}>
        <h1 style={s.pageTitle}>Descriptive Analytics</h1>
        <p style={s.pageSub}>Mode 1 — performance overview for your assigned subjects</p>
      </div>

      {/* ── Filters ────────────────────────────────────────────────── */}
      <div style={s.filterCard}>
        <div style={s.filterRow}>
          <div style={s.filterGroup}>
            <label style={s.filterLabel}>Year</label>
            <select style={s.select} value={yearF} onChange={e => { setYearF(e.target.value); setTrimeF(''); }}>
              <option value="">All Years</option>
              <option value="2023">2023</option>
              <option value="2024">2024</option>
              <option value="2025">2025</option>
            </select>
          </div>
          <div style={s.filterGroup}>
            <label style={s.filterLabel}>Study Period</label>
            <select style={s.select} value={trimeF} onChange={e => setTrimeF(e.target.value)}>
              <option value="">All Periods</option>
              {trimeOptions.map(t => <option key={t} value={t}>{t}</option>)}
            </select>
          </div>
          <div style={s.filterGroup}>
            <label style={s.filterLabel}>Subject</label>
            <select style={s.select} value={subjF} onChange={e => setSubjF(e.target.value)}>
              <option value="">All My Subjects</option>
              {mySubjects.map(s => <option key={s} value={s}>{s}</option>)}
            </select>
          </div>
        </div>
      </div>

      {/* ── Loading / Error ─────────────────────────────────────────── */}
      {loading && <Spinner />}
      {error && !loading && (
        <div style={s.errorBanner}>
          <span>⚠ {error}</span>
          <button style={s.retryBtn} onClick={fetchAll}>Retry</button>
        </div>
      )}

      {/* ── No data warning ─────────────────────────────────────────── */}
      {noData && !error && (
        <div style={s.noBanner}>
          ⚠ No dataset loaded. Go to <strong>Data Ingestion</strong> to upload the CSV file.
        </div>
      )}

      {/* ── KPI Cards ──────────────────────────────────────────────── */}
      {!loading && !error && (
        <div style={s.kpiRow}>
          <KpiCard
            label="Total Students"
            value={summary?.total_students?.toLocaleString() ?? '—'}
            sub="in scope"
          />
          <KpiCard
            label="Average Mark"
            value={fmtPct(summary?.avg_mark)}
            delta={avgMarkDelta}
            sub="vs previous period"
          />
          <KpiCard
            label="Pass Rate"
            value={fmtPct(summary?.pass_rate)}
            delta={passRateDelta}
            sub="≥ 50% mark"
          />
          <KpiCard
            label="At Risk"
            value={summary?.at_risk_count?.toLocaleString() ?? '—'}
            sub="below 50%"
            accent="#E24B4A"
          />
        </div>
      )}

      {/* ── Charts ─────────────────────────────────────────────────── */}
      {!loading && !error && (
        <div style={s.chartGrid}>

          <ChartCard title="Grade Distribution">
            {noData || gradeDist.length === 0 ? <NoData /> : (
              <ResponsiveContainer width="100%" height={280}>
                <BarChart data={gradeDist} margin={{ top: 8, right: 16, left: 0, bottom: 8 }}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#F1F5F9" />
                  <XAxis dataKey="band" tick={{ fontSize: 11 }} />
                  <YAxis tick={{ fontSize: 11 }} />
                  <Tooltip />
                  <Bar dataKey="count" name="Students" radius={[4, 4, 0, 0]}>
                    {gradeDist.map(entry => (
                      <Cell key={entry.band} fill={GRADE_COLORS(entry.band)} />
                    ))}
                  </Bar>
                </BarChart>
              </ResponsiveContainer>
            )}
          </ChartCard>

          <ChartCard title="Performance Trend">
            <div style={s.legendRow}>
              <span style={{ ...s.dot, background: '#2E6E8E' }} /> My Subject(s)
              <span style={{ ...s.dot, background: '#94A3B8', marginLeft: 16 }} /> Institution Avg
            </div>
            {noData || trend.every(t => t.subject_avg == null && t.institution_avg == null) ? <NoData /> : (
              <ResponsiveContainer width="100%" height={260}>
                <LineChart data={trend} margin={{ top: 8, right: 16, left: 0, bottom: 8 }}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#F1F5F9" />
                  <XAxis dataKey="period" type="category" tick={{ fontSize: 11 }} />
                  <YAxis domain={[0, 100]} unit="%" tick={{ fontSize: 11 }} />
                  <Tooltip formatter={v => v != null ? `${Number(v).toFixed(1)}%` : 'N/A'} />
                  <Line type="monotone" dataKey="subject_avg"     name="My Subject(s)"   stroke="#2E6E8E" strokeWidth={2} dot={{ r: 3 }} connectNulls />
                  <Line type="monotone" dataKey="institution_avg" name="Institution Avg" stroke="#94A3B8" strokeWidth={1.5} strokeDasharray="4 3" dot={false} connectNulls />
                </LineChart>
              </ResponsiveContainer>
            )}
          </ChartCard>

          <ChartCard title="Assessment Type Comparison">
            {noData || assessment.length === 0 ? <NoData /> : (
              <ResponsiveContainer width="100%" height={280}>
                <BarChart data={assessment} margin={{ top: 8, right: 16, left: 0, bottom: 8 }}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#F1F5F9" />
                  <XAxis dataKey="type" tick={{ fontSize: 11 }} />
                  <YAxis domain={[0, 100]} unit="%" tick={{ fontSize: 11 }} />
                  <Tooltip formatter={v => `${Number(v).toFixed(1)}%`} />
                  <Legend verticalAlign="top" />
                  <Bar dataKey="avg_mark"  name="Avg Mark %"  fill="#2E6E8E" radius={[4,4,0,0]} />
                  <Bar dataKey="pass_rate" name="Pass Rate %"  fill="#1D9E75" radius={[4,4,0,0]} />
                </BarChart>
              </ResponsiveContainer>
            )}
          </ChartCard>

          <ChartCard title="Pass / Fail Breakdown">
            {noData || passFail.length === 0 ? <NoData /> : (
              <>
                <ResponsiveContainer width="100%" height={220}>
                  <PieChart>
                    <Pie
                      data={passFail}
                      dataKey="count"
                      nameKey="status"
                      innerRadius="38%"
                      outerRadius="62%"
                      labelLine={false}
                      label={PieLabel}
                    >
                      {passFail.map((entry, i) => (
                        <Cell key={entry.status} fill={DONUT_COLORS[i % DONUT_COLORS.length]} />
                      ))}
                    </Pie>
                    <Tooltip formatter={(v, name) => [v.toLocaleString(), name]} />
                  </PieChart>
                </ResponsiveContainer>
                <div style={s.donutLegend}>
                  {passFail.map((entry, i) => (
                    <span key={entry.status} style={s.donutLegendItem}>
                      <span style={{ ...s.dot, background: DONUT_COLORS[i % DONUT_COLORS.length] }} />
                      {entry.status}: <strong>{entry.count?.toLocaleString()}</strong>
                    </span>
                  ))}
                </div>
              </>
            )}
          </ChartCard>

        </div>
      )}

      {/* ── AI Insights ────────────────────────────────────────────── */}
      <GeminiPanel
        subject={subjF}
        trimester={trimeF}
      />
    </div>
  );
}

// ── Styles ────────────────────────────────────────────────────────────────────

const s = {
  welcome: {
    background: 'linear-gradient(135deg, #1A2E40 0%, #2E6E8E 100%)',
    borderRadius: 12, padding: '20px 28px', marginBottom: 16, color: '#fff',
  },
  welcomeBadge: {
    display: 'inline-block', background: 'rgba(255,255,255,0.12)',
    border: '1px solid rgba(255,255,255,0.2)', color: 'rgba(255,255,255,0.85)',
    borderRadius: 20, padding: '2px 12px', fontSize: 11, fontWeight: 600,
    letterSpacing: 0.4, marginBottom: 8,
  },
  welcomeName: { margin: '0 0 4px', fontSize: 18, fontWeight: 600, color: '#fff' },
  welcomeSub:  { margin: 0, fontSize: 13, opacity: 0.7 },

  riskBanner: {
    display: 'flex', alignItems: 'center', gap: 10,
    background: '#FAEEDA', border: '0.5px solid #EF9F27',
    borderRadius: 10, padding: '12px 16px', marginBottom: 16,
    fontSize: 13, color: '#633806',
  },

  pageHeader:  { marginBottom: 20 },
  pageTitle:   { margin: '0 0 4px', fontSize: 24, fontWeight: 500, color: '#1A2E40' },
  pageSub:     { margin: 0, fontSize: 13, color: '#5A7A8A' },

  filterCard:  { background: '#fff', border: '0.5px solid #DDE4EA', borderRadius: 12, padding: '14px 16px', marginBottom: 24 },
  filterRow:   { display: 'flex', gap: 12, flexWrap: 'wrap', alignItems: 'flex-end' },
  filterGroup: { display: 'flex', flexDirection: 'column', gap: 4 },
  filterLabel: { fontSize: 11, fontWeight: 600, color: '#8BA5B8', textTransform: 'uppercase', letterSpacing: 0.5 },
  select: {
    height: 36, padding: '0 12px', borderRadius: 8,
    border: '0.5px solid #C5D2DC', fontSize: 13, color: '#1A2E40',
    background: '#fff', cursor: 'pointer', minWidth: 150, outline: 'none',
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
    borderRadius: 8, padding: '10px 16px', fontSize: 13, marginBottom: 16,
  },

  kpiRow: { display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 16, marginBottom: 24 },
  kpiCard: {
    background: '#fff', border: '0.5px solid #DDE4EA',
    borderRadius: 12, padding: '20px',
  },
  kpiLabel: { margin: '0 0 8px', fontSize: 11, fontWeight: 600, color: '#8BA5B8', textTransform: 'uppercase', letterSpacing: 0.5 },
  kpiValue: { margin: '0 0 4px', fontSize: 28, fontWeight: 500, letterSpacing: -0.5, display: 'flex', alignItems: 'center', color: '#1A2E40' },
  kpiSub:   { margin: 0, fontSize: 12, color: '#8BA5B8' },

  chartGrid: { display: 'grid', gridTemplateColumns: 'repeat(2, 1fr)', gap: 20 },
  chartCard: { background: '#fff', border: '0.5px solid #DDE4EA', borderRadius: 12, padding: '20px' },
  chartTitle: { margin: '0 0 14px', fontSize: 14, fontWeight: 500, color: '#1A2E40' },

  legendRow: { display: 'flex', alignItems: 'center', fontSize: 12, color: '#5A7A8A', marginBottom: 8 },
  dot: { display: 'inline-block', width: 10, height: 10, borderRadius: '50%', marginRight: 5 },
  donutLegend: { display: 'flex', gap: 20, marginTop: 8, justifyContent: 'center' },
  donutLegendItem: { display: 'flex', alignItems: 'center', gap: 6, fontSize: 13, color: '#475569' },
};
