// AI Config: which provider/model/API key powers every AI-insight feature
// in the app (the Gemini-labeled alert/analyse/ask endpoints under
// /api/gemini/*, kept under that prefix for backend compatibility even
// though they're no longer Gemini-exclusive) — admin only (Head of
// Technology / Head of School), matching the backend's
// require_head_of_school gate on the PUT endpoint. Replaces the single
// hardcoded GEMINI_API_KEY env var: changes here take effect on the very
// next AI call, no redeploy needed.
import { useState, useEffect } from 'react';
import api from '../services/api';
import { getErrorMessage } from '../utils/apiError';

const PROVIDER_LABELS = {
  anthropic: 'Anthropic',
  gemini:    'Gemini',
  openai:    'OpenAI',
};
const PROVIDER_ORDER = ['anthropic', 'gemini', 'openai'];

export default function AIConfigView() {
  const [loading, setLoading]   = useState(true);
  const [loadError, setLoadError] = useState(null);

  const [availableModels, setAvailableModels] = useState({});
  const [provider, setProvider] = useState('gemini');
  const [model,    setModel]    = useState('');
  const [apiKey,   setApiKey]   = useState('');
  const [hasKey,      setHasKey]      = useState(false);
  const [keyPreview,  setKeyPreview]  = useState(null);
  const [updatedBy,   setUpdatedBy]   = useState(null);
  const [updatedAt,   setUpdatedAt]   = useState(null);

  const [saving, setSaving] = useState(false);
  const [msg,    setMsg]    = useState(null);

  const load = () => {
    setLoading(true);
    api.get('/api/ai-config')
      .then(r => {
        setAvailableModels(r.data.available_models || {});
        setProvider(r.data.provider);
        setModel(r.data.model);
        setHasKey(r.data.has_key);
        setKeyPreview(r.data.key_preview);
        setUpdatedBy(r.data.updated_by);
        setUpdatedAt(r.data.updated_at);
      })
      .catch(err => setLoadError(getErrorMessage(err, 'Failed to load AI configuration.')))
      .finally(() => setLoading(false));
  };

  useEffect(load, []);

  const modelsForProvider = availableModels[provider] || [];

  // Switching provider mid-edit: jump to that provider's first model
  // rather than leaving a model id selected that belongs to a different
  // provider's API.
  const handleProviderChange = (next) => {
    setProvider(next);
    const firstModel = (availableModels[next] || [])[0];
    if (firstModel) setModel(firstModel.id);
  };

  const handleSave = async () => {
    setSaving(true);
    setMsg(null);
    try {
      const res = await api.put('/api/ai-config', {
        provider, model,
        api_key: apiKey || null, // blank = keep whatever key is already stored
      });
      setHasKey(res.data.has_key);
      setKeyPreview(res.data.key_preview);
      setUpdatedBy(res.data.updated_by);
      setUpdatedAt(res.data.updated_at);
      setApiKey('');
      setMsg({ type: 'success', text: 'Saved. The next AI request will use this configuration.' });
    } catch (err) {
      setMsg({ type: 'error', text: getErrorMessage(err, 'Failed to save.') });
    } finally {
      setSaving(false);
    }
  };

  return (
    <div style={{ maxWidth: 640 }}>
      <div style={s.pageHeader}>
        <h1 style={s.pageTitle}>AI Config</h1>
        <p style={s.pageSub}>Configure which AI provider powers insights across the app — no redeploy needed</p>
      </div>

      {loadError && <div style={s.errorBox}>{loadError}</div>}

      {!loading && !loadError && (
        <div style={s.card}>
          <p style={s.muted}>
            Used for every AI-generated insight (Predictor's plain-English summaries, dashboard
            alerts and analyses). Requires an API key from whichever provider you choose.
          </p>

          <div style={s.formField}>
            <label style={s.label}>AI Agent</label>
            <select style={s.select} value={provider} onChange={e => handleProviderChange(e.target.value)}>
              {PROVIDER_ORDER.map(p => (
                <option key={p} value={p}>{PROVIDER_LABELS[p]}</option>
              ))}
            </select>
          </div>

          <div style={{ ...s.formField, marginTop: 14 }}>
            <label style={s.label}>Model</label>
            <select style={s.select} value={model} onChange={e => setModel(e.target.value)}>
              {modelsForProvider.map(m => (
                <option key={m.id} value={m.id}>{m.label}</option>
              ))}
            </select>
          </div>

          <div style={{ ...s.formField, marginTop: 14 }}>
            <label style={s.label}>API Key</label>
            <input
              type="password"
              style={s.input}
              value={apiKey}
              onChange={e => setApiKey(e.target.value)}
              placeholder={hasKey ? `Leave blank to keep the current key (${keyPreview})` : 'Enter an API key'}
              autoComplete="off"
            />
            <p style={s.fieldNote}>
              {hasKey
                ? `A key is currently set (${keyPreview}). Only enter a new one to replace it.`
                : 'No key set yet — insights will show "unavailable" until one is added.'}
            </p>
          </div>

          {updatedAt && (
            <p style={s.fieldNote}>Last updated {new Date(updatedAt).toLocaleString()} by {updatedBy || 'unknown'}</p>
          )}

          {msg && (
            <div style={msg.type === 'success' ? s.successBox : s.errorBox}>{msg.text}</div>
          )}

          <button
            style={{ ...s.tealBtn, opacity: saving ? 0.6 : 1 }}
            disabled={saving}
            onClick={handleSave}
          >
            {saving ? 'Saving…' : 'Save'}
          </button>
        </div>
      )}
    </div>
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

  formField: { display: 'flex', flexDirection: 'column', gap: 6 },
  label:     { fontSize: 12, fontWeight: 600, color: '#334155' },
  input: {
    padding: '10px 14px', borderRadius: 8,
    border: '0.5px solid #C5D2DC', fontSize: 13, color: '#1E293B',
    outline: 'none', width: '100%', boxSizing: 'border-box',
  },
  select: {
    padding: '10px 14px', borderRadius: 8, border: '0.5px solid #C5D2DC',
    fontSize: 13, color: '#1E293B', background: '#fff', cursor: 'pointer',
    width: '100%', boxSizing: 'border-box', outline: 'none',
  },
  fieldNote: { margin: '6px 0 0', fontSize: 11, color: '#94A3B8' },

  successBox: { background: '#E1F5EE', color: '#0F6E56', borderRadius: 8, padding: '10px 14px', fontSize: 13, marginTop: 14 },
  errorBox:   { background: '#FCEBEB', color: '#A32D2D', borderRadius: 8, padding: '10px 14px', fontSize: 13, marginTop: 14 },

  tealBtn: {
    padding: '10px 20px', borderRadius: 8, border: 'none',
    background: '#2E6E8E', color: '#fff', fontSize: 13,
    fontWeight: 600, cursor: 'pointer', marginTop: 16,
  },

  muted: { margin: '0 0 16px', fontSize: 12, color: '#94A3B8' },
};
