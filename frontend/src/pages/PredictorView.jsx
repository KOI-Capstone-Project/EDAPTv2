// Predictor: roster-first risk view for real students, with an optional
// what-if simulator for hypothetical scenarios. Shared by admin (all subjects)
// and lecturer (assigned subjects only) via the isAdmin prop.
import { useState, useEffect } from 'react';
import { useSearchParams } from 'react-router-dom';
import { getUser } from '../utils/auth';
import api from '../services/api';
import { RiskBadge, MidTermTag } from '../components/RiskBadge';

// ── Sub-components ─────────────────────────────────────────────────────────────

// Real per-feature SHAP contributions for one prediction — the actual model
// math, not a Gemini-generated guess. `factors`: [{feature, value, contribution,
// direction}], contribution in percentage points of P(Pass) (same 0-100 scale
// as the headline probability), direction "Pass" | "Fail" | "Neutral".
const FEATURE_LABELS = {
  ASSESS1_MARK:             'Highest-weighted assessment mark',
  ASSESS1_WEIGHT:           'Highest-weighted assessment weight',
  ASSESS1_CONTRIBUTION:     'Highest-weighted assessment contribution',
  ASSESS2_MARK:             '2nd highest-weighted assessment mark',
  ASSESS2_WEIGHT:           '2nd highest-weighted assessment weight',
  ASSESS2_CONTRIBUTION:     '2nd highest-weighted assessment contribution',
  PARTIAL_WEIGHTED_SCORE:   'Cumulative weighted score so far',
  PARTIAL_WEIGHT_COVERAGE:  'Assessment coverage recorded so far',
  SUBJECT_DIFFICULTY:       'Subject historical fail rate',
  TRIMESTER_NUM:            'Study period',
  ATTENDANCE_RATE:          'Attendance rate',
};

function ShapFactorBars({ shap }) {
  if (!shap || !shap.top_factors || shap.top_factors.length === 0) return null;
  // Attendance is a real model input (see ATTENDANCE_RATE in FEATURE_LABELS)
  // but its SHAP contribution is usually small relative to assessment marks
  // — top_factors (top 3 by |contribution|) can easily omit it entirely,
  // which reads as "the model ignored attendance" when it didn't. Pull it
  // from all_factors (every feature, always present) and append it if it's
  // not already one of the naturally top-ranked factors, so it's never
  // silently invisible regardless of how small its pull was.
  const attendanceInTop = shap.top_factors.some(f => f.feature === 'ATTENDANCE_RATE');
  const attendanceFactor = !attendanceInTop
    ? (shap.all_factors || []).find(f => f.feature === 'ATTENDANCE_RATE')
    : null;
  const displayFactors = attendanceFactor ? [...shap.top_factors, attendanceFactor] : shap.top_factors;
  const maxAbs = Math.max(...displayFactors.map(f => Math.abs(f.contribution)), 1);
  return (
    <div style={{ marginBottom: 14 }}>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 8 }}>
        <span style={{ fontSize: 12, fontWeight: 700, color: '#1A2E40' }}>Top factors driving this prediction</span>
        {!shap.sum_check_ok && (
          <span title="The contributions below did not sum cleanly back to the predicted probability."
            style={{ fontSize: 10, color: '#B45309' }}>⚠ inconsistent</span>
        )}
      </div>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
        {displayFactors.map((f, i) => {
          const pct   = Math.min(100, (Math.abs(f.contribution) / maxAbs) * 100);
          const color = f.direction === 'Pass' ? '#059669' : f.direction === 'Fail' ? '#DC2626' : '#94A3B8';
          const isAppendedAttendance = attendanceFactor && f.feature === 'ATTENDANCE_RATE';
          return (
            <div key={i} style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
              <span style={{ fontSize: 11, color: '#475569', width: 190, flexShrink: 0 }}>
                {FEATURE_LABELS[f.feature] || f.feature}
                {isAppendedAttendance && (
                  <span title="Always shown regardless of rank, since attendance is otherwise easy to assume the model ignored."
                    style={{ marginLeft: 4, fontSize: 9, color: '#94A3B8' }}>
                    (always shown)
                  </span>
                )}
              </span>
              <div style={{ flex: 1, height: 8, background: '#F1F5F9', borderRadius: 4, position: 'relative', overflow: 'hidden' }}>
                <div style={{ width: `${pct}%`, height: '100%', background: color, borderRadius: 4 }} />
              </div>
              <span style={{ fontSize: 11, fontWeight: 700, color, width: 90, textAlign: 'right', flexShrink: 0 }}>
                {f.contribution > 0 ? '+' : ''}{f.contribution.toFixed(1)}pp {f.direction === 'Neutral' ? '' : `→ ${f.direction}`}
              </span>
            </div>
          );
        })}
      </div>
      <p style={{ margin: '8px 0 0', fontSize: 10, color: '#94A3B8' }}>
        SHAP contributions from the actual deployed model (percentage points of pass probability). Base rate {shap.base_value}% + these factors ≈ {shap.reconstructed_probability}%.
      </p>
    </div>
  );
}

// "What would help most" — rendered only when the backend supplies it, which
// is only for a real identified student. A hypothetical What-If scenario has
// nobody to advise, so the field is absent there and this renders nothing.
//
// The wording deliberately never promises an outcome ("improve attendance by
// 10% and this student reaches Safe"). SHAP contributions are not linearly
// interpretable as "change X, get Y" — claiming a number would require
// actually re-running the model with the feature adjusted. Direction and
// relative importance is what the data supports, so that is all this says.
function ActionableFactorCard({ factor }) {
  // No recommendation is a real answer, not a gap — and it must not be misread
  // as "nothing to improve". It means specifically that every factor this
  // student can act on (attendance, assessment marks) is currently HELPING
  // their prediction; the things hurting them are structural (subject
  // difficulty, assessment weighting, how much of the term has been marked).
  // It is NOT gated on the predicted outcome: predicted-Pass students do get a
  // recommendation whenever an actionable factor is still hurting them —
  // verified on a real 146-student roster, where 66 predicted-Pass students
  // received one.
  if (!factor) {
    return (
      <p style={{ margin: '10px 0 0', fontSize: 11, color: '#64748B', fontStyle: 'italic' }}>
        No actionable recommendation: attendance and assessment marks are currently
        helping this student. The factors weighing against them are structural
        (subject difficulty, assessment weighting, term coverage) rather than
        things they can change.
      </p>
    );
  }
  return (
    <div style={{
      marginTop: 12, padding: '12px 14px', borderRadius: 8,
      background: '#EFF6FF', border: '1px solid #BFDBFE',
    }}>
      <div style={{ display: 'flex', gap: 8, alignItems: 'flex-start' }}>
        <span style={{ fontSize: 15, flexShrink: 0, lineHeight: 1.4 }}>🎯</span>
        <div>
          <p style={{ margin: 0, fontSize: 13, color: '#1E3A8A', fontWeight: 600, lineHeight: 1.6 }}>
            {factor.message}
          </p>
          <p style={{ margin: '6px 0 0', fontSize: 11, color: '#475569' }}>
            Current value: <strong>{
              factor.feature === 'ATTENDANCE_RATE'
                ? `${(factor.value * 100).toFixed(0)}%`
                : factor.value.toFixed(1)
            }</strong>
            {' · '}pulls this prediction down by {Math.abs(factor.contribution).toFixed(2)} points
          </p>
          <p style={{ margin: '6px 0 0', fontSize: 11, color: '#64748B', fontStyle: 'italic' }}>
            Shows direction and relative importance only — not a predicted change in outcome.
          </p>
        </div>
      </div>
    </div>
  );
}

