import { useState, useEffect } from 'react';
import { useSearchParams } from 'react-router-dom';
import { getUser } from '../utils/auth';
import api from '../services/api';

export default function LecturerPredictor() {
  const user       = getUser();
  const mySubjects = user?.subjects || [];

  const [searchParams] = useSearchParams();

  // Inputs — pre-fill from URL query params if present
  const [subject,  setSubject]  = useState(searchParams.get('subject') || '');
  const [assess1,  setAssess1]  = useState(searchParams.get('mark')    || '');
  const [assess2,  setAssess2]  = useState('');

  // Result state
  const [result,   setResult]   = useState(null);
  const [loading,  setLoading]  = useState(false);
  const [error,    setError]    = useState('');

  // Validation
  const a1Num     = parseFloat(assess1);
  const a2Num     = parseFloat(assess2);
  const a1Invalid = assess1 !== '' && (isNaN(a1Num) || a1Num < 0 || a1Num > 100);
  const a2Invalid = assess2 !== '' && (isNaN(a2Num) || a2Num < 0 || a2Num > 100);
  const canSubmit = subject && assess1 !== '' && !a1Invalid && !a2Invalid;

  // Auto-select first subject if none selected and only one available
  useEffect(() => {
    if (!subject && mySubjects.length === 1) setSubject(mySubjects[0]);
  }, []);  // eslint-disable-line

  const handlePredict = async () => {
    setLoading(true);
    setError('');
    setResult(null);
    try {
      const body = {
        subject,
        assess1_mark: a1Num,
        ...(assess2 !== '' ? { assess2_mark: a2Num } : {}),
      };
      const res = await api.post('/api/predict', body);
      setResult(res.data);
    } catch (err) {
      setError(err.response?.data?.detail || 'Prediction failed. Please try again.');
    } finally {
      setLoading(false);
    }
  };

  const handleReset = () => {
    setSubject(''); setAssess1(''); setAssess2('');
    setResult(null); setError('');
  };

  const riskColour = result
    ? { green: '#1D9E75', amber: '#D97706', red: '#DC2626' }[result.risk_colour] ?? '#1D9E75'
    : '#1D9E75';

  return (
    <div style={{ maxWidth: 680, margin: '0 auto' }}>

      {/* ── Header ──────────────────────────────────────────────── */}
      <div style={s.pageHeader}>
        <h1 style={s.pageTitle}>Predictive Console</h1>
        <p style={s.pageSub}>
          Predict whether a student will pass based on their current marks
        </p>
      </div>

      {/* ── Input card ──────────────────────────────────────────── */}
      <div style={s.card}>
        <h2 style={s.cardTitle}>Student Assessment Inputs</h2>

        {/* Subject */}
        <div style={s.field}>
          <label style={s.label}>Subject <span style={s.req}>*</span></label>
          <select
            style={s.select}
            value={subject}
            onChange={e => setSubject(e.target.value)}
          >
            <option value="">Select subject…</option>
            {mySubjects.map(sub => (
              <option key={sub} value={sub}>{sub}</option>
            ))}
          </select>
        </div>

        {/* Assessment 1 */}
        <div style={s.field}>
          <label style={s.label}>Assessment 1 Mark <span style={s.req}>*</span></label>
          <input
            type="number"
            min={0} max={100}
            style={{ ...s.input, borderColor: a1Invalid ? '#DC2626' : '#C5D2DC' }}
            placeholder="e.g. 72.5"
            value={assess1}
            onChange={e => setAssess1(e.target.value)}
          />
          {a1Invalid && <p style={s.fieldErr}>Must be between 0 and 100</p>}
        </div>

        {/* Assessment 2 */}
        <div style={s.field}>
          <label style={s.label}>Assessment 2 Mark <span style={s.optional}>(Optional)</span></label>
          <input
            type="number"
            min={0} max={100}
            style={{ ...s.input, borderColor: a2Invalid ? '#DC2626' : '#C5D2DC' }}
            placeholder="Enter if available"
            value={assess2}
            onChange={e => setAssess2(e.target.value)}
          />
          {a2Invalid && <p style={s.fieldErr}>Must be between 0 and 100</p>}
          <p style={s.hint}>Leave blank if Assessment 2 is not yet completed</p>
        </div>

        {error && <div style={s.errorBox}>{error}</div>}

        <button
          style={{ ...s.btn, opacity: (!canSubmit || loading) ? 0.55 : 1 }}
          disabled={!canSubmit || loading}
          onClick={handlePredict}
        >
          {loading ? (
            <span style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 8 }}>
              <Spinner /> Predicting…
            </span>
          ) : 'Predict Outcome'}
        </button>
      </div>

      {/* ── Result card ─────────────────────────────────────────── */}
      {result && (
        <div style={s.card}>

          {/* Probability number */}
          <div style={{ textAlign: 'center', marginBottom: 20 }}>
            <p style={{ ...s.probNumber, color: riskColour }}>
              {result.pass_probability}%
            </p>
            <p style={{ margin: '4px 0 0', fontSize: 13, color: '#64748B' }}>
              chance of passing
            </p>
          </div>

          {/* Pass/Fail badge */}
          <div style={{ display: 'flex', justifyContent: 'center', marginBottom: 24 }}>
            <span style={{
              ...s.predBadge,
              background: result.risk_colour === 'green' ? '#E1F5EE'
                        : result.risk_colour === 'amber' ? '#FEF3C7' : '#FCEBEB',
              color:      result.risk_colour === 'green' ? '#0F6E56'
                        : result.risk_colour === 'amber' ? '#92400E' : '#A32D2D',
            }}>
              {result.prediction}
            </span>
          </div>

          {/* Risk bar */}
          <div style={{ marginBottom: 8 }}>
            <div style={s.barTrack}>
              <div style={{
                ...s.barFill,
                width:      `${result.pass_probability}%`,
                background: riskColour,
              }} />
            </div>
            <div style={s.barLabels}>
              <span>High Risk</span>
              <span>Safe</span>
            </div>
          </div>

          {/* Confidence note */}
          {result.confidence_records > 0 && (
            <p style={s.confNote}>
              Based on {result.confidence_records.toLocaleString()} similar historical records
            </p>
          )}

          {/* Gemini advice */}
          {result.gemini_advice && result.gemini_advice !== 'AI insight unavailable.' && (
            <div style={s.geminiBox}>
              <span style={s.geminiIcon}>🤖</span>
              <div>
                <p style={s.geminiLabel}>AI Insight</p>
                <p style={s.geminiText}>{result.gemini_advice}</p>
              </div>
            </div>
          )}

          <button style={{ ...s.btn, marginTop: 20, background: '#475569' }} onClick={handleReset}>
            Predict Again
          </button>
        </div>
      )}
    </div>
  );
}

