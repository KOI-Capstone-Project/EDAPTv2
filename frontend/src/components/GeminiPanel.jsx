import { useState, useEffect, useRef } from 'react';
import api from '../services/api';

/**
 * GeminiPanel — three-level AI insights panel.
 * Add to the bottom of any lecturer page:
 *   <GeminiPanel subject={subjF} trimester={trimeF} />
 */
export default function GeminiPanel({ subject, trimester }) {
  // Level 1 — auto alert
  const [alert,       setAlert]       = useState('');

  // Level 2 — full analysis
  const [analysis,    setAnalysis]    = useState('');
  const [analysing,   setAnalysing]   = useState(false);

  // Level 3 — Q&A history
  const [question,    setQuestion]    = useState('');
  const [asking,      setAsking]      = useState(false);
  const [qaHistory,   setQaHistory]   = useState([]); // [{q, a}] last 3
  const qaEndRef = useRef(null);

  // Fetch alert whenever subject/trimester scope changes
  useEffect(() => {
    setAlert('');
    setAnalysis('');
    const body = {};
    if (subject)   body.subject   = subject;
    if (trimester) body.trimester = trimester;
    api.post('/api/gemini/alert', body)
      .then(r => { if (r.data.alert) setAlert(r.data.alert); })
      .catch(() => {});
  }, [subject, trimester]);

  const handleAnalyse = async () => {
    if (!subject) return;
    setAnalysing(true);
    setAnalysis('');
    try {
      const r = await api.post('/api/gemini/analyse', {
        subject,
        ...(trimester ? { trimester } : {}),
      });
      setAnalysis(r.data.analysis || 'No analysis returned.');
    } catch {
      setAnalysis('AI analysis unavailable at this time.');
    } finally {
      setAnalysing(false);
    }
  };

  const handleAsk = async () => {
    if (!question.trim()) return;
    setAsking(true);
    const q = question.trim();
    setQuestion('');
    try {
      const r = await api.post('/api/gemini/ask', {
        question: q,
        ...(subject   ? { subject }   : {}),
        ...(trimester ? { trimester } : {}),
      });
      const a = r.data.answer || 'No answer returned.';
      setQaHistory(prev => [...prev.slice(-2), { q, a }]);
    } catch {
      setQaHistory(prev => [...prev.slice(-2), { q, a: 'AI insight unavailable.' }]);
    } finally {
      setAsking(false);
      setTimeout(() => qaEndRef.current?.scrollIntoView({ behavior: 'smooth' }), 100);
    }
  };

  return (
    <div style={s.wrapper}>
      <div style={s.header}>
        <span style={s.sparkIcon}>✦</span>
        <h2 style={s.title}>AI Insights</h2>
        <span style={s.badge}>Powered by Gemini</span>
      </div>

      {/* ── Level 1: Auto alert ─────────────────────────────────── */}
      {alert && (
        <div style={s.alertBanner}>
          <span style={{ fontSize: 16 }}>⚠</span>
          <span>{alert}</span>
        </div>
      )}

      {/* ── Level 2: Analyse subject ────────────────────────────── */}
      <div style={s.section}>
        <div style={s.sectionHeader}>
          <p style={s.sectionTitle}>Subject Analysis</p>
          <button
            style={{ ...s.tealBtn, opacity: (!subject || analysing) ? 0.55 : 1 }}
            disabled={!subject || analysing}
            onClick={handleAnalyse}
          >
            {analysing ? '⏳ Analysing…' : '✦ Analyse Subject'}
          </button>
        </div>
        {analysis && (
          <div style={s.analysisCard}>
            <p style={s.analysisText}>{analysis}</p>
          </div>
        )}
        {!subject && (
          <p style={s.muted}>Select a subject filter above to enable analysis.</p>
        )}
      </div>

      {/* ── Level 3: Free-form Q&A ──────────────────────────────── */}
      <div style={s.section}>
        <p style={s.sectionTitle}>Ask About Your Class</p>

        {/* Q&A history */}
        {qaHistory.length > 0 && (
          <div style={s.qaHistory}>
            {qaHistory.map((item, i) => (
              <div key={i} style={s.qaItem}>
                <p style={s.qaQuestion}>Q: {item.q}</p>
                <p style={s.qaAnswer}>{item.a}</p>
              </div>
            ))}
            <div ref={qaEndRef} />
          </div>
        )}

        {/* Input row */}
        <div style={s.askRow}>
          <input
            style={s.askInput}
            placeholder="Ask about your class…"
            value={question}
            onChange={e => setQuestion(e.target.value)}
            onKeyDown={e => e.key === 'Enter' && !asking && handleAsk()}
          />
          <button
            style={{ ...s.askBtn, opacity: (!question.trim() || asking) ? 0.55 : 1 }}
            disabled={!question.trim() || asking}
            onClick={handleAsk}
          >
            {asking ? '…' : 'Ask'}
          </button>
        </div>
      </div>
    </div>
  );
}

