// Settings: profile editor, password change, and preferences. Shared by
// admin (HoT/HoS) and lecturer accounts via the isLecturer prop — the
// lecturer role additionally sees its assigned-subjects list and a
// default-subject preference that doesn't apply to an admin, who has no
// fixed subject scope.
import { useState, useRef } from 'react';
import { getUser, getUserName, getUserInitials } from '../utils/auth';
import api from '../services/api';

const ALL_PERIODS = ['23.1','23.2','23.3','24.1','24.2','24.3','25.1','25.2','25.3'];

export default function SettingsView({ isLecturer }) {
  const user     = getUser();
  const email    = user?.email    || '';
  const role     = user?.role     || (isLecturer ? 'Lecturer' : 'Head of Technology');
  const subjects = user?.subjects || [];
  const PHOTO_KEY = `user_photo_${email}`;

  // ── Section 1: Profile ───────────────────────────────────────────────────
  const [name,       setName]       = useState(getUserName());
  const [phone,      setPhone]      = useState(user?.phone      || '');
  const [department, setDepartment] = useState(user?.department || '');
  const [bio,        setBio]        = useState(user?.bio        || '');
  const [profileMsg, setProfileMsg] = useState(null);
  const [profSaving, setProfSaving] = useState(false);

  const [photoSrc, setPhotoSrc] = useState(
    localStorage.getItem(PHOTO_KEY) || null
  );
  const fileRef = useRef(null);

  const handlePhotoChange = e => {
    const file = e.target.files?.[0];
    if (!file) return;
    const reader = new FileReader();
    reader.onload = ev => {
      const base64 = ev.target.result;
      localStorage.setItem(PHOTO_KEY, base64);
      setPhotoSrc(base64);
    };
    reader.readAsDataURL(file);
  };

  const handleSaveProfile = async () => {
    setProfSaving(true);
    setProfileMsg(null);
    try {
      await api.post('/api/auth/update-profile', { name, phone, department, bio });
      const stored = JSON.parse(localStorage.getItem('edapt_user') || '{}');
      localStorage.setItem('edapt_user', JSON.stringify({ ...stored, name, phone, department, bio }));
      setProfileMsg({ type: 'success', text: 'Profile updated successfully.' });
    } catch (err) {
      setProfileMsg({ type: 'error', text: err.response?.data?.detail || 'Failed to update profile.' });
    } finally {
      setProfSaving(false);
    }
  };

  // ── Section 2: Change Password ───────────────────────────────────────────
  const [curPwd,     setCurPwd]     = useState('');
  const [newPwd,     setNewPwd]     = useState('');
  const [confPwd,    setConfPwd]    = useState('');
  const [showCur,    setShowCur]    = useState(false);
  const [showNew,    setShowNew]    = useState(false);
  const [showConf,   setShowConf]   = useState(false);
  const [pwdMsg,     setPwdMsg]     = useState(null);
  const [pwdLoading, setPwdLoading] = useState(false);

  const pwdChecks = [
    { label: 'At least 10 characters',  met: newPwd.length >= 10 },
    { label: 'One uppercase letter',     met: /[A-Z]/.test(newPwd) },
    { label: 'One lowercase letter',     met: /[a-z]/.test(newPwd) },
    { label: 'One number',              met: /[0-9]/.test(newPwd) },
    { label: 'One special character',   met: /[^A-Za-z0-9]/.test(newPwd) },
  ];
  const pwdStrength   = pwdChecks.filter(c => c.met).length;
  const strengthLabel = pwdStrength <= 2 ? 'Weak' : pwdStrength <= 4 ? 'Fair' : 'Strong';
  const strengthColor = pwdStrength <= 2 ? '#DC2626' : pwdStrength <= 4 ? '#D97706' : '#059669';
  const allPwdMet     = pwdStrength === 5;

  const handleChangePassword = async e => {
    e.preventDefault();
    if (!allPwdMet || newPwd !== confPwd) return;
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
  const [prefSubject,   setPrefSubject]   = useState(localStorage.getItem('pref_default_subject')   || '');
  const [prefTrimester, setPrefTrimester] = useState(localStorage.getItem('pref_default_trimester') || '');
  const [prefSaved,     setPrefSaved]     = useState(false);

  const handleSavePrefs = () => {
    // Admin has no fixed subject scope, so pref_default_subject was never
    // written for that role before this merge — keep it that way.
    if (isLecturer) {
      localStorage.setItem('pref_default_subject', prefSubject);
    }
    localStorage.setItem('pref_default_trimester', prefTrimester);
    setPrefSaved(true);
    setTimeout(() => setPrefSaved(false), 2500);
  };

  const initials = getUserInitials();

  return (
    <div style={{ maxWidth: 720 }}>

      <div style={s.pageHeader}>
        <h1 style={s.pageTitle}>Settings</h1>
        <p style={s.pageSub}>Manage your account and preferences</p>
      </div>

      {/* ── Section 1: Profile ──────────────────────────────────── */}
      <div style={s.card}>
        <h2 style={s.cardTitle}>Profile</h2>

        {/* Photo + avatar */}
        <div style={s.photoRow}>
          <div style={s.photoWrap}>
            {photoSrc ? (
              <img src={photoSrc} alt="Profile" style={s.photo} />
            ) : (
              <div style={{
                ...s.avatarFallback,
                background: isLecturer
                  ? 'linear-gradient(135deg, #2E6E8E, #4f8ef7)'
                  : 'linear-gradient(135deg, #1A2E40, #2E6E8E)',
              }}>
                {initials}
              </div>
            )}
            <button style={s.photoOverlay} onClick={() => fileRef.current?.click()} title="Change photo">
              📷
            </button>
          </div>
          <input ref={fileRef} type="file" accept="image/*" style={{ display: 'none' }} onChange={handlePhotoChange} />
          <div>
            <p style={s.avatarName}>{name || getUserName()}</p>
            <p style={s.avatarRole}>{role}</p>
            <button style={s.linkBtn} onClick={() => fileRef.current?.click()}>Change photo</button>
            {photoSrc && (
              <button style={{ ...s.linkBtn, color: '#A32D2D', marginLeft: 12 }}
                onClick={() => { localStorage.removeItem(PHOTO_KEY); setPhotoSrc(null); }}>
                Remove
              </button>
            )}
          </div>
        </div>

        <div style={s.divider} />

        {/* Editable fields */}
        <div style={s.formGrid}>
          <div style={s.formField}>
            <label style={s.label}>Full Name</label>
            <input style={s.input} value={name} onChange={e => setName(e.target.value)} placeholder="Your name" />
          </div>
          <div style={s.formField}>
            <label style={s.label}>Email / Staff ID</label>
            <input style={{ ...s.input, background: '#F8FAFB', color: '#8BA5B8' }} value={email} readOnly />
          </div>
          <div style={s.formField}>
            <label style={s.label}>Role</label>
            <input style={{ ...s.input, background: '#F8FAFB', color: '#8BA5B8' }} value={role} readOnly />
          </div>
          <div style={s.formField}>
            <label style={s.label}>Phone</label>
            <input style={s.input} value={phone} onChange={e => setPhone(e.target.value)} placeholder="+61 4xx xxx xxx" />
          </div>
          <div style={s.formField}>
            <label style={s.label}>Department</label>
            <input style={s.input} value={department} onChange={e => setDepartment(e.target.value)} placeholder="e.g. Information Technology" />
          </div>
        </div>

        <div style={{ ...s.formField, marginTop: 4 }}>
          <label style={s.label}>Bio</label>
          <textarea
            style={{ ...s.input, height: 80, padding: '10px 12px', resize: 'vertical', fontFamily: 'inherit' }}
            value={bio}
            onChange={e => setBio(e.target.value)}
            placeholder="Short bio (optional)"
          />
        </div>

        {isLecturer && (
          <div style={s.prefField}>
            <label style={s.label}>Assigned Subjects</label>
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6, marginTop: 4 }}>
              {subjects.length > 0
                ? subjects.map(sub => <span key={sub} style={s.subjectChip}>{sub}</span>)
                : <span style={s.muted}>None assigned</span>
              }
            </div>
            <p style={s.fieldNote}>Subjects are assigned by the Head of Technology</p>
          </div>
        )}

        {profileMsg && (
          <div style={profileMsg.type === 'success' ? s.successBox : s.errorBox}>
            {profileMsg.text}
          </div>
        )}

        <button
          style={{ ...s.tealBtn, opacity: profSaving ? 0.6 : 1 }}
          disabled={profSaving}
          onClick={handleSaveProfile}
        >
          {profSaving ? 'Saving…' : 'Save Profile'}
        </button>
      </div>

      {/* ── Section 2: Security ─────────────────────────────────── */}
      <div style={s.card}>
        <h2 style={s.cardTitle}>Security</h2>
        <form onSubmit={handleChangePassword}>

          <PasswordField label="Current Password" value={curPwd} onChange={setCurPwd} show={showCur} onToggle={() => setShowCur(v => !v)} />
          <PasswordField label="New Password"     value={newPwd} onChange={setNewPwd} show={showNew} onToggle={() => setShowNew(v => !v)} />

          {newPwd && (
            <div style={{ marginBottom: 14 }}>
              <div style={{ display: 'flex', gap: 4, marginBottom: 6 }}>
                {[0,1,2,3,4].map(i => (
                  <div key={i} style={{ flex: 1, height: 4, borderRadius: 2, background: i < pwdStrength ? strengthColor : '#E2E8F0' }} />
                ))}
              </div>
              <div style={{ fontSize: 11, color: strengthColor, fontWeight: 600, marginBottom: 8 }}>{strengthLabel}</div>
              {pwdChecks.map((c, i) => (
                <div key={i} style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 4 }}>
                  <span style={{ width: 14, height: 14, borderRadius: '50%', border: `1.5px solid ${c.met ? '#059669' : '#C5D2DC'}`, background: c.met ? '#059669' : 'transparent', display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0 }}>
                    {c.met && <span style={{ color: '#fff', fontSize: 9, fontWeight: 700, lineHeight: 1 }}>✓</span>}
                  </span>
                  <span style={{ fontSize: 12, color: c.met ? '#059669' : '#64748B' }}>{c.label}</span>
                </div>
              ))}
            </div>
          )}

          <PasswordField label="Confirm New Password" value={confPwd} onChange={setConfPwd} show={showConf} onToggle={() => setShowConf(v => !v)} />
          {confPwd && newPwd !== confPwd && <p style={s.inlineErr}>Passwords do not match.</p>}

          {pwdMsg && (
            <div style={pwdMsg.type === 'success' ? s.successBox : s.errorBox}>
              {pwdMsg.text}
            </div>
          )}

          <button
            type="submit"
            style={{ ...s.tealBtn, opacity: (pwdLoading || !curPwd || !newPwd || !confPwd || !allPwdMet || newPwd !== confPwd) ? 0.55 : 1 }}
            disabled={pwdLoading || !curPwd || !newPwd || !confPwd || !allPwdMet || newPwd !== confPwd}
          >
            {pwdLoading ? 'Updating…' : 'Update Password'}
          </button>
        </form>
      </div>

      {/* ── Section 3: Preferences ──────────────────────────────── */}
      <div style={s.card}>
        <h2 style={s.cardTitle}>Preferences</h2>
        <p style={s.muted}>
          {isLecturer ? 'These preferences are applied when you log in.' : 'Applied when you log in or navigate to the dashboard.'}
        </p>

        {isLecturer && (
          <div style={s.prefField}>
            <label style={s.prefLabel}>Default Subject on Login</label>
            <select style={s.select} value={prefSubject} onChange={e => setPrefSubject(e.target.value)}>
              <option value="">All My Subjects</option>
              {subjects.map(sub => <option key={sub} value={sub}>{sub}</option>)}
            </select>
          </div>
        )}

        <div style={s.prefField}>
          <label style={s.prefLabel}>Default Trimester View</label>
          <select style={s.select} value={prefTrimester} onChange={e => setPrefTrimester(e.target.value)}>
            <option value="">Latest Available</option>
            {ALL_PERIODS.map(p => <option key={p} value={p}>{p}</option>)}
          </select>
        </div>

        {prefSaved && <div style={{ ...s.successBox, marginBottom: 12 }}>Preferences saved.</div>}

        <button style={s.tealBtn} onClick={handleSavePrefs}>
          Save Preferences
        </button>
      </div>
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

