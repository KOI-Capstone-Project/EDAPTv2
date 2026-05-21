import { useState, useEffect, useRef } from 'react';
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, Legend,
  LineChart, Line, ResponsiveContainer,
} from 'recharts';
import api from '../services/api';

const TEAL   = '#2E6E8E';
const ORANGE = '#E8873A';
const GRAY   = '#94A3B8';

const fmtPct = v => v != null ? `${v}%` : '—';
const diff   = (a, b) => a != null && b != null ? +(a - b).toFixed(1) : null;

function KpiCard({ label, value, sub, change, warn }) {
  const d = change;
  return (
    <div style={s.kpiCard}>
      <p style={s.kpiLabel}>{label}</p>
      <p style={{ ...s.kpiValue, color: warn ? '#DC2626' : '#1E293B' }}>{value ?? '—'}</p>
      {sub && <p style={s.kpiSub}>{sub}</p>}
      {d != null && (
        <p style={{ ...s.kpiDelta, color: d >= 0 ? '#059669' : '#DC2626' }}>
          {d >= 0 ? '▲' : '▼'} {Math.abs(d)}% vs prev period
        </p>
      )}
    </div>
  );
}

function DifficultyBadge({ level }) {
  const colors = { Low: '#059669', Medium: '#D97706', High: '#DC2626' };
  return (
    <span style={{ ...s.badge, background: colors[level] + '18', color: colors[level] }}>
      {level} Difficulty
    </span>
  );
}

