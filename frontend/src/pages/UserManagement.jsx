import { Fragment, useState, useEffect, useRef } from 'react';
import { useNavigate } from 'react-router-dom';
import api from '../services/api';

const ROLE_BADGE = {
  'Lecturer':          { bg: '#EEEDFE', color: '#534AB7', border: '#C5C2F5' },
  'Head of Technology':{ bg: '#1A2E40', color: '#fff',    border: '#1A2E40' },
  'Head of School':    { bg: '#D1FAE5', color: '#065F46', border: '#6EE7B7' },
};

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

const genPassword = () => {
  const upper   = 'ABCDEFGHJKMNPQRSTUVWXYZ';
  const lower   = 'abcdefghjkmnpqrstuvwxyz';
  const digits  = '23456789';
  const special = '!@#$%^&*';
  const all     = upper + lower + digits + special;
  const rand    = src => src[Math.floor(Math.random() * src.length)];
  const chars   = [rand(upper), rand(lower), rand(digits), rand(special)];
  for (let i = 0; i < 6; i++) chars.push(rand(all));
  for (let i = chars.length - 1; i > 0; i--) {
    const j = Math.floor(Math.random() * (i + 1));
    [chars[i], chars[j]] = [chars[j], chars[i]];
  }
  return chars.join('');
};

function Spinner({ cols = 6 }) {
  return (
    <tr>
      <td colSpan={cols} style={{ padding: 0, border: 'none' }}>
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', height: 200 }}>
          <div style={{ width: 32, height: 32, border: '3px solid #F0F4F8', borderTop: '3px solid #2E6E8E', borderRadius: '50%', animation: 'spin 0.8s linear infinite' }} />
        </div>
      </td>
    </tr>
  );
}

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

