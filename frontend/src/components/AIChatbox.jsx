// Floating AI assistant widget with Chat and FAQ tabs. Chat is answered by
// POST /api/chatbot/ask, which is scoped STRICTLY to this system's own
// student performance/attendance/risk data (same visibility rule as
// Students at Risk — a lecturer only ever sees their own subjects) and
// refuses anything outside that scope instead of answering from outside
// knowledge. Nothing here is persisted server-side; `messages` is just
// replayed back per-request as `history` for conversational continuity.
import { useState, useRef, useEffect } from 'react';
import api from '../services/api';

const FAQ_PROMPTS = [
  'Which subject currently has the most students at risk?',
  "What's the overall pass rate this period?",
  'How is my weakest subject trending compared to last period?',
];

const REFUSAL = "I'm restricted to answering questions about this system's student data and can't help with that.";

export default function AIChatbox() {
  const [open,       setOpen]       = useState(false);
  const [fullscreen, setFullscreen] = useState(false);
  const [tab,        setTab]        = useState('chat');

  const [messages,    setMessages]    = useState([]);
  const [chatInput,   setChatInput]   = useState('');
  const [chatLoading, setChatLoading] = useState(false);
  const chatEndRef = useRef(null);

  useEffect(() => {
    if (open && chatEndRef.current) {
      chatEndRef.current.scrollIntoView({ behavior: 'smooth' });
    }
  }, [messages, open]);

  const sendMessage = async (text) => {
    const q = (text ?? chatInput).trim();
    if (!q || chatLoading) return;

    const history = messages.slice(-8).map(m => ({ role: m.role === 'ai' ? 'assistant' : 'user', content: m.text }));
    setChatInput('');
    setTab('chat');
    setMessages(prev => [...prev, { role: 'user', text: q }]);
    setChatLoading(true);
    try {
      // Overrides the client's global timeout — the very first question
      // about a study period with no cached predictions yet can take a
      // moment; every question after that reads straight off the
      // Predictions table (fast, no live ML inference).
      const res = await api.post('/api/chatbot/ask', { question: q, history }, { timeout: 30000 });
      setMessages(prev => [...prev, { role: 'ai', text: res.data.answer, refusal: res.data.answer === REFUSAL }]);
    } catch {
      setMessages(prev => [...prev, { role: 'ai', text: 'Sorry, something went wrong. Please try again.' }]);
    } finally {
      setChatLoading(false);
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
            {['Chat', 'FAQ'].map(t => (
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
                    Ask me about student performance, attendance, or risk — or check the FAQ tab for ideas.
                  </div>
                )}
                {messages.map((m, i) => (
                  <div key={i} style={{ display: 'flex', justifyContent: m.role === 'user' ? 'flex-end' : 'flex-start' }}>
                    <div style={{
                      maxWidth: '82%', padding: '8px 12px',
                      borderRadius: m.role === 'user' ? '12px 12px 2px 12px' : '12px 12px 12px 2px',
                      background: m.role === 'user' ? '#2E6E8E' : (m.refusal ? '#FCEBEB' : '#F0F4F8'),
                      color: m.role === 'user' ? '#fff' : (m.refusal ? '#A32D2D' : '#1E293B'),
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
                  onClick={() => sendMessage()}
                  disabled={!chatInput.trim() || chatLoading}
                  style={{ padding: '8px 14px', borderRadius: 8, border: 'none', background: '#2E6E8E', color: '#fff', fontSize: 12, fontWeight: 600, cursor: 'pointer', opacity: (!chatInput.trim() || chatLoading) ? 0.55 : 1 }}
                >
                  Send
                </button>
              </div>
            </>
          )}

          {/* ── FAQ tab ── */}
          {tab === 'faq' && (
            <div style={{ flex: 1, overflowY: 'auto', padding: '14px' }}>
              <p style={{ margin: '0 0 12px', fontSize: 11.5, color: '#94A3B8' }}>
                Tap a question to ask it in Chat:
              </p>
              <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
                {FAQ_PROMPTS.map(q => (
                  <button
                    key={q}
                    onClick={() => sendMessage(q)}
                    style={{
                      textAlign: 'left', padding: '10px 12px', borderRadius: 8,
                      border: '0.5px solid #DDE4EA', background: '#F8FAFC',
                      color: '#1A2E40', fontSize: 12.5, cursor: 'pointer', lineHeight: 1.4,
                    }}
                  >
                    {q}
                  </button>
                ))}
              </div>
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
