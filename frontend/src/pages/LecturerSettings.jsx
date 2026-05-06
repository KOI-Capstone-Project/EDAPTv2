import { useState } from 'react';
import { getUser, getUserName, getUserInitials } from '../utils/auth';
import api from '../services/api';

const ALL_PERIODS = ['23.1','23.2','23.3','24.1','24.2','24.3','25.1','25.2','25.3'];

export default function LecturerSettings() {
  const user     = getUser();
  const name     = getUserName();
  const initials = getUserInitials();
  const email    = user?.email    || '—';
  const role     = user?.role     || 'Lecturer';
  const subjects = user?.subjects || [];

  // ── Section 2: Change Password ───────────────────────────────────────────
  const [curPwd,    setCurPwd]    = useState('');
  const [newPwd,    setNewPwd]    = useState('');
  const [confPwd,   setConfPwd]   = useState('');
  const [showCur,   setShowCur]   = useState(false);
  const [showNew,   setShowNew,]  = useState(false);
  const [showConf,  setShowConf]  = useState(false);
  const [pwdMsg,    setPwdMsg]    = useState(null); // {type:'success'|'error', text}
  const [pwdLoading,setPwdLoading]= useState(false);

  const pwdErrors = [];
  if (newPwd && newPwd.length < 8)       pwdErrors.push('New password must be at least 8 characters.');
  if (confPwd && newPwd !== confPwd)      pwdErrors.push('Passwords do not match.');

  const handleChangePassword = async e => {
    e.preventDefault();
    if (pwdErrors.length) return;
    setPwdLoading(true);
    setPwdMsg(null);
    try {
      await api.post('/api/auth/change-password', {
        current_password: curPwd,
        new_password:     newPwd,
      });
      setPwdMsg({ type: 'success', text: 'Password updated successfully.' });
      setCurPwd(''); setNewPwd(''); setConfPwd('');
    } catch (err) {
      setPwdMsg({ type: 'error', text: err.response?.data?.detail || 'Failed to update password.' });
    } finally {
      setPwdLoading(false);
    }
  };

  // ── Section 3: Preferences ───────────────────────────────────────────────
  const [prefSubject,  setPrefSubject]  = useState(localStorage.getItem('pref_default_subject')   || '');
  const [prefTrimester,setPrefTrimester]= useState(localStorage.getItem('pref_default_trimester') || '');
  const [prefSaved,    setPrefSaved]    = useState(false);

  const handleSavePrefs = () => {
    localStorage.setItem('pref_default_subject',   prefSubject);
    localStorage.setItem('pref_default_trimester', prefTrimester);
    setPrefSaved(true);
    setTimeout(() => setPrefSaved(false), 2500);
  };

  return (
    <div style={{ maxWidth: 720 }}>

      <div style={s.pageHeader}>
        <h1 style={s.pageTitle}>Settings</h1>
        <p style={s.pageSub}>Manage your account preferences</p>
      </div>

      {/* ── Section 1: Profile (read-only) ──────────────────────── */}
      <div style={s.card}>
        <h2 style={s.cardTitle}>Profile</h2>

        {/* Avatar */}
        <div style={s.profileRow}>
          <div style={s.avatar}>{initials}</div>
          <div>
            <p style={s.avatarName}>{name}</p>
            <p style={s.avatarRole}>{role}</p>
          </div>
        </div>

        <div style={s.divider} />

        {/* Fields */}
        <ProfileRow label="Full Name"       value={name} />
        <ProfileRow label="Email / Staff ID" value={email} />
        <ProfileRow label="Role"
          value={<span style={s.roleBadge}>{role}</span>}
        />

        <div style={s.profileField}>
          <span style={s.profileLabel}>Assigned Subjects</span>
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6, marginTop: 4 }}>
            {subjects.length > 0
              ? subjects.map(sub => (
                  <span key={sub} style={s.subjectChip}>{sub}</span>
                ))
              : <span style={s.muted}>None assigned</span>
            }
          </div>
          <p style={s.fieldNote}>Subjects are assigned by the Head of Technology</p>
        </div>
      </div>

      {/* ── Section 2: Security ─────────────────────────────────── */}
      <div style={s.card}>
        <h2 style={s.cardTitle}>Security</h2>
        <form onSubmit={handleChangePassword}>

          <PasswordField
            label="Current Password"
            value={curPwd}
            onChange={setCurPwd}
            show={showCur}
            onToggle={() => setShowCur(v => !v)}
          />
          <PasswordField
            label="New Password"
            value={newPwd}
            onChange={setNewPwd}
            show={showNew}
            onToggle={() => setShowNew(v => !v)}
          />
          {newPwd && newPwd.length < 8 && (
            <p style={s.inlineErr}>New password must be at least 8 characters.</p>
          )}

          <PasswordField
            label="Confirm New Password"
            value={confPwd}
            onChange={setConfPwd}
            show={showConf}
            onToggle={() => setShowConf(v => !v)}
          />
          {confPwd && newPwd !== confPwd && (
            <p style={s.inlineErr}>Passwords do not match.</p>
          )}

          {pwdMsg && (
            <div style={pwdMsg.type === 'success' ? s.successBox : s.errorBox}>
              {pwdMsg.text}
            </div>
          )}

          <button
            type="submit"
            style={{ ...s.tealBtn, opacity: (pwdLoading || pwdErrors.length > 0 || !curPwd || !newPwd || !confPwd) ? 0.55 : 1 }}
            disabled={pwdLoading || pwdErrors.length > 0 || !curPwd || !newPwd || !confPwd}
          >
            {pwdLoading ? 'Updating…' : 'Update Password'}
          </button>
        </form>
      </div>

      {/* ── Section 3: Preferences ──────────────────────────────── */}
      <div style={s.card}>
        <h2 style={s.cardTitle}>Preferences</h2>
        <p style={s.muted}>These preferences are applied when you log in.</p>

        <div style={s.prefField}>
          <label style={s.prefLabel}>Default Subject on Login</label>
          <select
            style={s.select}
            value={prefSubject}
            onChange={e => setPrefSubject(e.target.value)}
          >
            <option value="">All My Subjects</option>
            {subjects.map(sub => <option key={sub} value={sub}>{sub}</option>)}
          </select>
        </div>

        <div style={s.prefField}>
          <label style={s.prefLabel}>Default Trimester View</label>
          <select
            style={s.select}
            value={prefTrimester}
            onChange={e => setPrefTrimester(e.target.value)}
          >
            <option value="">Latest Available</option>
            {ALL_PERIODS.map(p => <option key={p} value={p}>{p}</option>)}
          </select>
        </div>

        {prefSaved && (
          <div style={{ ...s.successBox, marginBottom: 12 }}>Preferences saved.</div>
        )}

        <button style={s.tealBtn} onClick={handleSavePrefs}>
          Save Preferences
        </button>
      </div>
    </div>
  );
}