export default function UserManagement() {
  const navigate = useNavigate();

  const storedUser = (() => { try { return JSON.parse(localStorage.getItem('edapt_user')); } catch { return null; } })();
  const isSuperAdmin = storedUser?.email === 'admin';

  useEffect(() => {
    if (!isSuperAdmin) navigate('/dashboard', { replace: true });
  }, [isSuperAdmin, navigate]);

  const [users,        setUsers]        = useState([]);
  const [allSubjects,  setAllSubjects]  = useState([]);
  const [loading,      setLoading]      = useState(true);
  const [editingEmail, setEditingEmail] = useState(null);
  const [editSubjects, setEditSubjects] = useState([]);
  const [editSaving,   setEditSaving]   = useState(false);
  const [editMsg,      setEditMsg]      = useState('');
  const [showCreate,   setShowCreate]   = useState(false);
  const [createMsg,    setCreateMsg]    = useState('');
  const [nameErr,      setNameErr]      = useState('');
  const [emailErr,     setEmailErr]     = useState('');
  const [passwordErr,  setPasswordErr]  = useState('');
  const [subjectsErr,  setSubjectsErr]  = useState('');
  const [creating,     setCreating]     = useState(false);

  const [form, setForm]   = useState({ name: '', email: '', password: '', role: 'Lecturer', subjects: [] });
  const [showPwd, setShowPwd] = useState(false);

  useEffect(() => {
    if (!isSuperAdmin) return;
    api.get('/api/subjects/list').then(r => setAllSubjects(r.data)).catch(() => {});
    fetchUsers();
  }, [isSuperAdmin]);

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

  const handleDelete = async user => {
    if (!window.confirm(`Delete account "${user.name}" (${user.email})? This cannot be undone.`)) return;
    try {
      await api.delete(`/api/users/${encodeURIComponent(user.email)}`);
      setUsers(prev => prev.filter(u => u.email !== user.email));
      if (editingEmail === user.email) cancelEdit();
    } catch (err) {
      alert(err.response?.data?.detail || 'Failed to delete account.');
    }
  };

  const handleCreate = async () => {
    setNameErr(''); setEmailErr(''); setPasswordErr(''); setSubjectsErr('');
    let hasErr = false;
    if (!form.name.trim())         { setNameErr('Full name is required.'); hasErr = true; }
    if (!isValidEmail(form.email)) { setEmailErr('Please enter a valid email address (e.g. john.smith@koi.edu.au).'); hasErr = true; }
    if (form.password.length < 10) { setPasswordErr('Password must be at least 10 characters.'); hasErr = true; }
    if (form.role === 'Lecturer' && !form.subjects.length) { setSubjectsErr('At least one subject must be selected for a Lecturer.'); hasErr = true; }
    if (hasErr) return;

    setCreating(true);
    try {
      const payload = {
        name: form.name.trim(), email: form.email.trim(),
        password: form.password, role: form.role,
        subjects: form.role === 'Lecturer' ? form.subjects : [],
      };
      const res = await api.post('/api/users', payload);
      setUsers(prev => [res.data.user, ...prev]);
      setCreateMsg(`Account created. ${form.name.trim()} can now log in.`);
      setForm({ name: '', email: '', password: '', role: 'Lecturer', subjects: [] });
      setTimeout(() => { setShowCreate(false); setCreateMsg(''); }, 3000);
    } catch (err) {
      setEmailErr(err.response?.data?.detail || 'Failed to create account.');
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
        {subjects.length === 0 && <span style={{ fontSize: 12, color: '#C5D2DC' }}>—</span>}
      </div>
    );
  };

  const canCreate = isValidEmail(form.email) && Boolean(form.name.trim()) && form.password.length > 0;

  if (!isSuperAdmin) return null;

  return (
    <div>
      <style>{`@keyframes spin { to { transform: rotate(360deg); } }`}</style>

      {/* ── Header ──────────────────────────────────────────────────── */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 24 }}>
        <div>
          <h1 style={s.pageTitle}>User Management</h1>
          <p style={s.pageSub}>Create and manage user accounts</p>
        </div>
        <button style={s.createBtn} onClick={() => { setShowCreate(o => !o); setNameErr(''); setEmailErr(''); setPasswordErr(''); setSubjectsErr(''); setCreateMsg(''); }}>
          {showCreate ? '✕ Cancel' : '+ Create New User'}
        </button>
      </div>

      {/* ── Create form ─────────────────────────────────────────────── */}
      {showCreate && (
        <div style={s.createPanel}>
          <h3 style={{ margin: '0 0 16px', fontSize: 15, fontWeight: 500, color: '#1A2E40' }}>New User Account</h3>

          <div style={s.formGrid}>
            <div style={s.formField}>
              <label style={s.label}>Full Name *</label>
              <input style={s.input} value={form.name} onChange={e => { setForm(f => ({ ...f, name: e.target.value })); setNameErr(''); }} placeholder="Dr. Jane Smith" />
              {nameErr && <span style={s.fieldErr}>{nameErr}</span>}
            </div>
            <div style={s.formField}>
              <label style={s.label}>Email *</label>
              <div style={{ position: 'relative' }}>
                <input
                  style={{ ...s.input, paddingRight: isValidEmail(form.email) ? 32 : undefined }}
                  value={form.email}
                  onChange={e => { setForm(f => ({ ...f, email: e.target.value })); setEmailErr(''); }}
                  placeholder="e.g. john.smith@koi.edu.au"
                />
                {isValidEmail(form.email) && (
                  <span style={{ position: 'absolute', right: 10, top: '50%', transform: 'translateY(-50%)', color: '#059669', fontWeight: 700, fontSize: 14, pointerEvents: 'none' }}>✓</span>
                )}
              </div>
              {form.email && !isValidEmail(form.email) && (
                <span style={{ fontSize: 11, color: '#DC2626', marginTop: 3, display: 'block' }}>
                  Enter a valid email (e.g. john.smith@koi.edu.au)
                </span>
              )}
              {emailErr && <span style={s.fieldErr}>{emailErr}</span>}
            </div>
            <div style={s.formField}>
              <label style={s.label}>Role *</label>
              <select
                style={{ ...s.input, cursor: 'pointer' }}
                value={form.role}
                onChange={e => setForm(f => ({ ...f, role: e.target.value, subjects: [] }))}
              >
                <option value="Lecturer">Lecturer</option>
                <option value="Head of Technology">Head of Technology</option>
                <option value="Head of School">Head of School</option>
              </select>
            </div>
            <div style={{ ...s.formField, gridColumn: '1 / -1' }}>
              <label style={s.label}>Temporary Password *</label>
              <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
                <div style={{ position: 'relative', flex: 1, maxWidth: 360 }}>
                  <input
                    type={showPwd ? 'text' : 'password'}
                    style={{ ...s.input, paddingRight: 40 }}
                    value={form.password}
                    onChange={e => { setForm(f => ({ ...f, password: e.target.value })); setPasswordErr(''); }}
                    placeholder="Min 10 characters"
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
              {form.password && (
                <div style={{ marginTop: 8 }}>
                  {[
                    { label: 'At least 10 characters',  met: form.password.length >= 10 },
                    { label: 'One uppercase letter',     met: /[A-Z]/.test(form.password) },
                    { label: 'One lowercase letter',     met: /[a-z]/.test(form.password) },
                    { label: 'One number',              met: /[0-9]/.test(form.password) },
                    { label: 'One special character',   met: /[^A-Za-z0-9]/.test(form.password) },
                  ].map((c, i) => (
                    <div key={i} style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 3 }}>
                      <span style={{ width: 13, height: 13, borderRadius: '50%', border: `1.5px solid ${c.met ? '#059669' : '#C5D2DC'}`, background: c.met ? '#059669' : 'transparent', display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0 }}>
                        {c.met && <span style={{ color: '#fff', fontSize: 8, fontWeight: 700, lineHeight: 1 }}>✓</span>}
                      </span>
                      <span style={{ fontSize: 11, color: c.met ? '#059669' : '#64748B' }}>{c.label}</span>
                    </div>
                  ))}
                </div>
              )}
              {passwordErr && <span style={s.fieldErr}>{passwordErr}</span>}
            </div>
          </div>

          {form.role === 'Lecturer' && (
            <div style={{ marginTop: 16 }}>
              <label style={s.label}>Assigned Subjects * <span style={{ color: '#8BA5B8', fontWeight: 400 }}>(required for Lecturer)</span></label>
              <SubjectMultiSelect
                value={form.subjects}
                onChange={v => { setForm(f => ({ ...f, subjects: v })); setSubjectsErr(''); }}
                allSubjects={allSubjects}
                placeholder="Select subjects…"
              />
              {subjectsErr && <span style={s.fieldErr}>{subjectsErr}</span>}
            </div>
          )}

          {form.role === 'Head of School' && (
            <div style={{ marginTop: 16 }}>
              <label style={s.label}>Assigned Subjects</label>
              <input style={{ ...s.input, background: '#F0FDF4', color: '#065F46', border: '0.5px solid #6EE7B7' }} value="All subjects auto-assigned" disabled />
            </div>
          )}

          {createMsg && <div style={s.successMsg}>{createMsg}</div>}

          <div style={{ display: 'flex', gap: 12, marginTop: 16 }}>
            <button style={{ ...s.createBtn, opacity: (creating || !canCreate) ? 0.6 : 1 }} disabled={creating || !canCreate} onClick={handleCreate}>
              {creating ? 'Creating…' : 'Create Account'}
            </button>
            <button style={s.cancelLink} onClick={() => { setShowCreate(false); setNameErr(''); setEmailErr(''); setPasswordErr(''); setSubjectsErr(''); setCreateMsg(''); }}>Cancel</button>
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
              <th style={s.th}>Role</th>
              <th style={s.th}>Subjects</th>
              <th style={s.th}>Status</th>
              <th style={s.th}>Actions</th>
            </tr>
          </thead>
          <tbody>
            {loading ? (
              <Spinner cols={6} />
            ) : users.length === 0 ? (
              <tr>
                <td colSpan={6} style={{ padding: 0, border: 'none' }}>
                  <div style={{ textAlign: 'center', padding: '60px 20px', color: '#8BA5B8' }}>
                    <div style={{ fontSize: 32, marginBottom: 12 }}>📭</div>
                    <div style={{ fontSize: 14, fontWeight: 500, color: '#1A2E40', marginBottom: 4 }}>No accounts found</div>
                    <div style={{ fontSize: 13 }}>Create a new account to get started</div>
                  </div>
                </td>
              </tr>
            ) : users.map((user, i) => {
              const roleBadge = ROLE_BADGE[user.role] || ROLE_BADGE['Lecturer'];
              const isLecturer = user.role === 'Lecturer' || !user.role;
              return (
                <Fragment key={user.email}>
                  <tr style={{ background: editingEmail === user.email ? '#EFF6FF' : (i % 2 === 0 ? '#fff' : '#F8FAFB') }}>
                    <td style={s.td}>
                      <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                        <div style={s.avatar}>{user.name?.split(' ').map(w => w[0]).join('').slice(0,2).toUpperCase()}</div>
                        <span style={{ fontWeight: 500 }}>{user.name}</span>
                      </div>
                    </td>
                    <td style={{ ...s.td, color: '#5A7A8A', fontSize: 12, fontFamily: 'monospace' }}>{user.email}</td>
                    <td style={s.td}>
                      <span style={{ ...s.roleBadge, background: roleBadge.bg, color: roleBadge.color, borderColor: roleBadge.border }}>
                        {user.role || 'Lecturer'}
                      </span>
                    </td>
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
                        {isLecturer && (
                          <button style={s.iconBtn} title="Edit subjects" onClick={() => editingEmail === user.email ? cancelEdit() : startEdit(user)}>
                            ✏️
                          </button>
                        )}
                        <button
                          style={{ ...s.iconBtn, background: user.active !== false ? '#FAEEDA' : '#E1F5EE' }}
                          title={user.active !== false ? 'Deactivate' : 'Activate'}
                          onClick={() => toggleActive(user)}
                        >
                          {user.active !== false ? '🔒' : '✅'}
                        </button>
                        <button
                          style={{ ...s.iconBtn, background: '#FCEBEB', color: '#A32D2D' }}
                          title="Delete account"
                          onClick={() => handleDelete(user)}
                        >
                          🗑️
                        </button>
                      </div>
                    </td>
                  </tr>

                  {editingEmail === user.email && (
                    <tr key={`edit-${user.email}`}>
                      <td colSpan={6} style={{ padding: '12px 20px', background: '#EFF6FF', borderBottom: '0.5px solid #DDE4EA' }}>
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
                </Fragment>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}

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

  fieldErr:   { fontSize: 11, color: '#DC2626', marginTop: 3, display: 'block' },
  successMsg: { background: '#E1F5EE', border: '0.5px solid #5DCAA5', color: '#0F6E56', borderRadius: 8, padding: '10px 16px', fontSize: 13, marginTop: 12 },

  roleBadge: { display: 'inline-block', padding: '3px 10px', borderRadius: 20, border: '0.5px solid', fontSize: 12, fontWeight: 500, whiteSpace: 'nowrap' },

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
