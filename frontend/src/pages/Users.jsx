import React, { useState, useEffect, useCallback } from 'react';
import api from '../services/api';

const ROLE_BADGE = {
  administrator: { bg: '#F3E8FF', color: '#7C3AED', border: '#DDD6FE', label: 'Administrator' },
  hod:           { bg: '#EFF6FF', color: '#2563EB', border: '#BFDBFE', label: 'HOD'           },
  lecturer:      { bg: '#ECFDF5', color: '#059669', border: '#A7F3D0', label: 'Lecturer'      },
};

const STATUS_BADGE = {
  active:   { bg: '#ECFDF5', color: '#059669', border: '#A7F3D0', label: 'Active'   },
  inactive: { bg: '#FEF2F2', color: '#DC2626', border: '#FECACA', label: 'Inactive' },
};

function formatDate(dt) {
  if (!dt) return '—';
  return new Date(dt).toLocaleString('en-AU', {
    day: '2-digit', month: 'short', year: 'numeric',
    hour: '2-digit', minute: '2-digit',
  });
}

function Avatar({ name }) {
  const initials = name
    ? name.split(' ').map(w => w[0]).join('').slice(0, 2).toUpperCase()
    : 'U';
  return (
    <div style={s.avatar}>{initials}</div>
  );
}

function Modal({ title, onClose, children }) {
  return (
    <div style={s.overlay} onClick={e => e.target === e.currentTarget && onClose()}>
      <div style={s.modal}>
        <div style={s.modalHeader}>
          <h2 style={s.modalTitle}>{title}</h2>
          <button onClick={onClose} style={s.closeBtn} aria-label="Close">✕</button>
        </div>
        {children}
      </div>
    </div>
  );
}

const EMPTY_ADD = { name: '', email: '', password: '', role: 'lecturer', department: '' };

