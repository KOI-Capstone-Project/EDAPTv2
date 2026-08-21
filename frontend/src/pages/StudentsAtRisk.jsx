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
import { RiskBadge, MidTermTag, resolveSafeFloor } from '../components/RiskBadge';

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

const rowKey = (r) => `${r.subject}::${r.student_id}`;

// attendance_rate_used is a 0-1 fraction (or null — no attendance data
// matched this enrolment, e.g. a subject with no attendance rows ingested
// at all); probability is already a 0-100 "chance of passing" percentage
// from the model (see predictor.py) — both come straight through from
// subject_roster()'s per-student result, nothing computed client-side.
function formatAttendance(rate) {
  if (rate === null || rate === undefined) return '—';
  return `${Math.round(rate * 100)}%`;
}
function attendanceColor(rate) {
  if (rate === null || rate === undefined) return '#94A3B8';
  if (rate < 0.6) return '#DC2626';
  if (rate < 0.8) return '#D97706';
  return '#334155';
}
function formatProbability(probability) {
  if (probability === null || probability === undefined) return '—';
  return `${probability}%`;
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

  // Selection is keyed by "subject::student_id" (student_id alone isn't
  // unique across subjects) — powers the bulk "Log as emailed" action below.
  const [selected, setSelected] = useState(() => new Set());
  const [emailModalOpen, setEmailModalOpen] = useState(false);

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
    setSelected(new Set());
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
    navigate(`${base}?subject=${encodeURIComponent(row.subject)}&period=${encodeURIComponent(studyPeriod)}&student=${encodeURIComponent(row.student_id)}`);
  };

  const toggleRow = (row, e) => {
    e.stopPropagation();
    const key = rowKey(row);
    setSelected(prev => {
      const next = new Set(prev);
      if (next.has(key)) next.delete(key); else next.add(key);
      return next;
    });
  };

  const allFilteredSelected = filtered.length > 0 && filtered.every(r => selected.has(rowKey(r)));
  const toggleSelectAllFiltered = () => {
    setSelected(prev => {
      const next = new Set(prev);
      if (allFilteredSelected) {
        filtered.forEach(r => next.delete(rowKey(r)));
      } else {
        filtered.forEach(r => next.add(rowKey(r)));
      }
      return next;
    });
  };

  const selectedRows = students.filter(r => selected.has(rowKey(r)));

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
            <div style={{ display: 'flex', gap: 10, alignItems: 'center' }}>
              {selected.size > 0 && (
                <button style={s.emailBtn} onClick={() => setEmailModalOpen(true)}>
                  ✉ Log as Emailed ({selected.size})
                </button>
              )}
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
                  <th style={{ ...s.th, width: 32 }}>
                    <input
                      type="checkbox"
                      checked={allFilteredSelected}
                      onChange={toggleSelectAllFiltered}
                      aria-label="Select all filtered students"
                    />
                  </th>
                  {['Student', 'Subject', 'Attendance', 'Assessments Recorded', 'Weighted Score', 'Pass Probability', 'Risk'].map(h => (
                    <th key={h} style={s.th}>{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {filtered.map((r, i) => (
                  <tr
                    key={rowKey(r)}
                    style={{ background: i % 2 === 0 ? '#fff' : '#F8FAFC', cursor: 'pointer' }}
                    onClick={() => openInPredictor(r)}
                    title="Open in Predictor for the full breakdown"
                  >
                    <td style={s.td} onClick={e => e.stopPropagation()}>
                      <input
                        type="checkbox"
                        checked={selected.has(rowKey(r))}
                        onChange={e => toggleRow(r, e)}
                        aria-label={`Select ${r.student_id}`}
                      />
                    </td>
                    <td style={{ ...s.td, fontWeight: 700, color: '#1A2E40' }}>{r.student_id}</td>
                    <td style={s.td}>{r.subject}</td>
                    <td style={{ ...s.td, fontWeight: 600, color: attendanceColor(r.attendance_rate_used) }}>
                      {formatAttendance(r.attendance_rate_used)}
                    </td>
                    <td style={s.td}>{r.num_assessments_recorded}</td>
                    <td style={s.td}>{r.current_weighted_score}</td>
                    <td style={s.td}>{formatProbability(r.probability)}</td>
                    <td style={s.td}>
                      <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                        {r.estimate_type === 'mid-term estimate' && <MidTermTag />}
                        <RiskBadge
                          band={r.risk_band}
                          insufficientData={r.coverage_status === 'insufficient_data'}
                          probability={r.probability}
                          safeFloor={resolveSafeFloor(r)}
                        />
                      </div>
                    </td>
                  </tr>
                ))}
                {filtered.length === 0 && (
                  <tr><td style={s.td} colSpan={8}>No students match the current filters.</td></tr>
                )}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {emailModalOpen && (
        <RiskEmailModal
          targets={selectedRows}
          studyPeriod={studyPeriod}
          onClose={() => setEmailModalOpen(false)}
          onLogged={() => { setSelected(new Set()); setEmailModalOpen(false); }}
        />
      )}

      <style>{`@keyframes spin { to { transform: rotate(360deg); } }`}</style>
    </div>
  );
}

// ── Bulk "Log as emailed" modal ────────────────────────────────────────────
// Never sends a real email — this system has no real student email address
// anywhere (see RiskEmailTemplate's backend docstring). Staff review/edit the
// wording here, send the real email themselves outside this system, then
// confirm — which logs one Intervention row per selected student
// (action_type "email sent"), with {{placeholders}} rendered per-student
// server-side (see POST /api/interventions/bulk).
function RiskEmailModal({ targets, studyPeriod, onClose, onLogged }) {
  const [subject, setSubject] = useState('');
  const [body,    setBody]    = useState('');
  const [templateLoading, setTemplateLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error,  setError]  = useState(null);

  useEffect(() => {
    api.get('/api/risk-email-template')
      .then(r => { setSubject(r.data.subject); setBody(r.data.body); })
      .catch(() => setError('Could not load the email template. You can still edit and send below.'))
      .finally(() => setTemplateLoading(false));
  }, []);

  const preview = targets[0]
    ? body
        .replace('{{student_id}}',   targets[0].student_id)
        .replace('{{subject_code}}', targets[0].subject)
        .replace('{{study_period}}', studyPeriod)
        .replace('{{risk_band}}',    targets[0].risk_band || 'at risk')
    : '';

  const handleConfirm = async () => {
    setSaving(true);
    setError(null);
    try {
      await api.post('/api/interventions/bulk', {
        action_type: 'email sent',
        notes: body,
        targets: targets.map(t => ({
          student_id_masked: t.student_id,
          subject_code:       t.subject,
          study_period:        studyPeriod,
          risk_band:           t.risk_band,
        })),
      });
      onLogged();
    } catch (err) {
      setError(err.response?.data?.detail || 'Could not log these actions. Please try again.');
    } finally {
      setSaving(false);
    }
  };

  return (
    <div style={s.modalOverlay} role="dialog" aria-modal="true">
      <div style={s.modalCard}>
        <h3 style={s.modalTitle}>Log risk email as sent</h3>
        <p style={s.modalSub}>
          This doesn't send anything — the system has no real student email address on
          file. Send the email yourself using the wording below, then confirm to log it
          for all {targets.length} selected student{targets.length === 1 ? '' : 's'}.
        </p>

        {templateLoading ? (
          <p style={{ fontSize: 12, color: '#64748B' }}>Loading template…</p>
        ) : (
          <>
            <div style={s.fieldGroup}>
              <label style={s.label}>Subject</label>
              <input style={{ ...s.select, cursor: 'text' }} value={subject} onChange={e => setSubject(e.target.value)} />
            </div>
            <div style={{ ...s.fieldGroup, marginTop: 12 }}>
              <label style={s.label}>Body</label>
              <textarea
                style={{ ...s.select, height: 150, padding: '10px 12px', resize: 'vertical', fontFamily: 'inherit', cursor: 'text' }}
                value={body}
                onChange={e => setBody(e.target.value)}
              />
            </div>
            {targets[0] && (
              <div style={s.previewBox}>
                <p style={{ margin: '0 0 4px', fontSize: 10.5, fontWeight: 700, color: '#94A3B8', textTransform: 'uppercase' }}>
                  Preview — {targets[0].student_id}
                </p>
                <p style={{ margin: 0, fontSize: 12, color: '#334155', whiteSpace: 'pre-wrap' }}>{preview}</p>
              </div>
            )}
          </>
        )}

        {error && <div style={s.errBanner}>{error}</div>}

        <div style={s.modalActions}>
          <button style={s.modalCancelBtn} onClick={onClose} disabled={saving}>Cancel</button>
          <button style={{ ...s.emailBtn, opacity: saving ? 0.6 : 1 }} onClick={handleConfirm} disabled={saving || templateLoading}>
            {saving ? 'Logging…' : `I've sent it — log for ${targets.length}`}
          </button>
        </div>
      </div>
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

  emailBtn: {
    padding: '8px 16px', borderRadius: 8, border: 'none',
    background: '#2E6E8E', color: '#fff', fontSize: 12.5, fontWeight: 600,
    cursor: 'pointer', whiteSpace: 'nowrap',
  },

  modalOverlay: {
    position: 'fixed', inset: 0, background: 'rgba(15,23,42,0.45)',
    display: 'flex', alignItems: 'center', justifyContent: 'center',
    padding: 20, zIndex: 100,
  },
  modalCard: {
    background: '#fff', borderRadius: 14, padding: '24px 28px', width: '100%',
    maxWidth: 560, maxHeight: '85vh', overflowY: 'auto',
    boxShadow: '0 20px 50px rgba(0,0,0,0.25)',
  },
  modalTitle: { margin: '0 0 6px', fontSize: 18, fontWeight: 700, color: '#1A2E40' },
  modalSub:   { margin: '0 0 18px', fontSize: 13, color: '#5A7A8A', lineHeight: 1.5 },
  modalActions: { display: 'flex', justifyContent: 'flex-end', gap: 10, marginTop: 20 },
  modalCancelBtn: {
    padding: '10px 20px', borderRadius: 8, border: '0.5px solid #C5D2DC',
    background: '#fff', color: '#64748B', fontSize: 13, fontWeight: 600, cursor: 'pointer',
  },
  previewBox: {
    marginTop: 14, background: '#F8FAFC', border: '0.5px solid #E2E8F0',
    borderRadius: 8, padding: '10px 12px',
  },
};
