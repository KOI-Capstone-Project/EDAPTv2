import { useState, useEffect, useRef } from 'react';
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, Legend,
  LineChart, Line, ResponsiveContainer,
} from 'recharts';
import api from '../services/api';

const ALL_PERIODS = ['23.1','23.2','23.3','24.1','24.2','24.3','25.1','25.2','25.3'];

// ── Helpers ───────────────────────────────────────────────────────────────────

function Spinner() {
  return (
    <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', height: 200 }}>
      <div style={{ width: 32, height: 32, border: '3px solid #F0F4F8', borderTop: '3px solid #2E6E8E', borderRadius: '50%', animation: 'spin 0.8s linear infinite' }} />
    </div>
  );
}

// ── Searchable dropdown ───────────────────────────────────────────────────────

function SearchableSelect({ value, onChange, options, placeholder }) {
  const [q, setQ]       = useState('');
  const [open, setOpen] = useState(false);
  const ref             = useRef(null);

  useEffect(() => {
    const h = e => { if (ref.current && !ref.current.contains(e.target)) setOpen(false); };
    document.addEventListener('mousedown', h);
    return () => document.removeEventListener('mousedown', h);
  }, []);

  const filtered = q ? options.filter(o => o.toLowerCase().includes(q.toLowerCase())) : options;

  return (
    <div ref={ref} style={{ position: 'relative', minWidth: 200 }}>
      <div style={s.ssWrap}>
        <input
          style={s.ssInput}
          value={value || q}
          placeholder={placeholder}
          onChange={e => { setQ(e.target.value); if (value) onChange(''); setOpen(true); }}
          onFocus={() => setOpen(true)}
        />
        {(value || q) && (
          <button style={s.ssClear} onMouseDown={e => { e.preventDefault(); onChange(''); setQ(''); setOpen(false); }}>✕</button>
        )}
      </div>
      {open && filtered.length > 0 && (
        <div style={s.ssDrop}>
          {filtered.slice(0, 60).map(o => (
            <div key={o} style={s.ssItem}
              onMouseDown={e => { e.preventDefault(); onChange(o); setQ(''); setOpen(false); }}>
              {o}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

// ── Subject column ────────────────────────────────────────────────────────────

function SubjectColumn({ stats, selectedTrimester, label }) {
  if (!stats) return null;

  const vs        = parseFloat((stats.avg_mark - stats.institution_avg).toFixed(1));
  const diffColor = stats.difficulty === 'Low' ? '#1D9E75' : stats.difficulty === 'Medium' ? '#D97706' : '#DC2626';

  const passTrendVal = stats.prev_pass_rate != null
    ? parseFloat((stats.pass_rate - stats.prev_pass_rate).toFixed(1)) : null;

  return (
    <div>
      {label && (
        <div style={s.colHeader}>{label}</div>
      )}

      {/* ── 3 KPI cards ──────────────────────────────────────────── */}
      <div style={s.kpiRow}>
        <div style={s.kpiCard}>
          <p style={s.kpiLabel}>Average Grade</p>
          <p style={s.kpiValue}>{stats.avg_mark}%</p>
          <p style={s.kpiSub}>Institution avg: {stats.institution_avg}%</p>
          <span style={{ ...s.badge, background: vs >= 0 ? '#E1F5EE' : '#FCEBEB', color: vs >= 0 ? '#0F6E56' : '#A32D2D' }}>
            {vs >= 0 ? `+${vs}%` : `${vs}%`} {vs >= 0 ? 'above' : 'below'} average
          </span>
        </div>

        <div style={s.kpiCard}>
          <p style={s.kpiLabel}>Pass Rate</p>
          <p style={s.kpiValue}>{stats.pass_rate}%</p>
          <p style={s.kpiSub}>Institution: {stats.institution_pass_rate}%</p>
          {passTrendVal !== null && (
            <p style={{ fontSize: 12, fontWeight: 500, marginTop: 4, color: passTrendVal >= 0 ? '#1D9E75' : '#DC2626' }}>
              {passTrendVal >= 0 ? `↑ +${passTrendVal}%` : `↓ ${passTrendVal}%`} vs prev period
            </p>
          )}
        </div>

        <div style={s.kpiCard}>
          <p style={s.kpiLabel}>Subject Difficulty</p>
          <p style={{ ...s.kpiValue, color: diffColor }}>{stats.difficulty}</p>
          <p style={s.kpiSub}>{stats.failure_rate}% failure rate</p>
          <p style={{ fontSize: 11, color: '#8BA5B8', marginTop: 2 }}>{stats.student_count.toLocaleString()} students</p>
        </div>
      </div>

      {/* Chart 1: Grade Distribution */}
      <div style={s.chartCard}>
        <h3 style={s.chartTitle}>Grade Distribution — Subject vs Institution</h3>
        <ResponsiveContainer width="100%" height={280}>
          <BarChart data={stats.grade_distribution} margin={{ top: 4, right: 12, left: 0, bottom: 0 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="#F1F5F9" />
            <XAxis dataKey="band" tick={{ fontSize: 10 }} />
            <YAxis tick={{ fontSize: 11 }} />
            <Tooltip />
            <Legend />
            <Bar dataKey="subject_count"     name="Subject"     fill="#2E6E8E" radius={[3,3,0,0]} />
            <Bar dataKey="institution_count" name="Institution" fill="#94A3B8" radius={[3,3,0,0]} />
          </BarChart>
        </ResponsiveContainer>
      </div>

      {/* Chart 2: Performance Trend */}
      <div style={s.chartCard}>
        <h3 style={s.chartTitle}>Performance Trend</h3>
        <ResponsiveContainer width="100%" height={280}>
          <LineChart data={stats.performance_trend} margin={{ top: 4, right: 12, left: 0, bottom: 0 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="#F1F5F9" />
            <XAxis dataKey="period" type="category" tick={{ fontSize: 11 }} />
            <YAxis domain={[0, 100]} unit="%" tick={{ fontSize: 11 }} />
            <Tooltip formatter={v => v != null ? `${v}%` : 'N/A'} />
            <Legend />
            <Line type="monotone" dataKey="subject_avg"     name="Subject Avg"     stroke="#2E6E8E" strokeWidth={2}   dot={{ r: 3 }} connectNulls />
            <Line type="monotone" dataKey="institution_avg" name="Institution Avg" stroke="#1A2E40" strokeWidth={1.5} strokeDasharray="4 3" dot={false} connectNulls />
          </LineChart>
        </ResponsiveContainer>
      </div>

      {/* Chart 3: Assessment Type */}
      {stats.assessment_breakdown.length > 0 && (
        <div style={s.chartCard}>
          <h3 style={s.chartTitle}>Assessment Type Performance</h3>
          <ResponsiveContainer width="100%" height={Math.max(160, stats.assessment_breakdown.length * 42)}>
            <BarChart layout="vertical" data={stats.assessment_breakdown} margin={{ top: 4, right: 50, left: 0, bottom: 0 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="#F1F5F9" horizontal={false} />
              <XAxis type="number" domain={[0, 100]} unit="%" tick={{ fontSize: 11 }} />
              <YAxis type="category" dataKey="type" width={70} tick={{ fontSize: 11 }} />
              <Tooltip formatter={v => `${v}%`} />
              <Bar dataKey="avg" name="Avg Mark %" fill="#2E6E8E" radius={[0,3,3,0]} />
            </BarChart>
          </ResponsiveContainer>
        </div>
      )}

      {/* Chart 4: Trimester Comparison table */}
      <div style={s.chartCard}>
        <h3 style={s.chartTitle}>Trimester Comparison</h3>
        <div style={{ overflowX: 'auto' }}>
          <table style={s.table}>
            <thead>
              <tr style={s.thead}>
                <th style={s.th}>Study Period</th>
                <th style={s.th}>Avg Mark</th>
                <th style={s.th}>Pass Rate</th>
                <th style={s.th}>Student Count</th>
              </tr>
            </thead>
            <tbody>
              {stats.trimester_comparison.map((row, i) => {
                const highlighted = row.period === selectedTrimester;
                return (
                  <tr key={row.period} style={{ background: highlighted ? '#DFF0FA' : (i % 2 === 0 ? '#fff' : '#F8FAFB') }}>
                    <td style={{ ...s.td, fontWeight: highlighted ? 600 : 400, color: highlighted ? '#185FA5' : '#1A2E40' }}>{row.period}</td>
                    <td style={s.td}>{row.avg}%</td>
                    <td style={s.td}>{row.pass_rate}%</td>
                    <td style={s.td}>{row.count.toLocaleString()}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}

// ── Main component ────────────────────────────────────────────────────────────

export default function SubjectAnalytics() {
  const [subjects,  setSubjects]  = useState([]);
  const [subjectA,  setSubjectA]  = useState('');
  const [subjectB,  setSubjectB]  = useState('');
  const [trimester, setTrimester] = useState('');
  const [data,      setData]      = useState(null);
  const [loading,   setLoading]   = useState(false);
  const [error,     setError]     = useState('');

  useEffect(() => {
    api.get('/api/subjects/list').then(r => setSubjects(r.data)).catch(() => {});
  }, []);

  useEffect(() => {
    if (!subjectA) { setData(null); return; }
    setLoading(true);
    setError('');
    const params = { subject_a: subjectA };
    if (trimester) params.trimester = trimester;
    if (subjectB)  params.subject_b = subjectB;
    api.get('/api/subjects/analytics', { params })
      .then(r => setData(r.data))
      .catch(err => setError(err.response?.data?.detail || 'Failed to load analytics.'))
      .finally(() => setLoading(false));
  }, [subjectA, subjectB, trimester]);

  const comparing = !!(data?.subject_a && data?.subject_b);

  return (
    <div>
      <div style={s.pageHeader}>
        <h1 style={s.pageTitle}>
          {comparing ? `${subjectA} vs ${subjectB}` : 'Subject Analytics'}
        </h1>
        <p style={s.pageSub}>Comprehensive performance insights and comparative analysis</p>
      </div>

      {/* ── Scope selector ──────────────────────────────────────────── */}
      <div style={s.scopeCard}>
        <div style={s.scopeRow}>
          <div style={s.scopeField}>
            <label style={s.scopeLabel}>Subject A <span style={{ color: '#DC2626' }}>*</span></label>
            <SearchableSelect
              value={subjectA}
              onChange={v => { setSubjectA(v); if (!v) setSubjectB(''); }}
              options={subjects}
              placeholder="Select subject…"
            />
          </div>
          <div style={s.scopeField}>
            <label style={s.scopeLabel}>Study Period</label>
            <select style={s.select} value={trimester} onChange={e => setTrimester(e.target.value)}>
              <option value="">All Periods</option>
              {ALL_PERIODS.map(p => <option key={p} value={p}>{p}</option>)}
            </select>
          </div>
          <div style={s.scopeField}>
            <label style={s.scopeLabel}>Compare with (optional)</label>
            <SearchableSelect
              value={subjectB}
              onChange={setSubjectB}
              options={subjects.filter(s => s !== subjectA)}
              placeholder="Add subject B…"
            />
          </div>
        </div>
        {!subjectA && (
          <p style={{ margin: '10px 0 0', fontSize: 12, color: '#8BA5B8' }}>Select Subject A to begin.</p>
        )}
      </div>

      {error && (
        <div style={s.errorBox}>{error}</div>
      )}
      {loading && <Spinner />}

      {/* ── Content ─────────────────────────────────────────────────── */}
      {!loading && data?.subject_a && (
        comparing ? (
          <div style={s.compareGrid}>
            <SubjectColumn stats={data.subject_a} selectedTrimester={trimester} label={subjectA} />
            <SubjectColumn stats={data.subject_b} selectedTrimester={trimester} label={subjectB} />
          </div>
        ) : (
          <SubjectColumn stats={data.subject_a} selectedTrimester={trimester} />
        )
      )}
    </div>
  );
}

// ── Styles ────────────────────────────────────────────────────────────────────

const s = {
  pageHeader: { marginBottom: 24 },
  pageTitle:  { margin: '0 0 4px', fontSize: 24, fontWeight: 500, color: '#1A2E40' },
  pageSub:    { margin: 0, fontSize: 13, color: '#5A7A8A' },

  scopeCard:  { background: '#fff', border: '0.5px solid #DDE4EA', borderRadius: 12, padding: '16px 20px', marginBottom: 24 },
  scopeRow:   { display: 'flex', gap: 20, flexWrap: 'wrap', alignItems: 'flex-end' },
  scopeField: { display: 'flex', flexDirection: 'column', gap: 6 },
  scopeLabel: { fontSize: 11, fontWeight: 600, color: '#8BA5B8', textTransform: 'uppercase', letterSpacing: 0.5 },
  select: {
    height: 36, padding: '0 12px', borderRadius: 8,
    border: '0.5px solid #C5D2DC', fontSize: 13, color: '#1A2E40',
    background: '#fff', cursor: 'pointer', minWidth: 170, outline: 'none',
  },

  ssWrap:  { display: 'flex', alignItems: 'center', border: '0.5px solid #C5D2DC', borderRadius: 8, background: '#fff', overflow: 'hidden' },
  ssInput: { flex: 1, padding: '9px 12px', border: 'none', outline: 'none', fontSize: 13, color: '#1A2E40', background: 'transparent', minWidth: 0 },
  ssClear: { padding: '0 10px', background: 'none', border: 'none', cursor: 'pointer', color: '#94A3B8', fontSize: 12, flexShrink: 0 },
  ssDrop: {
    position: 'absolute', top: '100%', left: 0, right: 0, zIndex: 200,
    background: '#fff', border: '0.5px solid #C5D2DC', borderRadius: 8,
    maxHeight: 220, overflowY: 'auto', boxShadow: '0 4px 12px rgba(0,0,0,0.1)',
  },
  ssItem: { padding: '9px 14px', fontSize: 13, cursor: 'pointer', color: '#1A2E40', borderBottom: '0.5px solid #F8FAFB' },

  errorBox: {
    background: '#FCEBEB', border: '0.5px solid #F09595',
    color: '#A32D2D', borderRadius: 8, padding: '10px 16px', fontSize: 13, marginBottom: 16,
  },

  compareGrid: { display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 24 },

  colHeader: {
    margin: '0 0 16px', fontSize: 15, fontWeight: 600, color: '#fff',
    padding: '10px 16px', background: '#1A2E40', borderRadius: 8,
  },

  kpiRow:  { display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 12, marginBottom: 16 },
  kpiCard: {
    background: '#fff', border: '0.5px solid #DDE4EA', borderRadius: 12, padding: '20px 16px',
    transition: 'box-shadow 0.2s',
  },
  kpiLabel: { margin: '0 0 8px', fontSize: 11, fontWeight: 600, color: '#8BA5B8', textTransform: 'uppercase', letterSpacing: 0.5 },
  kpiValue: { margin: '0 0 4px', fontSize: 28, fontWeight: 500, color: '#1A2E40', letterSpacing: -0.5 },
  kpiSub:   { margin: 0, fontSize: 11, color: '#5A7A8A' },
  badge:    { display: 'inline-block', marginTop: 6, padding: '3px 10px', borderRadius: 20, fontSize: 11, fontWeight: 500 },

  chartCard:  { background: '#fff', border: '0.5px solid #DDE4EA', borderRadius: 12, padding: '20px', marginBottom: 16 },
  chartTitle: { margin: '0 0 14px', fontSize: 14, fontWeight: 500, color: '#1A2E40' },

  table: { width: '100%', borderCollapse: 'collapse', fontSize: 13 },
  thead: { background: '#F0F4F8' },
  th: { padding: '12px 16px', fontSize: 11, fontWeight: 500, color: '#5A7A8A', textTransform: 'uppercase', letterSpacing: 0.5, textAlign: 'left', borderBottom: '0.5px solid #F0F4F8' },
  td: { padding: '12px 16px', color: '#1A2E40', borderBottom: '0.5px solid #F0F4F8' },
};
