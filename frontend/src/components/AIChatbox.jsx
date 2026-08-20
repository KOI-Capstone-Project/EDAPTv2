// Floating AI assistant widget with Chat and Insights tabs powered by Gemini.
import { useState, useRef, useEffect } from 'react';
import { getUser } from '../utils/auth';
import api from '../services/api';

const ALL_PERIODS = ['23.1','23.2','23.3','24.1','24.2','24.3','25.1','25.2','25.3'];

export default function AIChatbox() {
  const [open,       setOpen]       = useState(false);
  const [fullscreen, setFullscreen] = useState(false);
  const [tab,        setTab]        = useState('chat');

  // Chat
  const [messages,    setMessages]    = useState([]);
  const [chatInput,   setChatInput]   = useState('');
  const [chatLoading, setChatLoading] = useState(false);
  const chatEndRef = useRef(null);

  // Subjects (for Insights tab)
  const [subjects, setSubjects] = useState([]);

  // Insights
  const [insSubject,   setInsSubject]   = useState('');
  const [insTrimester, setInsTrimester] = useState('');
  const [alertText,    setAlertText]    = useState('');
  const [analysisText, setAnalysisText] = useState('');
  const [insLoading,   setInsLoading]   = useState(null);

  const user    = getUser();
  const isAdmin = user?.role === 'Head of Technology' || user?.role === 'Head of School';

  useEffect(() => {
    if (isAdmin) {
      api.get('/api/subjects/list').then(r => setSubjects(r.data)).catch(() => {});
    } else {
      setSubjects(user?.subjects || []);
    }
  }, [isAdmin, user?.subjects]); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    if (open && chatEndRef.current) {
      chatEndRef.current.scrollIntoView({ behavior: 'smooth' });
    }
  }, [messages, open]);

  const sendMessage = async () => {
    if (!chatInput.trim() || chatLoading) return;
    const q = chatInput.trim();
    setChatInput('');
    setMessages(prev => [...prev, { role: 'user', text: q }]);
    setChatLoading(true);
    try {
      const res = await api.post('/api/gemini/ask', { question: q });
      setMessages(prev => [...prev, { role: 'ai', text: res.data.answer }]);
    } catch {
      setMessages(prev => [...prev, { role: 'ai', text: 'Sorry, something went wrong. Please try again.' }]);
    } finally {
      setChatLoading(false);
    }
  };

  const handleAlert = async () => {
    setInsLoading('alert');
    setAlertText('');
    try {
      const res = await api.post('/api/gemini/alert', {
        ...(insSubject   ? { subject:   insSubject }   : {}),
        ...(insTrimester ? { trimester: insTrimester } : {}),
      });
      setAlertText(res.data.alert);
    } catch {
      setAlertText('Failed to get alert.');
    } finally {
      setInsLoading(null);
    }
  };

  const handleAnalysis = async () => {
    setInsLoading('analysis');
    setAnalysisText('');
    try {
      const res = await api.post('/api/gemini/analyse', {
        ...(insSubject   ? { subject:   insSubject }   : {}),
        ...(insTrimester ? { trimester: insTrimester } : {}),
      });
      setAnalysisText(res.data.analysis);
    } catch {
      setAnalysisText('Failed to get analysis.');
    } finally {
      setInsLoading(null);
    }
  };

  const panelHeight = fullscreen ? '80vh' : 420;

  return (
    <div style={{ position: 'fixed', bottom: 24, right: 24, zIndex: 9999, display: 'flex', flexDirection: 'column', alignItems: 'flex-end', gap: 12 }}>

      {/* Panel */}
      {open && (
        <div style={{ width: 380, height: panelHeight, background: '#fff', borderRadius: 14, boxShadow: '0 8px 40px rgba(0,0,0,0.18)', border: '0.5px solid #DDE4EA', display: 'flex', flexDirection: 'column', overflow: 'hidden' }}>

          {/* Header */}
          <div style={{ background: '#1A2E40', padding: '11px 14px', display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexShrink: 0 }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
              <span style={{ color: '#4f8ef7', fontSize: 15 }}>✦</span>
              <span style={{ fontSize: 13, fontWeight: 700, color: '#fff' }}>EDAPT AI Assistant</span>
            </div>
            <div style={{ display: 'flex', gap: 4 }}>
              <button
                onClick={() => setFullscreen(f => !f)}
                style={hdrBtn}
                title={fullscreen ? 'Compact view' : 'Expand'}
              >
                {fullscreen ? '⊡' : '⊞'}
              </button>
              <button onClick={() => setOpen(false)} style={hdrBtn} title="Minimise">✕</button>
            </div>
          </div>

          {/* Tabs */}
          <div style={{ display: 'flex', borderBottom: '0.5px solid #E2E8F0', flexShrink: 0, background: '#fff' }}>
            {['Chat', 'Insights'].map(t => (
              <button
                key={t}
                onClick={() => setTab(t.toLowerCase())}
                style={{
                  flex: 1, padding: '9px 0', border: 'none', cursor: 'pointer', fontSize: 12, fontWeight: 600,
                  background: 'transparent',
                  color: tab === t.toLowerCase() ? '#1A2E40' : '#94A3B8',
                  borderBottom: tab === t.toLowerCase() ? '2px solid #2E6E8E' : '2px solid transparent',
                  transition: 'color 0.15s',
                }}
              >
                {t}
              </button>
            ))}
          </div>

          {/* ── Chat tab ── */}
          {tab === 'chat' && (
            <>
              <div style={{ flex: 1, overflowY: 'auto', padding: '12px 14px', display: 'flex', flexDirection: 'column', gap: 8 }}>
                {messages.length === 0 && (
                  <div style={{ textAlign: 'center', padding: '28px 0', color: '#94A3B8', fontSize: 12 }}>
                    Ask me anything about student performance.
                  </div>
                )}
                {messages.map((m, i) => (
                  <div key={i} style={{ display: 'flex', justifyContent: m.role === 'user' ? 'flex-end' : 'flex-start' }}>
                    <div style={{
                      maxWidth: '82%', padding: '8px 12px',
                      borderRadius: m.role === 'user' ? '12px 12px 2px 12px' : '12px 12px 12px 2px',
                      background: m.role === 'user' ? '#2E6E8E' : '#F0F4F8',
                      color: m.role === 'user' ? '#fff' : '#1E293B',
                      fontSize: 13, lineHeight: 1.55,
                    }}>
                      {m.text}
                    </div>
                  </div>
                ))}
                {chatLoading && (
                  <div style={{ display: 'flex', justifyContent: 'flex-start' }}>
                    <div style={{ padding: '10px 14px', borderRadius: '12px 12px 12px 2px', background: '#F0F4F8', display: 'flex', gap: 5, alignItems: 'center' }}>
                      {[0,1,2].map(i => (
                        <div key={i} style={{ width: 6, height: 6, borderRadius: '50%', background: '#94A3B8', animation: `chatBounce 1s ${i * 0.18}s infinite` }} />
                      ))}
                    </div>
                  </div>
                )}
                <div ref={chatEndRef} />
              </div>
              <div style={{ padding: '10px 12px', borderTop: '0.5px solid #E2E8F0', display: 'flex', gap: 8, flexShrink: 0 }}>
                <input
                  value={chatInput}
                  onChange={e => setChatInput(e.target.value)}
                  onKeyDown={e => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); sendMessage(); } }}
                  placeholder="Ask a question…"
                  style={{ flex: 1, padding: '8px 12px', borderRadius: 8, border: '0.5px solid #C5D2DC', fontSize: 13, outline: 'none', fontFamily: 'inherit' }}
                />
                <button
                  onClick={sendMessage}
                  disabled={!chatInput.trim() || chatLoading}
                  style={{ padding: '8px 14px', borderRadius: 8, border: 'none', background: '#2E6E8E', color: '#fff', fontSize: 12, fontWeight: 600, cursor: 'pointer', opacity: (!chatInput.trim() || chatLoading) ? 0.55 : 1 }}
                >
                  Send
                </button>
              </div>
            </>
          )}

          {/* ── Insights tab ── */}
          {tab === 'insights' && (
            <div style={{ flex: 1, overflowY: 'auto', padding: '14px' }}>
              <div style={fld}>
                <label style={lbl}>Subject</label>
                <select value={insSubject} onChange={e => setInsSubject(e.target.value)} style={sel}>
                  <option value="">All Subjects</option>
                  {subjects.map(sv => <option key={sv} value={sv}>{sv}</option>)}
                </select>
              </div>
              <div style={{ ...fld, marginBottom: 14 }}>
                <label style={lbl}>Trimester</label>
                <select value={insTrimester} onChange={e => setInsTrimester(e.target.value)} style={sel}>
                  <option value="">All Trimesters</option>
                  {ALL_PERIODS.map(p => <option key={p} value={p}>{p}</option>)}
                </select>
              </div>
              <div style={{ display: 'flex', gap: 8, marginBottom: 14 }}>
                <button
                  onClick={handleAlert}
                  disabled={insLoading === 'alert'}
                  style={{ flex: 1, padding: '9px', borderRadius: 8, border: '0.5px solid #DDE4EA', background: '#F8FAFC', color: '#1A2E40', fontSize: 12, fontWeight: 600, cursor: 'pointer', opacity: insLoading === 'alert' ? 0.6 : 1 }}
                >
                  {insLoading === 'alert' ? '…' : '⚠ Get Alert'}
                </button>
                <button
                  onClick={handleAnalysis}
                  disabled={insLoading === 'analysis'}
                  style={{ flex: 1, padding: '9px', borderRadius: 8, border: 'none', background: '#2E6E8E', color: '#fff', fontSize: 12, fontWeight: 600, cursor: 'pointer', opacity: insLoading === 'analysis' ? 0.6 : 1 }}
                >
                  {insLoading === 'analysis' ? '…' : '✦ Deep Analysis'}
                </button>
              </div>
              {alertText && (
                <div style={{ background: '#FEF9C3', border: '0.5px solid #FDE68A', borderRadius: 8, padding: '10px 12px', marginBottom: 10, fontSize: 12, color: '#78350F', lineHeight: 1.55 }}>
                  <strong>Alert:</strong> {alertText}
                </div>
              )}
              {analysisText && (
                <div style={{ background: '#EFF6FF', border: '0.5px solid #BFDBFE', borderRadius: 8, padding: '10px 12px', fontSize: 12, color: '#1E293B', lineHeight: 1.55 }}>
                  <strong>Analysis:</strong> {analysisText}
                </div>
              )}
            </div>
          )}
        </div>
      )}

      {/* Floating button */}
      <button
        onClick={() => setOpen(o => !o)}
        style={{
          width: 52, height: 52, borderRadius: '50%',
          background: open ? '#1A2E40' : '#2E6E8E',
          border: 'none', cursor: 'pointer',
          display: 'flex', alignItems: 'center', justifyContent: 'center',
          boxShadow: '0 4px 16px rgba(46,110,142,0.35)',
          color: '#fff', fontSize: 20, flexShrink: 0,
          transition: 'background 0.2s',
        }}
        title="EDAPT AI Assistant"
      >
        ✦
      </button>

      <style>{`
        @keyframes chatBounce {
          0%, 80%, 100% { transform: translateY(0); }
          40%           { transform: translateY(-5px); }
        }
      `}</style>
    </div>
  );
}

const hdrBtn = {
  background: 'rgba(255,255,255,0.1)', border: 'none', cursor: 'pointer',
  color: '#CBD5E1', borderRadius: 6, width: 26, height: 26,
  display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 13,
};

const fld = { marginBottom: 12 };
const lbl = { display: 'block', fontSize: 11, fontWeight: 600, color: '#475569', textTransform: 'uppercase', letterSpacing: 0.4, marginBottom: 5 };
const sel = { width: '100%', border: '0.5px solid #C5D2DC', borderRadius: 8, padding: '8px 10px', fontSize: 13, color: '#1E293B', background: '#fff', outline: 'none', cursor: 'pointer', boxSizing: 'border-box' };
