// OAuth Providers: configure Google / Microsoft sign-in from the app
// instead of GOOGLE_CLIENT_ID/MICROSOFT_CLIENT_ID/MICROSOFT_TENANT_ID env
// vars — admin only (Head of Technology / Head of School), matching the
// backend's require_head_of_school gate on the write endpoint. Both
// providers always list, even before either has ever been configured, so
// there's somewhere obvious to go set them up.
import { useState, useEffect } from 'react';
import api from '../services/api';

const PROVIDER_META = {
  google:    { label: 'Google',    hint: 'Sign-in with a Google Workspace / Gmail account.' },
  microsoft: { label: 'Microsoft', hint: 'Sign-in with a Microsoft / Azure AD (Entra ID) account.' },
};
const PROVIDER_ORDER = ['google', 'microsoft'];

export default function OAuthProvidersView() {
  const [providers, setProviders] = useState(null);
  const [loadError, setLoadError] = useState(null);
  const [expanded,  setExpanded]  = useState(null);

  const load = () => {
    api.get('/api/oauth-providers')
      .then(r => {
        const byProvider = {};
        r.data.providers.forEach(p => { byProvider[p.provider] = p; });
        setProviders(byProvider);
      })
      .catch(err => setLoadError(err.response?.data?.detail || 'Failed to load OAuth provider settings.'));
  };

  useEffect(load, []);

  return (
    <div style={{ maxWidth: 720 }}>
      <div style={s.pageHeader}>
        <h1 style={s.pageTitle}>OAuth Providers</h1>
        <p style={s.pageSub}>Configure Google / Microsoft sign-in — changes apply immediately, no redeploy needed</p>
      </div>

      {loadError && <div style={s.errorBox}>{loadError}</div>}

      {providers && PROVIDER_ORDER.map(key => (
        <ProviderCard
          key={key}
          providerKey={key}
          meta={PROVIDER_META[key]}
          config={providers[key]}
          isOpen={expanded === key}
          onToggle={() => setExpanded(prev => prev === key ? null : key)}
          onSaved={load}
        />
      ))}
    </div>
  );
}

function ProviderCard({ providerKey, meta, config, isOpen, onToggle, onSaved }) {
  const [clientId, setClientId] = useState(config.client_id || '');
  const [tenantId, setTenantId] = useState(config.tenant_id || '');
  const [enabled,  setEnabled]  = useState(config.enabled);
  const [saving,   setSaving]   = useState(false);
  const [msg,      setMsg]      = useState(null);

  const handleSave = async () => {
    setSaving(true);
    setMsg(null);
    try {
      const res = await api.put(`/api/oauth-providers/${providerKey}`, {
        client_id: clientId,
        tenant_id: providerKey === 'microsoft' ? tenantId : null,
        enabled,
      });
      setClientId(res.data.client_id);
      setTenantId(res.data.tenant_id || '');
      setEnabled(res.data.enabled);
      setMsg({
        type: 'success',
        text: res.data.enabled
          ? 'Saved. Sign-in is live.'
          : (enabled && !res.data.enabled
              ? 'Saved, but left disabled — a Client ID is required to enable sign-in.'
              : 'Saved.'),
      });
      onSaved();
    } catch (err) {
      setMsg({ type: 'error', text: err.response?.data?.detail || 'Failed to save.' });
    } finally {
      setSaving(false);
    }
  };

  return (
    <div style={s.card}>
      <button type="button" style={s.cardHeader} onClick={onToggle}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
          <span style={s.cardTitle}>{meta.label}</span>
          <span style={config.enabled ? s.statusOn : s.statusOff}>
            {config.enabled ? 'Enabled' : 'Not configured'}
          </span>
        </div>
        <span style={{ ...s.chevron, transform: isOpen ? 'rotate(90deg)' : 'rotate(0deg)' }}>›</span>
      </button>

      {isOpen && (
        <div style={s.cardBody}>
          <p style={s.muted}>{meta.hint}</p>

          <div style={s.formField}>
            <label style={s.label}>Client ID</label>
            <input
              style={s.input}
              value={clientId}
              onChange={e => setClientId(e.target.value)}
              placeholder={`${meta.label} OAuth Client ID`}
            />
          </div>

          {providerKey === 'microsoft' && (
            <div style={{ ...s.formField, marginTop: 14 }}>
              <label style={s.label}>Tenant ID</label>
              <input
                style={s.input}
                value={tenantId}
                onChange={e => setTenantId(e.target.value)}
                placeholder="common (default — any organization or personal account)"
              />
              <p style={s.fieldNote}>Leave blank for "common" (multi-tenant), or set your organization's tenant/directory ID to restrict sign-in to it.</p>
            </div>
          )}

          <label style={s.toggleRow}>
            <input type="checkbox" checked={enabled} onChange={e => setEnabled(e.target.checked)} />
            <span>Enabled</span>
          </label>

          {config.updated_at && (
            <p style={s.fieldNote}>Last updated {new Date(config.updated_at).toLocaleString()} by {config.updated_by || 'unknown'}</p>
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
    borderRadius: 10, marginBottom: 16, overflow: 'hidden',
  },
  cardHeader: {
    width: '100%', display: 'flex', alignItems: 'center', justifyContent: 'space-between',
    padding: '18px 24px', background: 'none', border: 'none', cursor: 'pointer', textAlign: 'left',
  },
  cardTitle: { fontSize: 15, fontWeight: 600, color: '#1E293B' },
  chevron: { fontSize: 18, color: '#94A3B8', transition: 'transform 0.15s' },
  cardBody: { padding: '0 24px 24px' },

  statusOn:  { fontSize: 11, fontWeight: 700, color: '#0F6E56', background: '#E1F5EE', borderRadius: 20, padding: '3px 10px' },
  statusOff: { fontSize: 11, fontWeight: 700, color: '#64748B', background: '#F1F5F9', borderRadius: 20, padding: '3px 10px' },

  formField: { display: 'flex', flexDirection: 'column', gap: 6 },
  label:     { fontSize: 12, fontWeight: 600, color: '#334155' },
  input: {
    padding: '10px 14px', borderRadius: 8,
    border: '0.5px solid #C5D2DC', fontSize: 13, color: '#1E293B',
    outline: 'none', width: '100%', boxSizing: 'border-box',
  },
  fieldNote: { margin: '6px 0 0', fontSize: 11, color: '#94A3B8' },

  toggleRow: { display: 'flex', alignItems: 'center', gap: 8, fontSize: 13, color: '#334155', marginTop: 16, cursor: 'pointer' },

  successBox: { background: '#E1F5EE', color: '#0F6E56', borderRadius: 8, padding: '10px 14px', fontSize: 13, marginTop: 14 },
  errorBox:   { background: '#FCEBEB', color: '#A32D2D', borderRadius: 8, padding: '10px 14px', fontSize: 13, marginTop: 14 },

  tealBtn: {
    padding: '10px 20px', borderRadius: 8, border: 'none',
    background: '#2E6E8E', color: '#fff', fontSize: 13,
    fontWeight: 600, cursor: 'pointer', marginTop: 16,
  },

  muted: { margin: '0 0 16px', fontSize: 12, color: '#94A3B8' },
};