// ── Sub-components ────────────────────────────────────────────────────────────

function ProfileRow({ label, value }) {
  return (
    <div style={s.profileField}>
      <span style={s.profileLabel}>{label}</span>
      <span style={s.profileValue}>{value}</span>
    </div>
  );
}

function PasswordField({ label, value, onChange, show, onToggle }) {
  return (
    <div style={s.pwdField}>
      <label style={s.prefLabel}>{label}</label>
      <div style={s.pwdRow}>
        <input
          type={show ? 'text' : 'password'}
          value={value}
          onChange={e => onChange(e.target.value)}
          style={s.input}
          autoComplete="new-password"
        />
        <button type="button" onClick={onToggle} style={s.eyeBtn} tabIndex={-1}>
          {show ? '🙈' : '👁'}
        </button>
      </div>
    </div>
  );
}

// ── Styles ────────────────────────────────────────────────────────────────────

const s = {
  pageHeader: { marginBottom: 24 },
  pageTitle:  { margin: '0 0 4px', fontSize: 24, fontWeight: 500, color: '#1A2E40' },
  pageSub:    { margin: 0, fontSize: 13, color: '#5A7A8A' },

  card: {
    background: '#fff', border: '0.5px solid #DDE4EA',
    borderRadius: 10, padding: '24px 28px', marginBottom: 20,
  },
  cardTitle: { margin: '0 0 20px', fontSize: 16, fontWeight: 600, color: '#1E293B' },

  profileRow: { display: 'flex', alignItems: 'center', gap: 16, marginBottom: 20 },
  avatar: {
    width: 64, height: 64, borderRadius: '50%', flexShrink: 0,
    background: 'linear-gradient(135deg, #2E6E8E, #4f8ef7)',
    display: 'flex', alignItems: 'center', justifyContent: 'center',
    fontSize: 22, fontWeight: 700, color: '#fff',
  },
  avatarName: { margin: '0 0 4px', fontSize: 16, fontWeight: 600, color: '#1E293B' },
  avatarRole: { margin: 0, fontSize: 12, color: '#64748B' },

  divider: { borderTop: '1px solid #F1F5F9', margin: '4px 0 16px' },

  profileField: { display: 'flex', flexDirection: 'column', gap: 4, marginBottom: 16 },
  profileLabel: { fontSize: 11, fontWeight: 700, color: '#94A3B8', textTransform: 'uppercase', letterSpacing: 0.5 },
  profileValue: { fontSize: 14, color: '#1E293B' },
  fieldNote:    { margin: '6px 0 0', fontSize: 11, color: '#94A3B8' },

  roleBadge: {
    display: 'inline-block', background: '#E6F1FB', color: '#185FA5',
    borderRadius: 20, padding: '2px 12px', fontSize: 12, fontWeight: 600,
  },
  subjectChip: {
    background: '#E6F1FB', color: '#185FA5',
    borderRadius: 20, padding: '3px 10px', fontSize: 11, fontWeight: 600,
  },
  muted: { margin: '0 0 16px', fontSize: 12, color: '#94A3B8' },

  pwdField: { marginBottom: 14 },
  pwdRow:   { display: 'flex', gap: 8, alignItems: 'center' },
  input: {
    flex: 1, padding: '10px 14px', borderRadius: 8,
    border: '0.5px solid #C5D2DC', fontSize: 13, color: '#1E293B', outline: 'none',
  },
  eyeBtn: {
    padding: '8px 10px', borderRadius: 8, border: '0.5px solid #C5D2DC',
    background: '#fff', cursor: 'pointer', fontSize: 14,
  },
  inlineErr:  { margin: '-8px 0 10px', fontSize: 11, color: '#DC2626' },

  successBox: {
    background: '#E1F5EE', color: '#0F6E56',
    borderRadius: 8, padding: '10px 14px', fontSize: 13, marginBottom: 14,
  },
  errorBox: {
    background: '#FCEBEB', color: '#A32D2D',
    borderRadius: 8, padding: '10px 14px', fontSize: 13, marginBottom: 14,
  },

  tealBtn: {
    padding: '10px 20px', borderRadius: 8, border: 'none',
    background: '#2E6E8E', color: '#fff', fontSize: 13,
    fontWeight: 600, cursor: 'pointer',
  },

  prefField: { marginBottom: 16 },
  prefLabel: { display: 'block', fontSize: 13, fontWeight: 600, color: '#334155', marginBottom: 6 },
  select: {
    padding: '10px 14px', borderRadius: 8, border: '0.5px solid #C5D2DC',
    fontSize: 13, color: '#1E293B', background: '#fff', cursor: 'pointer',
    minWidth: 240, outline: 'none',
  },
};