const s = {
  pageHeader: { marginBottom: 24 },
  pageTitle:  { margin: '0 0 4px', fontSize: 24, fontWeight: 500, color: '#1A2E40' },
  pageSub:    { margin: 0, fontSize: 13, color: '#5A7A8A' },

  card: {
    background: '#fff', border: '0.5px solid #DDE4EA',
    borderRadius: 10, padding: '24px 28px', marginBottom: 20,
  },
  cardTitle: { margin: '0 0 20px', fontSize: 16, fontWeight: 600, color: '#1E293B' },

  photoRow: { display: 'flex', alignItems: 'center', gap: 20, marginBottom: 20 },
  photoWrap: { position: 'relative', width: 72, height: 72, flexShrink: 0 },
  photo: { width: 72, height: 72, borderRadius: '50%', objectFit: 'cover', display: 'block' },
  avatarFallback: {
    width: 72, height: 72, borderRadius: '50%',
    display: 'flex', alignItems: 'center', justifyContent: 'center',
    fontSize: 24, fontWeight: 700, color: '#fff',
  },
  photoOverlay: {
    position: 'absolute', bottom: 0, right: 0,
    width: 26, height: 26, borderRadius: '50%',
    background: '#2E6E8E', border: '2px solid #fff',
    display: 'flex', alignItems: 'center', justifyContent: 'center',
    cursor: 'pointer', fontSize: 11,
  },
  avatarName: { margin: '0 0 2px', fontSize: 16, fontWeight: 600, color: '#1E293B' },
  avatarRole: { margin: '0 0 8px', fontSize: 12, color: '#64748B' },
  linkBtn:    { background: 'none', border: 'none', cursor: 'pointer', fontSize: 12, color: '#2E6E8E', fontWeight: 500, padding: 0 },

  divider: { borderTop: '1px solid #F1F5F9', margin: '4px 0 20px' },

  formGrid:  { display: 'grid', gridTemplateColumns: 'repeat(2, 1fr)', gap: 16 },
  formField: { display: 'flex', flexDirection: 'column', gap: 6 },
  label:     { fontSize: 12, fontWeight: 600, color: '#334155' },
  input: {
    padding: '10px 14px', borderRadius: 8,
    border: '0.5px solid #C5D2DC', fontSize: 13, color: '#1E293B',
    outline: 'none', width: '100%', boxSizing: 'border-box',
  },

  subjectChip: {
    background: '#E6F1FB', color: '#185FA5',
    borderRadius: 20, padding: '3px 10px', fontSize: 11, fontWeight: 600,
  },
  fieldNote: { margin: '6px 0 0', fontSize: 11, color: '#94A3B8' },

  successBox: { background: '#E1F5EE', color: '#0F6E56', borderRadius: 8, padding: '10px 14px', fontSize: 13, marginBottom: 14 },
  errorBox:   { background: '#FCEBEB', color: '#A32D2D', borderRadius: 8, padding: '10px 14px', fontSize: 13, marginBottom: 14 },

  tealBtn: {
    padding: '10px 20px', borderRadius: 8, border: 'none',
    background: '#2E6E8E', color: '#fff', fontSize: 13,
    fontWeight: 600, cursor: 'pointer', marginTop: 4,
  },

  pwdField: { marginBottom: 14 },
  pwdRow:   { display: 'flex', gap: 8, alignItems: 'center' },
  eyeBtn: {
    padding: '8px 10px', borderRadius: 8, border: '0.5px solid #C5D2DC',
    background: '#fff', cursor: 'pointer', fontSize: 14, flexShrink: 0,
  },
  inlineErr: { margin: '-8px 0 10px', fontSize: 11, color: '#DC2626' },

  prefField: { marginBottom: 16 },
  prefLabel: { display: 'block', fontSize: 13, fontWeight: 600, color: '#334155', marginBottom: 6 },
  select: {
    padding: '10px 14px', borderRadius: 8, border: '0.5px solid #C5D2DC',
    fontSize: 13, color: '#1E293B', background: '#fff', cursor: 'pointer',
    minWidth: 240, outline: 'none',
  },
  muted: { margin: '0 0 16px', fontSize: 12, color: '#94A3B8' },
};
