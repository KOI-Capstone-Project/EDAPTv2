// Admin predictive reports page: batch-level pass-probability view for all subjects.
import { useState, useEffect } from 'react';
import api from '../services/api';

// ── Sub-components ─────────────────────────────────────────────────────────────

function RiskBadge({ band }) {
  const map = {
    Safe:        { bg: '#DCFCE7', color: '#166534' },
    'At Risk':   { bg: '#FEF9C3', color: '#854D0E' },
    'High Risk': { bg: '#FEE2E2', color: '#991B1B' },
  };
  const c = map[band] || map['At Risk'];
  return (
    <span style={{ fontSize: 12, fontWeight: 600, padding: '4px 12px', borderRadius: 20, whiteSpace: 'nowrap', background: c.bg, color: c.color }}>
      {band}
    </span>
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

// ── Main component ─────────────────────────────────────────────────────────────

export default function AdminPredictor() {
  const [subjects,        setSubjects]        = useState([]);
  const [subject,         setSubject]         = useState('');
  const [assessmentTypes, setAssessmentTypes] = useState([]);
  const [marks,           setMarks]           = useState({});
  const [markErrors,      setMarkErrors]      = useState({});
  const [studyPeriod,     setStudyPeriod]     = useState('');
  const [periods,         setPeriods]         = useState([]);
  const [weightComplete,  setWeightComplete]  = useState(true);
  const [result,          setResult]          = useState(null);
  const [loading,         setLoading]         = useState(false);
  const [geminiLoading,   setGeminiLoading]   = useState(false);
  const [geminiInsight,   setGeminiInsight]   = useState(null);
  const [error,           setError]           = useState(null);
  const [predictionUnavailable, setPredictionUnavailable] = useState(false);
  const [unavailableMessage,    setUnavailableMessage]    = useState('');
  const [reliabilityWarning,    setReliabilityWarning]    = useState(null);
  const [history,              setHistory]              = useState([]);
  const [partialWeightedScore, setPartialWeightedScore] = useState(0);

  useEffect(() => {
    api.get('/api/filters')
      .then(r => { setSubjects(r.data.subjects || []); setPeriods(r.data.periods || []); })
      .catch(() => {});
  }, []);

  useEffect(() => {
    setAssessmentTypes([]);
    setMarks({});
    setMarkErrors({});
    setWeightComplete(true);
    setResult(null);
    setGeminiInsight(null);
    setError(null);
    setPredictionUnavailable(false);
    setUnavailableMessage('');
    setReliabilityWarning(null);
    if (!subject || !studyPeriod) return;
    api.get(`/api/subjects/${encodeURIComponent(subject)}/assessments?study_period=${encodeURIComponent(studyPeriod)}`)
      .then(r => {
        if (r.data.prediction_available === false) {
          setPredictionUnavailable(true);
          setUnavailableMessage(r.data.message || '');
          setAssessmentTypes([]);
          setMarks({});
          return;
        }
        setAssessmentTypes(r.data.assessments || []);
        setWeightComplete(r.data.weight_complete ?? true);
        setReliabilityWarning(r.data.reliability_warning || null);
      })
      .catch(() => {
        setAssessmentTypes([]);
        setError('Failed to load assessments for this subject. Please try again.');
      });
  }, [subject, studyPeriod]);

  useEffect(() => {
    // Raw marks already equal weighted contributions (MAXMARK === WEIGHTING),
    // so the weighted score is simply the sum of the raw marks entered.
    const score = assessmentTypes.reduce((sum, a) => {
      const mark = parseFloat(marks[a.assessmentType] || 0);
      return sum + mark;
    }, 0);
    setPartialWeightedScore(parseFloat(score.toFixed(1)));
  }, [marks, assessmentTypes]);

  const partialWeightCoverage = assessmentTypes.reduce((sum, at) => {
    const m = parseFloat(marks[at.assessmentType]);
    return isNaN(m) ? sum : sum + at.weighting;
  }, 0) / 100;

  const handleMarkChange = (assessmentType, weighting, value) => {
    setMarks(p => ({ ...p, [assessmentType]: value }));
    const num = parseFloat(value);
    setMarkErrors(p => {
      if (!isNaN(num) && num > weighting) {
        return { ...p, [assessmentType]: `Maximum mark for this assessment is ${weighting}.` };
      }
      const next = { ...p };
      delete next[assessmentType];
      return next;
    });
  };

  const canPredict =
    subject !== '' &&
    studyPeriod !== '' &&
    !predictionUnavailable &&
    assessmentTypes.length > 0 &&
    assessmentTypes.every(a => marks[a.assessmentType] !== undefined && marks[a.assessmentType] !== '') &&
    Object.keys(markErrors).length === 0 &&
    !loading;

  const fetchGeminiInsight = async (predResult) => {
    setGeminiLoading(true);
    const bkdn = (predResult.assessments_used || [])
      .map(a => `${a.type}: ${a.mark_percent}%`)
      .join(', ');
    const question =
      `A student in subject ${predResult.subject} scored a weighted total of ` +
      `${predResult.partial_weighted_score}% with risk band ${predResult.risk_band}. ` +
      `Their assessment breakdown is ${bkdn}. Give a two sentence plain English insight ` +
      `for their lecturer about what this result suggests and what action to consider.`;
    try {
      const res = await api.post('/api/gemini/ask', {
        question,
        subject:   subject,
        trimester: studyPeriod,
      });
      const answer = res.data.answer || '';
      setGeminiInsight(
        answer && answer !== 'AI insight unavailable.'
          ? answer
          : 'AI insight temporarily unavailable. Please try again.'
      );
    } catch {
      setGeminiInsight('AI insight temporarily unavailable. Please try again.');
    } finally {
      setGeminiLoading(false);
    }
  };

  const handlePredict = async () => {
    if (!canPredict) return;
    setLoading(true);
    setError(null);
    setResult(null);
    setGeminiInsight(null);

    const totalWeight     = assessmentTypes.reduce((s, at) => s + at.weighting, 0);
    const assessmentsUsed = assessmentTypes.map(at => {
      const rawMark = parseFloat(marks[at.assessmentType]);
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
      partial_weighted_score:  parseFloat(partialWeightedScore.toFixed(4)),
      partial_weight_coverage: parseFloat(partialWeightCoverage.toFixed(4)),
      num_assessments:         assessmentTypes.length,
      total_weight_recorded:   totalWeight,
      weight_complete:         weightComplete,
      assessments_used:        assessmentsUsed,
    };

    try {
      const res = await api.post('/api/predict', body);
      setResult(res.data);
      fetchGeminiInsight(res.data);
      setHistory(prev => [
        { ts: new Date().toLocaleTimeString(), subject, weightedScore: parseFloat(partialWeightedScore.toFixed(2)), probability: res.data.probability, prediction: res.data.prediction },
        ...prev,
      ].slice(0, 5));
    } catch (err) {
      setError(err.response?.data?.detail || 'Prediction failed. Please check your inputs and try again.');
    } finally {
      setLoading(false);
    }
  };

  const probColor = result
    ? result.probability >= 65 ? '#059669' : result.probability >= 40 ? '#D97706' : '#DC2626'
    : '#64748B';

  return (
    <div style={s.page}>
      {/* Header */}
      <div style={s.pageHeader}>
        <div>
          <h1 style={s.pageTitle}>Predictive Reports</h1>
          <p style={s.pageSub}>Run ML predictions for individual students</p>
        </div>
        {result?.model_name && (
          <div style={s.modelTag}>
            <span style={s.modelLabel}>Model</span>
            <span style={s.modelName}>{result.model_name}</span>
            {result.model_accuracy != null && (
              <span style={s.modelAcc}>{(result.model_accuracy * 100).toFixed(1)}% accuracy</span>
            )}
          </div>
        )}
      </div>

      <div style={s.layout}>

        {/* ── Left panel ── */}
        <div style={{ flex: '0 0 300px', minWidth: 0 }}>
          <div style={s.card}>
            <h3 style={s.cardTitle}>Run Prediction</h3>

            {/* Subject */}
            <div style={s.fieldGroup}>
              <label style={s.label}>Subject <span style={{ color: '#DC2626' }}>*</span></label>
              <select style={s.select} value={subject}
                onChange={e => setSubject(e.target.value)}>
                <option value="">Select subject…</option>
                {subjects.map(sv => <option key={sv} value={sv}>{sv}</option>)}
              </select>
            </div>

            {/* Reliability warning (mostly_clean subjects) */}
            {subject && reliabilityWarning && (
              <div style={s.warnBanner}>
                ⚠ Assessment data for this subject is incomplete in some periods. Predictions may be less accurate for the selected period.
              </div>
            )}

            {/* Weight warning */}
            {subject && !weightComplete && (
              <div style={s.warnBanner}>
                ⚠ Assessment weightings for this subject are incomplete. Predictions may be less accurate.
              </div>
            )}

            {/* Study period */}
            <div style={s.fieldGroup}>
              <label style={s.label}>Study Period <span style={{ color: '#DC2626' }}>*</span></label>
              <select style={s.select} value={studyPeriod}
                onChange={e => { setStudyPeriod(e.target.value); setError(null); }}>
                <option value="">Select period…</option>
                {periods.map(p => <option key={p} value={p}>{p}</option>)}
              </select>
            </div>

            {/* Prompt to select period when subject is chosen but period is not */}
            {subject && !studyPeriod && (
              <p style={{ fontSize: 12, color: '#64748B', margin: '0 0 16px' }}>
                Select a study period to load assessment types.
              </p>
            )}

            {/* Unreliable subject — assessment inputs replaced with a red panel */}
            {predictionUnavailable && (
              <div style={s.unavailablePanel}>
                <p style={s.unavailableMsg}>{unavailableMessage}</p>
                <p style={s.unavailableSub}>Contact your Head of Technology to report this data gap.</p>
              </div>
            )}

            {/* Assessment inputs */}
            {!predictionUnavailable && assessmentTypes.length > 0 && (
              <>
                <div style={{ marginBottom: 6 }}>
                  <label style={s.label}>Assessment Marks <span style={{ color: '#DC2626' }}>*</span></label>
                </div>
                {assessmentTypes.map(at => (
                  <div key={at.assessmentType} style={{ marginBottom: 8 }}>
                    <div style={s.assessRow}>
                      <span style={s.assessCode}>{at.assessmentType} (out of {at.weighting})</span>
                      <input
                        type="number" min="0" max={at.weighting} step="0.1"
                        style={s.assessInput}
                        placeholder={`0 – ${at.weighting}`}
                        value={marks[at.assessmentType] ?? ''}
                        onChange={e => handleMarkChange(at.assessmentType, at.weighting, e.target.value)}
                      />
                    </div>
                    {markErrors[at.assessmentType] && (
                      <p style={s.markError}>{markErrors[at.assessmentType]}</p>
                    )}
                  </div>
                ))}

                {/* Running weighted score */}
                <div style={s.scoreBox}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 6 }}>
                    <span style={{ fontSize: 12, fontWeight: 600, color: '#475569' }}>Weighted Score</span>
                    <span style={{ fontSize: 13, fontWeight: 700, color: '#1A2E40' }}>
                      {partialWeightedScore.toFixed(1)} / 100
                    </span>
                  </div>
                  <div style={s.progressTrack}>
                    <div style={{
                      ...s.progressFill,
                      width: `${partialWeightedScore}%`,
                      background: partialWeightedScore >= 50 ? '#059669' : '#DC2626',
                    }} />
                  </div>
                </div>
              </>
            )}

            <button
              style={{ ...s.predictBtn, opacity: !canPredict ? 0.5 : 1, cursor: !canPredict ? 'not-allowed' : 'pointer' }}
              disabled={!canPredict}
              onClick={handlePredict}
            >
              {loading ? 'Predicting…' : '✦ Predict Outcome'}
            </button>

            {error && <div style={s.errBanner}>{error}</div>}
          </div>
        </div>

        {/* ── Right panel ── */}
        <div style={{ flex: 1, minWidth: 0 }}>

          {!result && !loading && (
            <div style={s.emptyCard}>
              <div style={s.emptyIcon}>🎯</div>
              <p style={s.emptyText}>Select a subject, enter marks, and click <strong>Predict Outcome</strong>.</p>
            </div>
          )}

          {loading && (
            <div style={s.emptyCard}>
              <div style={{ ...s.spinner, margin: '0 auto 16px' }} />
              <p style={s.emptyText}>Running prediction…</p>
            </div>
          )}

          {result && (
            <>
              <div style={s.resultCard}>

                {/* Section 1 — Header */}
                <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', marginBottom: 20 }}>
                  <div>
                    <h2 style={{ margin: 0, fontSize: 22, fontWeight: 800, color: '#1A2E40' }}>{result.subject}</h2>
                    <p style={{ margin: '4px 0 0', fontSize: 13, color: '#64748B' }}>Study Period {result.study_period}</p>
                  </div>
                  <RiskBadge band={result.risk_band} />
                </div>

                {/* Section 2 — Gauge */}
                <div style={{ textAlign: 'center', paddingBottom: 20, borderBottom: '0.5px solid #E2E8F0' }}>
                  <Gauge pct={result.probability} />
                  <div style={{ fontSize: 34, fontWeight: 800, color: probColor, lineHeight: 1, marginTop: 8 }}>
                    {result.probability}%
                  </div>
                  <div style={{ fontSize: 16, fontWeight: 700, color: '#1A2E40', marginTop: 6 }}>
                    {result.prediction}
                  </div>
                  <div style={{ fontSize: 12, color: '#94A3B8', marginTop: 4 }}>
                    Based on similar historical records
                  </div>
                </div>

                {/* Section 3 — Assessment breakdown */}
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
                            <td style={{ ...s.td, fontVariantNumeric: 'tabular-nums' }}>
                              {((a.mark_percent * a.weighting) / 100).toFixed(1)}
                            </td>
                          </tr>
                        ))}
                        <tr style={{ background: '#F0F4F8' }}>
                          <td style={{ ...s.td, fontWeight: 700, color: '#1A2E40' }}>Total</td>
                          <td style={s.td}>—</td>
                          <td style={s.td}>{result.total_weight_recorded}%</td>
                          <td style={{ ...s.td, fontWeight: 800, color: probColor }}>
                            {result.weighted_final}
                          </td>
                        </tr>
                      </tbody>
                    </table>
                  </div>
                </div>

                {/* Section 4 — AI Insight */}
                <div style={{ paddingTop: 20, paddingBottom: 20, borderBottom: '0.5px solid #E2E8F0' }}>
                  <p style={s.sectionLabel}>AI Assisted Insight</p>
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
                        AI Assisted Insight — generated by Gemini. Verify before acting on this advice.
                      </p>
                    </div>
                  )}
                </div>

                {/* Section 5 — Risk scale */}
                <div style={{ paddingTop: 20 }}>
                  <p style={s.sectionLabel}>Risk Scale</p>
                  <div style={{ display: 'flex', gap: 8 }}>
                    {[
                      { key: 'High Risk', label: 'High Risk', range: '0 – 39%',   bg: '#FEE2E2', text: '#991B1B', border: '#DC2626' },
                      { key: 'At Risk',   label: 'At Risk',   range: '40 – 64%',  bg: '#FEF9C3', text: '#854D0E', border: '#D97706' },
                      { key: 'Safe',      label: 'Safe',      range: '65 – 100%', bg: '#DCFCE7', text: '#166534', border: '#059669' },
                    ].map(t => (
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

              {/* Model scope footnote */}
              <p style={s.scopeFootnote}>
                Prediction based on 57 verified subjects. Model trained on periods 23.2 to 25.2, validated on 25.3.
              </p>

              {/* Section 6 — Recent predictions */}
              {history.length > 0 && (
                <div style={{ ...s.card, marginTop: 16, marginBottom: 0 }}>
                  <h3 style={s.cardTitle}>Recent Predictions</h3>
                  <div style={{ overflowX: 'auto' }}>
                    <table style={{ width: '100%', borderCollapse: 'collapse' }}>
                      <thead>
                        <tr>
                          {['Time', 'Subject', 'Weighted Score', 'Probability', 'Prediction'].map(h => (
                            <th key={h} style={s.th}>{h}</th>
                          ))}
                        </tr>
                      </thead>
                      <tbody>
                        {history.map((row, i) => {
                          const pc = row.probability >= 65 ? '#059669' : row.probability >= 40 ? '#D97706' : '#DC2626';
                          return (
                            <tr key={i} style={{ background: i % 2 === 0 ? '#fff' : '#F8FAFC' }}>
                              <td style={s.td}>{row.ts}</td>
                              <td style={{ ...s.td, fontWeight: 600, color: '#1A2E40' }}>{row.subject}</td>
                              <td style={s.td}>{row.weightedScore.toFixed(1)}%</td>
                              <td style={{ ...s.td, fontWeight: 700, color: pc }}>{row.probability}%</td>
                              <td style={s.td}>{row.prediction}</td>
                            </tr>
                          );
                        })}
                      </tbody>
                    </table>
                  </div>
                </div>
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
  progressTrack: { height: 4, background: '#E2E8F0', borderRadius: 4, overflow: 'hidden' },
  progressFill:  { height: '100%', borderRadius: 4, transition: 'width 0.3s ease' },

  emptyCard: { background: '#fff', border: '0.5px solid #DDE4EA', borderRadius: 10, padding: '64px 24px', textAlign: 'center' },
  emptyIcon: { fontSize: 36, margin: '0 0 12px' },
  emptyText: { margin: 0, fontSize: 14, color: '#64748B' },

  geminiBox: { background: '#F0FDFA', border: '1px solid #99F6E4', borderRadius: 8, padding: '14px', display: 'flex', flexDirection: 'column' },
  spinner:   { width: 20, height: 20, border: '2px solid #E2E8F0', borderTopColor: '#0D9488', borderRadius: '50%', animation: 'spin 0.8s linear infinite', flexShrink: 0 },

  th:        { fontSize: 11, fontWeight: 600, color: '#94A3B8', padding: '10px 12px', textAlign: 'left', borderBottom: '1px solid #E2E8F0', textTransform: 'uppercase', letterSpacing: 0.5, background: '#F8FAFC', whiteSpace: 'nowrap' },
  td:        { fontSize: 12, color: '#475569', padding: '10px 12px', borderBottom: '0.5px solid #F0F4F8', whiteSpace: 'nowrap' },
  errBanner: { background: '#FEE2E2', border: '0.5px solid #FECACA', borderRadius: 8, padding: '10px 12px', fontSize: 12, color: '#991B1B', marginTop: 12, lineHeight: 1.5 },
};