export default function Users() {
  const [users, setUsers]         = useState([]);
  const [loading, setLoading]     = useState(true);
  const [fetchError, setFetchError] = useState(null);

  const [showAdd, setShowAdd]     = useState(false);
  const [addForm, setAddForm]     = useState(EMPTY_ADD);
  const [addBusy, setAddBusy]     = useState(false);
  const [addError, setAddError]   = useState(null);

  const [editUser, setEditUser]   = useState(null);
  const [editForm, setEditForm]   = useState({ role: '', department: '' });
  const [editBusy, setEditBusy]   = useState(false);
  const [editError, setEditError] = useState(null);

  const load = useCallback(() => {
    setLoading(true);
    setFetchError(null);
    api.get('/api/v1/users/')
      .then(res => setUsers(res.data))
      .catch(() => setFetchError('Failed to load users. Make sure you are logged in as an Administrator.'))
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => { load(); }, [load]);

  /* ── Add user ─────────────────────────────────────────────────────── */
  const handleAdd = async e => {
    e.preventDefault();
    setAddBusy(true);
    setAddError(null);
    try {
      await api.post('/api/v1/users/', {
        name:       addForm.name,
        email:      addForm.email,
        password:   addForm.password,
        role:       addForm.role,
        department: addForm.department || null,
      });
      setShowAdd(false);
      setAddForm(EMPTY_ADD);
      load();
    } catch (err) {
      const detail = err.response?.data?.detail;
      setAddError(Array.isArray(detail) ? detail.map(d => d.msg).join(', ') : (detail || 'Failed to create user.'));
    } finally {
      setAddBusy(false);
    }
  };

  /* ── Edit user ────────────────────────────────────────────────────── */
  const openEdit = u => {
    setEditUser(u);
    setEditForm({ role: u.role, department: u.department || '' });
    setEditError(null);
  };

  const handleEdit = async e => {
    e.preventDefault();
    setEditBusy(true);
    setEditError(null);
    try {
      await api.patch(`/api/v1/users/${editUser.id}`, {
        role:       editForm.role,
        department: editForm.department || null,
      });
      setEditUser(null);
      load();
    } catch (err) {
      const detail = err.response?.data?.detail;
      setEditError(typeof detail === 'string' ? detail : 'Failed to update user.');
    } finally {
      setEditBusy(false);
    }
  };

  /* ── Deactivate / reactivate ──────────────────────────────────────── */
  const handleDeactivate = async u => {
    if (!window.confirm(`Deactivate ${u.name}?\nThey will no longer be able to log in.`)) return;
    try {
      await api.delete(`/api/v1/users/${u.id}`);
      load();
    } catch (err) {
      alert(err.response?.data?.detail || 'Failed to deactivate user.');
    }
  };

  const handleReactivate = async u => {
    try {
      await api.patch(`/api/v1/users/${u.id}`, { is_active: true });
      load();
    } catch (err) {
      alert(err.response?.data?.detail || 'Failed to reactivate user.');
    }
  };

  /* ── Render ───────────────────────────────────────────────────────── */
  return (
    <div>
      {/* Header */}
      <div style={s.topRow}>
        <div>
          <h1 style={s.pageTitle}>Users</h1>
          <p style={s.pageSubtitle}>Manage accounts, roles, and access — Administrator only</p>
        </div>
        <button onClick={() => { setShowAdd(true); setAddError(null); }} style={s.addBtn}>
          <IconPlus /> Add User
        </button>
      </div>

      {/* Table */}
      <div style={s.card}>
        <div style={s.tableWrapper}>
          <table style={s.table}>
            <thead>
              <tr>
                {['User', 'Email', 'Role', 'Department', 'Last Login', 'Status', 'Actions'].map(col => (
                  <th key={col} style={s.th}>{col}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {loading ? (
                <tr><td colSpan={7} style={s.emptyCell}>Loading…</td></tr>
              ) : fetchError ? (
                <tr><td colSpan={7} style={{ ...s.emptyCell, color: '#DC2626' }}>{fetchError}</td></tr>
              ) : users.length === 0 ? (
                <tr><td colSpan={7} style={s.emptyCell}>No users found.</td></tr>
              ) : users.map((u, i) => {
                const rb = ROLE_BADGE[u.role] || ROLE_BADGE.lecturer;
                const sb = u.is_active ? STATUS_BADGE.active : STATUS_BADGE.inactive;
                return (
                  <tr key={u.id} style={i % 2 === 0 ? s.trEven : s.trOdd}>
                    <td style={s.td}>
                      <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                        <Avatar name={u.name} />
                        <span style={{ fontWeight: 600, color: '#1E293B' }}>{u.name}</span>
                      </div>
                    </td>
                    <td style={{ ...s.td, ...s.tdMono }}>{u.email}</td>
                    <td style={s.td}>
                      <span style={{ ...s.badge, background: rb.bg, color: rb.color, borderColor: rb.border }}>
                        {rb.label}
                      </span>
                    </td>
                    <td style={{ ...s.td, color: '#64748B' }}>{u.department || '—'}</td>
                    <td style={{ ...s.td, ...s.tdMono, whiteSpace: 'nowrap' }}>{formatDate(u.last_login_at)}</td>
                    <td style={s.td}>
                      <span style={{ ...s.badge, background: sb.bg, color: sb.color, borderColor: sb.border }}>
                        {sb.label}
                      </span>
                    </td>
                    <td style={s.td}>
                      <div style={{ display: 'flex', gap: 6 }}>
                        <button onClick={() => openEdit(u)} style={s.actionBtn}>Edit</button>
                        {u.is_active
                          ? <button onClick={() => handleDeactivate(u)} style={{ ...s.actionBtn, color: '#DC2626', borderColor: '#FECACA' }}>Deactivate</button>
                          : <button onClick={() => handleReactivate(u)} style={{ ...s.actionBtn, color: '#059669', borderColor: '#A7F3D0' }}>Reactivate</button>
                        }
                      </div>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
        <div style={s.footer}>
          {!loading && !fetchError && <>{users.length} user{users.length !== 1 ? 's' : ''} total</>}
        </div>
      </div>

      {/* ── Add User Modal ─────────────────────────────────────────────── */}
      {showAdd && (
        <Modal title="Add New User" onClose={() => { setShowAdd(false); setAddError(null); }}>
          <form onSubmit={handleAdd}>
            {addError && <div style={s.formError}>{addError}</div>}
            <div style={s.formGrid}>
              <FormField label="Full Name">
                <input required style={s.input} value={addForm.name}
                  onChange={e => setAddForm(f => ({ ...f, name: e.target.value }))}
                  placeholder="Jane Smith" />
              </FormField>
              <FormField label="Email">
                <input required type="email" style={s.input} value={addForm.email}
                  onChange={e => setAddForm(f => ({ ...f, email: e.target.value }))}
                  placeholder="jane@koi.edu.au" />
              </FormField>
              <FormField label="Temporary Password">
                <input required type="password" style={s.input} value={addForm.password}
                  onChange={e => setAddForm(f => ({ ...f, password: e.target.value }))}
                  placeholder="Min. 8 characters" />
              </FormField>
              <FormField label="Role">
                <select style={s.input} value={addForm.role}
                  onChange={e => setAddForm(f => ({ ...f, role: e.target.value }))}>
                  <option value="lecturer">Lecturer</option>
                  <option value="hod">HOD</option>
                  <option value="administrator">Administrator</option>
                </select>
              </FormField>
              <FormField label="Department (optional)">
                <input style={s.input} value={addForm.department}
                  onChange={e => setAddForm(f => ({ ...f, department: e.target.value }))}
                  placeholder="e.g. Information Technology" />
              </FormField>
            </div>
            <div style={s.modalFooter}>
              <button type="button" onClick={() => { setShowAdd(false); setAddError(null); }} style={s.cancelBtn}>Cancel</button>
              <button type="submit" style={s.submitBtn} disabled={addBusy}>
                {addBusy ? 'Creating…' : 'Create User'}
              </button>
            </div>
          </form>
        </Modal>
      )}

      {/* ── Edit User Modal ────────────────────────────────────────────── */}
      {editUser && (
        <Modal title={`Edit — ${editUser.name}`} onClose={() => setEditUser(null)}>
          <form onSubmit={handleEdit}>
            {editError && <div style={s.formError}>{editError}</div>}
            <div style={s.formGrid}>
              <FormField label="Role">
                <select style={s.input} value={editForm.role}
                  onChange={e => setEditForm(f => ({ ...f, role: e.target.value }))}>
                  <option value="lecturer">Lecturer</option>
                  <option value="hod">HOD</option>
                  <option value="administrator">Administrator</option>
                </select>
              </FormField>
              <FormField label="Department">
                <input style={s.input} value={editForm.department}
                  onChange={e => setEditForm(f => ({ ...f, department: e.target.value }))}
                  placeholder="e.g. Information Technology" />
              </FormField>
            </div>
            <div style={s.modalFooter}>
              <button type="button" onClick={() => setEditUser(null)} style={s.cancelBtn}>Cancel</button>
              <button type="submit" style={s.submitBtn} disabled={editBusy}>
                {editBusy ? 'Saving…' : 'Save Changes'}
              </button>
            </div>
          </form>
        </Modal>
      )}
    </div>
  );
}

function FormField({ label, children }) {
  return (
    <label style={{ display: 'flex', flexDirection: 'column', gap: 6, fontSize: 13, fontWeight: 600, color: '#374151' }}>
      {label}
      {children}
    </label>
  );
}

function IconPlus() {
  return (
    <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor"
      strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" style={{ marginRight: 7 }}>
      <line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/>
    </svg>
  );
}

const s = {
  topRow:       { display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 28 },
  pageTitle:    { margin: '0 0 6px', fontSize: 26, fontWeight: 700, color: '#1E293B' },
  pageSubtitle: { margin: 0, fontSize: 14, color: '#64748B' },

  addBtn: {
    display: 'flex', alignItems: 'center',
    background: '#2E6E8E', color: '#fff',
    border: 'none', borderRadius: 8,
    padding: '10px 20px', fontSize: 14, fontWeight: 600,
    cursor: 'pointer', whiteSpace: 'nowrap', alignSelf: 'center',
  },

  card:         { background: '#fff', border: '0.5px solid #DDE4EA', borderRadius: 10, overflow: 'hidden' },
  tableWrapper: { overflowX: 'auto' },
  table:        { width: '100%', borderCollapse: 'collapse', fontSize: 13 },
  th: {
    padding: '12px 16px', textAlign: 'left',
    fontSize: 11, fontWeight: 700, color: '#94A3B8',
    textTransform: 'uppercase', letterSpacing: 0.6,
    background: '#F8FAFC', borderBottom: '1px solid #E2E8F0', whiteSpace: 'nowrap',
  },
  trEven:   { background: '#fff' },
  trOdd:    { background: '#F8FAFC' },
  td:       { padding: '12px 16px', color: '#334155', borderBottom: '1px solid #F1F5F9', verticalAlign: 'middle' },
  tdMono:   { fontFamily: "'SF Mono','Fira Code',monospace", fontSize: 12, color: '#475569' },
  emptyCell: { padding: '40px 16px', textAlign: 'center', color: '#94A3B8', fontStyle: 'italic' },

  avatar: {
    width: 32, height: 32, borderRadius: '50%', flexShrink: 0,
    background: 'linear-gradient(135deg, #2E6E8E, #4f8ef7)',
    display: 'flex', alignItems: 'center', justifyContent: 'center',
    fontSize: 12, fontWeight: 700, color: '#fff',
  },

  badge: {
    display: 'inline-block', padding: '3px 10px',
    borderRadius: 12, border: '1px solid',
    fontSize: 12, fontWeight: 600, letterSpacing: 0.3,
  },

  footer: {
    padding: '12px 20px', borderTop: '1px solid #E2E8F0',
    fontSize: 13, color: '#64748B', background: '#F8FAFC',
  },

  actionBtn: {
    padding: '5px 12px', border: '1px solid #E2E8F0',
    borderRadius: 6, background: '#fff', fontSize: 12,
    fontWeight: 500, cursor: 'pointer', color: '#334155',
  },

  overlay: {
    position: 'fixed', inset: 0,
    background: 'rgba(15,23,42,0.45)', backdropFilter: 'blur(3px)',
    display: 'flex', alignItems: 'center', justifyContent: 'center',
    zIndex: 1000,
  },
  modal: {
    background: '#fff', borderRadius: 14,
    boxShadow: '0 24px 60px rgba(0,0,0,0.2)',
    width: '100%', maxWidth: 460,
    padding: '28px 32px', boxSizing: 'border-box',
    margin: '0 16px',
  },
  modalHeader: {
    display: 'flex', justifyContent: 'space-between',
    alignItems: 'center', marginBottom: 24,
  },
  modalTitle: { margin: 0, fontSize: 18, fontWeight: 700, color: '#1E293B' },
  closeBtn: {
    background: 'none', border: 'none', fontSize: 18,
    cursor: 'pointer', color: '#94A3B8', padding: '2px 6px',
    borderRadius: 6, lineHeight: 1,
  },

  formGrid:  { display: 'flex', flexDirection: 'column', gap: 16 },
  input: {
    marginTop: 2, padding: '9px 12px',
    border: '1px solid #DDE4EA', borderRadius: 7,
    fontSize: 14, color: '#1E293B', outline: 'none',
    width: '100%', boxSizing: 'border-box',
    fontFamily: 'inherit',
  },
  formError: {
    background: '#FEF2F2', border: '1px solid #FECACA',
    borderRadius: 7, padding: '10px 14px',
    color: '#DC2626', fontSize: 13, marginBottom: 16,
  },
  modalFooter: { display: 'flex', justifyContent: 'flex-end', gap: 10, marginTop: 28 },
  cancelBtn: {
    padding: '9px 20px', border: '1px solid #DDE4EA',
    borderRadius: 7, background: '#fff', fontSize: 14,
    fontWeight: 500, cursor: 'pointer', color: '#64748B',
  },
  submitBtn: {
    padding: '9px 24px', border: 'none',
    borderRadius: 7, background: '#2E6E8E', color: '#fff',
    fontSize: 14, fontWeight: 600, cursor: 'pointer',
  },
};
