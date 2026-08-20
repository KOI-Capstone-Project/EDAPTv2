// Students at Risk — cross-subject risk view for one study period. Backed
// by GET /api/students-at-risk, which aggregates the same per-subject roster
// logic /api/subjects/{subject}/roster already uses (see that endpoint in
// backend/app/main.py) — so a student's risk_band here can never disagree
// with what the Predictor page shows for the same subject/period. Clicking
// a row deep-links into Predictor (?subject=X&period=Y) for the full
// drill-down (SHAP factors, intervention logging) rather than duplicating
// that here.
import { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { isAdmin as checkIsAdmin } from '../utils/auth';
import api from '../services/api';
import { RiskBadge, MidTermTag } from '../components/RiskBadge';

const TABS = [
  { key: 'at_risk', label: 'At Risk' },
  { key: 'safe',    label: 'Safe' },
  { key: 'all',     label: 'All' },
];

function matchesTab(row, tab) {
  if (tab === 'all') return true;
  if (tab === 'safe') return row.risk_band === 'Safe';
  // 'at_risk': At Risk + High Risk. A row with no band at all (insufficient
  // coverage, or the model unavailable) isn't a risk signal — it belongs
  // under "All" only, not asserted as either safe or at risk.
  return row.risk_band === 'At Risk' || row.risk_band === 'High Risk';
}

export default function StudentsAtRisk() {
  const navigate = useNavigate();
  const admin = checkIsAdmin();

  const [periods,     setPeriods]     = useState([]);
  const [studyPeriod, setStudyPeriod] = useState('');

  const [loading, setLoading] = useState(false);
  const [error,   setError]   = useState(null);
  const [students, setStudents] = useState([]);
  const [subjectsIncluded, setSubjectsIncluded] = useState(0);

  const [tab,    setTab]    = useState('at_risk');
  const [search, setSearch] = useState('');
  const [subjectFilter, setSubjectFilter] = useState('');

  useEffect(() => {
    api.get('/api/filters')
      .then(r => setPeriods(r.data.periods || []))
      .catch(() => {});
  }, []);

  useEffect(() => {
    setStudents([]);
    setSubjectsIncluded(0);
    setError(null);
    setSubjectFilter('');
    if (!studyPeriod) return;

    setLoading(true);
    api.get('/api/students-at-risk', { params: { study_period: studyPeriod } })
      .then(r => {
        setStudents(r.data.students || []);
        setSubjectsIncluded(r.data.subjects_included || 0);
      })
      .catch(err => setError(err.response?.data?.detail || 'Could not load students at risk.'))
      .finally(() => setLoading(false));
  }, [studyPeriod]);

  const subjectOptions = [...new Set(students.map(r => r.subject))].sort();

  const filtered = students.filter(r =>
    matchesTab(r, tab) &&
    (subjectFilter === '' || r.subject === subjectFilter) &&
    r.student_id.toLowerCase().includes(search.trim().toLowerCase())
  );

  const counts = {
    at_risk: students.filter(r => matchesTab(r, 'at_risk')).length,
    safe:    students.filter(r => matchesTab(r, 'safe')).length,
    all:     students.length,
  };

  const openInPredictor = (row) => {
    const base = admin ? '/predictive-reports' : '/predictor';
    navigate(`${base}?subject=${encodeURIComponent(row.subject)}&period=${encodeURIComponent(studyPeriod)}`);
  };

  return (
    <div style={s.page}>
      <div style={s.pageHeader}>
        <div>
          <h1 style={s.pageTitle}>Students at Risk</h1>
          <p style={s.pageSub}>
            Every student's current risk classification across {admin ? 'all subjects' : 'your subjects'}, for one study period
          </p>
        </div>
      </div>

      <div style={s.card}>
        <div style={s.fieldGroup}>
          <label style={s.label}>Study Period <span style={{ color: '#DC2626' }}>*</span></label>
          <select style={{ ...s.select, maxWidth: 240 }} value={studyPeriod} onChange={e => setStudyPeriod(e.target.value)}>
            <option value="">Select period…</option>
            {periods.map(p => <option key={p} value={p}>{p}</option>)}
          </select>
        </div>
      </div>

      {!studyPeriod && (
        <div style={s.emptyCard}>
          <div style={s.emptyIcon}>📋</div>
          <p style={s.emptyText}>Select a study period to view students at risk.</p>
        </div>
      )}

      {studyPeriod && loading && (
        <div style={s.emptyCard}>
          <div style={{ ...s.spinner, margin: '0 auto 16px' }} />
          <p style={s.emptyText}>Scanning every subject for this period…</p>
        </div>
      )}

      {error && <div style={s.errBanner}>{error}</div>}

      {studyPeriod && !loading && !error && students.length === 0 && (
        <div style={s.emptyCard}>
          <div style={s.emptyIcon}>✓</div>
          <p style={s.emptyText}>No student data found for period {studyPeriod}.</p>
        </div>
      )}

      {studyPeriod && !loading && !error && students.length > 0 && (
        <div style={s.card}>
          <div style={s.toolbar}>
            <div style={s.tabRow}>
              {TABS.map(t => (
                <button
                  key={t.key}
                  style={{ ...s.tab, ...(tab === t.key ? s.tabActive : {}) }}
                  onClick={() => setTab(t.key)}
                >
                  {t.label} <span style={s.tabCount}>{counts[t.key]}</span>
                </button>
              ))}
            </div>
            <div style={{ display: 'flex', gap: 10 }}>
              <select style={{ ...s.select, width: 180 }} value={subjectFilter} onChange={e => setSubjectFilter(e.target.value)}>
                <option value="">All subjects ({subjectsIncluded})</option>
                {subjectOptions.map(sv => <option key={sv} value={sv}>{sv}</option>)}
              </select>
              <input
                style={s.searchInput}
                placeholder="Search student ID…"
                value={search}
                onChange={e => setSearch(e.target.value)}
              />
            </div>
          </div>

          <div style={{ overflowX: 'auto', maxHeight: 600, overflowY: 'auto' }}>
            <table style={{ width: '100%', borderCollapse: 'collapse' }}>
              <thead>
                <tr>
                  {['Student', 'Subject', 'Assessments Recorded', 'Weight Recorded', 'Weighted Score', 'Risk'].map(h => (
                    <th key={h} style={s.th}>{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {filtered.map((r, i) => (
                  <tr
                    key={`${r.subject}-${r.student_id}`}
                    style={{ background: i % 2 === 0 ? '#fff' : '#F8FAFC', cursor: 'pointer' }}
                    onClick={() => openInPredictor(r)}
                    title="Open in Predictor for the full breakdown"
                  >
                    <td style={{ ...s.td, fontWeight: 700, color: '#1A2E40' }}>{r.student_id}</td>
                    <td style={s.td}>{r.subject}</td>
                    <td style={s.td}>{r.num_assessments_recorded}</td>
                    <td style={s.td}>{r.cumulative_weighting_recorded}%</td>
                    <td style={s.td}>{r.current_weighted_score}</td>
                    <td style={s.td}>
                      <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                        {r.estimate_type === 'mid-term estimate' && <MidTermTag />}
                        <RiskBadge band={r.risk_band} insufficientData={r.coverage_status === 'insufficient_data'} />
                      </div>
                    </td>
                  </tr>
                ))}
                {filtered.length === 0 && (
                  <tr><td style={s.td} colSpan={6}>No students match the current filters.</td></tr>
                )}
              </tbody>
            </table>
          </div>
        </div>
      )}

      <style>{`@keyframes spin { to { transform: rotate(360deg); } }`}</style>
    </div>
  );
}

const s = {
  page:       { padding: '28px 32px', background: '#F0F4F8', minHeight: '100vh', boxSizing: 'border-box' },
  pageHeader: { display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', marginBottom: 24 },
  pageTitle:  { margin: 0, fontSize: 20, fontWeight: 700, color: '#1A2E40' },
  pageSub:    { margin: '4px 0 0', fontSize: 13, color: '#64748B' },

  card:      { background: '#fff', border: '0.5px solid #DDE4EA', borderRadius: 10, padding: '20px 24px', marginBottom: 16 },
  fieldGroup:{ marginBottom: 0 },
  label:     { display: 'block', fontSize: 11, fontWeight: 600, color: '#475569', textTransform: 'uppercase', letterSpacing: 0.5, marginBottom: 6 },
  select:    { width: '100%', border: '0.5px solid #C5D2DC', borderRadius: 8, padding: '9px 12px', fontSize: 13, color: '#1E293B', background: '#fff', outline: 'none', cursor: 'pointer', boxSizing: 'border-box' },

  emptyCard: { background: '#fff', border: '0.5px solid #DDE4EA', borderRadius: 10, padding: '64px 24px', textAlign: 'center' },
  emptyIcon: { fontSize: 36, margin: '0 0 12px' },
  emptyText: { margin: 0, fontSize: 14, color: '#64748B' },
  spinner:   { width: 20, height: 20, border: '2px solid #E2E8F0', borderTopColor: '#0D9488', borderRadius: '50%', animation: 'spin 0.8s linear infinite', flexShrink: 0 },
  errBanner: { background: '#FEE2E2', border: '0.5px solid #FECACA', borderRadius: 8, padding: '10px 12px', fontSize: 12, color: '#991B1B', marginBottom: 16, lineHeight: 1.5 },

  toolbar:  { display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: 12, marginBottom: 14 },
  tabRow:   { display: 'flex', gap: 6, background: '#F1F5F9', borderRadius: 9, padding: 4 },
  tab: {
    padding: '7px 14px', borderRadius: 7, border: 'none', background: 'transparent',
    color: '#64748B', fontSize: 12.5, fontWeight: 600, cursor: 'pointer',
    display: 'flex', alignItems: 'center', gap: 6,
  },
  tabActive: { background: '#fff', color: '#1A2E40', boxShadow: '0 1px 2px rgba(0,0,0,0.08)' },
  tabCount:  { fontSize: 11, fontWeight: 700, color: '#94A3B8' },

  searchInput: { border: '0.5px solid #C5D2DC', borderRadius: 8, padding: '7px 10px', fontSize: 12, color: '#1E293B', outline: 'none', width: 200, boxSizing: 'border-box' },

  th: { fontSize: 11, fontWeight: 600, color: '#94A3B8', padding: '10px 12px', textAlign: 'left', borderBottom: '1px solid #E2E8F0', textTransform: 'uppercase', letterSpacing: 0.5, background: '#F8FAFC', whiteSpace: 'nowrap' },
  td: { fontSize: 12, color: '#475569', padding: '10px 12px', borderBottom: '0.5px solid #F0F4F8', whiteSpace: 'nowrap' },
};
