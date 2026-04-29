import React from 'react';

export default function Settings() {
  const user = (() => {
    try { return JSON.parse(localStorage.getItem('edapt_user') || '{}'); }
    catch { return {}; }
  })();

  return (
    <div>
      <div style={s.header}>
        <h1 style={s.title}>Settings</h1>
        <p style={s.subtitle}>Manage your account and application preferences</p>
      </div>

      <div style={s.card}>
        <h2 style={s.cardTitle}>Account</h2>
        <div style={s.row}>
          <span style={s.label}>Name</span>
          <span style={s.value}>{user.name || '—'}</span>
        </div>
        <div style={s.row}>
          <span style={s.label}>Email</span>
          <span style={s.value}>{user.email || '—'}</span>
        </div>
        <div style={s.row}>
          <span style={s.label}>Role</span>
          <span style={s.value}>{user.role || '—'}</span>
        </div>
      </div>

      <div style={s.card}>
        <h2 style={s.cardTitle}>Preferences</h2>
        <p style={s.comingSoon}>Additional settings coming soon.</p>
      </div>
    </div>
  );
}

const s = {
  header:      { marginBottom: 28 },
  title:       { margin: '0 0 6px', fontSize: 26, fontWeight: 700, color: '#1E293B' },
  subtitle:    { margin: 0, fontSize: 14, color: '#64748B' },
  card: {
    background: '#fff', border: '0.5px solid #DDE4EA',
    borderRadius: 12, padding: '24px 28px', marginBottom: 20,
  },
  cardTitle: { margin: '0 0 16px', fontSize: 15, fontWeight: 600, color: '#1E293B' },
  row: {
    display: 'flex', alignItems: 'center',
    padding: '10px 0', borderBottom: '1px solid #F1F5F9',
  },
  label: { width: 120, fontSize: 13, color: '#64748B', fontWeight: 500 },
  value: { fontSize: 13, color: '#1E293B' },
  comingSoon: { margin: 0, fontSize: 14, color: '#94A3B8' },
};
