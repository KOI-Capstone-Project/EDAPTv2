import React, { useEffect, useState } from 'react';

const API = process.env.REACT_APP_API_BASE_URL || '';

const MODELS = [
  { value: 'gemini-2.0-flash',      label: 'Gemini 2.0 Flash',      desc: 'Latest model — fast, multimodal, best for most tasks' },
  { value: 'gemini-2.0-flash-lite', label: 'Gemini 2.0 Flash Lite', desc: 'Lightweight variant — lowest latency and cost' },
  { value: 'gemini-1.5-pro',        label: 'Gemini 1.5 Pro',        desc: 'Most capable — complex reasoning and long context' },
  { value: 'gemini-1.5-flash',      label: 'Gemini 1.5 Flash',      desc: 'Balanced speed and quality for production workloads' },
];

function authHeader() {
  const token = localStorage.getItem('edapt_token');
  return token ? { Authorization: `Bearer ${token}` } : {};
}

const EyeIcon = ({ open }) => open ? (
  <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"/>
    <circle cx="12" cy="12" r="3"/>
  </svg>
) : (
  <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <path d="M17.94 17.94A10.07 10.07 0 0 1 12 20c-7 0-11-8-11-8a18.45 18.45 0 0 1 5.06-5.94M9.9 4.24A9.12 9.12 0 0 1 12 4c7 0 11 8 11 8a18.5 18.5 0 0 1-2.16 3.19m-6.72-1.07a3 3 0 1 1-4.24-4.24"/>
    <line x1="1" y1="1" x2="23" y2="23"/>
  </svg>
);

const CheckIcon = () => (
  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round">
    <polyline points="20 6 9 17 4 12"/>
  </svg>
);

export default function AIEngine() {
  const [current, setCurrent]       = useState(null);
  const [apiKey, setApiKey]         = useState('');
  const [model, setModel]           = useState('gemini-2.0-flash');
  const [showKey, setShowKey]       = useState(false);
  const [loading, setLoading]       = useState(true);
  const [saving, setSaving]         = useState(false);
  const [saved, setSaved]           = useState(false);
  const [error, setError]           = useState('');

  useEffect(() => {
    fetch(`${API}/api/v1/ai-engine/`, { headers: authHeader() })
      .then(r => r.json())
      .then(data => {
        setCurrent(data);
        setModel(data.gemini_model || 'gemini-2.0-flash');
      })
      .catch(() => setError('Failed to load AI engine settings.'))
      .finally(() => setLoading(false));
  }, []);

  const handleSave = async (e) => {
    e.preventDefault();
    setError('');
    setSaving(true);
    try {
      const body = { gemini_model: model };
      if (apiKey.trim()) body.gemini_api_key = apiKey.trim();

      const res = await fetch(`${API}/api/v1/ai-engine/`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json', ...authHeader() },
        body: JSON.stringify(body),
      });
      if (!res.ok) {
        const err = await res.json();
        throw new Error(err.detail || 'Save failed.');
      }
      const data = await res.json();
      setCurrent(data);
      setApiKey('');
      setSaved(true);
      setTimeout(() => setSaved(false), 3000);
    } catch (err) {
      setError(err.message);
    } finally {
      setSaving(false);
    }
  };

  const selectedModelInfo = MODELS.find(m => m.value === model);

  return (
    <div>
      <div style={s.header}>
        <h1 style={s.title}>AI Engine</h1>
        <p style={s.subtitle}>Configure Google Gemini for natural language predictions and insights</p>
      </div>

      {loading ? (
        <div style={s.loadingWrap}><span style={s.loadingText}>Loading settings…</span></div>
      ) : (
        <form onSubmit={handleSave}>

          {/* ── API Key Card ── */}
          <div style={s.card}>
            <h2 style={s.cardTitle}>Gemini API Key</h2>
            <p style={s.cardDesc}>
              Your API key is stored securely and never exposed in full after saving.
              Leave the field blank to keep the current key unchanged.
            </p>

            {current?.gemini_api_key_set && (
              <div style={s.keyStatus}>
                <span style={s.keyDot} />
                Current key: <code style={s.keyPreview}>{current.gemini_api_key_preview}</code>
                <span style={s.keyTag}>active</span>
              </div>
            )}

            <div style={s.inputWrap}>
              <input
                type={showKey ? 'text' : 'password'}
                placeholder={current?.gemini_api_key_set ? 'Enter new key to replace…' : 'AIzaSy…'}
                value={apiKey}
                onChange={e => setApiKey(e.target.value)}
                style={s.input}
                autoComplete="off"
              />
              <button
                type="button"
                onClick={() => setShowKey(v => !v)}
                style={s.eyeBtn}
                title={showKey ? 'Hide key' : 'Show key'}
              >
                <EyeIcon open={showKey} />
              </button>
            </div>
          </div>

          {/* ── Model Card ── */}
          <div style={s.card}>
            <h2 style={s.cardTitle}>AI Model</h2>
            <p style={s.cardDesc}>Select the Gemini model used for predictions and natural language insights.</p>

            <div style={s.modelGrid}>
              {MODELS.map(m => (
                <div
                  key={m.value}
                  onClick={() => setModel(m.value)}
                  style={{
                    ...s.modelCard,
                    ...(model === m.value ? s.modelCardActive : {}),
                  }}
                >
                  <div style={s.modelCardTop}>
                    <span style={{ ...s.modelName, ...(model === m.value ? { color: '#2E6E8E' } : {}) }}>
                      {m.label}
                    </span>
                    {model === m.value && (
                      <span style={s.modelCheck}><CheckIcon /></span>
                    )}
                  </div>
                  <span style={s.modelDesc}>{m.desc}</span>
                </div>
              ))}
            </div>
          </div>

          {/* ── Actions ── */}
          {error && <div style={s.errorBanner}>{error}</div>}

          <div style={s.actions}>
            <button type="submit" disabled={saving} style={s.saveBtn}>
              {saving ? 'Saving…' : saved ? '✓ Saved' : 'Save Settings'}
            </button>
            {saved && <span style={s.savedNote}>Settings updated successfully.</span>}
          </div>

        </form>
      )}
    </div>
  );
}

