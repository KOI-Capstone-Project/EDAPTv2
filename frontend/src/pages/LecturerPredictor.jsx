import { useState } from 'react';
import { getUser } from '../utils/auth';
import api from '../services/api';

function RiskBadge({ level }) {
  const map = {
    Safe:        { bg: '#DCFCE7', color: '#166534' },
    'At Risk':   { bg: '#FEF9C3', color: '#854D0E' },
    'High Risk': { bg: '#FEE2E2', color: '#991B1B' },
  };
  const c = map[level] || map['At Risk'];
  return <span style={{ ...s.badge, background: c.bg, color: c.color }}>{level}</span>;
}

function ProbabilityArc({ pct }) {
  const r = 54, cx = 70, cy = 70, stroke = 8;
  const circumference = Math.PI * r;
  const arc = circumference * (pct / 100);
  const color = pct >= 65 ? '#059669' : pct >= 40 ? '#D97706' : '#DC2626';
  return (
    <svg width={140} height={80} viewBox="0 0 140 80">
      <path d={`M ${cx - r} ${cy} A ${r} ${r} 0 0 1 ${cx + r} ${cy}`} fill="none" stroke="#EEF0F4" strokeWidth={stroke} strokeLinecap="round" />
      <path d={`M ${cx - r} ${cy} A ${r} ${r} 0 0 1 ${cx + r} ${cy}`} fill="none" stroke={color} strokeWidth={stroke} strokeLinecap="round" strokeDasharray={`${arc} ${circumference}`} />
      <text x={cx} y={cy - 6} textAnchor="middle" fontSize={22} fontWeight={700} fill={color}>{pct}%</text>
      <text x={cx} y={cy + 12} textAnchor="middle" fontSize={10} fill="#94A3B8">pass probability</text>
    </svg>
  );
}

