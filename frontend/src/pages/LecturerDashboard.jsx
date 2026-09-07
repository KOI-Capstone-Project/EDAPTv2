// Lecturer dashboard with subject-scoped KPI cards, grade chart, and trend line.
import { useEffect, useState, useCallback } from 'react';
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip,
  ResponsiveContainer, Legend, AreaChart, Area,
  PieChart, Pie, Cell,
} from 'recharts';
import api from '../services/api';
import { getUser, getUserName } from '../utils/auth';
import GeminiPanel from '../components/GeminiPanel';
import {
  DashboardKeyframes, KpiCard, ChartCard, NoData, chartGradientDefs, CustomTooltip, COLOR,
  gradUrl, useChartGradUid,
} from '../components/DashboardKit';

// ── Constants ─────────────────────────────────────────────────────────────────

const ALL_PERIODS  = ['23.1','23.2','23.3','24.1','24.2','24.3','25.1','25.2','25.3'];
const YEAR_PERIODS = { '2023':['23.1','23.2','23.3'], '2024':['24.1','24.2','24.3'], '2025':['25.1','25.2','25.3'] };
const DONUT_COLORS = ['#1D9E75','#E24B4A'];

// ── Helpers ───────────────────────────────────────────────────────────────────

function Spinner() {
  return (
    <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', height: 200 }}>
      <div style={{ width: 32, height: 32, border: '3px solid #F0F4F8', borderTop: '3px solid #2E6E8E', borderRadius: '50%', animation: 'spin 0.8s linear infinite' }} />
    </div>
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
  const [attOutcome, setAttOutcome] = useState(null);
  const [attBySubj,  setAttBySubj]  = useState(null);
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
      api.get('/api/dashboard/attendance-outcome',    { params: p }),
      api.get('/api/dashboard/attendance-by-subject'),
    ]).then(([sumR, gradeR, trendR, assessR, pfR, aoR, abR]) => {
      if (sumR.status   === 'fulfilled') setSummary(sumR.value.data);
      if (gradeR.status === 'fulfilled') setGradeDist(gradeR.value.data.data   ?? []);
      if (assessR.status=== 'fulfilled') setAssessment(assessR.value.data.data ?? []);
      if (pfR.status    === 'fulfilled') setPassFail(pfR.value.data.breakdown   ?? []);
      if (aoR.status    === 'fulfilled') setAttOutcome(aoR.value.data);
      if (abR.status    === 'fulfilled') setAttBySubj(abR.value.data.data ?? []);

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

  // Distinct gradient-id namespace per chart card — see useChartGradUid's
  // docstring in DashboardKit.jsx for why this can't just be a literal id.
  const gid = useChartGradUid();

  const atRisk     = summary?.at_risk_count ?? 0;
  const atRiskSubj = subjF || (mySubjects[0] || 'your subject');
  const noData     = !loading && summary?.total_students === 0;

  const avgMarkDelta  = summary?.avg_mark != null && summary?.avg_mark_prev != null
    ? +(summary.avg_mark  - summary.avg_mark_prev ).toFixed(1) : null;
  const passRateDelta = summary?.pass_rate != null && summary?.pass_rate_prev != null
    ? +(summary.pass_rate - summary.pass_rate_prev).toFixed(1) : null;

  return (
    <div>
      <DashboardKeyframes />

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
            index={0} icon="🎓"
            label="Total Students"
            value={summary?.total_students}
            sub="in scope"
          />
          <KpiCard
            index={1} icon="📈"
            label="Average Mark"
            value={summary?.avg_mark}
            decimals={1} suffix="%"
            accent={COLOR.teal}
            delta={avgMarkDelta}
            sub="vs previous period"
          />
          <KpiCard
            index={2} icon="✅"
            label="Pass Rate"
            value={summary?.pass_rate}
            decimals={1} suffix="%"
            accent={COLOR.green}
            delta={passRateDelta}
            sub="≥ 50% mark"
          />
          <KpiCard
            index={3} icon="⚠️"
            label="At Risk"
            value={summary?.at_risk_count}
            sub="below 50%"
            warn
          />
        </div>
      )}

      {/* ── Charts ─────────────────────────────────────────────────── */}
      {!loading && !error && (
        <div style={s.chartGrid}>

          <ChartCard index={0} title="Grade Distribution" subtitle="Students per mark band">
            {noData || gradeDist.length === 0 ? <NoData /> : (
              <ResponsiveContainer width="100%" height={280}>
                <BarChart data={gradeDist} margin={{ top: 8, right: 16, left: 0, bottom: 8 }}>
                  {chartGradientDefs(gid(0))}
                  <CartesianGrid strokeDasharray="3 3" stroke="#F1F5F9" vertical={false} />
                  <XAxis dataKey="band" tick={{ fontSize: 11 }} axisLine={{ stroke: '#E2E8F0' }} tickLine={false} />
                  <YAxis tick={{ fontSize: 11 }} axisLine={false} tickLine={false} />
                  <Tooltip content={<CustomTooltip />} cursor={{ fill: 'rgba(46,110,142,0.06)' }} />
                  <Bar dataKey="count" name="Students" radius={[6, 6, 0, 0]} animationDuration={900} animationEasing="ease-out">
                    {gradeDist.map(entry => (
                      <Cell key={entry.band} fill={parseInt(entry.band.split('-')[0], 10) < 50 ? gradUrl(gid(0), 'red') : gradUrl(gid(0), 'green')} />
                    ))}
                  </Bar>
                </BarChart>
              </ResponsiveContainer>
            )}
          </ChartCard>

          <ChartCard index={1} title="Performance Trend" subtitle="My subject(s) vs institution average">
            {noData || trend.every(t => t.subject_avg == null && t.institution_avg == null) ? <NoData /> : (
              <ResponsiveContainer width="100%" height={260}>
                <AreaChart data={trend} margin={{ top: 8, right: 16, left: 0, bottom: 8 }}>
                  {chartGradientDefs(gid(1))}
                  <CartesianGrid strokeDasharray="3 3" stroke="#F1F5F9" vertical={false} />
                  <XAxis dataKey="period" type="category" tick={{ fontSize: 11 }} axisLine={{ stroke: '#E2E8F0' }} tickLine={false} />
                  <YAxis domain={[0, 100]} unit="%" tick={{ fontSize: 11 }} axisLine={false} tickLine={false} />
                  <Tooltip content={<CustomTooltip formatter={v => v != null ? `${Number(v).toFixed(1)}%` : 'N/A'} />} />
                  <Legend wrapperStyle={{ fontSize: 12 }} />
                  <Area type="monotone" dataKey="subject_avg"     name="My Subject(s)"   stroke={COLOR.teal}  strokeWidth={2.5}
                    fill={gradUrl(gid(1), 'tealArea')} dot={{ r: 3 }} activeDot={{ r: 5 }} connectNulls animationDuration={1000} />
                  <Area type="monotone" dataKey="institution_avg" name="Institution Avg" stroke={COLOR.slate} strokeWidth={1.5}
                    strokeDasharray="4 3" fill={gradUrl(gid(1), 'slateArea')} dot={false} activeDot={{ r: 5 }} connectNulls animationDuration={1000} />
                </AreaChart>
              </ResponsiveContainer>
            )}
          </ChartCard>

          <ChartCard index={2} title="Assessment Type Comparison" subtitle="Average mark and pass rate by type">
            {noData || assessment.length === 0 ? <NoData /> : (
              <ResponsiveContainer width="100%" height={280}>
                <BarChart data={assessment} margin={{ top: 8, right: 16, left: 0, bottom: 8 }}>
                  {chartGradientDefs(gid(2))}
                  <CartesianGrid strokeDasharray="3 3" stroke="#F1F5F9" vertical={false} />
                  <XAxis dataKey="type" tick={{ fontSize: 11 }} axisLine={{ stroke: '#E2E8F0' }} tickLine={false} />
                  <YAxis domain={[0, 100]} unit="%" tick={{ fontSize: 11 }} axisLine={false} tickLine={false} />
                  <Tooltip content={<CustomTooltip formatter={v => `${Number(v).toFixed(1)}%`} />} cursor={{ fill: 'rgba(46,110,142,0.06)' }} />
                  <Legend verticalAlign="top" wrapperStyle={{ fontSize: 12 }} />
                  <Bar dataKey="avg_mark"  name="Avg Mark %"  fill={gradUrl(gid(2), 'teal')}  radius={[6,6,0,0]} animationDuration={900} animationEasing="ease-out" />
                  <Bar dataKey="pass_rate" name="Pass Rate %" fill={gradUrl(gid(2), 'green')} radius={[6,6,0,0]} animationDuration={900} animationEasing="ease-out" />
                </BarChart>
              </ResponsiveContainer>
            )}
          </ChartCard>

          <ChartCard index={3} title="Pass / Fail Breakdown" subtitle="Outcome split for the current scope">
            {noData || passFail.length === 0 ? <NoData /> : (
              <>
                <ResponsiveContainer width="100%" height={220}>
                  <PieChart>
                    {chartGradientDefs(gid(3))}
                    <Pie
                      data={passFail}
                      dataKey="count"
                      nameKey="status"
                      innerRadius="38%"
                      outerRadius="62%"
                      paddingAngle={3}
                      cornerRadius={6}
                      labelLine={false}
                      label={PieLabel}
                      animationDuration={900}
                      animationEasing="ease-out"
                    >
                      {passFail.map((entry, i) => (
                        <Cell key={entry.status} fill={i % 2 === 0 ? gradUrl(gid(3), 'green') : gradUrl(gid(3), 'red')} />
                      ))}
                    </Pie>
                    <Tooltip content={<CustomTooltip formatter={(v, name) => [v.toLocaleString(), name]} />} />
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

          <ChartCard index={4} title="Attendance vs Outcome" subtitle="Average attendance, pass vs fail">
            {noData || !attOutcome || attOutcome.n === 0 ? <NoData /> : (
              <>
                <ResponsiveContainer width="100%" height={260}>
                  <BarChart
                    data={[
                      { status: 'Pass', rate: attOutcome.mean_attendance_pass },
                      { status: 'Fail', rate: attOutcome.mean_attendance_fail },
                    ]}
                    margin={{ top: 8, right: 16, left: 0, bottom: 8 }}
                  >
                    {chartGradientDefs(gid(4))}
                    <CartesianGrid strokeDasharray="3 3" stroke="#F1F5F9" vertical={false} />
                    <XAxis dataKey="status" tick={{ fontSize: 11 }} axisLine={{ stroke: '#E2E8F0' }} tickLine={false} />
                    <YAxis domain={[0, 100]} unit="%" tick={{ fontSize: 11 }} axisLine={false} tickLine={false} />
                    <Tooltip content={<CustomTooltip formatter={v => `${v}%`} />} cursor={{ fill: 'rgba(46,110,142,0.06)' }} />
                    <Bar dataKey="rate" name="Avg Attendance %" radius={[6,6,0,0]} animationDuration={900} animationEasing="ease-out">
                      <Cell fill={gradUrl(gid(4), 'green')} />
                      <Cell fill={gradUrl(gid(4), 'red')} />
                    </Bar>
                  </BarChart>
                </ResponsiveContainer>
                <p style={s.chartFootnote}>
                  Correlation {attOutcome.correlation} · n={attOutcome.n?.toLocaleString()} · {attOutcome.population}
                </p>
              </>
            )}
          </ChartCard>

          <ChartCard index={5} title="Attendance by Subject">
            {noData || !attBySubj || attBySubj.length === 0 ? <NoData /> : (
              <>
                <ResponsiveContainer width="100%" height={Math.max(220, attBySubj.length * 26)}>
                  <BarChart layout="vertical" data={attBySubj} margin={{ top: 8, right: 30, left: 0, bottom: 8 }}>
                    {chartGradientDefs(gid(5))}
                    <CartesianGrid strokeDasharray="3 3" stroke="#F1F5F9" horizontal={false} />
                    <XAxis type="number" domain={[0, 100]} unit="%" tick={{ fontSize: 10 }} axisLine={false} tickLine={false} />
                    <YAxis type="category" dataKey="SUBJECTCODE" width={80} tick={{ fontSize: 10 }} axisLine={false} tickLine={false} />
                    <Tooltip content={<CustomTooltip formatter={v => `${v}%`} />} cursor={{ fill: 'rgba(46,110,142,0.06)' }} />
                    <Bar dataKey="avg_attendance_rate" name="Avg Attendance %" fill={gradUrl(gid(5), 'tealH')} radius={[0,6,6,0]} animationDuration={900} animationEasing="ease-out" />
                  </BarChart>
                </ResponsiveContainer>
                <p style={s.chartFootnote}>My assigned subject(s) only</p>
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

  chartGrid: { display: 'grid', gridTemplateColumns: 'repeat(2, 1fr)', gap: 20 },
  chartFootnote: { margin: '10px 0 0', fontSize: 10.5, color: '#8BA5B8', lineHeight: 1.4 },

  dot: { display: 'inline-block', width: 10, height: 10, borderRadius: '50%', marginRight: 5 },
  donutLegend: { display: 'flex', gap: 20, marginTop: 8, justifyContent: 'center' },
  donutLegendItem: { display: 'flex', alignItems: 'center', gap: 6, fontSize: 13, color: '#475569' },
};
