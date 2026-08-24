// Assistant: a chat interface over POST /api/chatbot/ask — answers are
// generated strictly from this system's own student performance/attendance/
// risk data (same visibility rule as Students at Risk: a lecturer only ever
// sees their own subjects), and anything outside that scope gets a fixed
// refusal from the backend rather than a real answer. Nothing here is
// persisted server-side — history is just replayed back to the backend
// per-request for conversational continuity, same as every other Gemini
// endpoint in this app.
import { useState, useRef, useEffect } from 'react';
import api from '../services/api';

const SUGGESTIONS = [
  'Which subject currently has the most students at risk?',
  "What's the overall pass rate this period?",
  'How many students have insufficient data to be scored yet?',
];

function Spinner() {
  return <span style={s.spinner} />;
}

function MessageBubble({ role, content, refusal }) {
  const isUser = role === 'user';
  return (
    <div style={{ display: 'flex', justifyContent: isUser ? 'flex-end' : 'flex-start', marginBottom: 12 }}>
      <div style={{
        ...s.bubble,
        ...(isUser ? s.bubbleUser : s.bubbleAssistant),
        ...(refusal ? s.bubbleRefusal : {}),
      }}>
        {content}
      </div>
    </div>
  );
}

export default function AssistantView() {
  const [periods, setPeriods]         = useState([]);
  const [studyPeriod, setStudyPeriod] = useState('');
  const [messages, setMessages]       = useState([]);
  const [input, setInput]             = useState('');
  const [sending, setSending]         = useState(false);
  const [error, setError]             = useState(null);
  const [usedPeriod, setUsedPeriod]   = useState(null);
  const scrollRef = useRef(null);

  useEffect(() => {
    api.get('/api/filters')
      .then(r => setPeriods(r.data.periods || []))
      .catch(() => {});
  }, []);

  useEffect(() => {
    if (scrollRef.current) scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
  }, [messages, sending]);

  const send = async (text) => {
    const question = (text ?? input).trim();
    if (!question || sending) return;

    const history = messages.slice(-8).map(m => ({ role: m.role, content: m.content }));
    setMessages(prev => [...prev, { role: 'user', content: question }]);
    setInput('');
    setSending(true);
    setError(null);

    try {
      // Overrides the client's global timeout — the first question about a
      // new study period re-runs the same per-subject ML inference Students
      // at Risk does (confirmed ~50s on the full dataset); follow-up
      // questions about the same period reuse the backend's 5-minute cache
      // and return quickly.
      const res = await api.post(
        '/api/chatbot/ask',
        { question, study_period: studyPeriod || undefined, history },
        { timeout: 120000 },
      );
      setUsedPeriod(res.data.study_period_used);
      setMessages(prev => [...prev, {
        role: 'assistant',
        content: res.data.answer,
        refusal: res.data.answer === "I'm restricted to answering questions about this system's student data and can't help with that.",
      }]);
    } catch (err) {
      setError(err.response?.data?.detail || 'Could not reach the assistant. Please try again.');
      setMessages(prev => prev.slice(0, -1));
      setInput(question);
    } finally {
      setSending(false);
    }
  };

  const handleKeyDown = (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      send();
    }
  };

  return (
    <div style={s.page}>
      <div style={s.pageHeader}>
        <div>
          <h1 style={s.pageTitle}>Assistant</h1>
          <p style={s.pageSub}>
            Ask about student performance, attendance, or risk in this system — nothing else.
          </p>
        </div>
        <div style={s.periodPicker}>
          <label style={s.periodLabel}>Study Period</label>
          <select style={s.select} value={studyPeriod} onChange={e => setStudyPeriod(e.target.value)}>
            <option value="">Latest available</option>
            {periods.map(p => <option key={p} value={p}>{p}</option>)}
          </select>
        </div>
      </div>

      <div style={s.chatCard}>
        <div style={s.chatBody} ref={scrollRef}>
          {messages.length === 0 && (
            <div style={s.emptyState}>
              <div style={{ fontSize: 30, marginBottom: 10 }}>💬</div>
              <p style={{ margin: '0 0 14px', fontSize: 13.5, color: '#5A7A8A' }}>
                Try asking:
              </p>
              <div style={{ display: 'flex', flexDirection: 'column', gap: 8, alignItems: 'center' }}>
                {SUGGESTIONS.map(q => (
                  <button key={q} style={s.suggestionChip} onClick={() => send(q)}>{q}</button>
                ))}
              </div>
            </div>
          )}

          {messages.map((m, i) => (
            <MessageBubble key={i} role={m.role} content={m.content} refusal={m.refusal} />
          ))}

          {sending && (
            <div style={{ display: 'flex', alignItems: 'center', gap: 8, color: '#5A7A8A', fontSize: 13 }}>
              <Spinner /> Checking the data for {studyPeriod || 'the latest period'}…
            </div>
          )}
        </div>

        {error && <div style={s.errBanner}>{error}</div>}
        {usedPeriod && !sending && messages.length > 0 && (
          <p style={s.periodNote}>Answered using study period {usedPeriod}.</p>
        )}

        <div style={s.inputRow}>
          <textarea
            style={s.textarea}
            placeholder="Ask about students at risk, pass rates, attendance…"
            value={input}
            onChange={e => setInput(e.target.value)}
            onKeyDown={handleKeyDown}
            rows={2}
            disabled={sending}
          />
          <button style={{ ...s.sendBtn, opacity: sending || !input.trim() ? 0.6 : 1 }} onClick={() => send()} disabled={sending || !input.trim()}>
            Send
          </button>
        </div>
      </div>

      <style>{`@keyframes assistantSpin { to { transform: rotate(360deg); } }`}</style>
    </div>
  );
}

