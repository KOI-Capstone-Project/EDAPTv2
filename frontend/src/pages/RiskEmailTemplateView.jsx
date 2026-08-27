// Risk Email Templates: a list of named templates for the "Log as emailed"
// bulk action on the Students at Risk page, which lets staff pick which one
// to use from a dropdown. Admin only (Head of Technology / Head of School),
// matching the backend's require_head_of_school gate on create/update/
// delete. This system has no real student email address on file anywhere
// (see RiskEmailTemplate's backend docstring), so nothing is ever sent from
// here — staff copy the rendered wording into the real email they send
// themselves, then use the bulk action to record that it happened.
import { useState, useEffect, useCallback } from 'react';
import api from '../services/api';
import { getErrorMessage } from '../utils/apiError';
import RichTextEditor from '../components/RichTextEditor';

const EMPTY_FORM = { name: '', subject: '', body: '' };

function Spinner() {
  return <span style={s.spinner} />;
}

export default function RiskEmailTemplateView() {
  const [templates, setTemplates] = useState([]);
  const [loading,   setLoading]   = useState(true);

  const [showForm,  setShowForm]  = useState(false);
  const [editingId, setEditingId] = useState(null); // null = creating new
  const [form,       setForm]      = useState(EMPTY_FORM);
  const [saving,      setSaving]      = useState(false);
  const [formError,   setFormError]   = useState(null);

  const fetchTemplates = useCallback(() => {
    setLoading(true);
    api.get('/api/risk-email-templates')
      .then(r => setTemplates(r.data.templates || []))
      .catch(() => setTemplates([]))
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => { fetchTemplates(); }, [fetchTemplates]);

  const openCreate = () => {
    setEditingId(null);
    setForm(EMPTY_FORM);
    setFormError(null);
    setShowForm(true);
  };

  const openEdit = (tpl) => {
    setEditingId(tpl.id);
    setForm({ name: tpl.name, subject: tpl.subject, body: tpl.body });
    setFormError(null);
    setShowForm(true);
  };

  const closeForm = () => setShowForm(false);

  const handleSave = async () => {
    if (!form.name.trim() || !form.subject.trim() || !form.body.trim()) {
      setFormError('Name, subject, and body are all required.');
      return;
    }
    setSaving(true);
    setFormError(null);
    try {
      const payload = { name: form.name.trim(), subject: form.subject, body: form.body };
      if (editingId) await api.put(`/api/risk-email-templates/${editingId}`, payload);
      else           await api.post('/api/risk-email-templates', payload);
      closeForm();
      fetchTemplates();
    } catch (err) {
      setFormError(getErrorMessage(err, 'Failed to save this template.'));
    } finally {
      setSaving(false);
    }
  };

  const handleDelete = async (tpl) => {
    if (!window.confirm(`Delete "${tpl.name}"? This can't be undone.`)) return;
    try {
      await api.delete(`/api/risk-email-templates/${tpl.id}`);
      fetchTemplates();
    } catch (err) {
      alert(getErrorMessage(err, 'Failed to delete this template.'));
    }
  };

  return (
    <div>
      <style>{`@keyframes riskTplSpin { to { transform: rotate(360deg); } }`}</style>

      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 24, flexWrap: 'wrap', gap: 12 }}>
        <div>
          <h1 style={s.pageTitle}>Risk Email Templates</h1>
          <p style={s.pageSub}>Reference wording for the "Log as emailed" action on Students at Risk</p>
        </div>
        <button style={s.createBtn} onClick={showForm && editingId === null ? closeForm : openCreate}>
          {showForm && editingId === null ? '✕ Cancel' : '+ New Template'}
        </button>
      </div>

      <p style={s.muted}>
        This system has no real student email address on file, so nothing is sent automatically —
        staff copy the rendered wording into the real email they send themselves, then use the bulk
        action on Students at Risk to record that it happened. Every saved template here shows up as
        a choice in that page's template dropdown.
      </p>

      {/* ── Create / edit form ─────────────────────────────────────── */}
      {showForm && (
        <div style={s.formPanel}>
          <h3 style={s.formTitle}>{editingId ? 'Edit Template' : 'New Template'}</h3>

          <div style={s.formField}>
            <label style={s.label}>Name *</label>
            <input
              style={s.input} value={form.name}
              onChange={e => setForm(f => ({ ...f, name: e.target.value }))}
              placeholder="e.g. First Notice, Final Warning"
            />
          </div>

          <div style={{ ...s.formField, marginTop: 14 }}>
            <label style={s.label}>Subject *</label>
            <input
              style={s.input} value={form.subject}
              onChange={e => setForm(f => ({ ...f, subject: e.target.value }))}
            />
          </div>

          <div style={{ ...s.formField, marginTop: 14 }}>
            <label style={s.label}>Body *</label>
            <RichTextEditor
              value={form.body}
              onChange={html => setForm(f => ({ ...f, body: html }))}
            />
          </div>

          <p style={s.fieldNote}>
            Placeholders: <code>{'{{student_id}}'}</code>{' '}
            <code>{'{{subject_code}}'}</code>{' '}
            <code>{'{{study_period}}'}</code>{' '}
            <code>{'{{risk_band}}'}</code>
          </p>

          {formError && <div style={s.errorBox}>{formError}</div>}

          <div style={{ display: 'flex', gap: 12, marginTop: 18 }}>
            <button style={{ ...s.createBtn, opacity: saving ? 0.6 : 1 }} disabled={saving} onClick={handleSave}>
              {saving ? 'Saving…' : editingId ? 'Save Changes' : 'Add Template'}
            </button>
            <button style={s.cancelLink} onClick={closeForm}>Cancel</button>
          </div>
        </div>
      )}

      {/* ── Templates table ─────────────────────────────────────────── */}
      <div style={s.tableWrapper}>
        <table style={s.table}>
          <thead>
            <tr style={s.thead}>
              {['Name', 'Subject', 'Updated By', 'Updated', 'Actions'].map(col => (
                <th key={col} style={s.th}>{col}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {loading ? (
              <tr><td colSpan={5} style={{ padding: '50px 0', textAlign: 'center' }}><Spinner /></td></tr>
            ) : templates.length === 0 ? (
              <tr>
                <td colSpan={5} style={{ padding: 0, border: 'none' }}>
                  <div style={{ textAlign: 'center', padding: '50px 20px', color: '#8BA5B8' }}>
                    <div style={{ fontSize: 32, marginBottom: 12 }}>✉️</div>
                    <div style={{ fontSize: 14, fontWeight: 500, color: '#1A2E40', marginBottom: 4 }}>No templates yet</div>
                    <div style={{ fontSize: 13 }}>Add one so Students at Risk has something to offer in its dropdown</div>
                  </div>
                </td>
              </tr>
            ) : templates.map((tpl, i) => (
              <tr key={tpl.id} style={{ background: i % 2 === 0 ? '#fff' : '#F8FAFB' }}>
                <td style={s.td}>{tpl.name}</td>
                <td style={{ ...s.td, maxWidth: 320, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{tpl.subject}</td>
                <td style={s.td}>{tpl.updated_by || '—'}</td>
                <td style={s.td}>{tpl.updated_at ? new Date(tpl.updated_at).toLocaleString() : '—'}</td>
                <td style={s.td}>
                  <div style={{ display: 'flex', gap: 8 }}>
                    <button style={s.iconBtnNeutral} onClick={() => openEdit(tpl)}>Edit</button>
                    <button style={s.iconBtn} onClick={() => handleDelete(tpl)}>Delete</button>
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

const s = {
  pageTitle: { margin: '0 0 4px', fontSize: 24, fontWeight: 500, color: '#1A2E40' },
  pageSub:   { margin: 0, fontSize: 13, color: '#5A7A8A' },
  muted:     { margin: '0 0 20px', fontSize: 12, color: '#94A3B8' },

  createBtn: {
    padding: '10px 20px', borderRadius: 8, border: 'none',
    background: '#2E6E8E', color: '#fff', fontSize: 13, fontWeight: 500, cursor: 'pointer',
  },
  cancelLink: { background: 'none', border: 'none', cursor: 'pointer', fontSize: 13, color: '#5A7A8A', textDecoration: 'underline', fontWeight: 500 },

  formPanel: { background: '#fff', border: '0.5px solid #DDE4EA', borderRadius: 12, padding: '20px 24px', marginBottom: 24 },
  formTitle: { margin: '0 0 16px', fontSize: 15, fontWeight: 500, color: '#1A2E40' },
  formField: { display: 'flex', flexDirection: 'column', gap: 6 },
  label:     { fontSize: 12, fontWeight: 600, color: '#334155' },
  input: {
    padding: '10px 14px', borderRadius: 8,
    border: '0.5px solid #C5D2DC', fontSize: 13, color: '#1E293B',
    outline: 'none', width: '100%', boxSizing: 'border-box',
  },
  fieldNote: { margin: '6px 0 0', fontSize: 11, color: '#94A3B8' },

  errorBox: { background: '#FCEBEB', color: '#A32D2D', borderRadius: 8, padding: '10px 14px', fontSize: 13, marginTop: 14 },

  spinner: {
    display: 'inline-block', width: 14, height: 14, borderRadius: '50%',
    border: '2px solid #DDE4EA', borderTopColor: '#2E6E8E', animation: 'riskTplSpin 0.8s linear infinite',
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
  td: { padding: '12px 16px', color: '#1A2E40', borderBottom: '0.5px solid #F0F4F8', verticalAlign: 'middle' },

  iconBtn:        { padding: '5px 12px', borderRadius: 6, border: '0.5px solid #DDE4EA', background: '#fff', fontSize: 12, fontWeight: 500, color: '#A32D2D', cursor: 'pointer' },
  iconBtnNeutral: { padding: '5px 12px', borderRadius: 6, border: '0.5px solid #DDE4EA', background: '#fff', fontSize: 12, fontWeight: 500, color: '#2E6E8E', cursor: 'pointer' },
};