const s = {
  wrapper: {
    background: '#fff', border: '0.5px solid #DDE4EA',
    borderRadius: 10, padding: '20px 24px', marginTop: 24,
  },
  header: { display: 'flex', alignItems: 'center', gap: 8, marginBottom: 16 },
  sparkIcon: { fontSize: 18, color: '#2E6E8E' },
  title:  { margin: 0, fontSize: 16, fontWeight: 600, color: '#1A2E40' },
  badge: {
    marginLeft: 'auto', fontSize: 10, fontWeight: 600, color: '#2E6E8E',
    background: '#EFF6FF', borderRadius: 20, padding: '2px 10px', letterSpacing: 0.3,
  },

  alertBanner: {
    display: 'flex', alignItems: 'center', gap: 10,
    background: '#FAEEDA', border: '0.5px solid #EF9F27',
    borderRadius: 8, padding: '10px 14px', marginBottom: 16,
    fontSize: 13, color: '#633806',
  },

  section: { marginBottom: 20 },
  sectionHeader: { display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 10 },
  sectionTitle:  { margin: 0, fontSize: 13, fontWeight: 600, color: '#475569' },
  muted:         { margin: '8px 0 0', fontSize: 12, color: '#94A3B8' },

  tealBtn: {
    padding: '7px 16px', borderRadius: 8, border: 'none',
    background: '#2E6E8E', color: '#fff', fontSize: 12,
    fontWeight: 600, cursor: 'pointer',
  },

  analysisCard: {
    borderLeft: '3px solid #2E6E8E', padding: '12px 16px',
    background: '#F8FAFC', borderRadius: '0 8px 8px 0',
  },
  analysisText: { margin: 0, fontSize: 13, color: '#1E293B', lineHeight: 1.65 },

  qaHistory: {
    background: '#F8FAFC', borderRadius: 8, padding: '12px 16px',
    marginBottom: 10, maxHeight: 280, overflowY: 'auto',
    display: 'flex', flexDirection: 'column', gap: 16,
  },
  qaItem: {},
  qaQuestion: { margin: '0 0 4px', fontSize: 12, color: '#94A3B8', fontStyle: 'italic' },
  qaAnswer:   { margin: 0, fontSize: 13, color: '#1E293B', lineHeight: 1.6 },

  askRow: { display: 'flex', gap: 8 },
  askInput: {
    flex: 1, padding: '9px 14px', borderRadius: 8,
    border: '0.5px solid #C5D2DC', fontSize: 13, color: '#1E293B', outline: 'none',
  },
  askBtn: {
    padding: '9px 18px', borderRadius: 8, border: 'none',
    background: '#2E6E8E', color: '#fff', fontSize: 13,
    fontWeight: 600, cursor: 'pointer', whiteSpace: 'nowrap',
  },
};