const s = {
  page:       { padding: '28px 32px', background: '#F0F4F8', minHeight: '100vh', boxSizing: 'border-box' },
  pageHeader: { display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', marginBottom: 20, flexWrap: 'wrap', gap: 12 },
  pageTitle:  { margin: '0 0 4px', fontSize: 24, fontWeight: 500, color: '#1A2E40' },
  pageSub:    { margin: 0, fontSize: 13, color: '#5A7A8A' },

  periodPicker: { display: 'flex', flexDirection: 'column', gap: 4 },
  periodLabel:  { fontSize: 11, fontWeight: 600, color: '#8BA5B8', textTransform: 'uppercase', letterSpacing: 0.5 },
  select: {
    height: 36, padding: '0 12px', borderRadius: 8, border: '0.5px solid #C5D2DC',
    fontSize: 13, color: '#1A2E40', background: '#fff', cursor: 'pointer', outline: 'none', minWidth: 180,
  },

  chatCard: {
    background: '#fff', border: '0.5px solid #DDE4EA', borderRadius: 12,
    display: 'flex', flexDirection: 'column', height: 'calc(100vh - 200px)', minHeight: 420,
  },
  chatBody: { flex: 1, overflowY: 'auto', padding: '20px 24px' },

  emptyState: { textAlign: 'center', padding: '40px 20px' },
  suggestionChip: {
    padding: '9px 16px', borderRadius: 20, border: '0.5px solid #C5D2DC',
    background: '#F8FAFB', color: '#2E6E8E', fontSize: 12.5, fontWeight: 500,
    cursor: 'pointer', maxWidth: 420,
  },

  bubble: {
    maxWidth: '75%', padding: '10px 14px', borderRadius: 12,
    fontSize: 13.5, lineHeight: 1.5, whiteSpace: 'pre-wrap', wordBreak: 'break-word',
  },
  bubbleUser:      { background: '#2E6E8E', color: '#fff', borderBottomRightRadius: 3 },
  bubbleAssistant: { background: '#F0F4F8', color: '#1A2E40', borderBottomLeftRadius: 3 },
  bubbleRefusal:   { background: '#FCEBEB', color: '#A32D2D' },

  spinner: {
    display: 'inline-block', width: 16, height: 16, borderRadius: '50%',
    border: '2.5px solid #DDE4EA', borderTopColor: '#2E6E8E', animation: 'assistantSpin 0.8s linear infinite',
  },

  errBanner: { margin: '0 24px', padding: '8px 12px', background: '#FCEBEB', color: '#A32D2D', borderRadius: 8, fontSize: 12.5 },
  periodNote: { margin: '0 24px 8px', fontSize: 11.5, color: '#8BA5B8' },

  inputRow: { display: 'flex', gap: 10, padding: '14px 24px', borderTop: '0.5px solid #F0F4F8' },
  textarea: {
    flex: 1, resize: 'none', border: '0.5px solid #C5D2DC', borderRadius: 8,
    padding: '10px 12px', fontSize: 13.5, fontFamily: 'inherit', outline: 'none', boxSizing: 'border-box',
  },
  sendBtn: {
    padding: '0 22px', borderRadius: 8, border: 'none', background: '#2E6E8E',
    color: '#fff', fontSize: 13, fontWeight: 600, cursor: 'pointer',
  },
};