function Spinner() {
  return (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor"
      strokeWidth="2.5" style={{ animation: 'spin 0.8s linear infinite' }}>
      <style>{`@keyframes spin{to{transform:rotate(360deg)}}`}</style>
      <path d="M12 2v4M12 18v4M4.93 4.93l2.83 2.83M16.24 16.24l2.83 2.83M2 12h4M18 12h4M4.93 19.07l2.83-2.83M16.24 7.76l2.83-2.83"/>
    </svg>
  );
}

const s = {
  pageHeader: { marginBottom: 24 },
  pageTitle:  { margin: '0 0 4px', fontSize: 24, fontWeight: 500, color: '#1A2E40' },
  pageSub:    { margin: 0, fontSize: 13, color: '#5A7A8A' },

  card: {
    background: '#fff', border: '0.5px solid #DDE4EA',
    borderRadius: 10, padding: '24px 28px', marginBottom: 20,
  },
  cardTitle: { margin: '0 0 20px', fontSize: 16, fontWeight: 600, color: '#1E293B' },

  field:    { marginBottom: 18 },
  label:    { display: 'block', fontSize: 13, fontWeight: 600, color: '#334155', marginBottom: 6 },
  req:      { color: '#DC2626', marginLeft: 2 },
  optional: { fontSize: 11, color: '#94A3B8', fontWeight: 400, marginLeft: 4 },
  hint:     { margin: '5px 0 0', fontSize: 11, color: '#94A3B8' },
  fieldErr: { margin: '5px 0 0', fontSize: 11, color: '#DC2626' },

  select: {
    width: '100%', padding: '10px 14px', borderRadius: 8,
    border: '0.5px solid #C5D2DC', fontSize: 13, color: '#1E293B',
    background: '#fff', cursor: 'pointer', outline: 'none',
  },
  input: {
    width: '100%', padding: '10px 14px', borderRadius: 8,
    border: '0.5px solid #C5D2DC', fontSize: 13, color: '#1E293B',
    outline: 'none', boxSizing: 'border-box',
  },

  errorBox: {
    background: '#FCEBEB', color: '#A32D2D', borderRadius: 8,
    padding: '10px 14px', fontSize: 13, marginBottom: 16,
  },

  btn: {
    width: '100%', padding: '12px 0', borderRadius: 8, border: 'none',
    background: '#2E6E8E', color: '#fff', fontSize: 14, fontWeight: 600,
    cursor: 'pointer', letterSpacing: 0.3, transition: 'background 0.15s',
  },

  probNumber: { margin: 0, fontSize: 56, fontWeight: 500, letterSpacing: -2, lineHeight: 1 },

  predBadge: {
    display: 'inline-block', borderRadius: 20, padding: '8px 22px',
    fontSize: 15, fontWeight: 600,
  },

  barTrack: {
    width: '100%', height: 10, background: '#F0F4F8',
    borderRadius: 5, overflow: 'hidden',
  },
  barFill: {
    height: '100%', borderRadius: 5, transition: 'width 0.6s ease',
  },
  barLabels: {
    display: 'flex', justifyContent: 'space-between',
    fontSize: 11, color: '#94A3B8', marginTop: 4,
  },

  confNote: { margin: '12px 0 0', fontSize: 12, color: '#94A3B8', textAlign: 'center' },

  geminiBox: {
    display: 'flex', gap: 12, alignItems: 'flex-start',
    background: '#F0F9FF', border: '1px solid #BAE6FD',
    borderRadius: 8, padding: '12px 16px', marginTop: 20,
  },
  geminiIcon:  { fontSize: 20, flexShrink: 0 },
  geminiLabel: { margin: '0 0 4px', fontSize: 11, fontWeight: 700, color: '#0369A1', textTransform: 'uppercase', letterSpacing: 0.5 },
  geminiText:  { margin: 0, fontSize: 13, color: '#1E293B', lineHeight: 1.5 },
};