export default function LecturerPredictor() {
  const user     = getUser();
  const subjects = user?.subjects || [];

  const [subject,  setSubject]  = useState('');
  const [assess1,  setAssess1]  = useState('');
  const [assess2,  setAssess2]  = useState('');
  const [result,   setResult]   = useState(null);
  const [loading,  setLoading]  = useState(false);
  const [error,    setError]    = useState(null);
  const [history,  setHistory]  = useState([]);

  const handlePredict = async () => {
    if (!subject || assess1 === '') return;
    const mark1 = parseFloat(assess1);
    if (isNaN(mark1) || mark1 < 0 || mark1 > 100) {
      setError('Assessment 1 mark must be between 0 and 100.');
      return;
    }
    setLoading(true);
    setError(null);
    setResult(null);
    try {
      const mark2 = assess2 !== '' ? parseFloat(assess2) : NaN;
      const body = {
        subject,
        assess1_mark: mark1,
        ...(!isNaN(mark2) && mark2 >= 0 && mark2 <= 100 ? { assess2_mark: mark2 } : {}),
      };
      const res = await api.post('/api/predict', body);
      setResult(res.data);
      setHistory(prev => [
        { subject, assess1: mark1, assess2: assess2 || '—', ...res.data, ts: new Date().toLocaleTimeString() },
        ...prev.slice(0, 9),
      ]);
    } catch (err) {
      setError(err.response?.data?.detail || 'Prediction failed. Ensure the ML model is trained.');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div style={s.page}>
      <div style={s.pageHeader}>
        <div>
          <h1 style={s.pageTitle}>Predictor</h1>
          <p style={s.pageSub}>Predict student pass probability using the ML model</p>
        </div>
      </div>

      <div style={s.layout}>
        {/* Input panel */}
        <div style={{ flex: '0 0 320px' }}>
          <div style={s.card}>
            <h3 style={s.cardTitle}>Run Prediction</h3>

            <div style={s.fieldGroup}>
              <label style={s.label}>Subject <span style={{ color: '#DC2626' }}>*</span></label>
              <select style={s.select} value={subject} onChange={e => { setSubject(e.target.value); setResult(null); }}>
                <option value="">Select subject…</option>
                {subjects.map(sv => <option key={sv} value={sv}>{sv}</option>)}
              </select>
            </div>

            <div style={s.fieldGroup}>
              <label style={s.label}>Assessment 1 Mark (%) <span style={{ color: '#DC2626' }}>*</span></label>
              <input
                type="number" min="0" max="100" step="0.1"
                style={s.input} placeholder="e.g. 62.5"
                value={assess1}
                onChange={e => { setAssess1(e.target.value); setResult(null); }}
              />
            </div>

            <div style={s.fieldGroup}>
              <label style={s.label}>
                Assessment 2 Mark (%)
                <span style={{ color: '#94A3B8', fontSize: 10, marginLeft: 6 }}>optional — uses median if blank</span>
              </label>
              <input
                type="number" min="0" max="100" step="0.1"
                style={s.input} placeholder="e.g. 58.0"
                value={assess2}
                onChange={e => { setAssess2(e.target.value); setResult(null); }}
              />
            </div>

            {error && <p style={s.errorMsg}>{error}</p>}

            <button
              style={{ ...s.predictBtn, opacity: (!subject || assess1 === '' || loading) ? 0.55 : 1 }}
              disabled={!subject || assess1 === '' || loading}
              onClick={handlePredict}
            >
              {loading ? 'Predicting…' : '✦ Predict Outcome'}
            </button>
          </div>

          <div style={s.infoCard}>
            <p style={s.infoTitle}>How it works</p>
            <p style={s.infoText}>
              The ML model uses Assessment 1 marks, subject difficulty index, and trimester
              to predict pass probability. Assessment 2 is optional — median is used when omitted.
            </p>
          </div>
        </div>

        {/* Result panel */}
        <div style={{ flex: 1, minWidth: 0 }}>
          {!result && !loading && (
            <div style={s.emptyCard}>
              <p style={s.emptyIcon}>🎯</p>
              <p style={s.emptyText}>Fill in the inputs and click <strong>Predict Outcome</strong> to see results.</p>
            </div>
          )}

          {loading && (
            <div style={s.emptyCard}>
              <p style={s.emptyText}>Running prediction…</p>
            </div>
          )}

          {result && (
            <div style={s.resultCard}>
              <div style={s.resultHeader}>
                <div>
                  <p style={s.resultSubject}>{subject}</p>
                  <p style={s.resultSub}>Assessment 1: {assess1}% {assess2 ? `· Assessment 2: ${assess2}%` : ''}</p>
                </div>
                <RiskBadge level={result.risk_level} />
              </div>

              <div style={s.gaugeRow}>
                <ProbabilityArc pct={result.pass_probability} />
                <div style={s.predictionLabel}>
                  <p style={s.predText}>{result.prediction}</p>
                  <p style={s.confText}>Based on {result.confidence_records} similar records</p>
                </div>
              </div>

              {result.gemini_advice && (
                <div style={s.adviceBox}>
                  <span style={s.sparkIcon}>✦</span>
                  <p style={s.adviceText}>{result.gemini_advice}</p>
                </div>
              )}

              <div style={s.riskScale}>
                {[
                  { label: 'High Risk', range: '0–39%',   color: '#FEE2E2', text: '#991B1B' },
                  { label: 'At Risk',   range: '40–64%',  color: '#FEF9C3', text: '#854D0E' },
                  { label: 'Safe',      range: '65–100%', color: '#DCFCE7', text: '#166534' },
                ].map(tier => (
                  <div key={tier.label} style={{ ...s.riskTier, background: tier.color }}>
                    <span style={{ fontWeight: 700, color: tier.text, fontSize: 12 }}>{tier.label}</span>
                    <span style={{ color: tier.text, fontSize: 11, opacity: 0.8 }}>{tier.range}</span>
                  </div>
                ))}
              </div>
            </div>
          )}

          {history.length > 0 && (
            <div style={{ ...s.card, marginTop: 20 }}>
              <h3 style={s.cardTitle}>Recent Predictions</h3>
              <div style={{ overflowX: 'auto' }}>
                <table style={{ width: '100%', borderCollapse: 'collapse' }}>
                  <thead>
                    <tr>
                      {['Time', 'Subject', 'A1', 'A2', 'Probability', 'Prediction'].map(h => (
                        <th key={h} style={s.th}>{h}</th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {history.map((row, i) => (
                      <tr key={i} style={{ background: i % 2 === 0 ? '#fff' : '#FAFBFC' }}>
                        <td style={s.td}>{row.ts}</td>
                        <td style={{ ...s.td, fontWeight: 600 }}>{row.subject}</td>
                        <td style={s.td}>{row.assess1}%</td>
                        <td style={s.td}>{row.assess2}</td>
                        <td style={{ ...s.td, fontWeight: 700, color: row.pass_probability >= 65 ? '#059669' : row.pass_probability >= 40 ? '#D97706' : '#DC2626' }}>
                          {row.pass_probability}%
                        </td>
                        <td style={s.td}><RiskBadge level={row.risk_level} /></td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}
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
  layout:     { display: 'flex', gap: 24, alignItems: 'flex-start' },

  card:      { background: '#fff', border: '0.5px solid #DDE4EA', borderRadius: 10, padding: '20px 24px', marginBottom: 16 },
  cardTitle: { margin: '0 0 18px', fontSize: 14, fontWeight: 700, color: '#1A2E40' },

  fieldGroup: { marginBottom: 16 },
  label: { display: 'block', fontSize: 11, fontWeight: 600, color: '#475569', textTransform: 'uppercase', letterSpacing: 0.5, marginBottom: 6 },
  select: {
    width: '100%', border: '0.5px solid #C5D2DC', borderRadius: 8, padding: '9px 12px',
    fontSize: 13, color: '#1E293B', background: '#fff', outline: 'none', cursor: 'pointer', boxSizing: 'border-box',
  },
  input: {
    width: '100%', border: '0.5px solid #C5D2DC', borderRadius: 8, padding: '9px 12px',
    fontSize: 13, color: '#1E293B', outline: 'none', boxSizing: 'border-box',
  },
  errorMsg: { margin: '0 0 12px', fontSize: 12, color: '#DC2626' },
  predictBtn: {
    width: '100%', padding: '10px', borderRadius: 8, border: 'none',
    background: '#2E6E8E', color: '#fff', fontSize: 13, fontWeight: 700, cursor: 'pointer',
  },

  infoCard: { background: '#F8FAFC', border: '0.5px solid #DDE4EA', borderRadius: 10, padding: '14px 16px' },
  infoTitle: { margin: '0 0 6px', fontSize: 12, fontWeight: 700, color: '#475569' },
  infoText:  { margin: 0, fontSize: 12, color: '#94A3B8', lineHeight: 1.6 },

  emptyCard: { background: '#fff', border: '0.5px solid #DDE4EA', borderRadius: 10, padding: '64px 24px', textAlign: 'center' },
  emptyIcon: { fontSize: 36, margin: '0 0 12px' },
  emptyText: { margin: 0, fontSize: 14, color: '#64748B' },

  resultCard:    { background: '#fff', border: '0.5px solid #DDE4EA', borderRadius: 10, padding: '24px' },
  resultHeader:  { display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', marginBottom: 20 },
  resultSubject: { margin: 0, fontSize: 18, fontWeight: 700, color: '#1A2E40' },
  resultSub:     { margin: '4px 0 0', fontSize: 12, color: '#94A3B8' },

  gaugeRow:        { display: 'flex', alignItems: 'center', gap: 24, marginBottom: 20 },
  predText:        { margin: 0, fontSize: 18, fontWeight: 700, color: '#1E293B' },
  confText:        { margin: '6px 0 0', fontSize: 12, color: '#94A3B8' },
  predictionLabel: {},

  adviceBox: {
    display: 'flex', gap: 10, alignItems: 'flex-start',
    background: '#EFF6FF', border: '0.5px solid #BFDBFE', borderRadius: 8,
    padding: '12px 14px', marginBottom: 20,
  },
  sparkIcon: { fontSize: 16, color: '#2E6E8E', flexShrink: 0, marginTop: 1 },
  adviceText: { margin: 0, fontSize: 13, color: '#1E293B', lineHeight: 1.6 },

  riskScale: { display: 'flex', gap: 8 },
  riskTier:  { flex: 1, borderRadius: 8, padding: '8px 12px', display: 'flex', flexDirection: 'column', gap: 2 },

  badge: { fontSize: 12, fontWeight: 600, padding: '3px 10px', borderRadius: 20, whiteSpace: 'nowrap' },
  th:    { fontSize: 11, fontWeight: 600, color: '#94A3B8', padding: '10px 12px', textAlign: 'left', borderBottom: '1px solid #E2E8F0', textTransform: 'uppercase', letterSpacing: 0.5, background: '#F8FAFC', whiteSpace: 'nowrap' },
  td:    { fontSize: 12, color: '#475569', padding: '10px 12px', borderBottom: '0.5px solid #F0F4F8', whiteSpace: 'nowrap' },
};