// Log an action taken for a real student, and show what has already been
// logged. Deliberately placed with the prediction rather than on a separate
// page: the moment a lecturer reads "High Risk" is the moment they decide to
// act, and a record made then is far more likely to happen than one that
// requires navigating elsewhere.
export function InterventionPanel({ studentId, subject, studyPeriod }) {
  const [actionTypes, setActionTypes] = useState([]);
  const [actionType, setActionType] = useState('');
  const [notes, setNotes] = useState('');
  const [history, setHistory] = useState([]);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState(null);
  const [saved, setSaved] = useState(false);

  // The whitelist comes from the server so the UI can never offer a value the
  // API would reject, and the two can't drift apart.
  useEffect(() => {
    api.get('/api/interventions/action-types')
      .then(r => {
        const types = r.data.action_types || [];
        setActionTypes(types);
        setActionType(prev => prev || types[0] || '');
      })
      .catch(() => setActionTypes([]));
  }, []);

  const loadHistory = () => {
    if (!studentId || !subject || !studyPeriod) return;
    api.get('/api/interventions', { params: {
      student_id_masked: studentId, subject_code: subject, study_period: studyPeriod } })
      .then(r => setHistory(r.data.interventions || []))
      .catch(() => setHistory([]));
  };

  useEffect(loadHistory, [studentId, subject, studyPeriod]);

  const submit = () => {
    if (!actionType) return;
    setSaving(true); setError(null); setSaved(false);
    api.post('/api/interventions', {
      student_id_masked: studentId, subject_code: subject,
      study_period: studyPeriod, action_type: actionType,
      notes: notes.trim() || null,
    })
      .then(() => { setNotes(''); setSaved(true); loadHistory(); })
      .catch(e => setError(e.response?.data?.detail || 'Could not save this action.'))
      .finally(() => setSaving(false));
  };

  return (
    <div style={{ marginTop: 16, padding: 16, background: '#FFF', borderRadius: 10,
                  border: '1px solid #E2E8F0' }}>
      <p style={{ ...s.sectionLabel, marginTop: 0 }}>Log an action</p>

      <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', alignItems: 'center' }}>
        <select value={actionType} onChange={e => setActionType(e.target.value)}
                style={{ ...s.select, minWidth: 200, flex: '0 0 auto' }}
                aria-label="Action type">
          {actionTypes.map(t => <option key={t} value={t}>{t}</option>)}
        </select>
        <input
          type="text" value={notes} placeholder="Optional note (what was discussed?)"
          onChange={e => setNotes(e.target.value)} maxLength={2000}
          style={{ ...s.searchInput, flex: '1 1 240px', margin: 0 }} aria-label="Note"
        />
        <button onClick={submit} disabled={saving || !actionType}
                style={{ ...s.predictBtn, width: 'auto', padding: '10px 18px',
                         opacity: saving || !actionType ? 0.6 : 1 }}>
          {saving ? 'Saving…' : 'Log action'}
        </button>
      </div>

      {error && <div style={{ ...s.errBanner, marginTop: 10 }}>{error}</div>}
      {saved && !error && (
        <p style={{ margin: '10px 0 0', fontSize: 12, color: '#166534' }}>✓ Action logged.</p>
      )}

      <p style={{ ...s.sectionLabel, marginBottom: 6 }}>
        History {history.length > 0 && `(${history.length})`}
      </p>
      {history.length === 0 ? (
        <p style={{ margin: 0, fontSize: 12, color: '#94A3B8', fontStyle: 'italic' }}>
          No actions logged for this student in this subject yet.
        </p>
      ) : (
        <ul style={{ margin: 0, padding: 0, listStyle: 'none' }}>
          {history.map(h => (
            <li key={h.id} style={{ padding: '8px 0', borderTop: '1px solid #F1F5F9',
                                    fontSize: 12, color: '#334155' }}>
              <strong style={{ color: '#1A2E40' }}>{h.action_type}</strong>
              {' — '}
              <span style={{ color: '#64748B' }}>
                {h.created_at ? new Date(h.created_at).toLocaleString() : 'time unknown'}
                {' by '}{h.created_by}
              </span>
              {h.notes && <div style={{ marginTop: 3, color: '#475569' }}>{h.notes}</div>}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

function Gauge({ pct }) {
  const cx = 110, cy = 100, r = 82, sw = 14;
  const C      = Math.PI * r;
  const arcLen = C * (pct / 100);
  const color  = pct >= 65 ? '#059669' : pct >= 40 ? '#D97706' : '#DC2626';
  const angle  = Math.PI * (1 - pct / 100);
  const nx     = cx + (r - 10) * Math.cos(angle);
  const ny     = cy - (r - 10) * Math.sin(angle);
  return (
    <svg width={220} height={112} viewBox="0 0 220 112" style={{ display: 'block', margin: '0 auto' }}>
      <path d={`M ${cx-r} ${cy} A ${r} ${r} 0 0 1 ${cx+r} ${cy}`}
        fill="none" stroke="#E2E8F0" strokeWidth={sw} strokeLinecap="round" />
      {pct > 0 && (
        <path d={`M ${cx-r} ${cy} A ${r} ${r} 0 0 1 ${cx+r} ${cy}`}
          fill="none" stroke={color} strokeWidth={sw} strokeLinecap="round"
          strokeDasharray={`${arcLen} ${C}`} />
      )}
      <line x1={cx} y1={cy} x2={nx} y2={ny} stroke="#334155" strokeWidth={2.5} strokeLinecap="round" />
      <circle cx={cx} cy={cy} r={5} fill="#334155" />
      <text x={cx-r-2} y={cy+15} fontSize={9} fill="#94A3B8" textAnchor="middle">0%</text>
      <text x={cx+r+2} y={cy+15} fontSize={9} fill="#94A3B8" textAnchor="middle">100%</text>
    </svg>
  );
}

// Shared result rendering — used for both a real student's detail view and a
// what-if hypothetical scenario. `result` shape: { subject, study_period,
// probability, probability_calibrated?, prediction, risk_band,
// safe_floor_percent?, assessments_used: [{type, mark_percent,
// weighting}], total_weight_recorded, partial_weighted_score,
// attendance_rate_used?, attendance_rate_is_default?, model_name?,
// model_accuracy?, coverage_status?, estimate_type? }.
export function PredictionResultPanel({ result, geminiLoading, geminiInsight }) {
  const isInsufficientData = result.coverage_status === 'insufficient_data';
  const isMidTerm          = result.estimate_type === 'mid-term estimate';
  // Falls back to the historical defaults (75 mid-term / 65 complete-record)
  // for older API responses (e.g. cached roster rows) that predate this
  // field — matches predictor.py's _safe_floor() so the legend never shows
  // a number the backend didn't actually use to decide the risk band.
  const safeFloor = result.safe_floor_percent ?? (isMidTerm ? 75 : 65);
  const probColor = result.probability >= 65 ? '#059669' : result.probability >= 40 ? '#D97706' : '#DC2626';
  // The Assessment Breakdown table's "Total" row must sum exactly the
  // Contribution cells rendered directly above it — anything else reads as
  // a bug (it looked like one: a 5-item breakdown summing to 50 next to a
  // "Total" of 30). `result.partial_weighted_score` is NOT that sum for a
  // complete-record prediction — predictor.compute_partial_score() defines
  // it as the top-2-highest-weighted-items feature the main model was
  // trained on (a deliberate, narrower quantity — see build_early_features()
  // in train_model.py for why summing all items isn't safe as a training
  // feature on this dataset), which only coincides with "sum of everything
  // shown" when there are 2 or fewer items. Compute the real total directly
  // from the same assessments_used rows the table iterates, so this can
  // never drift from what's displayed above it, in either flow.
  const totalContribution = (result.assessments_used || [])
    .reduce((sum, a) => sum + (a.mark_percent * a.weighting) / 100, 0);
  return (
    <div style={s.resultCard}>
      <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', marginBottom: 20 }}>
        <div>
          <h2 style={{ margin: 0, fontSize: 22, fontWeight: 800, color: '#1A2E40' }}>{result.subject}</h2>
          <p style={{ margin: '4px 0 0', fontSize: 13, color: '#64748B' }}>Study Period {result.study_period}</p>
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          {isMidTerm && <MidTermTag />}
          <RiskBadge band={result.risk_band} insufficientData={isInsufficientData} />
        </div>
      </div>

      {/* Always shown, not just when defaulted — ATTENDANCE_RATE is a real
          model input (see FEATURE_LABELS/ShapFactorBars), but with nothing
          on this screen ever labeled "Attendance," it read as though the
          model ignored it entirely. This is the one place that number is
          visible at all. */}
      {result.attendance_rate_used != null ? (
        <p style={{ margin: '-12px 0 16px', fontSize: 12, color: '#475569' }}>
          📊 Attendance rate used: <strong>{(result.attendance_rate_used * 100).toFixed(0)}%</strong>
          {result.attendance_rate_is_default
            ? " — this subject's average (no individual attendance record for this student)"
            : " — this student's own attendance record"}
        </p>
      ) : (
        <p style={{ margin: '-12px 0 16px', fontSize: 11, color: '#94A3B8', fontStyle: 'italic' }}>
          Attendance rate: not available for this student.
        </p>
      )}

      {isInsufficientData ? (
        <div style={{ textAlign: 'center', paddingBottom: 20, borderBottom: '0.5px solid #E2E8F0' }}>
          <div style={{ fontSize: 36, margin: '12px 0' }}>📋</div>
          <div style={{ fontSize: 15, fontWeight: 700, color: '#475569' }}>Not enough data yet</div>
          <div style={{ fontSize: 12, color: '#94A3B8', marginTop: 4, maxWidth: 320, marginLeft: 'auto', marginRight: 'auto' }}>
            Fewer than half of this subject's assessments are recorded so far — check back once more marks are in.
          </div>
        </div>
      ) : (
      <div style={{ textAlign: 'center', paddingBottom: 20, borderBottom: '0.5px solid #E2E8F0' }}>
        <Gauge pct={result.probability ?? 0} />
        <div style={{ fontSize: 34, fontWeight: 800, color: probColor, lineHeight: 1, marginTop: 8 }}>
          {result.probability ?? '—'}%
        </div>
        <div style={{ fontSize: 16, fontWeight: 700, color: '#1A2E40', marginTop: 6 }}>
          {result.prediction || '—'}
        </div>
        <div style={{ fontSize: 12, color: '#94A3B8', marginTop: 4 }}>
          Based on similar historical records
        </div>
      </div>
      )}

      <div style={{ paddingTop: 20, paddingBottom: 20, borderBottom: '0.5px solid #E2E8F0' }}>
        <p style={s.sectionLabel}>Assessment Breakdown</p>
        <div style={{ overflowX: 'auto' }}>
          <table style={{ width: '100%', borderCollapse: 'collapse' }}>
            <thead>
              <tr>
                {['Type', 'Mark', 'Weight', 'Contribution'].map(h => (
                  <th key={h} style={s.th}>{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {(result.assessments_used || []).map((a, i) => (
                <tr key={i} style={{ background: i % 2 === 0 ? '#fff' : '#F8FAFC' }}>
                  <td style={{ ...s.td, fontWeight: 700, color: '#1A2E40' }}>{a.type}</td>
                  <td style={s.td}>
                    {Math.round((a.mark_percent * a.weighting) / 100)} / {a.weighting} ({Math.round(a.mark_percent)}%)
                  </td>
                  <td style={s.td}>{a.weighting}%</td>
                  <td style={{ ...s.td, fontVariantNumeric: 'tabular-nums' }} data-testid="assessment-contribution">
                    {((a.mark_percent * a.weighting) / 100).toFixed(1)}
                  </td>
                </tr>
              ))}
              {(!result.assessments_used || result.assessments_used.length === 0) && (
                <tr><td style={s.td} colSpan={4}>No assessment items recorded yet.</td></tr>
              )}
              <tr style={{ background: '#F0F4F8' }}>
                <td style={{ ...s.td, fontWeight: 700, color: '#1A2E40' }}>Total</td>
                <td style={s.td}>—</td>
                <td style={s.td}>{result.total_weight_recorded}%</td>
                <td style={{ ...s.td, fontWeight: 800, color: probColor }} data-testid="assessment-total">
                  {totalContribution.toFixed(1)}
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>

      {!isInsufficientData && (
      <div style={{ paddingTop: 20, paddingBottom: 20, borderBottom: '0.5px solid #E2E8F0' }}>
        <p style={s.sectionLabel}>AI Assisted Insight</p>
        <ShapFactorBars shap={result.shap_explanation} />
        {/* Derived from the same real SHAP factors shown above, narrowed to
            what the student can actually act on. Absent for hypothetical
            What-If scenarios, so this renders nothing there. */}
        <ActionableFactorCard factor={result.top_actionable_factor} />
        {geminiLoading && (
          <div style={{ ...s.geminiBox, flexDirection: 'row', alignItems: 'center', gap: 12 }}>
            <div style={s.spinner} />
            <span style={{ fontSize: 13, color: '#0D9488' }}>Generating insight…</span>
          </div>
        )}
        {!geminiLoading && geminiInsight && (
          <div style={s.geminiBox}>
            <div style={{ display: 'flex', gap: 8, alignItems: 'flex-start' }}>
              <span style={{ color: '#0D9488', fontSize: 16, flexShrink: 0, lineHeight: 1.5 }}>✦</span>
              <p style={{ margin: 0, fontSize: 13, color: '#1E293B', lineHeight: 1.7 }}>
                {geminiInsight}
              </p>
            </div>
            <p style={{ margin: '10px 0 0', fontSize: 11, color: '#64748B', fontStyle: 'italic' }}>
              Plain-English summary generated by Gemini from the real factors above. Verify before acting on this advice.
            </p>
          </div>
        )}
      </div>
      )}

      <div style={{ paddingTop: 20 }}>
        <p style={s.sectionLabel}>Risk Scale</p>
        {isMidTerm && (
          <p style={s.midTermBandNote}>
            ⚠ Mid-term estimates use their own risk scale (Safe starts at {safeFloor}%, not 65%)
            because this early-in-term model's percentages aren't yet on the same scale as
            a complete-record percentage — the same number wouldn't mean the same level of
            risk on both.
          </p>
        )}
        <div style={{ display: 'flex', gap: 8 }}>
          {(isMidTerm
            ? [
                { key: 'High Risk', label: 'High Risk', range: '0 – 39%',   bg: '#FEE2E2', text: '#991B1B', border: '#DC2626' },
                { key: 'At Risk',   label: 'At Risk',   range: `40 – ${safeFloor - 1}%`,  bg: '#FEF9C3', text: '#854D0E', border: '#D97706' },
                { key: 'Safe',      label: 'Safe',      range: `${safeFloor} – 100%`, bg: '#DCFCE7', text: '#166534', border: '#059669' },
              ]
            : [
                { key: 'High Risk', label: 'High Risk', range: '0 – 39%',   bg: '#FEE2E2', text: '#991B1B', border: '#DC2626' },
                { key: 'At Risk',   label: 'At Risk',   range: `40 – ${safeFloor - 1}%`,  bg: '#FEF9C3', text: '#854D0E', border: '#D97706' },
                { key: 'Safe',      label: 'Safe',      range: `${safeFloor} – 100%`, bg: '#DCFCE7', text: '#166534', border: '#059669' },
              ]
          ).map(t => (
            <div key={t.key} style={{
              flex: 1, borderRadius: 8, padding: '10px 12px',
              display: 'flex', flexDirection: 'column', gap: 3,
              background: t.bg,
              border: result.risk_band === t.key ? `2px solid ${t.border}` : '2px solid transparent',
              boxSizing: 'border-box',
            }}>
              <span style={{ fontWeight: 700, color: t.text, fontSize: 12 }}>{t.label}</span>
              <span style={{ color: t.text, fontSize: 11, opacity: 0.8 }}>{t.range}</span>
              {result.risk_band === t.key && (
                <span style={{ fontSize: 10, color: t.border, fontWeight: 700, marginTop: 2 }}>▶ Current</span>
              )}
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

// Turns a shap_explanation's top_factors into a short clause for a Gemini
// prompt — so Gemini is fed the real numbers and asked to phrase them in
// plain English, rather than asked to guess a plausible-sounding reason.
function shapFactorsText(shap) {
  if (!shap || !shap.top_factors || shap.top_factors.length === 0) return null;
  return shap.top_factors
    .map(f => `${FEATURE_LABELS[f.feature] || f.feature} (${f.contribution > 0 ? '+' : ''}${f.contribution.toFixed(1)} points toward ${f.direction})`)
    .join(', ');
}

// ── Main component ─────────────────────────────────────────────────────────────

export default function PredictorView({ isAdmin }) {
  const [allSubjects, setAllSubjects] = useState([]);
  const subjects = isAdmin ? allSubjects : (getUser()?.subjects || []);

  // Pre-selected when arriving from Students at Risk (?subject=X&period=Y) —
  // read once on mount so the roster loads straight away instead of making
  // the admin/lecturer re-pick a subject+period they already chose there.
  const [searchParams] = useSearchParams();
  const [subject,     setSubject]     = useState(() => searchParams.get('subject') || '');
  const [studyPeriod, setStudyPeriod] = useState(() => searchParams.get('period') || '');
  const [periods,     setPeriods]     = useState([]);

  // view: 'roster' (default) | 'detail' (a real student clicked) | 'whatif' (hypothetical scenario)
  const [view, setView] = useState('roster');

  // Roster
  const [rosterLoading,         setRosterLoading]         = useState(false);
  const [roster,                setRoster]                = useState([]);
  const [rosterMeta,            setRosterMeta]            = useState(null);
  const [rosterSearch,          setRosterSearch]          = useState('');
  const [predictionUnavailable, setPredictionUnavailable] = useState(false);
  const [unavailableMessage,    setUnavailableMessage]    = useState('');
  const [reliabilityWarning,    setReliabilityWarning]    = useState(null);
  const [rosterError,           setRosterError]           = useState(null);

  // Real-student detail (drilled in from a roster row)
  const [selectedStudentId, setSelectedStudentId] = useState(null);
  const [studentDetail,     setStudentDetail]     = useState(null);
  const [detailLoading,     setDetailLoading]     = useState(false);
  const [detailError,       setDetailError]       = useState(null);
  const [detailGeminiLoading, setDetailGeminiLoading] = useState(false);
  const [detailGeminiInsight, setDetailGeminiInsight] = useState(null);

  // What-if simulator (secondary, manual entry — never the default view)
  const [whatIfAssessmentTypes, setWhatIfAssessmentTypes] = useState([]);
  const [whatIfMarks,           setWhatIfMarks]           = useState({});
  const [whatIfMarkErrors,      setWhatIfMarkErrors]      = useState({});
  const [whatIfWeightComplete,  setWhatIfWeightComplete]  = useState(true);
  // Left blank by default — /api/predict fills in this subject's real
  // average attendance rate server-side when omitted (attendance_rate_is_default
  // in the response tells us to caption it as a default, not user input).
  const [whatIfAttendanceRate,  setWhatIfAttendanceRate]  = useState('');
  const [whatIfAttendanceError, setWhatIfAttendanceError] = useState(null);
  const [whatIfResult,          setWhatIfResult]          = useState(null);
  const [whatIfLoading,         setWhatIfLoading]         = useState(false);
  const [whatIfError,           setWhatIfError]           = useState(null);
  const [whatIfGeminiLoading,   setWhatIfGeminiLoading]   = useState(false);
  const [whatIfGeminiInsight,   setWhatIfGeminiInsight]   = useState(null);

  useEffect(() => {
    api.get('/api/filters')
      .then(r => {
        setPeriods(r.data.periods || []);
        if (isAdmin) setAllSubjects(r.data.subjects || []);
      })
      .catch(() => {});
  }, [isAdmin]);

  // Reset everything downstream of subject/period and load the roster.
  useEffect(() => {
    setView('roster');
    setRoster([]);
    setRosterMeta(null);
    setRosterSearch('');
    setPredictionUnavailable(false);
    setUnavailableMessage('');
    setReliabilityWarning(null);
    setRosterError(null);
    setSelectedStudentId(null);
    setStudentDetail(null);
    setDetailGeminiInsight(null);
    setWhatIfAssessmentTypes([]);
    setWhatIfMarks({});
    setWhatIfMarkErrors({});
    setWhatIfResult(null);
    setWhatIfGeminiInsight(null);

    if (!subject || !studyPeriod) return;

    setRosterLoading(true);
    api.get(`/api/subjects/${encodeURIComponent(subject)}/roster?study_period=${encodeURIComponent(studyPeriod)}`)
      .then(r => {
        if (r.data.prediction_available === false) {
          setPredictionUnavailable(true);
          setUnavailableMessage(r.data.message || '');
          return;
        }
        setRoster(r.data.roster || []);
        setRosterMeta({
          totalStudents:     r.data.total_students,
          periodTotalWeight: r.data.period_total_weight,
        });
        setReliabilityWarning(r.data.reliability_warning || null);
      })
      .catch(() => setRosterError('Failed to load the roster for this subject and period. Please try again.'))
      .finally(() => setRosterLoading(false));
  }, [subject, studyPeriod]);

  const filteredRoster = roster.filter(r =>
    r.student_id.toLowerCase().includes(rosterSearch.trim().toLowerCase())
  );

  // ── Real-student detail (roster row → assessments + AI insight) ────────────

  const fetchDetailGeminiInsight = async (detail) => {
    setDetailGeminiLoading(true);
    const factorsText = shapFactorsText(detail.shap_explanation);
    // When real SHAP factors are available, the per-item breakdown is
    // redundant (the factors already reflect assessment-driven features) and
    // was pushing the question past the backend's length limit for students
    // with several recorded items — verified this 422'd in practice, not
    // just theoretically. Only include the raw breakdown as a fallback when
    // there's no SHAP data to ground the question in instead.
    const question = factorsText
      ? `A student in subject ${detail.subject} has risk band ${detail.risk_band} ` +
        `(${detail.probability}% pass probability), cumulative weighted score ${detail.partial_weighted_score}%. ` +
        `Real SHAP feature attributions for this prediction: ${factorsText}. ` +
        `Give a two sentence plain English insight for their lecturer, based ONLY on these ` +
        `real factors — do not invent other reasons. Suggest what action to consider.`
      : `A student in subject ${detail.subject} has a cumulative weighted score of ` +
        `${detail.partial_weighted_score}% so far, with risk band ${detail.risk_band}, ` +
        `based on ${(detail.assessments_used || []).length} recorded assessment(s): ` +
        `${(detail.assessments_used || []).map(a => `${a.type}: ${Math.round(a.mark_percent)}%`).join(', ')}. ` +
        `Give a two sentence plain English insight for their lecturer about what this result ` +
        `suggests and what action to consider.`;
    try {
      const res = await api.post('/api/gemini/ask', { question, subject, trimester: studyPeriod });
      const answer = res.data.answer || '';
      setDetailGeminiInsight(
        answer && answer !== 'AI insight unavailable.'
          ? answer
          : 'AI insight temporarily unavailable. Please try again.'
      );
    } catch {
      setDetailGeminiInsight('AI insight temporarily unavailable. Please try again.');
    } finally {
      setDetailGeminiLoading(false);
    }
  };

  const openStudentDetail = (studentId) => {
    const rosterRow = roster.find(r => r.student_id === studentId);
    if (!rosterRow) return;
    setSelectedStudentId(studentId);
    setView('detail');
    setStudentDetail(null);
    setDetailError(null);
    setDetailGeminiInsight(null);
    setDetailLoading(true);

    api.get(`/api/explorer/student/${encodeURIComponent(studentId)}?subject=${encodeURIComponent(subject)}&study_period=${encodeURIComponent(studyPeriod)}`)
      .then(async (r) => {
        const assessmentsUsed = (r.data.records || []).map(rec => ({
          type:         rec.assessment_type,
          mark_percent: rec.mark_percent,
          weighting:    rec.weighting,
        }));

        const baseDetail = {
          subject,
          study_period:            studyPeriod,
          probability:             rosterRow.probability,
          prediction:              rosterRow.prediction,
          risk_band:               rosterRow.risk_band,
          assessments_used:        assessmentsUsed,
          total_weight_recorded:   rosterRow.cumulative_weighting_recorded,
          partial_weighted_score:  rosterRow.current_weighted_score,
          coverage_status:         rosterRow.coverage_status,
          estimate_type:           rosterRow.estimate_type,
        };

        // No prediction exists yet for an insufficient-data student — nothing
        // for Gemini or SHAP to comment on, and the prompt would reference a
        // null risk_band nonsensically.
        if (baseDetail.coverage_status === 'insufficient_data') {
          setStudentDetail(baseDetail);
          return;
        }

        // The roster endpoint doesn't compute SHAP per student (would be
        // wasteful across 250+ rows on every roster load) — re-run this one
        // student through /api/predict on demand so the detail view gets
        // real per-feature attributions from the exact model that scores
        // them, not just the roster's cached probability/risk band.
        const sorted = [...assessmentsUsed].sort((a, b) => b.weighting - a.weighting);
        const a1 = sorted[0] || { mark_percent: 0, weighting: 0 };
        const a2 = sorted[1] || { mark_percent: 0, weighting: 0 };
        try {
          const predictRes = await api.post('/api/predict', {
            subject,
            study_period:            studyPeriod,
            trimester_num:           parseFloat(studyPeriod),
            student_id:              studentId,
            assess1_mark:            a1.mark_percent,
            assess1_weight:          a1.weighting,
            assess1_contribution:    parseFloat(((a1.mark_percent * a1.weighting) / 100).toFixed(4)),
            assess2_mark:            a2.mark_percent,
            assess2_weight:          a2.weighting,
            assess2_contribution:    parseFloat(((a2.mark_percent * a2.weighting) / 100).toFixed(4)),
            // /api/predict recomputes both server-side from assessments_used —
            // see handlePredictWhatIf's identical comment.
            partial_weighted_score:  0,
            partial_weight_coverage: 0,
            num_assessments:         assessmentsUsed.length,
            total_weight_recorded:   assessmentsUsed.reduce((sum, a) => sum + a.weighting, 0),
            weight_complete:         baseDetail.estimate_type == null,
            assessments_used:        assessmentsUsed,
          });
          const detail = { ...baseDetail, ...predictRes.data };
          setStudentDetail(detail);
          fetchDetailGeminiInsight(detail);
        } catch {
          // SHAP/re-prediction is an enhancement, not the primary data —
          // fall back to the roster-cached view rather than blocking the
          // whole detail page on this extra call failing.
          setStudentDetail(baseDetail);
          fetchDetailGeminiInsight(baseDetail);
        }
      })
      .catch(() => setDetailError('Failed to load this student\'s assessment history. Please try again.'))
      .finally(() => setDetailLoading(false));
  };

  const backToRoster = () => {
    setView('roster');
    setSelectedStudentId(null);
    setStudentDetail(null);
    setDetailGeminiInsight(null);
  };

  // ── What-if simulator (secondary, manual entry) ─────────────────────────────

  useEffect(() => {
    if (view !== 'whatif' || !subject || !studyPeriod) return;
    setWhatIfAssessmentTypes([]);
    setWhatIfMarks({});
    setWhatIfMarkErrors({});
    setWhatIfWeightComplete(true);
    setWhatIfResult(null);
    setWhatIfGeminiInsight(null);
    setWhatIfError(null);
    api.get(`/api/subjects/${encodeURIComponent(subject)}/assessments?study_period=${encodeURIComponent(studyPeriod)}`)
      .then(r => {
        if (r.data.prediction_available === false) {
          setWhatIfAssessmentTypes([]);
          return;
        }
        setWhatIfAssessmentTypes(r.data.assessments || []);
        setWhatIfWeightComplete(r.data.weight_complete ?? true);
      })
      .catch(() => setWhatIfError('Failed to load assessment types for this subject.'));
  }, [view, subject, studyPeriod]);

  const handleWhatIfMarkChange = (assessmentType, weighting, value) => {
    setWhatIfMarks(p => ({ ...p, [assessmentType]: value }));
    const num = parseFloat(value);
    setWhatIfMarkErrors(p => {
      if (!isNaN(num) && num > weighting) {
        return { ...p, [assessmentType]: `Maximum mark for this assessment is ${weighting}.` };
      }
      const next = { ...p };
      delete next[assessmentType];
      return next;
    });
  };

  const handleWhatIfAttendanceChange = (value) => {
    setWhatIfAttendanceRate(value);
    const num = parseFloat(value);
    setWhatIfAttendanceError(
      value !== '' && (isNaN(num) || num < 0 || num > 100)
        ? 'Attendance rate must be between 0 and 100.'
        : null
    );
  };

  // Requires at least one filled field, not every field — the point of the
  // what-if tool is to test genuinely partial scenarios too (e.g. 2 of 5
  // assessments). Coverage below 50% still gets a real "insufficient data"
  // response from the server (see handlePredictWhatIf/classify_coverage),
  // this button just no longer blocks reaching that server round-trip.
  const canPredictWhatIf =
    subject !== '' &&
    studyPeriod !== '' &&
    whatIfAssessmentTypes.length > 0 &&
    whatIfAssessmentTypes.some(a => whatIfMarks[a.assessmentType] !== undefined && whatIfMarks[a.assessmentType] !== '') &&
    Object.keys(whatIfMarkErrors).length === 0 &&
    !whatIfAttendanceError &&
    !whatIfLoading;

  const fetchWhatIfGeminiInsight = async (predResult) => {
    setWhatIfGeminiLoading(true);
    const factorsText = shapFactorsText(predResult.shap_explanation);
    // See fetchDetailGeminiInsight's identical comment — the per-item
    // breakdown is dropped when real SHAP factors are available since it's
    // redundant and was pushing the question past the backend's length
    // limit (verified: 422 in practice for realistic assessment counts).
    const question = factorsText
      ? `A hypothetical student in subject ${predResult.subject} scored a weighted total of ` +
        `${predResult.partial_weighted_score}% with risk band ${predResult.risk_band} ` +
        `(${predResult.probability}% pass probability). ` +
        `Real SHAP feature attributions for this prediction: ${factorsText}. ` +
        `Give a two sentence plain English insight for their lecturer, based ONLY on these ` +
        `real factors — do not invent other reasons. Suggest what action to consider.`
      : `A hypothetical student in subject ${predResult.subject} scored a weighted total of ` +
        `${predResult.partial_weighted_score}% with risk band ${predResult.risk_band}. ` +
        `Their assessment breakdown is ${(predResult.assessments_used || []).map(a => `${a.type}: ${a.mark_percent}%`).join(', ')}. ` +
        `Give a two sentence plain English insight ` +
        `for their lecturer about what this result suggests and what action to consider.`;
    try {
      const res = await api.post('/api/gemini/ask', { question, subject, trimester: studyPeriod });
      const answer = res.data.answer || '';
      setWhatIfGeminiInsight(
        answer && answer !== 'AI insight unavailable.'
          ? answer
          : 'AI insight temporarily unavailable. Please try again.'
      );
    } catch {
      setWhatIfGeminiInsight('AI insight temporarily unavailable. Please try again.');
    } finally {
      setWhatIfGeminiLoading(false);
    }
  };

  const handlePredictWhatIf = async () => {
    if (!canPredictWhatIf) return;
    setWhatIfLoading(true);
    setWhatIfError(null);
    setWhatIfResult(null);
    setWhatIfGeminiInsight(null);

    // Only the fields the user actually filled in — NOT every assessment
    // type for the subject. This is what makes cumulative_weighting_recorded
    // (computed server-side in main.py as sum(a["weighting"] for a in
    // assessments_used), never from a client-sent total) reflect a genuinely
    // partial scenario instead of always reading as 100% regardless of what
    // was entered.
    const filledTypes = whatIfAssessmentTypes.filter(
      at => whatIfMarks[at.assessmentType] !== undefined && whatIfMarks[at.assessmentType] !== ''
    );
    const totalWeight     = filledTypes.reduce((s, at) => s + at.weighting, 0);
    const assessmentsUsed = filledTypes.map(at => {
      const rawMark = parseFloat(whatIfMarks[at.assessmentType]);
      return {
        type:         at.assessmentType,
        mark_percent: (rawMark / at.weighting) * 100,
        weighting:    at.weighting,
      };
    });
    const sorted = [...assessmentsUsed].sort((a, b) => b.weighting - a.weighting);
    const a1 = sorted[0] || { mark_percent: 0, weighting: 0 };
    const a2 = sorted[1] || { mark_percent: 0, weighting: 0 };
    const body = {
      subject,
      study_period:            studyPeriod,
      trimester_num:           parseFloat(studyPeriod),
      assess1_mark:            a1.mark_percent,
      assess1_weight:          a1.weighting,
      assess1_contribution:    parseFloat(((a1.mark_percent * a1.weighting) / 100).toFixed(4)),
      assess2_mark:            a2.mark_percent,
      assess2_weight:          a2.weighting,
      assess2_contribution:    parseFloat(((a2.mark_percent * a2.weighting) / 100).toFixed(4)),
      // /api/predict recomputes both of these server-side from assessments_used
      // (top-2-by-weight, matching how the model was trained) and ignores
      // whatever is sent here — these are placeholders only, to satisfy the
      // request schema. See predictor.compute_partial_score().
      partial_weighted_score:  0,
      partial_weight_coverage: 0,
      num_assessments:         filledTypes.length,
      total_weight_recorded:   totalWeight,
      weight_complete:         whatIfWeightComplete,
      assessments_used:        assessmentsUsed,
      // Left as null when blank — the backend fills in this subject's real
      // average attendance rate rather than the frontend guessing one.
      attendance_rate:         whatIfAttendanceRate !== '' ? parseFloat(whatIfAttendanceRate) / 100 : null,
    };

    try {
      const res = await api.post('/api/predict', body);
      setWhatIfResult(res.data);
      // No prediction exists for an insufficient-data result — nothing for
      // Gemini to comment on, and the prompt would reference an undefined
      // risk_band/probability. Same guard as the real-student detail flow.
      if (res.data.coverage_status !== 'insufficient_data') {
        fetchWhatIfGeminiInsight(res.data);
      }
    } catch (err) {
      setWhatIfError(err.response?.data?.detail || 'Prediction failed. Please check your inputs and try again.');
    } finally {
      setWhatIfLoading(false);
    }
  };

  // ── Render ───────────────────────────────────────────────────────────────────

  return (
    <div style={s.page}>
      <div style={s.pageHeader}>
        <div>
          <h1 style={s.pageTitle}>{isAdmin ? 'Predictive Reports' : 'Predictor'}</h1>
          <p style={s.pageSub}>
            {view === 'whatif'
              ? 'Test a hypothetical scenario — not a real student'
              : 'Real-time risk across your roster, from actual recorded assessments'}
          </p>
        </div>
      </div>

      <div style={s.layout}>

        {/* ── Left panel — subject/period selection, always visible ── */}
        <div style={{ flex: '0 0 300px', minWidth: 0 }}>
          <div style={s.card}>
            <h3 style={s.cardTitle}>Select Subject & Period</h3>

            <div style={s.fieldGroup}>
              <label style={s.label}>Subject <span style={{ color: '#DC2626' }}>*</span></label>
              <select style={s.select} value={subject} onChange={e => setSubject(e.target.value)}>
                <option value="">Select subject…</option>
                {subjects.map(sv => <option key={sv} value={sv}>{sv}</option>)}
              </select>
            </div>

            {subject && reliabilityWarning && (
              <div style={s.warnBanner}>
                ⚠ Assessment data for this subject is incomplete in some periods. Predictions may be less accurate for the selected period.
              </div>
            )}

            <div style={s.fieldGroup}>
              <label style={s.label}>Study Period <span style={{ color: '#DC2626' }}>*</span></label>
              <select style={s.select} value={studyPeriod} onChange={e => setStudyPeriod(e.target.value)}>
                <option value="">Select period…</option>
                {periods.map(p => <option key={p} value={p}>{p}</option>)}
              </select>
            </div>

            {subject && !studyPeriod && (
              <p style={{ fontSize: 12, color: '#64748B', margin: '0 0 16px' }}>
                Select a study period to load the roster.
              </p>
            )}

            {predictionUnavailable && (
              <div style={s.unavailablePanel}>
                <p style={s.unavailableMsg}>{unavailableMessage}</p>
                <p style={s.unavailableSub}>Contact your Head of Technology to report this data gap.</p>
              </div>
            )}

            {!predictionUnavailable && rosterMeta && (
              <div style={s.scoreBox}>
                <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 4 }}>
                  <span style={{ fontSize: 12, color: '#475569' }}>Students</span>
                  <span style={{ fontSize: 13, fontWeight: 700, color: '#1A2E40' }}>{rosterMeta.totalStudents}</span>
                </div>
                <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                  <span style={{ fontSize: 12, color: '#475569' }}>Period Total Weight</span>
                  <span style={{ fontSize: 13, fontWeight: 700, color: '#1A2E40' }}>{rosterMeta.periodTotalWeight}%</span>
                </div>
              </div>
            )}

            {!predictionUnavailable && subject && studyPeriod && (
              <button
                style={{ ...s.whatIfToggleBtn, ...(view === 'whatif' ? s.whatIfToggleBtnActive : {}) }}
                onClick={() => setView(view === 'whatif' ? 'roster' : 'whatif')}
              >
                {view === 'whatif' ? '← Back to Roster' : '✎ Test a Hypothetical Scenario'}
              </button>
            )}
          </div>
        </div>

        {/* ── Right panel ── */}
        <div style={{ flex: 1, minWidth: 0 }}>

          {(!subject || !studyPeriod) && (
            <div style={s.emptyCard}>
              <div style={s.emptyIcon}>📋</div>
              <p style={s.emptyText}>Select a subject and study period to view the roster.</p>
            </div>
          )}

          {subject && studyPeriod && rosterLoading && (
            <div style={s.emptyCard}>
              <div style={{ ...s.spinner, margin: '0 auto 16px' }} />
              <p style={s.emptyText}>Loading roster…</p>
            </div>
          )}

          {rosterError && <div style={s.errBanner}>{rosterError}</div>}

          {/* ── Default view: roster table ── */}
          {view === 'roster' && !rosterLoading && !predictionUnavailable && subject && studyPeriod && roster.length > 0 && (
            <div style={s.card}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 14 }}>
                <h3 style={{ ...s.cardTitle, margin: 0 }}>Student Roster — sorted by risk</h3>
                <input
                  style={s.searchInput}
                  placeholder="Search student ID…"
                  value={rosterSearch}
                  onChange={e => setRosterSearch(e.target.value)}
                />
              </div>
              <div style={{ overflowX: 'auto', maxHeight: 560, overflowY: 'auto' }}>
                <table style={{ width: '100%', borderCollapse: 'collapse' }}>
                  <thead>
                    <tr>
                      {['Student', 'Assessments Recorded', 'Weight Recorded', 'Weighted Score', 'Risk'].map(h => (
                        <th key={h} style={s.th}>{h}</th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {filteredRoster.map((r, i) => (
                      <tr
                        key={r.student_id}
                        style={{ background: i % 2 === 0 ? '#fff' : '#F8FAFC', cursor: 'pointer' }}
                        onClick={() => openStudentDetail(r.student_id)}
                      >
                        <td style={{ ...s.td, fontWeight: 700, color: '#1A2E40' }}>{r.student_id}</td>
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
                    {filteredRoster.length === 0 && (
                      <tr><td style={s.td} colSpan={5}>No students match "{rosterSearch}".</td></tr>
                    )}
                  </tbody>
                </table>
              </div>
            </div>
          )}

          {view === 'roster' && !rosterLoading && !predictionUnavailable && subject && studyPeriod && roster.length === 0 && !rosterError && (
            <div style={s.emptyCard}>
              <div style={s.emptyIcon}>📭</div>
              <p style={s.emptyText}>No students found for this subject and period.</p>
            </div>
          )}

          {/* ── Real-student detail (drilled in from roster) ── */}
          {view === 'detail' && (
            <>
              <button style={s.backBtn} onClick={backToRoster}>← Back to Roster</button>
              {detailLoading && (
                <div style={s.emptyCard}>
                  <div style={{ ...s.spinner, margin: '0 auto 16px' }} />
                  <p style={s.emptyText}>Loading {selectedStudentId}'s assessment history…</p>
                </div>
              )}
              {detailError && <div style={s.errBanner}>{detailError}</div>}
              {!detailLoading && studentDetail && (
                <>
                  <div style={{ marginBottom: 8, fontSize: 13, color: '#64748B' }}>
                    Student <strong style={{ color: '#1A2E40' }}>{selectedStudentId}</strong> — real recorded data
                  </div>
                  <PredictionResultPanel
                    result={studentDetail}
                    geminiLoading={detailGeminiLoading}
                    geminiInsight={detailGeminiInsight}
                  />
                  {/* Real student only — the what-if view never renders this,
                      since there is no real person to log an action against. */}
                  <InterventionPanel
                    studentId={selectedStudentId}
                    subject={subject}
                    studyPeriod={studyPeriod}
                  />
                  <p style={s.scopeFootnote}>
                    Prediction based on 124 verified subjects. Model trained on periods 23.2 to 25.2, validated on 25.3.
                  </p>
                </>
              )}
            </>
          )}

          {/* ── What-if simulator (secondary, clearly separated) ── */}
          {view === 'whatif' && (
            <>
              <div style={s.whatIfBanner}>
                ✎ <strong>What-If Simulator</strong> — enter hypothetical marks to test a scenario. This is not a real student's data.
              </div>

              {predictionUnavailable ? (
                <div style={s.unavailablePanel}>
                  <p style={s.unavailableMsg}>{unavailableMessage}</p>
                </div>
              ) : (
                <div style={s.card}>
                  {whatIfAssessmentTypes.length === 0 && (
                    <p style={s.emptyText}>Loading assessment types…</p>
                  )}
                  {!whatIfWeightComplete && whatIfAssessmentTypes.length > 0 && (
                    <div style={s.warnBanner}>
                      ⚠ Assessment weightings for this subject are incomplete. Predictions may be less accurate.
                    </div>
                  )}
                  {whatIfAssessmentTypes.map(at => (
                    <div key={at.assessmentType} style={{ marginBottom: 8 }}>
                      <div style={s.assessRow}>
                        <span style={s.assessCode}>{at.assessmentType} (out of {at.weighting})</span>
                        <input
                          type="number" min="0" max={at.weighting} step="0.1"
                          style={s.assessInput}
                          placeholder={`0 – ${at.weighting}`}
                          value={whatIfMarks[at.assessmentType] ?? ''}
                          onChange={e => handleWhatIfMarkChange(at.assessmentType, at.weighting, e.target.value)}
                        />
                      </div>
                      {whatIfMarkErrors[at.assessmentType] && (
                        <p style={s.markError}>{whatIfMarkErrors[at.assessmentType]}</p>
                      )}
                    </div>
                  ))}

                  {whatIfAssessmentTypes.length > 0 && (
                    <div style={{ marginBottom: 8 }}>
                      <div style={s.assessRow}>
                        <span style={s.assessCode}>Attendance rate (%)</span>
                        <input
                          type="number" min="0" max="100" step="1"
                          style={s.assessInput}
                          placeholder="Subject average"
                          value={whatIfAttendanceRate}
                          onChange={e => handleWhatIfAttendanceChange(e.target.value)}
                        />
                      </div>
                      {whatIfAttendanceError && (
                        <p style={s.markError}>{whatIfAttendanceError}</p>
                      )}
                      {whatIfAttendanceRate === '' && (
                        <p style={{ margin: '4px 0 0', fontSize: 11, color: '#94A3B8', fontStyle: 'italic' }}>
                          Left blank — this subject's real average attendance rate will be used.
                        </p>
                      )}
                    </div>
                  )}

                  <button
                    style={{ ...s.predictBtn, opacity: !canPredictWhatIf ? 0.5 : 1, cursor: !canPredictWhatIf ? 'not-allowed' : 'pointer' }}
                    disabled={!canPredictWhatIf}
                    onClick={handlePredictWhatIf}
                  >
                    {whatIfLoading ? 'Predicting…' : '✦ Predict Hypothetical Outcome'}
                  </button>

                  {whatIfError && <div style={s.errBanner}>{whatIfError}</div>}
                </div>
              )}

              {whatIfLoading && (
                <div style={s.emptyCard}>
                  <div style={{ ...s.spinner, margin: '0 auto 16px' }} />
                  <p style={s.emptyText}>Running prediction…</p>
                </div>
              )}

              {whatIfResult && (
                <>
                  {whatIfResult.model_name && (
                    <div style={{ ...s.modelTag, marginBottom: 12 }}>
                      <span style={s.modelLabel}>Model</span>
                      <span style={s.modelName}>{whatIfResult.model_name}</span>
                      {whatIfResult.model_accuracy != null && (
                        <span style={s.modelAcc}>{(whatIfResult.model_accuracy * 100).toFixed(1)}% accuracy</span>
                      )}
                    </div>
                  )}
                  <PredictionResultPanel
                    result={whatIfResult}
                    geminiLoading={whatIfGeminiLoading}
                    geminiInsight={whatIfGeminiInsight}
                  />
                </>
              )}
            </>
          )}
        </div>
      </div>

      <style>{`@keyframes spin { to { transform: rotate(360deg); } }`}</style>
    </div>
  );
}

// ── Styles ─────────────────────────────────────────────────────────────────────

const s = {
  page:       { padding: '28px 32px', background: '#F0F4F8', minHeight: '100vh', boxSizing: 'border-box' },
  pageHeader: { display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', marginBottom: 24 },
  pageTitle:  { margin: 0, fontSize: 20, fontWeight: 700, color: '#1A2E40' },
  pageSub:    { margin: '4px 0 0', fontSize: 13, color: '#64748B' },
  layout:     { display: 'flex', gap: 24, alignItems: 'flex-start' },

  modelTag:   { display: 'flex', alignItems: 'center', gap: 8, background: '#fff', border: '0.5px solid #DDE4EA', borderRadius: 10, padding: '8px 14px' },
  modelLabel: { fontSize: 10, fontWeight: 600, color: '#94A3B8', textTransform: 'uppercase', letterSpacing: 0.5 },
  modelName:  { fontSize: 12, fontWeight: 700, color: '#1E293B' },
  modelAcc:   { fontSize: 11, color: '#059669', fontWeight: 600 },

  card:        { background: '#fff', border: '0.5px solid #DDE4EA', borderRadius: 10, padding: '20px 24px', marginBottom: 16 },
  resultCard:  { background: '#fff', border: '0.5px solid #DDE4EA', borderRadius: 10, padding: '24px' },
  cardTitle:   { margin: '0 0 18px', fontSize: 14, fontWeight: 700, color: '#1A2E40' },
  sectionLabel:{ margin: '0 0 12px', fontSize: 11, fontWeight: 700, color: '#475569', textTransform: 'uppercase', letterSpacing: 0.6 },
  midTermBandNote: {
    background: '#FEF9C3', border: '0.5px solid #FDE68A', borderRadius: 8,
    padding: '9px 12px', fontSize: 11.5, color: '#854D0E', lineHeight: 1.5, marginBottom: 10,
  },

  fieldGroup: { marginBottom: 16 },
  label:      { display: 'block', fontSize: 11, fontWeight: 600, color: '#475569', textTransform: 'uppercase', letterSpacing: 0.5, marginBottom: 6 },
  select:     { width: '100%', border: '0.5px solid #C5D2DC', borderRadius: 8, padding: '9px 12px', fontSize: 13, color: '#1E293B', background: '#fff', outline: 'none', cursor: 'pointer', boxSizing: 'border-box' },
  predictBtn: { width: '100%', padding: '10px', borderRadius: 8, border: 'none', background: '#2E6E8E', color: '#fff', fontSize: 13, fontWeight: 700, cursor: 'pointer' },

  warnBanner: { background: '#FEF9C3', border: '0.5px solid #FDE68A', borderRadius: 8, padding: '10px 12px', fontSize: 12, color: '#854D0E', marginBottom: 16, lineHeight: 1.5 },

  unavailablePanel: { background: '#FEE2E2', border: '1px solid #FCA5A5', borderRadius: 8, padding: '16px', marginBottom: 16 },
  unavailableMsg:   { margin: 0, fontSize: 13, color: '#991B1B', fontWeight: 600, lineHeight: 1.5 },
  unavailableSub:   { margin: '8px 0 0', fontSize: 12, color: '#B91C1C', lineHeight: 1.5 },

  scopeFootnote: { margin: '10px 2px 0', fontSize: 11, color: '#94A3B8', lineHeight: 1.5 },

  assessRow:    { display: 'flex', alignItems: 'center', gap: 8 },
  assessCode:   { fontSize: 12, fontWeight: 700, color: '#1A2E40', whiteSpace: 'nowrap', flexShrink: 0 },
  assessInput:  { flex: 1, border: '0.5px solid #C5D2DC', borderRadius: 8, padding: '7px 10px', fontSize: 13, color: '#1E293B', outline: 'none', minWidth: 0, boxSizing: 'border-box' },
  markError:    { margin: '4px 0 0', fontSize: 11, color: '#DC2626', lineHeight: 1.4 },

  scoreBox:      { background: '#F8FAFC', border: '0.5px solid #DDE4EA', borderRadius: 8, padding: '12px 14px', marginBottom: 16 },

  emptyCard: { background: '#fff', border: '0.5px solid #DDE4EA', borderRadius: 10, padding: '64px 24px', textAlign: 'center' },
  emptyIcon: { fontSize: 36, margin: '0 0 12px' },
  emptyText: { margin: 0, fontSize: 14, color: '#64748B' },

  geminiBox: { background: '#F0FDFA', border: '1px solid #99F6E4', borderRadius: 8, padding: '14px', display: 'flex', flexDirection: 'column' },
  spinner:   { width: 20, height: 20, border: '2px solid #E2E8F0', borderTopColor: '#0D9488', borderRadius: '50%', animation: 'spin 0.8s linear infinite', flexShrink: 0 },

  th:        { fontSize: 11, fontWeight: 600, color: '#94A3B8', padding: '10px 12px', textAlign: 'left', borderBottom: '1px solid #E2E8F0', textTransform: 'uppercase', letterSpacing: 0.5, background: '#F8FAFC', whiteSpace: 'nowrap' },
  td:        { fontSize: 12, color: '#475569', padding: '10px 12px', borderBottom: '0.5px solid #F0F4F8', whiteSpace: 'nowrap' },
  errBanner: { background: '#FEE2E2', border: '0.5px solid #FECACA', borderRadius: 8, padding: '10px 12px', fontSize: 12, color: '#991B1B', marginTop: 12, lineHeight: 1.5 },

  searchInput:  { border: '0.5px solid #C5D2DC', borderRadius: 8, padding: '7px 10px', fontSize: 12, color: '#1E293B', outline: 'none', width: 200, boxSizing: 'border-box' },
  backBtn:      { background: 'none', border: 'none', color: '#2E6E8E', fontSize: 13, fontWeight: 700, cursor: 'pointer', padding: '0 0 12px', display: 'block' },

  whatIfToggleBtn:       { width: '100%', marginTop: 4, padding: '9px', borderRadius: 8, border: '0.5px solid #C5D2DC', background: '#fff', color: '#475569', fontSize: 12, fontWeight: 700, cursor: 'pointer' },
  whatIfToggleBtnActive: { background: '#EEF2F6', color: '#1A2E40', border: '0.5px solid #2E6E8E' },
  whatIfBanner: { background: '#EEF2FF', border: '0.5px solid #C7D2FE', borderRadius: 8, padding: '10px 14px', fontSize: 12, color: '#3730A3', marginBottom: 16, lineHeight: 1.5 },
};