const s = {
  header:      { marginBottom: 28 },
  title:       { margin: '0 0 6px', fontSize: 26, fontWeight: 700, color: '#1E293B' },
  subtitle:    { margin: 0, fontSize: 14, color: '#64748B' },
  loadingWrap: { padding: 40, textAlign: 'center' },
  loadingText: { color: '#94A3B8', fontSize: 14 },
  card: {
    background: '#fff',
    border: '0.5px solid #DDE4EA',
    borderRadius: 12,
    padding: '24px 28px',
    marginBottom: 20,
  },
  cardTitle: { margin: '0 0 6px', fontSize: 15, fontWeight: 600, color: '#1E293B' },
  cardDesc:  { margin: '0 0 18px', fontSize: 13, color: '#64748B', lineHeight: 1.6 },
  keyStatus: {
    display: 'flex', alignItems: 'center', gap: 8,
    fontSize: 13, color: '#475569', marginBottom: 14,
  },
  keyDot: {
    width: 8, height: 8, borderRadius: '50%',
    background: '#22C55E', flexShrink: 0,
  },
  keyPreview: {
    fontFamily: 'monospace', fontSize: 13,
    background: '#F8FAFC', padding: '1px 6px', borderRadius: 4,
  },
  keyTag: {
    background: '#DCFCE7', color: '#16A34A',
    fontSize: 11, fontWeight: 600, padding: '2px 8px',
    borderRadius: 10, textTransform: 'uppercase', letterSpacing: 0.5,
  },
  inputWrap: { position: 'relative', maxWidth: 480 },
  input: {
    width: '100%', padding: '10px 40px 10px 14px',
    border: '1px solid #CBD5E1', borderRadius: 8,
    fontSize: 13, color: '#1E293B', outline: 'none',
    boxSizing: 'border-box', fontFamily: 'monospace',
    background: '#FAFBFC',
  },
  eyeBtn: {
    position: 'absolute', right: 12, top: '50%', transform: 'translateY(-50%)',
    background: 'none', border: 'none', cursor: 'pointer',
    color: '#94A3B8', display: 'flex', alignItems: 'center', padding: 0,
  },
  modelGrid: {
    display: 'grid',
    gridTemplateColumns: 'repeat(auto-fill, minmax(220px, 1fr))',
    gap: 12,
  },
  modelCard: {
    border: '1.5px solid #E2E8F0', borderRadius: 10,
    padding: '14px 16px', cursor: 'pointer',
    transition: 'border-color 0.15s, background 0.15s',
    background: '#FAFBFC',
  },
  modelCardActive: {
    borderColor: '#2E6E8E', background: '#EFF6FF',
  },
  modelCardTop: {
    display: 'flex', justifyContent: 'space-between', alignItems: 'center',
    marginBottom: 6,
  },
  modelName: { fontSize: 13, fontWeight: 600, color: '#1E293B' },
  modelCheck: {
    width: 20, height: 20, borderRadius: '50%',
    background: '#2E6E8E', display: 'flex',
    alignItems: 'center', justifyContent: 'center', color: '#fff', flexShrink: 0,
  },
  modelDesc: { fontSize: 12, color: '#64748B', lineHeight: 1.5 },
  errorBanner: {
    background: '#FEF2F2', border: '1px solid #FECACA', color: '#DC2626',
    borderRadius: 8, padding: '10px 16px', fontSize: 13, marginBottom: 16,
  },
  actions: { display: 'flex', alignItems: 'center', gap: 16 },
  saveBtn: {
    background: '#2E6E8E', color: '#fff',
    border: 'none', borderRadius: 8, cursor: 'pointer',
    fontSize: 13, fontWeight: 600, padding: '10px 24px',
    transition: 'opacity 0.15s',
  },
  savedNote: { fontSize: 13, color: '#16A34A', fontWeight: 500 },
};
