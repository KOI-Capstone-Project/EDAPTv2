// Outgoing Mail Servers: admin-managed SMTP servers that power every
// outbound email the app sends (currently just the forgot-password reset
// code) — replaces the single hardcoded GMAIL_SENDER/GMAIL_APP_PASSWORD env
// var pair. Multiple servers are supported (lowest Priority among the
// active ones is the one actually used to send); fields and the
// "Test Connection" flow are modeled on Odoo's Outgoing Mail Servers form.
import { useState, useEffect, useCallback } from 'react';
import api from '../services/api';
import { getErrorMessage } from '../utils/apiError';
import { getUser } from '../utils/auth';
import RichTextEditor from '../components/RichTextEditor';

function isValidEmail(email) {
  if (!email || email.length > 254) return false;
  const at = email.indexOf('@');
  if (at <= 0 || email.indexOf('@', at + 1) !== -1) return false;
  const local  = email.slice(0, at);
  const rest   = email.slice(at + 1);
  if (!/^[a-zA-Z0-9._%+-]+$/.test(local)) return false;
  const dot = rest.lastIndexOf('.');
  if (dot <= 0) return false;
  const ext = rest.slice(dot + 1);
  return ext.length >= 2;
}

const SECURITY_OPTIONS = [
  { value: 'none',     label: 'None' },
  { value: 'starttls', label: 'TLS (STARTTLS)' },
  { value: 'ssl',      label: 'SSL/TLS' },
];
const DEFAULT_PORT_BY_SECURITY = { none: 25, starttls: 587, ssl: 465 };

const EMPTY_FORM = {
  name: '', host: '', port: 587, security: 'starttls',
  username: '', password: '', from_email: '', priority: 10, active: true,
};

function Spinner() {
  return <span style={s.spinner} />;
}

function TestResultBanner({ result, runningLabel = 'Testing connection…' }) {
  if (!result) return null;
  if (result.status === 'running') {
    return <div style={s.testBanner}><Spinner /> {runningLabel}</div>;
  }
  const ok = result.status === 'success';
  return (
    <div style={{ ...s.testBanner, ...(ok ? s.testBannerOk : s.testBannerFail) }}>
      {ok ? '✓' : '⚠'} {result.message}
      {typeof result.elapsed_seconds === 'number' && !ok && ` (${result.elapsed_seconds}s)`}
    </div>
  );
}

// to_email defaults to the logged-in user's own address — read fresh each
// time the panel opens, not baked into a module-level constant, since it
// depends on who's currently signed in.
const emptySendForm = () => ({
  server_id: '', from_email: '', to_email: getUser()?.email || '',
  subject: 'EDAPT Test Email', body: '<p>This is a test email from EDAPT.</p>',
});

