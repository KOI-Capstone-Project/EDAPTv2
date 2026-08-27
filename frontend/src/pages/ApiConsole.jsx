// API Console: Head of Technology admins generate/revoke API keys for the
// external pass/fail prediction endpoint (/api/v1/predict), and get the
// usage docs needed to call it from outside the app.
import { useState, useEffect, useCallback } from 'react';
import {
  LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer,
} from 'recharts';
import api from '../services/api';
import { getErrorMessage } from '../utils/apiError';

const API_BASE_URL = process.env.REACT_APP_API_BASE_URL || 'http://localhost:8000';

// Fixed 4-slot categorical order for the "By Key" view, validated CVD-safe
// against a white chart surface (adjacent + all-pairs, light mode) — see
// dataviz skill's palette validator. Never cycled/regenerated per extra key;
// a 5th+ key folds into "Other" (muted gray) instead of growing the palette.
const KEY_COLORS = ['#2a78d6', '#eb6834', '#1baf7a', '#eda100'];
const OTHER_COLOR = '#8BA5B8';

const SAMPLE_REQUEST = `curl -X POST ${API_BASE_URL}/api/v1/predict \\
  -H "X-API-Key: <your-key>" \\
  -H "Content-Type: application/json" \\
  -d '{
    "subject": "ACC101",
    "study_period": "2026.2",
    "trimester_num": 2,
    "assessments": [
      { "type": "Assignment 1",  "mark_percent": 78, "weighting": 20 },
      { "type": "Quiz 1",        "mark_percent": 85, "weighting": 10 },
      { "type": "Midterm Exam",  "mark_percent": 70, "weighting": 30 },
      { "type": "Final Exam",    "mark_percent": 75, "weighting": 40 }
    ],
    "attendance_percentage": 92.5
  }'`;

const SAMPLE_RESPONSE = `{
  "prediction_available": true,
  "subject": "ACC101",
  "study_period": "2026.2",
  "coverage_status": "complete",
  "result": "Pass",
  "pass_percentage": 99.3,
  "risk_band": "Safe",
  "estimate_type": null,
  "model_version": "20260808_110630"
}`;

function Spinner() {
  return (
    <tr>
      <td colSpan={6} style={{ padding: 0, border: 'none' }}>
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', height: 160 }}>
          <div style={{ width: 32, height: 32, border: '3px solid #F0F4F8', borderTop: '3px solid #2E6E8E', borderRadius: '50%', animation: 'spin 0.8s linear infinite' }} />
        </div>
      </td>
    </tr>
  );
}

function fmt(d) {
  if (!d) return '—';
  return new Date(d).toLocaleString('en-AU', { day: '2-digit', month: 'short', year: 'numeric', hour: '2-digit', minute: '2-digit' });
}

function fmtDay(iso) {
  return new Date(iso + 'T00:00:00').toLocaleDateString('en-AU', { day: '2-digit', month: 'short' });
}

const NoData = () => (
  <div style={{ height: 240, display: 'flex', alignItems: 'center', justifyContent: 'center', color: '#94A3B8', fontSize: 13 }}>
    No API requests in this window yet
  </div>
);