function SearchableSelect({ value, onChange, options, placeholder }) {
  const [open, setOpen] = useState(false);
  const [q,    setQ]    = useState('');
  const ref             = useRef(null);

  useEffect(() => {
    const h = e => { if (ref.current && !ref.current.contains(e.target)) setOpen(false); };
    document.addEventListener('mousedown', h);
    return () => document.removeEventListener('mousedown', h);
  }, []);

  const filtered = options.filter(o => o.toLowerCase().includes(q.toLowerCase()));

  return (
    <div ref={ref} style={{ position: 'relative', minWidth: 160 }}>
      <button
        type="button"
        onClick={() => { setOpen(o => !o); setQ(''); }}
        style={{
          ...s.select, display: 'flex', alignItems: 'center',
          justifyContent: 'space-between', width: '100%', cursor: 'pointer',
          color: value ? '#1E293B' : '#8BA5B8',
        }}
      >
        <span style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
          {value || placeholder}
        </span>
        <span style={{ fontSize: 10, color: '#8BA5B8', flexShrink: 0, marginLeft: 6 }}>▾</span>
      </button>
      {open && (
        <div style={{ position: 'absolute', top: '100%', left: 0, right: 0, zIndex: 300, background: '#fff', border: '0.5px solid #C5D2DC', borderRadius: 8, boxShadow: '0 4px 12px rgba(0,0,0,0.1)', marginTop: 4 }}>
          <input
            autoFocus
            value={q}
            onChange={e => setQ(e.target.value)}
            placeholder="Search…"
            style={{ width: '100%', padding: '8px 12px', border: 'none', borderBottom: '0.5px solid #F0F4F8', outline: 'none', fontSize: 13, boxSizing: 'border-box' }}
            onClick={e => e.stopPropagation()}
          />
          <div style={{ maxHeight: 200, overflowY: 'auto' }}>
            <div
              onClick={() => { onChange(''); setOpen(false); setQ(''); }}
              style={{ padding: '9px 12px', fontSize: 13, cursor: 'pointer', color: '#8BA5B8' }}
            >
              {placeholder}
            </div>
            {filtered.map(o => (
              <div
                key={o}
                onClick={() => { onChange(o); setOpen(false); setQ(''); }}
                style={{ padding: '9px 12px', fontSize: 13, cursor: 'pointer', color: '#1E293B', background: o === value ? '#F0F4F8' : 'transparent' }}
              >
                {o}
              </div>
            ))}
            {filtered.length === 0 && (
              <div style={{ padding: '9px 12px', fontSize: 13, color: '#94A3B8' }}>No matches</div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}

export default function SubjectAnalytics() {
  const [subjects,   setSubjects]   = useState([]);
  const [trimesters, setTrimesters] = useState([]);
  const [subjectA,   setSubjectA]   = useState('');
  const [subjectB,   setSubjectB]   = useState('');
  const [trimester,  setTrimester]  = useState('');
  const [data,       setData]       = useState(null);
  const [loading,    setLoading]    = useState(false);
  const [error,      setError]      = useState(null);

  useEffect(() => {
    api.get('/api/subjects/list').then(r => setSubjects(r.data)).catch(() => {});
    api.get('/api/explorer/filters').then(r => setTrimesters(r.data.trimesters || [])).catch(() => {});
  }, []);

  const handleLoad = async () => {
    if (!subjectA) return;
    setLoading(true);
    setError(null);
    try {
      const params = { subject_a: subjectA };
      if (subjectB)   params.subject_b = subjectB;
      if (trimester)  params.trimester = trimester;
      const res = await api.get('/api/subjects/analytics', { params });
      setData(res.data);
    } catch (err) {
      setError(err.response?.data?.detail || 'Failed to load analytics.');
    } finally {
      setLoading(false);
    }
  };

  const a = data?.subject_a;
  const b = data?.subject_b;

  // Merge grade distribution for grouped bar chart
  const gradeDist = a ? a.grade_distribution.map((row, i) => ({
    band:        row.band,
    [a.subject]: row.subject_count,
    ...(b ? { [b.subject]: b.grade_distribution[i]?.subject_count ?? 0 } : {}),
    Institution: row.institution_count,
  })) : [];

  // Merge performance trend by period
  const trendMap = {};
  if (a) {
    a.performance_trend.forEach(p => {
      trendMap[p.period] = { period: p.period, [a.subject]: p.subject_avg, Institution: p.institution_avg };
    });
  }
  if (b) {
    b.performance_trend.forEach(p => {
      if (!trendMap[p.period]) trendMap[p.period] = { period: p.period };
      trendMap[p.period][b.subject] = p.subject_avg;
    });
  }
  const trendData = Object.values(trendMap);

  // Merge assessment breakdown by type
  const typeMap = {};
  if (a) a.assessment_breakdown.forEach(ab => { typeMap[ab.type] = { type: ab.type, [a.subject]: ab.avg }; });
  if (b) b.assessment_breakdown.forEach(ab => {
    if (!typeMap[ab.type]) typeMap[ab.type] = { type: ab.type };
    typeMap[ab.type][b.subject] = ab.avg;
  });
  const breakdownData = Object.values(typeMap);

  return (
    <div style={s.page}>
      {/* Header */}
      <div style={s.pageHeader}>
        <div>
          <h1 style={s.pageTitle}>Subject Analytics</h1>
          <p style={s.pageSub}>Compare subject performance and grade distributions</p>
        </div>
      </div>

      {/* Filters */}
      <div style={s.card}>
        <div style={s.filterRow}>
          <div style={s.filterGroup}>
            <label style={s.filterLabel}>Subject A <span style={{ color: '#DC2626' }}>*</span></label>
            <SearchableSelect
              value={subjectA}
              onChange={v => { setSubjectA(v); setData(null); }}
              options={subjects}
              placeholder="Select subject…"
            />
          </div>
          <div style={s.filterGroup}>
            <label style={s.filterLabel}>Subject B <span style={{ color: '#94A3B8', fontSize: 11 }}>(compare)</span></label>
            <SearchableSelect
              value={subjectB}
              onChange={v => { setSubjectB(v); setData(null); }}
              options={subjects.filter(sv => sv !== subjectA)}
              placeholder="None"
            />
          </div>
          <div style={s.filterGroup}>
            <label style={s.filterLabel}>Trimester</label>
            <select style={s.select} value={trimester} onChange={e => { setTrimester(e.target.value); setData(null); }}>
              <option value="">All periods</option>
              {trimesters.map(t => <option key={t} value={t}>{t}</option>)}
            </select>
          </div>
          <button
            style={{ ...s.loadBtn, opacity: (!subjectA || loading) ? 0.55 : 1 }}
            disabled={!subjectA || loading}
            onClick={handleLoad}
          >
            {loading ? 'Loading…' : 'Load Analytics'}
          </button>
        </div>
        {error && <p style={s.errorMsg}>{error}</p>}
      </div>

      {/* Empty state */}
      {!a && !loading && (
        <div style={s.emptyCard}>
          <p style={s.emptyIcon}>📊</p>
          <p style={s.emptyText}>Select a subject and click <strong>Load Analytics</strong> to view insights.</p>
        </div>
      )}

      {/* Results */}
      {a && (
        <>
          {/* Subject headers */}
          <div style={s.subjectHeaders}>
            <div style={s.subjectBadge}>
              <span style={{ ...s.badge, background: TEAL + '18', color: TEAL }}>{a.subject}</span>
              <DifficultyBadge level={a.difficulty} />
              <span style={s.kpiSub}>{a.student_count} students</span>
            </div>
            {b && (
              <div style={s.subjectBadge}>
                <span style={{ ...s.badge, background: ORANGE + '18', color: ORANGE }}>{b.subject}</span>
                <DifficultyBadge level={b.difficulty} />
                <span style={s.kpiSub}>{b.student_count} students</span>
              </div>
            )}
          </div>

          {/* KPI row */}
          <div style={{ ...s.kpiRow, gridTemplateColumns: b ? 'repeat(4, 1fr)' : 'repeat(4, 1fr)' }}>
            {b ? (
              <>
                <KpiCard label={`${a.subject} — Avg Mark`} value={fmtPct(a.avg_mark)}
                  sub={`Institution: ${fmtPct(a.institution_avg)}`}
                  change={diff(a.avg_mark, a.prev_avg)} />
                <KpiCard label={`${b.subject} — Avg Mark`} value={fmtPct(b.avg_mark)}
                  sub={`Institution: ${fmtPct(b.institution_avg)}`}
                  change={diff(b.avg_mark, b.prev_avg)} />
                <KpiCard label={`${a.subject} — Pass Rate`} value={fmtPct(a.pass_rate)}
                  change={diff(a.pass_rate, a.prev_pass_rate)} warn={a.pass_rate < 50} />
                <KpiCard label={`${b.subject} — Pass Rate`} value={fmtPct(b.pass_rate)}
                  change={diff(b.pass_rate, b.prev_pass_rate)} warn={b.pass_rate < 50} />
              </>
            ) : (
              <>
                <KpiCard label="Average Mark" value={fmtPct(a.avg_mark)}
                  sub={`Institution: ${fmtPct(a.institution_avg)}`}
                  change={diff(a.avg_mark, a.prev_avg)} />
                <KpiCard label="Pass Rate" value={fmtPct(a.pass_rate)}
                  sub={`Institution: ${fmtPct(a.institution_pass_rate)}`}
                  change={diff(a.pass_rate, a.prev_pass_rate)} warn={a.pass_rate < 50} />
                <KpiCard label="Failure Rate" value={fmtPct(a.failure_rate)} warn={a.failure_rate > 40}
                  sub="≥40% is high difficulty" />
                <KpiCard label="Enrolled Students" value={a.student_count}
                  sub={`Difficulty: ${a.difficulty}`} />
              </>
            )}
          </div>

          {/* Charts row 1 */}
          <div style={s.chartGrid}>
            <div style={s.chartCard}>
              <h3 style={s.chartTitle}>Grade Distribution</h3>
              <ResponsiveContainer width="100%" height={220}>
                <BarChart data={gradeDist} barCategoryGap="20%">
                  <CartesianGrid strokeDasharray="3 3" stroke="#EEF0F4" vertical={false} />
                  <XAxis dataKey="band" tick={{ fontSize: 11, fill: '#64748B' }} />
                  <YAxis tick={{ fontSize: 11, fill: '#64748B' }} />
                  <Tooltip />
                  <Legend iconType="circle" iconSize={8} wrapperStyle={{ fontSize: 12 }} />
                  <Bar dataKey={a.subject} fill={TEAL} radius={[4, 4, 0, 0]} />
                  {b && <Bar dataKey={b.subject} fill={ORANGE} radius={[4, 4, 0, 0]} />}
                  <Bar dataKey="Institution" fill={GRAY} radius={[4, 4, 0, 0]} opacity={0.6} />
                </BarChart>
              </ResponsiveContainer>
            </div>

            <div style={s.chartCard}>
              <h3 style={s.chartTitle}>Performance Trend</h3>
              <ResponsiveContainer width="100%" height={220}>
                <LineChart data={trendData}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#EEF0F4" vertical={false} />
                  <XAxis dataKey="period" tick={{ fontSize: 11, fill: '#64748B' }} />
                  <YAxis tick={{ fontSize: 11, fill: '#64748B' }} domain={[0, 100]} unit="%" />
                  <Tooltip formatter={v => `${v}%`} />
                  <Legend iconType="circle" iconSize={8} wrapperStyle={{ fontSize: 12 }} />
                  <Line type="monotone" dataKey={a.subject} stroke={TEAL} strokeWidth={2} dot={{ r: 3 }} />
                  {b && <Line type="monotone" dataKey={b.subject} stroke={ORANGE} strokeWidth={2} dot={{ r: 3 }} />}
                  <Line type="monotone" dataKey="Institution" stroke={GRAY} strokeWidth={1.5}
                    dot={{ r: 2 }} strokeDasharray="4 3" />
                </LineChart>
              </ResponsiveContainer>
            </div>
          </div>

          {/* Assessment breakdown */}
          {breakdownData.length > 0 && (
            <div style={s.card}>
              <h3 style={s.chartTitle}>Assessment Type Breakdown — Average Mark</h3>
              <ResponsiveContainer width="100%" height={Math.max(160, breakdownData.length * 46)}>
                <BarChart data={breakdownData} layout="vertical" barCategoryGap="25%">
                  <CartesianGrid strokeDasharray="3 3" stroke="#EEF0F4" horizontal={false} />
                  <XAxis type="number" tick={{ fontSize: 11, fill: '#64748B' }} domain={[0, 100]} unit="%" />
                  <YAxis dataKey="type" type="category" tick={{ fontSize: 12, fill: '#475569' }} width={80} />
                  <Tooltip formatter={v => `${v}%`} />
                  <Legend iconType="circle" iconSize={8} wrapperStyle={{ fontSize: 12 }} />
                  <Bar dataKey={a.subject} fill={TEAL} radius={[0, 4, 4, 0]} />
                  {b && <Bar dataKey={b.subject} fill={ORANGE} radius={[0, 4, 4, 0]} />}
                </BarChart>
              </ResponsiveContainer>
            </div>
          )}

          {/* Trimester comparison (single subject only) */}
          {!b && a.trimester_comparison?.length > 0 && (
            <div style={s.card}>
              <h3 style={s.chartTitle}>Period-by-Period Comparison — {a.subject}</h3>
              <ResponsiveContainer width="100%" height={220}>
                <BarChart data={a.trimester_comparison} barCategoryGap="20%">
                  <CartesianGrid strokeDasharray="3 3" stroke="#EEF0F4" vertical={false} />
                  <XAxis dataKey="period" tick={{ fontSize: 11, fill: '#64748B' }} />
                  <YAxis tick={{ fontSize: 11, fill: '#64748B' }} domain={[0, 100]} unit="%" />
                  <Tooltip formatter={v => `${v}%`} />
                  <Legend iconType="circle" iconSize={8} wrapperStyle={{ fontSize: 12 }} />
                  <Bar dataKey="avg"       name="Avg Mark"  fill={TEAL}   radius={[4, 4, 0, 0]} />
                  <Bar dataKey="pass_rate" name="Pass Rate" fill='#1D9E75' radius={[4, 4, 0, 0]} />
                </BarChart>
              </ResponsiveContainer>
            </div>
          )}
        </>
      )}
    </div>
  );
}

const s = {
  page:       { padding: '28px 32px', background: '#F0F4F8', minHeight: '100vh', boxSizing: 'border-box' },
  pageHeader: { display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', marginBottom: 24 },
  pageTitle:  { margin: 0, fontSize: 20, fontWeight: 700, color: '#1A2E40' },
  pageSub:    { margin: '4px 0 0', fontSize: 13, color: '#64748B' },

  card: {
    background: '#fff', border: '0.5px solid #DDE4EA', borderRadius: 10,
    padding: '20px 24px', marginBottom: 20,
  },
  filterRow:   { display: 'flex', flexWrap: 'wrap', alignItems: 'flex-end', gap: 16 },
  filterGroup: { display: 'flex', flexDirection: 'column', gap: 4 },
  filterLabel: { fontSize: 11, fontWeight: 600, color: '#475569', textTransform: 'uppercase', letterSpacing: 0.5 },
  select: {
    border: '0.5px solid #C5D2DC', borderRadius: 8, padding: '8px 12px',
    fontSize: 13, color: '#1E293B', background: '#fff', outline: 'none',
    minWidth: 160, cursor: 'pointer',
  },
  loadBtn: {
    padding: '9px 22px', borderRadius: 8, border: 'none',
    background: '#2E6E8E', color: '#fff', fontSize: 13,
    fontWeight: 600, cursor: 'pointer', alignSelf: 'flex-end',
  },
  errorMsg: { margin: '12px 0 0', fontSize: 12, color: '#DC2626' },

  emptyCard: {
    background: '#fff', border: '0.5px solid #DDE4EA', borderRadius: 10,
    padding: '56px 24px', textAlign: 'center',
  },
  emptyIcon: { fontSize: 36, margin: '0 0 12px' },
  emptyText: { margin: 0, fontSize: 14, color: '#64748B' },

  subjectHeaders: { display: 'flex', gap: 20, marginBottom: 16, flexWrap: 'wrap' },
  subjectBadge:   { display: 'flex', alignItems: 'center', gap: 8 },
  badge: { fontSize: 12, fontWeight: 600, padding: '3px 10px', borderRadius: 20 },

  kpiRow:  { display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 16, marginBottom: 20 },
  kpiCard: {
    background: '#fff', border: '0.5px solid #DDE4EA', borderRadius: 10,
    padding: '16px 20px',
  },
  kpiLabel: { margin: 0, fontSize: 11, fontWeight: 600, color: '#64748B', textTransform: 'uppercase', letterSpacing: 0.5 },
  kpiValue: { margin: '8px 0 4px', fontSize: 24, fontWeight: 700, color: '#1E293B' },
  kpiSub:   { margin: 0, fontSize: 11, color: '#94A3B8' },
  kpiDelta: { margin: '6px 0 0', fontSize: 11, fontWeight: 600 },

  chartGrid: { display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 20, marginBottom: 20 },
  chartCard: {
    background: '#fff', border: '0.5px solid #DDE4EA', borderRadius: 10,
    padding: '20px 24px',
  },
  chartTitle: { margin: '0 0 16px', fontSize: 14, fontWeight: 600, color: '#1A2E40' },
};
