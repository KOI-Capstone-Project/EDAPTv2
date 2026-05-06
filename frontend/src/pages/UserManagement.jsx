import { useState, useEffect, useRef } from 'react';
import api from '../services/api';

// ── Helpers ───────────────────────────────────────────────────────────────────

const genPassword = () => {
  const chars = 'ABCDEFGHJKMNPQRSTUVWXYZabcdefghjkmnpqrstuvwxyz23456789!@#$';
  return Array.from({ length: 8 }, () => chars[Math.floor(Math.random() * chars.length)]).join('');
};

function Spinner() {
  return (
    <tr>
      <td colSpan={5} style={{ padding: 0, border: 'none' }}>
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', height: 200 }}>
          <div style={{ width: 32, height: 32, border: '3px solid #F0F4F8', borderTop: '3px solid #2E6E8E', borderRadius: '50%', animation: 'spin 0.8s linear infinite' }} />
        </div>
      </td>
    </tr>
  );
}

// ── Multi-select for subjects ─────────────────────────────────────────────────

function SubjectMultiSelect({ value, onChange, allSubjects, placeholder }) {
  const [open, setOpen] = useState(false);
  const [q, setQ]       = useState('');
  const ref             = useRef(null);

  useEffect(() => {
    const h = e => { if (ref.current && !ref.current.contains(e.target)) setOpen(false); };
    document.addEventListener('mousedown', h);
    return () => document.removeEventListener('mousedown', h);
  }, []);

  const toggle = subj =>
    onChange(value.includes(subj) ? value.filter(s => s !== subj) : [...value, subj]);

  const filtered = q
    ? allSubjects.filter(s => s.toLowerCase().includes(q.toLowerCase()))
    : allSubjects;

  return (
    <div ref={ref} style={{ position: 'relative' }}>
      <div style={s.msBox} onClick={() => setOpen(o => !o)}>
        <span style={{ fontSize: 13, color: value.length ? '#1A2E40' : '#8BA5B8' }}>
          {value.length ? `${value.length} subject${value.length !== 1 ? 's' : ''} selected` : (placeholder || 'Select subjects…')}
        </span>
        <span style={{ color: '#5A7A8A', fontSize: 11 }}>▾</span>
      </div>
      {open && (
        <div style={s.msDrop}>
          <input
            style={s.msSearch}
            placeholder="Search subjects…"
            value={q}
            onChange={e => setQ(e.target.value)}
            autoFocus
            onClick={e => e.stopPropagation()}
          />
          <div style={{ maxHeight: 200, overflowY: 'auto' }}>
            {filtered.map(subj => (
              <label key={subj} style={s.msItem}>
                <input type="checkbox" checked={value.includes(subj)} onChange={() => toggle(subj)} style={{ marginRight: 8 }} />
                {subj}
              </label>
            ))}
          </div>
        </div>
      )}
      {value.length > 0 && (
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: 4, marginTop: 6 }}>
          {value.map(subj => (
            <span key={subj} style={s.chip}>
              {subj}
              <button onClick={() => toggle(subj)} style={s.chipX}>×</button>
            </span>
          ))}
        </div>
      )}
    </div>
  );
}

// ── Main component ────────────────────────────────────────────────────────────