export default function ApiConsole() {
  const [keys,        setKeys]        = useState([]);
  const [loading,     setLoading]     = useState(true);
  const [showCreate,  setShowCreate]  = useState(false);
  const [name,        setName]        = useState('');
  const [nameErr,     setNameErr]     = useState('');
  const [creating,    setCreating]    = useState(false);
  const [revealed,    setRevealed]    = useState(null); // { name, api_key, created_at } — shown once
  const [copied,      setCopied]      = useState(false);

  const [usage,        setUsage]        = useState(null);
  const [usageLoading,  setUsageLoading] = useState(true);
  const [usageView,     setUsageView]    = useState('total'); // 'total' | 'byKey'

  const fetchKeys = useCallback(() => {
    setLoading(true);
    api.get('/api/api-keys')
      .then(res => setKeys(Array.isArray(res.data) ? res.data : []))
      .catch(() => setKeys([]))
      .finally(() => setLoading(false));
  }, []);

  const fetchUsage = useCallback(() => {
    setUsageLoading(true);
    api.get('/api/api-keys/usage', { params: { days: 30 } })
      .then(res => setUsage(res.data))
      .catch(() => setUsage(null))
      .finally(() => setUsageLoading(false));
  }, []);

  useEffect(() => { fetchKeys(); fetchUsage(); }, [fetchKeys, fetchUsage]);

  const usageChartData = (usage?.days || []).map((day, i) => {
    const row = { day: fmtDay(day), total: usage.total[i] };
    for (const k of usage.by_key) row[k.name] = k.counts[i];
    return row;
  });
  const hasUsageData = (usage?.total || []).some(v => v > 0);

  const handleCreate = async () => {
    if (!name.trim()) { setNameErr('Give this key a name so you can recognize it later.'); return; }
    setNameErr('');
    setCreating(true);
    try {
      const res = await api.post('/api/api-keys', { name: name.trim() });
      setRevealed(res.data);
      setName('');
      setShowCreate(false);
      fetchKeys();
    } catch (err) {
      setNameErr(getErrorMessage(err, 'Failed to generate API key.'));
    } finally {
      setCreating(false);
    }
  };

  const handleRevoke = async key => {
    if (!window.confirm(`Revoke "${key.name}"? Any system using this key will immediately lose access.`)) return;
    try {
      await api.delete(`/api/api-keys/${key.id}`);
      setKeys(prev => prev.map(k => k.id === key.id ? { ...k, revoked: true } : k));
    } catch (err) {
      alert(getErrorMessage(err, 'Failed to revoke key.'));
    }
  };

  const copyKey = () => {
    if (!revealed) return;
    navigator.clipboard.writeText(revealed.api_key).then(() => {
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    });
  };

  return (
    <div>
      <style>{`@keyframes spin { to { transform: rotate(360deg); } }`}</style>

      {/* ── Header ──────────────────────────────────────────────────── */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 24, flexWrap: 'wrap', gap: 12 }}>
        <div>
          <h1 style={s.pageTitle}>API Console</h1>
          <p style={s.pageSub}>Generate and manage API keys for external pass/fail prediction access</p>
        </div>
        <button
          style={s.createBtn}
          onClick={() => { setShowCreate(o => !o); setNameErr(''); }}
        >
          {showCreate ? '✕ Cancel' : '+ Generate New API Key'}
        </button>
      </div>

      {/* ── One-time key reveal ────────────────────────────────────── */}
      {revealed && (
        <div style={s.revealPanel}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', gap: 12 }}>
            <div style={{ flex: 1, minWidth: 0 }}>
              <div style={{ fontWeight: 600, fontSize: 13, color: '#633806', marginBottom: 6 }}>
                ⚠️ "{revealed.name}" created — copy this key now, it won't be shown again
              </div>
              <div style={s.revealKeyBox}>
                <code style={s.revealKeyText}>{revealed.api_key}</code>
                <button style={s.copyBtn} onClick={copyKey}>{copied ? 'Copied ✓' : 'Copy'}</button>
              </div>
            </div>
            <button style={s.cancelLink} onClick={() => setRevealed(null)}>Dismiss</button>
          </div>
        </div>
      )}

      {/* ── Create form ─────────────────────────────────────────────── */}
      {showCreate && (
        <div style={s.createPanel}>
          <h3 style={{ margin: '0 0 16px', fontSize: 15, fontWeight: 500, color: '#1A2E40' }}>New API Key</h3>
          <div style={s.formField}>
            <label style={s.label}>Key Name / Label *</label>
            <input
              style={s.input}
              value={name}
              onChange={e => { setName(e.target.value); setNameErr(''); }}
              placeholder="e.g. SIS Integration"
            />
            {nameErr && <span style={s.fieldErr}>{nameErr}</span>}
          </div>
          <div style={{ display: 'flex', gap: 12, marginTop: 16 }}>
            <button style={{ ...s.createBtn, opacity: creating ? 0.6 : 1 }} disabled={creating} onClick={handleCreate}>
              {creating ? 'Generating…' : 'Generate Key'}
            </button>
            <button style={s.cancelLink} onClick={() => { setShowCreate(false); setNameErr(''); }}>Cancel</button>
          </div>
        </div>
      )}

      {/* ── API usage chart ─────────────────────────────────────────── */}
      <div style={s.chartCard}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 14, flexWrap: 'wrap', gap: 10 }}>
          <h3 style={s.chartTitle}>API Usage — last 30 days</h3>
          <div style={s.viewToggle}>
            <button
              style={{ ...s.viewToggleBtn, ...(usageView === 'total' ? s.viewToggleBtnActive : {}) }}
              onClick={() => setUsageView('total')}
            >
              Total
            </button>
            <button
              style={{ ...s.viewToggleBtn, ...(usageView === 'byKey' ? s.viewToggleBtnActive : {}) }}
              onClick={() => setUsageView('byKey')}
            >
              By Key
            </button>
          </div>
        </div>

        {usageLoading ? (
          <div style={{ height: 240, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
            <div style={{ width: 32, height: 32, border: '3px solid #F0F4F8', borderTop: '3px solid #2E6E8E', borderRadius: '50%', animation: 'spin 0.8s linear infinite' }} />
          </div>
        ) : !hasUsageData ? (
          <NoData />
        ) : (
          <ResponsiveContainer width="100%" height={240}>
            <LineChart data={usageChartData} margin={{ top: 4, right: 12, left: 0, bottom: 0 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="#F1F5F9" />
              <XAxis dataKey="day" tick={{ fontSize: 11 }} interval={3} />
              <YAxis allowDecimals={false} tick={{ fontSize: 11 }} />
              <Tooltip />
              {usageView === 'total' ? (
                <Line type="monotone" dataKey="total" name="Requests" stroke="#2E6E8E" strokeWidth={2} dot={false} />
              ) : (
                <>
                  <Legend />
                  {usage.by_key.map((k, i) => (
                    <Line
                      key={k.name}
                      type="monotone"
                      dataKey={k.name}
                      name={k.name}
                      stroke={k.name === 'Other' ? OTHER_COLOR : KEY_COLORS[i % KEY_COLORS.length]}
                      strokeWidth={2}
                      dot={false}
                    />
                  ))}
                </>
              )}
            </LineChart>
          </ResponsiveContainer>
        )}
      </div>

      {/* ── Main content: keys table + docs side panel ───────────────── */}
      <div style={s.contentGrid}>
        <div style={s.tableWrapper}>
          <table style={s.table}>
            <thead>
              <tr style={s.thead}>
                {['Name', 'Key', 'Created', 'Last Used', 'Status', 'Actions'].map(col => (
                  <th key={col} style={s.th}>{col}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {loading ? (
                <Spinner />
              ) : keys.length === 0 ? (
                <tr>
                  <td colSpan={6} style={{ padding: 0, border: 'none' }}>
                    <div style={{ textAlign: 'center', padding: '50px 20px', color: '#8BA5B8' }}>
                      <div style={{ fontSize: 32, marginBottom: 12 }}>🔑</div>
                      <div style={{ fontSize: 14, fontWeight: 500, color: '#1A2E40', marginBottom: 4 }}>No API keys yet</div>
                      <div style={{ fontSize: 13 }}>Generate one to enable external prediction access</div>
                    </div>
                  </td>
                </tr>
              ) : keys.map((k, i) => (
                <tr key={k.id} style={{ background: i % 2 === 0 ? '#fff' : '#F8FAFB' }}>
                  <td style={s.td}>{k.name}</td>
                  <td style={{ ...s.td, ...s.tdMono }}>{k.key_prefix}…</td>
                  <td style={{ ...s.td, whiteSpace: 'nowrap' }}>{fmt(k.created_at)}</td>
                  <td style={{ ...s.td, whiteSpace: 'nowrap' }}>{fmt(k.last_used_at)}</td>
                  <td style={s.td}>
                    <span style={{ ...s.badge, ...(k.revoked ? s.badgeRevoked : s.badgeActive) }}>
                      {k.revoked ? 'Revoked' : 'Active'}
                    </span>
                  </td>
                  <td style={s.td}>
                    <button
                      style={{ ...s.iconBtn, opacity: k.revoked ? 0.4 : 1, cursor: k.revoked ? 'default' : 'pointer' }}
                      disabled={k.revoked}
                      onClick={() => handleRevoke(k)}
                    >
                      Revoke
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        {/* ── API usage docs ─────────────────────────────────────────── */}
        <div style={s.docsCard}>
          <h3 style={{ margin: '0 0 12px', fontSize: 14, fontWeight: 600, color: '#1A2E40' }}>API Usage</h3>

          <div style={s.docsLabel}>Endpoint</div>
          <pre style={s.codeBlock}>POST {API_BASE_URL}/api/v1/predict</pre>

          <div style={s.docsLabel}>Header</div>
          <pre style={s.codeBlock}>X-API-Key: &lt;your-key&gt;</pre>

          <div style={s.docsLabel}>Parameters</div>
          <table style={s.paramTable}>
            <tbody>
              {[
                ['subject', 'string', 'Subject code, e.g. "ACC101"'],
                ['study_period', 'string', 'Study period, e.g. "2026.2"'],
                ['trimester_num', 'number', 'Trimester number, e.g. 2'],
                ['assessments', 'array', '{type, mark_percent, weighting} per assessment'],
                ['attendance_percentage', 'number', '0–100'],
              ].map(([p, t, d]) => (
                <tr key={p}>
                  <td style={s.paramName}>{p}</td>
                  <td style={s.paramType}>{t}</td>
                  <td style={s.paramDesc}>{d}</td>
                </tr>
              ))}
            </tbody>
          </table>

          <div style={s.docsLabel}>Sample request</div>
          <pre style={s.codeBlock}>{SAMPLE_REQUEST}</pre>

          <div style={s.docsLabel}>Sample response</div>
          <pre style={s.codeBlock}>{SAMPLE_RESPONSE}</pre>
        </div>
      </div>
    </div>
  );
}

const s = {
  pageTitle: { margin: '0 0 4px', fontSize: 24, fontWeight: 500, color: '#1A2E40' },
  pageSub:   { margin: 0, fontSize: 13, color: '#5A7A8A' },

  createBtn: {
    padding: '10px 20px', borderRadius: 8, border: 'none',
    background: '#2E6E8E', color: '#fff', fontSize: 13, fontWeight: 500, cursor: 'pointer',
  },
  cancelLink: { background: 'none', border: 'none', cursor: 'pointer', fontSize: 13, color: '#5A7A8A', textDecoration: 'underline', fontWeight: 500, whiteSpace: 'nowrap' },

  createPanel: { background: '#fff', border: '0.5px solid #DDE4EA', borderRadius: 12, padding: '20px 24px', marginBottom: 24, maxWidth: 420 },
  formField:   { display: 'flex', flexDirection: 'column', gap: 6 },
  label:       { fontSize: 12, fontWeight: 600, color: '#334155' },
  input: {
    height: 36, padding: '0 12px', borderRadius: 8,
    border: '0.5px solid #C5D2DC', fontSize: 13, color: '#1A2E40',
    outline: 'none', width: '100%', boxSizing: 'border-box',
  },
  fieldErr: { fontSize: 11, color: '#DC2626', marginTop: 3, display: 'block' },

  revealPanel: {
    background: '#FAEEDA', border: '0.5px solid #EF9F27', borderRadius: 12,
    padding: '16px 20px', marginBottom: 24,
  },
  revealKeyBox: {
    display: 'flex', alignItems: 'center', gap: 10,
    background: '#fff', border: '0.5px solid #EF9F27', borderRadius: 8,
    padding: '8px 12px', overflowX: 'auto',
  },
  revealKeyText: { fontFamily: "'SF Mono','Fira Code',monospace", fontSize: 12.5, color: '#1A2E40', whiteSpace: 'nowrap' },
  copyBtn: {
    flexShrink: 0, padding: '6px 14px', borderRadius: 6, border: 'none',
    background: '#2E6E8E', color: '#fff', fontSize: 12, fontWeight: 500, cursor: 'pointer',
  },

  chartCard:  { background: '#fff', border: '0.5px solid #DDE4EA', borderRadius: 12, padding: '20px', marginBottom: 20 },
  chartTitle: { margin: 0, fontSize: 14, fontWeight: 500, color: '#1A2E40' },
  viewToggle: { display: 'flex', background: '#F0F4F8', borderRadius: 8, padding: 3, gap: 2 },
  viewToggleBtn: {
    padding: '5px 14px', borderRadius: 6, border: 'none', background: 'transparent',
    fontSize: 12, fontWeight: 500, color: '#5A7A8A', cursor: 'pointer',
  },
  viewToggleBtnActive: { background: '#fff', color: '#1A2E40', boxShadow: '0 1px 2px rgba(0,0,0,0.08)' },

  contentGrid: { display: 'grid', gridTemplateColumns: 'minmax(0, 2fr) minmax(280px, 1fr)', gap: 20, alignItems: 'start' },

  tableWrapper: { background: '#fff', border: '0.5px solid #DDE4EA', borderRadius: 12, overflow: 'hidden' },
  table:        { width: '100%', borderCollapse: 'collapse', fontSize: 13 },
  thead:        { background: '#F0F4F8' },
  th: {
    padding: '12px 16px', textAlign: 'left',
    fontSize: 11, fontWeight: 500, color: '#5A7A8A',
    textTransform: 'uppercase', letterSpacing: 0.5,
    borderBottom: '0.5px solid #F0F4F8', whiteSpace: 'nowrap',
  },
  td:     { padding: '12px 16px', color: '#1A2E40', borderBottom: '0.5px solid #F0F4F8', verticalAlign: 'middle' },
  tdMono: { fontFamily: "'SF Mono','Fira Code',monospace", fontSize: 12, color: '#5A7A8A' },

  badge: { display: 'inline-block', padding: '3px 10px', borderRadius: 20, border: '0.5px solid', fontSize: 12, fontWeight: 500 },
  badgeActive:  { background: '#E1F5EE', color: '#0F6E56', borderColor: '#5DCAA5' },
  badgeRevoked: { background: '#FCEBEB', color: '#A32D2D', borderColor: '#F09595' },

  iconBtn: { padding: '5px 12px', borderRadius: 6, border: '0.5px solid #DDE4EA', background: '#fff', fontSize: 12, fontWeight: 500, color: '#A32D2D' },

  docsCard: { background: '#fff', border: '0.5px solid #DDE4EA', borderRadius: 12, padding: '18px 20px' },
  docsLabel: { fontSize: 11, fontWeight: 600, color: '#8BA5B8', textTransform: 'uppercase', letterSpacing: 0.5, margin: '14px 0 6px' },
  codeBlock: {
    background: '#F0F4F8', borderRadius: 8, padding: '10px 12px',
    fontFamily: "'SF Mono','Fira Code',monospace", fontSize: 11.5, color: '#1A2E40',
    whiteSpace: 'pre-wrap', wordBreak: 'break-word', margin: 0, overflowX: 'auto',
  },
  paramTable: { width: '100%', fontSize: 12, borderCollapse: 'collapse' },
  paramName: { padding: '4px 0', fontFamily: "'SF Mono','Fira Code',monospace", color: '#2E6E8E', fontWeight: 600, verticalAlign: 'top', whiteSpace: 'nowrap' },
  paramType: { padding: '4px 8px', color: '#8BA5B8', verticalAlign: 'top', whiteSpace: 'nowrap' },
  paramDesc: { padding: '4px 0', color: '#5A7A8A', verticalAlign: 'top' },
};