export default function OutgoingMailServersView() {
  const [servers, setServers] = useState([]);
  const [loading, setLoading] = useState(true);

  const [showForm, setShowForm]   = useState(false);
  const [editingId, setEditingId] = useState(null); // null = creating new
  const [form, setForm]           = useState(EMPTY_FORM);
  const [saving, setSaving]       = useState(false);
  const [formError, setFormError] = useState(null);
  const [testState, setTestState] = useState(null); // {status:'running'|'success'|'failed', message, elapsed_seconds} | null
  const [testing, setTesting]     = useState(false);

  const [rowTest, setRowTest] = useState({}); // {[id]: {status, message, elapsed_seconds}}

  const [showSendTest, setShowSendTest]   = useState(false);
  const [sendForm, setSendForm]           = useState(emptySendForm);
  const [sending, setSending]             = useState(false);
  const [sendResult, setSendResult]       = useState(null); // {status:'running'|'success'|'failed', message} | null

  const fetchServers = useCallback(() => {
    setLoading(true);
    api.get('/api/mail-servers')
      .then(r => setServers(r.data.servers || []))
      .catch(() => setServers([]))
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => { fetchServers(); }, [fetchServers]);

  const openCreate = () => {
    setEditingId(null);
    setForm(EMPTY_FORM);
    setFormError(null);
    setTestState(null);
    setShowForm(true);
  };

  const openEdit = (srv) => {
    setEditingId(srv.id);
    setForm({
      name: srv.name, host: srv.host, port: srv.port, security: srv.security,
      username: srv.username || '', password: '', from_email: srv.from_email || '',
      priority: srv.priority, active: srv.active,
    });
    setFormError(null);
    setTestState(null);
    setShowForm(true);
  };

  const closeForm = () => { setShowForm(false); setTestState(null); };

  const handleSecurityChange = (security) => {
    setForm(f => ({ ...f, security, port: DEFAULT_PORT_BY_SECURITY[security] ?? f.port }));
  };

  const buildTestPayload = () => {
    const payload = {
      host: form.host, port: Number(form.port), security: form.security,
      username: form.username || null, password: form.password || null,
    };
    // Editing with a blank password means "use whatever's already stored" —
    // server_id lets the backend fill that in server-side, since the
    // plaintext password was never sent back to this form after saving.
    if (editingId) payload.server_id = editingId;
    return payload;
  };

  const handleTest = async () => {
    if (!form.host.trim() || !form.port) {
      setTestState({ status: 'failed', message: 'Host and port are required to test a connection.' });
      return;
    }
    setTesting(true);
    setTestState({ status: 'running' });
    try {
      const res = await api.post('/api/mail-servers/test', buildTestPayload());
      setTestState({
        status: res.data.success ? 'success' : 'failed',
        message: res.data.message, elapsed_seconds: res.data.elapsed_seconds,
      });
    } catch (err) {
      setTestState({ status: 'failed', message: getErrorMessage(err, 'Test failed. Please try again.') });
    } finally {
      setTesting(false);
    }
  };

  const handleSave = async () => {
    if (!form.name.trim() || !form.host.trim() || !form.port) {
      setFormError('Name, SMTP server, and port are required.');
      return;
    }
    setSaving(true);
    setFormError(null);
    try {
      const payload = {
        name: form.name.trim(), host: form.host.trim(), port: Number(form.port), security: form.security,
        username: form.username.trim() || null, password: form.password || null,
        from_email: form.from_email.trim() || null, priority: Number(form.priority), active: form.active,
      };
      if (editingId) await api.put(`/api/mail-servers/${editingId}`, payload);
      else           await api.post('/api/mail-servers', payload);
      closeForm();
      fetchServers();
    } catch (err) {
      setFormError(getErrorMessage(err, 'Failed to save this mail server.'));
    } finally {
      setSaving(false);
    }
  };

  const handleDelete = async (srv) => {
    if (!window.confirm(`Delete "${srv.name}"? This can't be undone.`)) return;
    try {
      await api.delete(`/api/mail-servers/${srv.id}`);
      fetchServers();
    } catch (err) {
      alert(getErrorMessage(err, 'Failed to delete this mail server.'));
    }
  };

  const handleRowTest = async (srv) => {
    setRowTest(prev => ({ ...prev, [srv.id]: { status: 'running' } }));
    try {
      const res = await api.post('/api/mail-servers/test', { server_id: srv.id });
      setRowTest(prev => ({
        ...prev,
        [srv.id]: { status: res.data.success ? 'success' : 'failed', message: res.data.message, elapsed_seconds: res.data.elapsed_seconds },
      }));
    } catch (err) {
      setRowTest(prev => ({ ...prev, [srv.id]: { status: 'failed', message: getErrorMessage(err, 'Test failed.') } }));
    }
  };

  const openSendTest = () => {
    setSendForm(emptySendForm());
    setSendResult(null);
    setShowSendTest(true);
  };
  const closeSendTest = () => { setShowSendTest(false); setSendResult(null); };

  const handleSendTest = async () => {
    if (!sendForm.from_email.trim() || !sendForm.to_email.trim() || !sendForm.body.trim()) {
      setSendResult({ status: 'failed', message: 'From, To, and Body are all required.' });
      return;
    }
    if (!isValidEmail(sendForm.from_email.trim())) {
      setSendResult({ status: 'failed', message: 'Enter a valid From email address.' });
      return;
    }
    if (!isValidEmail(sendForm.to_email.trim())) {
      setSendResult({ status: 'failed', message: 'Enter a valid To email address.' });
      return;
    }
    setSending(true);
    setSendResult({ status: 'running' });
    try {
      const res = await api.post('/api/mail-servers/send-test-email', {
        server_id:  sendForm.server_id || null,
        from_email: sendForm.from_email.trim(),
        to_email:   sendForm.to_email.trim(),
        subject:    sendForm.subject.trim() || 'EDAPT Test Email',
        body:       sendForm.body,
      });
      setSendResult({
        status: res.data.status === 'sent' ? 'success' : 'failed',
        message: res.data.status === 'sent'
          ? `Sent — logged as #${res.data.log_id}. See Email Logs for details.`
          : (res.data.failure_reason || 'Send failed.'),
      });
    } catch (err) {
      setSendResult({ status: 'failed', message: getErrorMessage(err, 'Failed to send test email.') });
    } finally {
      setSending(false);
    }
  };

  const securityLabel = (value) => SECURITY_OPTIONS.find(o => o.value === value)?.label || value;

  return (
    <div>
      <style>{`@keyframes mailSpin { to { transform: rotate(360deg); } }`}</style>

      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 24, flexWrap: 'wrap', gap: 12 }}>
        <div>
          <h1 style={s.pageTitle}>Outgoing Mail Servers</h1>
          <p style={s.pageSub}>Configure SMTP servers used to send email from EDAPT (e.g. password reset codes)</p>
        </div>
        <div style={{ display: 'flex', gap: 10 }}>
          <button style={s.testBtn} onClick={showSendTest ? closeSendTest : openSendTest}>
            {showSendTest ? '✕ Cancel' : 'Send Test Email'}
          </button>
          <button style={s.createBtn} onClick={showForm && editingId === null ? closeForm : openCreate}>
            {showForm && editingId === null ? '✕ Cancel' : '+ Add Mail Server'}
          </button>
        </div>
      </div>

      {/* ── Send test email ─────────────────────────────────────────── */}
      {showSendTest && (
        <div style={s.formPanel}>
          <h3 style={s.formTitle}>Send Test Email</h3>
          <div style={s.formGrid}>
            <div style={{ ...s.field, gridColumn: '1 / -1' }}>
              <label style={s.label}>Send Through</label>
              <select style={s.select} value={sendForm.server_id} onChange={e => setSendForm(f => ({ ...f, server_id: e.target.value }))}>
                <option value="">Active server (lowest priority)</option>
                {servers.map(srv => (
                  <option key={srv.id} value={srv.id}>{srv.name} ({srv.host})</option>
                ))}
              </select>
            </div>
            <div style={s.field}>
              <label style={s.label}>From *</label>
              <input style={s.input} value={sendForm.from_email} onChange={e => setSendForm(f => ({ ...f, from_email: e.target.value }))} placeholder="sender@yourdomain.com" />
              {sendForm.from_email && !isValidEmail(sendForm.from_email) && (
                <span style={s.fieldErr}>Enter a valid email address.</span>
              )}
            </div>
            <div style={s.field}>
              <label style={s.label}>To *</label>
              <input style={s.input} value={sendForm.to_email} onChange={e => setSendForm(f => ({ ...f, to_email: e.target.value }))} placeholder="recipient@example.com" />
              {sendForm.to_email && !isValidEmail(sendForm.to_email) && (
                <span style={s.fieldErr}>Enter a valid email address.</span>
              )}
            </div>
            <div style={{ ...s.field, gridColumn: '1 / -1' }}>
              <label style={s.label}>Subject</label>
              <input style={s.input} value={sendForm.subject} onChange={e => setSendForm(f => ({ ...f, subject: e.target.value }))} />
            </div>
            <div style={{ ...s.field, gridColumn: '1 / -1' }}>
              <label style={s.label}>Body (HTML) *</label>
              <RichTextEditor
                value={sendForm.body}
                onChange={html => setSendForm(f => ({ ...f, body: html }))}
                minHeight={150}
                placeholder="Your HTML email content…"
              />
            </div>
          </div>

          <TestResultBanner result={sendResult} runningLabel="Sending…" />

          <div style={{ display: 'flex', gap: 12, marginTop: 18 }}>
            <button style={{ ...s.createBtn, opacity: sending ? 0.6 : 1 }} disabled={sending} onClick={handleSendTest}>
              {sending ? 'Sending…' : 'Send'}
            </button>
            <button style={s.cancelLink} onClick={closeSendTest}>Cancel</button>
          </div>
        </div>
      )}

      {/* ── Create / edit form ─────────────────────────────────────── */}
      {showForm && (
        <div style={s.formPanel}>
          <h3 style={s.formTitle}>{editingId ? 'Edit Mail Server' : 'New Mail Server'}</h3>

          <div style={s.formGrid}>
            <div style={s.field}>
              <label style={s.label}>Description *</label>
              <input style={s.input} value={form.name} onChange={e => setForm(f => ({ ...f, name: e.target.value }))} placeholder="e.g. Gmail SMTP" />
            </div>
            <div style={s.field}>
              <label style={s.label}>Priority</label>
              <input type="number" style={s.input} value={form.priority} onChange={e => setForm(f => ({ ...f, priority: e.target.value }))} />
              <p style={s.fieldNote}>Lower number = tried first among active servers</p>
            </div>

            <div style={s.field}>
              <label style={s.label}>SMTP Server *</label>
              <input style={s.input} value={form.host} onChange={e => setForm(f => ({ ...f, host: e.target.value }))} placeholder="smtp.gmail.com" />
            </div>
            <div style={s.field}>
              <label style={s.label}>SMTP Port *</label>
              <input type="number" style={s.input} value={form.port} onChange={e => setForm(f => ({ ...f, port: e.target.value }))} />
            </div>

            <div style={s.field}>
              <label style={s.label}>Connection Security</label>
              <select style={s.select} value={form.security} onChange={e => handleSecurityChange(e.target.value)}>
                {SECURITY_OPTIONS.map(o => <option key={o.value} value={o.value}>{o.label}</option>)}
              </select>
            </div>
            <div style={s.field}>
              <label style={s.label}>From Email</label>
              <input style={s.input} value={form.from_email} onChange={e => setForm(f => ({ ...f, from_email: e.target.value }))} placeholder="Falls back to Username if blank" />
            </div>

            <div style={s.field}>
              <label style={s.label}>Username</label>
              <input style={s.input} value={form.username} onChange={e => setForm(f => ({ ...f, username: e.target.value }))} />
            </div>
            <div style={s.field}>
              <label style={s.label}>Password</label>
              <input
                type="password" style={s.input} value={form.password}
                onChange={e => setForm(f => ({ ...f, password: e.target.value }))}
                placeholder={editingId ? 'Leave blank to keep the current password' : ''}
                autoComplete="new-password"
              />
            </div>

            <div style={{ ...s.field, gridColumn: '1 / -1' }}>
              <label style={s.checkboxRow}>
                <input type="checkbox" checked={form.active} onChange={e => setForm(f => ({ ...f, active: e.target.checked }))} />
                Active
              </label>
            </div>
          </div>

          {formError && <div style={s.errorBox}>{formError}</div>}
          <TestResultBanner result={testState} />

          <div style={{ display: 'flex', gap: 12, marginTop: 18, flexWrap: 'wrap' }}>
            <button style={{ ...s.testBtn, opacity: testing ? 0.6 : 1 }} disabled={testing} onClick={handleTest}>
              {testing ? 'Testing…' : 'Test Connection'}
            </button>
            <button style={{ ...s.createBtn, opacity: saving ? 0.6 : 1 }} disabled={saving} onClick={handleSave}>
              {saving ? 'Saving…' : editingId ? 'Save Changes' : 'Add Server'}
            </button>
            <button style={s.cancelLink} onClick={closeForm}>Cancel</button>
          </div>
        </div>
      )}

      {/* ── Servers table ─────────────────────────────────────────── */}
      <div style={s.tableWrapper}>
        <table style={s.table}>
          <thead>
            <tr style={s.thead}>
              {['Priority', 'Description', 'SMTP Server', 'Security', 'Status', 'Test', 'Actions'].map(col => (
                <th key={col} style={s.th}>{col}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {loading ? (
              <tr><td colSpan={7} style={{ padding: '50px 0', textAlign: 'center' }}><Spinner /></td></tr>
            ) : servers.length === 0 ? (
              <tr>
                <td colSpan={7} style={{ padding: 0, border: 'none' }}>
                  <div style={{ textAlign: 'center', padding: '50px 20px', color: '#8BA5B8' }}>
                    <div style={{ fontSize: 32, marginBottom: 12 }}>✉️</div>
                    <div style={{ fontSize: 14, fontWeight: 500, color: '#1A2E40', marginBottom: 4 }}>No mail servers configured</div>
                    <div style={{ fontSize: 13 }}>Add one to enable email sending (e.g. password reset codes)</div>
                  </div>
                </td>
              </tr>
            ) : servers.map((srv, i) => {
              const rt = rowTest[srv.id];
              return (
                <tr key={srv.id} style={{ background: i % 2 === 0 ? '#fff' : '#F8FAFB' }}>
                  <td style={s.td}>{srv.priority}</td>
                  <td style={s.td}>{srv.name}</td>
                  <td style={{ ...s.td, ...s.tdMono }}>{srv.host}:{srv.port}</td>
                  <td style={s.td}>{securityLabel(srv.security)}</td>
                  <td style={s.td}>
                    <span style={{ ...s.badge, ...(srv.active ? s.badgeActive : s.badgeInactive) }}>
                      {srv.active ? 'Active' : 'Inactive'}
                    </span>
                  </td>
                  <td style={s.td}>
                    <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
                      <button style={s.iconBtnNeutral} onClick={() => handleRowTest(srv)} disabled={rt?.status === 'running'}>
                        {rt?.status === 'running' ? <Spinner /> : 'Test'}
                      </button>
                      {rt && rt.status !== 'running' && (
                        <span style={{ fontSize: 11, color: rt.status === 'success' ? '#0F6E56' : '#A32D2D', maxWidth: 220 }}>
                          {rt.status === 'success' ? '✓' : '⚠'} {rt.message}
                        </span>
                      )}
                    </div>
                  </td>
                  <td style={s.td}>
                    <div style={{ display: 'flex', gap: 8 }}>
                      <button style={s.iconBtnNeutral} onClick={() => openEdit(srv)}>Edit</button>
                      <button style={s.iconBtn} onClick={() => handleDelete(srv)}>Delete</button>
                    </div>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
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
  testBtn: {
    padding: '10px 20px', borderRadius: 8, border: '0.5px solid #2E6E8E',
    background: '#fff', color: '#2E6E8E', fontSize: 13, fontWeight: 500, cursor: 'pointer',
  },
  cancelLink: { background: 'none', border: 'none', cursor: 'pointer', fontSize: 13, color: '#5A7A8A', textDecoration: 'underline', fontWeight: 500 },

  formPanel: { background: '#fff', border: '0.5px solid #DDE4EA', borderRadius: 12, padding: '20px 24px', marginBottom: 24 },
  formTitle: { margin: '0 0 16px', fontSize: 15, fontWeight: 500, color: '#1A2E40' },
  formGrid:  { display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '14px 20px' },
  field:     { display: 'flex', flexDirection: 'column', gap: 6 },
  label:     { fontSize: 12, fontWeight: 600, color: '#334155' },
  fieldNote: { margin: '2px 0 0', fontSize: 11, color: '#94A3B8' },
  fieldErr:  { fontSize: 11, color: '#DC2626', marginTop: 3, display: 'block' },
  input: {
    height: 36, padding: '0 12px', borderRadius: 8,
    border: '0.5px solid #C5D2DC', fontSize: 13, color: '#1A2E40',
    outline: 'none', width: '100%', boxSizing: 'border-box',
  },
  select: {
    height: 36, padding: '0 12px', borderRadius: 8, border: '0.5px solid #C5D2DC',
    fontSize: 13, color: '#1A2E40', background: '#fff', cursor: 'pointer',
    width: '100%', boxSizing: 'border-box', outline: 'none',
  },
  checkboxRow: { display: 'flex', alignItems: 'center', gap: 8, fontSize: 13, fontWeight: 500, color: '#334155', cursor: 'pointer' },

  errorBox: { background: '#FCEBEB', color: '#A32D2D', borderRadius: 8, padding: '10px 14px', fontSize: 13, marginTop: 14 },

  testBanner:   { marginTop: 14, padding: '10px 14px', borderRadius: 8, fontSize: 13, display: 'flex', alignItems: 'center', gap: 8, background: '#F0F4F8', color: '#334155' },
  testBannerOk: { background: '#E1F5EE', color: '#0F6E56' },
  testBannerFail: { background: '#FCEBEB', color: '#A32D2D' },

  spinner: {
    display: 'inline-block', width: 14, height: 14, borderRadius: '50%',
    border: '2px solid #DDE4EA', borderTopColor: '#2E6E8E', animation: 'mailSpin 0.8s linear infinite',
  },

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
  badgeActive:   { background: '#E1F5EE', color: '#0F6E56', borderColor: '#5DCAA5' },
  badgeInactive: { background: '#F0F4F8', color: '#5A7A8A', borderColor: '#DDE4EA' },

  iconBtn:        { padding: '5px 12px', borderRadius: 6, border: '0.5px solid #DDE4EA', background: '#fff', fontSize: 12, fontWeight: 500, color: '#A32D2D', cursor: 'pointer' },
  iconBtnNeutral: { padding: '5px 12px', borderRadius: 6, border: '0.5px solid #DDE4EA', background: '#fff', fontSize: 12, fontWeight: 500, color: '#2E6E8E', cursor: 'pointer' },
};