export default function UserManagement() {
  const [users,        setUsers]        = useState([]);
  const [allSubjects,  setAllSubjects]  = useState([]);
  const [loading,      setLoading]      = useState(true);
  const [editingEmail, setEditingEmail] = useState(null);
  const [editSubjects, setEditSubjects] = useState([]);
  const [editSaving,   setEditSaving]   = useState(false);
  const [editMsg,      setEditMsg]      = useState('');
  const [showCreate,   setShowCreate]   = useState(false);
  const [createMsg,    setCreateMsg]    = useState('');
  const [createErr,    setCreateErr]    = useState('');
  const [creating,     setCreating]     = useState(false);

  const [form, setForm]     = useState({ name: '', email: '', password: '', subjects: [] });
  const [showPwd, setShowPwd] = useState(false);

  useEffect(() => {
    api.get('/api/subjects/list').then(r => setAllSubjects(r.data)).catch(() => {});
    fetchUsers();
  }, []);

  const fetchUsers = () => {
    setLoading(true);
    api.get('/api/users')
      .then(r => setUsers(Array.isArray(r.data) ? r.data : []))
      .catch(() => setUsers([]))
      .finally(() => setLoading(false));
  };

  const startEdit = user => { setEditingEmail(user.email); setEditSubjects([...(user.subjects || [])]); setEditMsg(''); };
  const cancelEdit = () => { setEditingEmail(null); setEditMsg(''); };

  const saveEdit = async () => {
    setEditSaving(true);
    try {
      await api.put(`/api/users/${encodeURIComponent(editingEmail)}`, { subjects: editSubjects });
      setUsers(prev => prev.map(u => u.email === editingEmail ? { ...u, subjects: editSubjects } : u));
      setEditMsg('Subjects updated successfully');
      setTimeout(() => { setEditingEmail(null); setEditMsg(''); }, 1500);
    } catch (err) {
      setEditMsg(err.response?.data?.detail || 'Failed to save.');
    } finally {
      setEditSaving(false);
    }
  };

  const toggleActive = async user => {
    try {
      await api.put(`/api/users/${encodeURIComponent(user.email)}`, { active: !user.active });
      setUsers(prev => prev.map(u => u.email === user.email ? { ...u, active: !u.active } : u));
    } catch (err) {
      alert(err.response?.data?.detail || 'Failed to update status.');
    }
  };

  const handleCreate = async () => {
    setCreateErr('');
    if (!form.name.trim())        return setCreateErr('Full name is required.');
    if (!form.email.trim())       return setCreateErr('Email is required.');
    if (form.password.length < 6) return setCreateErr('Password must be at least 6 characters.');
    if (!form.subjects.length)    return setCreateErr('At least one subject must be selected.');

    setCreating(true);
    try {
      const res = await api.post('/api/users', {
        name: form.name.trim(), email: form.email.trim(),
        password: form.password, subjects: form.subjects,
      });
      setUsers(prev => [res.data.user, ...prev]);
      setCreateMsg(`Account created. ${form.name.trim()} can now log in.`);
      setForm({ name: '', email: '', password: '', subjects: [] });
      setTimeout(() => { setShowCreate(false); setCreateMsg(''); }, 3000);
    } catch (err) {
      setCreateErr(err.response?.data?.detail || 'Failed to create account.');
    } finally {
      setCreating(false);
    }
  };

  const SubjectChips = ({ subjects }) => {
    const visible = subjects.slice(0, 3);
    const extra   = subjects.length - 3;
    return (
      <div style={{ display: 'flex', flexWrap: 'wrap', gap: 4 }}>
        {visible.map(sub => <span key={sub} style={s_chip}>{sub}</span>)}
        {extra > 0 && <span style={{ ...s_chip, background: '#F0F4F8', color: '#5A7A8A' }}>+{extra} more</span>}
      </div>
    );
  };

  return (
    <div>
      {/* ── Header ──────────────────────────────────────────────────── */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 24 }}>
        <div>
          <h1 style={s.pageTitle}>User Management</h1>
          <p style={s.pageSub}>Create and manage lecturer accounts</p>
        </div>
        <button style={s.createBtn} onClick={() => { setShowCreate(o => !o); setCreateErr(''); setCreateMsg(''); }}>
          {showCreate ? '✕ Cancel' : '+ Create New Lecturer'}
        </button>
      </div>

      {/* ── Create form ─────────────────────────────────────────────── */}
      {showCreate && (
        <div style={s.createPanel}>
          <h3 style={{ margin: '0 0 16px', fontSize: 15, fontWeight: 500, color: '#1A2E40' }}>New Lecturer Account</h3>

          <div style={s.formGrid}>
            <div style={s.formField}>
              <label style={s.label}>Full Name *</label>
              <input style={s.input} value={form.name} onChange={e => setForm(f => ({ ...f, name: e.target.value }))} placeholder="Dr. Jane Smith" />
            </div>
            <div style={s.formField}>
              <label style={s.label}>Email / Staff ID *</label>
              <input style={s.input} value={form.email} onChange={e => setForm(f => ({ ...f, email: e.target.value }))} placeholder="jane.smith" />
            </div>
            <div style={s.formField}>
              <label style={s.label}>Temporary Password *</label>
              <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
                <div style={{ position: 'relative', flex: 1 }}>
                  <input
                    type={showPwd ? 'text' : 'password'}
                    style={{ ...s.input, paddingRight: 40 }}
                    value={form.password}
                    onChange={e => setForm(f => ({ ...f, password: e.target.value }))}
                    placeholder="Min 6 characters"
                  />
                  <button type="button" onClick={() => setShowPwd(v => !v)}
                    style={{ position: 'absolute', right: 10, top: '50%', transform: 'translateY(-50%)', background: 'none', border: 'none', cursor: 'pointer', fontSize: 14 }}>
                    {showPwd ? '🙈' : '👁'}
                  </button>
                </div>
                <button style={s.autoGenBtn} onClick={() => setForm(f => ({ ...f, password: genPassword() }))}>
                  Auto-generate
                </button>
              </div>
            </div>
          </div>

          <div style={{ marginTop: 16 }}>
            <label style={s.label}>Assigned Subjects * <span style={{ color: '#8BA5B8', fontWeight: 400 }}>(required)</span></label>
            <SubjectMultiSelect
              value={form.subjects}
              onChange={v => setForm(f => ({ ...f, subjects: v }))}
              allSubjects={allSubjects}
              placeholder="Select subjects…"
            />
          </div>

          {createErr && <div style={s.errMsg}>{createErr}</div>}
          {createMsg && <div style={s.successMsg}>{createMsg}</div>}

          <div style={{ display: 'flex', gap: 12, marginTop: 16 }}>
            <button style={{ ...s.createBtn, opacity: creating ? 0.6 : 1 }} disabled={creating} onClick={handleCreate}>
              {creating ? 'Creating…' : 'Create Account'}
            </button>
            <button style={s.cancelLink} onClick={() => { setShowCreate(false); setCreateErr(''); setCreateMsg(''); }}>Cancel</button>
          </div>
        </div>
      )}

      {/* ── Users table ─────────────────────────────────────────────── */}
      <div style={s.tableWrapper}>
        <table style={s.table}>
          <thead>
            <tr style={s.thead}>
              <th style={s.th}>Name</th>
              <th style={s.th}>Email</th>
              <th style={s.th}>Subjects</th>
              <th style={s.th}>Status</th>
              <th style={s.th}>Actions</th>
            </tr>
          </thead>
          <tbody>
            {loading ? (
              <Spinner />
            ) : users.length === 0 ? (
              <tr>
                <td colSpan={5} style={{ padding: 0, border: 'none' }}>
                  <div style={{ textAlign: 'center', padding: '60px 20px', color: '#8BA5B8' }}>
                    <div style={{ fontSize: 32, marginBottom: 12 }}>📭</div>
                    <div style={{ fontSize: 14, fontWeight: 500, color: '#1A2E40', marginBottom: 4 }}>No lecturer accounts found</div>
                    <div style={{ fontSize: 13 }}>Create a new account to get started</div>
                  </div>
                </td>
              </tr>
            ) : users.map((user, i) => (
              <>
                <tr key={user.email} style={{ background: editingEmail === user.email ? '#EFF6FF' : (i % 2 === 0 ? '#fff' : '#F8FAFB') }}>
                  <td style={s.td}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                      <div style={s.avatar}>{user.name?.split(' ').map(w => w[0]).join('').slice(0,2).toUpperCase()}</div>
                      <span style={{ fontWeight: 500 }}>{user.name}</span>
                    </div>
                  </td>
                  <td style={{ ...s.td, color: '#5A7A8A', fontSize: 12, fontFamily: 'monospace' }}>{user.email}</td>
                  <td style={s.td}>
                    <SubjectChips subjects={user.subjects || []} />
                  </td>
                  <td style={s.td}>
                    <span style={{
                      background: user.active !== false ? '#E1F5EE' : '#FCEBEB',
                      color:      user.active !== false ? '#0F6E56' : '#A32D2D',
                      borderRadius: 20, padding: '3px 10px', fontSize: 12, fontWeight: 500,
                    }}>
                      {user.active !== false ? 'Active' : 'Inactive'}
                    </span>
                  </td>
                  <td style={s.td}>
                    <div style={{ display: 'flex', gap: 8 }}>
                      <button style={s.iconBtn} title="Edit subjects" onClick={() => editingEmail === user.email ? cancelEdit() : startEdit(user)}>
                        ✏️
                      </button>
                      <button
                        style={{ ...s.iconBtn, background: user.active !== false ? '#FAEEDA' : '#E1F5EE' }}
                        title={user.active !== false ? 'Deactivate' : 'Activate'}
                        onClick={() => toggleActive(user)}
                      >
                        {user.active !== false ? '🔒' : '✅'}
                      </button>
                    </div>
                  </td>
                </tr>

                {editingEmail === user.email && (
                  <tr key={`edit-${user.email}`}>
                    <td colSpan={5} style={{ padding: '12px 20px', background: '#EFF6FF', borderBottom: '0.5px solid #DDE4EA' }}>
                      <div style={{ maxWidth: 520 }}>
                        <p style={{ margin: '0 0 8px', fontSize: 13, fontWeight: 500, color: '#1A2E40' }}>Edit Subjects for {user.name}</p>
                        <SubjectMultiSelect value={editSubjects} onChange={setEditSubjects} allSubjects={allSubjects} />
                        {editMsg && (
                          <div style={{
                            marginTop: 8, fontSize: 12, fontWeight: 500,
                            color: editMsg.includes('success') ? '#0F6E56' : '#A32D2D',
                          }}>
                            {editMsg}
                          </div>
                        )}
                        <div style={{ display: 'flex', gap: 10, marginTop: 12 }}>
                          <button style={{ ...s.createBtn, fontSize: 12, padding: '7px 16px', opacity: editSaving ? 0.6 : 1 }} disabled={editSaving} onClick={saveEdit}>
                            {editSaving ? 'Saving…' : 'Save Changes'}
                          </button>
                          <button style={s.cancelLink} onClick={cancelEdit}>Cancel</button>
                        </div>
                      </div>
                    </td>
                  </tr>
                )}
              </>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

// ── Styles ────────────────────────────────────────────────────────────────────

const s_chip = {
  background: '#E6F1FB', color: '#185FA5',
  borderRadius: 20, padding: '3px 10px', fontSize: 12, fontWeight: 500,
};

const s = {
  pageTitle: { margin: '0 0 4px', fontSize: 24, fontWeight: 500, color: '#1A2E40' },
  pageSub:   { margin: 0, fontSize: 13, color: '#5A7A8A' },

  createBtn: {
    padding: '10px 20px', borderRadius: 8, border: 'none',
    background: '#2E6E8E', color: '#fff', fontSize: 13, fontWeight: 500, cursor: 'pointer',
  },
  cancelLink: { background: 'none', border: 'none', cursor: 'pointer', fontSize: 13, color: '#5A7A8A', textDecoration: 'underline', fontWeight: 500 },

  createPanel: { background: '#fff', border: '0.5px solid #DDE4EA', borderRadius: 12, padding: '20px 24px', marginBottom: 24 },
  formGrid:    { display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 16 },
  formField:   { display: 'flex', flexDirection: 'column', gap: 6 },
  label:       { fontSize: 12, fontWeight: 600, color: '#334155' },
  input: {
    height: 36, padding: '0 12px', borderRadius: 8,
    border: '0.5px solid #C5D2DC', fontSize: 13, color: '#1A2E40',
    outline: 'none', width: '100%', boxSizing: 'border-box',
  },
  autoGenBtn: {
    padding: '0 12px', height: 36, borderRadius: 8,
    border: '0.5px solid #2E6E8E', background: '#fff', color: '#2E6E8E',
    fontSize: 12, fontWeight: 500, cursor: 'pointer', whiteSpace: 'nowrap',
  },

  errMsg:     { background: '#FCEBEB', border: '0.5px solid #F09595', color: '#A32D2D', borderRadius: 8, padding: '10px 16px', fontSize: 13, marginTop: 12 },
  successMsg: { background: '#E1F5EE', border: '0.5px solid #5DCAA5', color: '#0F6E56', borderRadius: 8, padding: '10px 16px', fontSize: 13, marginTop: 12 },

  msBox:    { display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '0 12px', height: 36, border: '0.5px solid #C5D2DC', borderRadius: 8, cursor: 'pointer', background: '#fff', userSelect: 'none' },
  msDrop:   { position: 'absolute', top: '100%', left: 0, right: 0, zIndex: 200, background: '#fff', border: '0.5px solid #C5D2DC', borderRadius: 8, boxShadow: '0 4px 12px rgba(0,0,0,0.1)', marginTop: 4 },
  msSearch: { width: '100%', padding: '8px 12px', border: 'none', borderBottom: '0.5px solid #F0F4F8', outline: 'none', fontSize: 13, boxSizing: 'border-box' },
  msItem:   { display: 'flex', alignItems: 'center', padding: '8px 14px', fontSize: 13, cursor: 'pointer', userSelect: 'none', color: '#1A2E40' },
  chip:     { background: '#E6F1FB', color: '#185FA5', borderRadius: 20, padding: '3px 10px', fontSize: 12, fontWeight: 500, display: 'flex', alignItems: 'center', gap: 4 },
  chipX:    { background: 'none', border: 'none', cursor: 'pointer', color: '#185FA5', fontWeight: 700, fontSize: 13, padding: 0 },

  tableWrapper: { background: '#fff', border: '0.5px solid #DDE4EA', borderRadius: 12, overflow: 'hidden' },
  table:        { width: '100%', borderCollapse: 'collapse' },
  thead:        { background: '#F0F4F8' },
  th: { padding: '12px 16px', fontSize: 11, fontWeight: 500, color: '#5A7A8A', textTransform: 'uppercase', letterSpacing: 0.5, textAlign: 'left', borderBottom: '0.5px solid #F0F4F8', whiteSpace: 'nowrap' },
  td: { padding: '12px 16px', fontSize: 13, color: '#1A2E40', borderBottom: '0.5px solid #F0F4F8', verticalAlign: 'middle' },

  avatar: { width: 32, height: 32, borderRadius: '50%', background: '#2E6E8E', display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 12, fontWeight: 600, color: '#fff', flexShrink: 0 },
  iconBtn: { padding: '5px 8px', borderRadius: 6, border: '0.5px solid #DDE4EA', background: '#fff', cursor: 'pointer', fontSize: 13 },
};
