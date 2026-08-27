// Risk Email Template: reference wording for the "Log as emailed" bulk
// action on the Students at Risk page. Admin only (Head of Technology /
// Head of School), matching the backend's require_head_of_school gate on
// the PUT endpoint. This system has no real student email address on
// file anywhere (see RiskEmailTemplate's backend docstring), so nothing
// is ever sent from here — staff copy this into the real email they send
// themselves, then use the bulk action to record that it happened.
import { useState, useEffect } from 'react';
import api from '../services/api';
import { getErrorMessage } from '../utils/apiError';

export default function RiskEmailTemplateView() {
  const [subject, setSubject] = useState('');
  const [body,    setBody]    = useState('');
  const [msg,     setMsg]     = useState(null);
  const [saving,  setSaving]  = useState(false);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    api.get('/api/risk-email-template')
      .then(r => { setSubject(r.data.subject); setBody(r.data.body); })
      .catch(() => {})
      .finally(() => setLoading(false));
  }, []);

  const handleSave = async () => {
    setSaving(true);
    setMsg(null);
    try {
      const res = await api.put('/api/risk-email-template', { subject, body });
      setSubject(res.data.subject);
      setBody(res.data.body);
      setMsg({ type: 'success', text: 'Template saved.' });
    } catch (err) {
      setMsg({ type: 'error', text: getErrorMessage(err, 'Failed to save template.') });
    } finally {
      setSaving(false);
    }
  };

  return (
    <div style={{ maxWidth: 720 }}>
      <div style={s.pageHeader}>
        <h1 style={s.pageTitle}>Risk Email Template</h1>
        <p style={s.pageSub}>Reference wording for the "Log as emailed" action on Students at Risk</p>
      </div>

      <div style={s.card}>
        <p style={s.muted}>
          This system has no real student email address on file, so nothing is sent
          automatically — copy this into the real email you send yourself, then use the
          bulk action on the Students at Risk page to record that it happened.
        </p>

        {loading ? (
          <p style={s.muted}>Loading…</p>
        ) : (
          <>
            <div style={s.formField}>
              <label style={s.label}>Subject</label>
              <input
                style={s.input}
                value={subject}
                onChange={e => setSubject(e.target.value)}
              />
            </div>

            <div style={{ ...s.formField, marginTop: 14 }}>
              <label style={s.label}>Body</label>
              <textarea
                style={{ ...s.input, height: 170, padding: '10px 12px', resize: 'vertical', fontFamily: 'inherit' }}
                value={body}
                onChange={e => setBody(e.target.value)}
              />
            </div>

            <p style={s.fieldNote}>
              Placeholders: <code>{'{{student_id}}'}</code>{' '}
              <code>{'{{subject_code}}'}</code>{' '}
              <code>{'{{study_period}}'}</code>{' '}
              <code>{'{{risk_band}}'}</code>
            </p>

            {msg && (
              <div style={msg.type === 'success' ? s.successBox : s.errorBox}>
                {msg.text}
              </div>
            )}

            <button
              style={{ ...s.tealBtn, opacity: saving ? 0.6 : 1 }}
              disabled={saving}
              onClick={handleSave}
            >
              {saving ? 'Saving…' : 'Save Template'}
            </button>
          </>
        )}
      </div>
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
  fieldNote: { margin: '6px 0 0', fontSize: 11, color: '#94A3B8' },

  successBox: { background: '#E1F5EE', color: '#0F6E56', borderRadius: 8, padding: '10px 14px', fontSize: 13, marginBottom: 14, marginTop: 14 },
  errorBox:   { background: '#FCEBEB', color: '#A32D2D', borderRadius: 8, padding: '10px 14px', fontSize: 13, marginBottom: 14, marginTop: 14 },

  tealBtn: {
    padding: '10px 20px', borderRadius: 8, border: 'none',
    background: '#2E6E8E', color: '#fff', fontSize: 13,
    fontWeight: 600, cursor: 'pointer', marginTop: 4,
  },

  muted: { margin: '0 0 16px', fontSize: 12, color: '#94A3B8' },
};
