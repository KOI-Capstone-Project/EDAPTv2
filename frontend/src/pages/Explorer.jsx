import React from 'react';

export default function Explorer() {
  return (
    <div>
      <div style={s.header}>
        <h1 style={s.title}>Explorer</h1>
        <p style={s.subtitle}>Browse and filter anonymised student records</p>
      </div>

      <div style={s.card}>
        <div style={s.comingSoon}>
          <div style={s.icon}>🔍</div>
          <h2 style={s.cardTitle}>Coming Soon</h2>
          <p style={s.cardText}>
            The Explorer module will let you browse, search, and filter anonymised student
            records linked to assessments and trimester enrolments.
          </p>
        </div>
      </div>
    </div>
  );
}

const s = {
  header:   { marginBottom: 28 },
  title:    { margin: '0 0 6px', fontSize: 26, fontWeight: 700, color: '#1E293B' },
  subtitle: { margin: 0, fontSize: 14, color: '#64748B' },
  card: {
    background: '#fff', border: '0.5px solid #DDE4EA',
    borderRadius: 12, padding: '48px 32px',
  },
  comingSoon: { display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 12, textAlign: 'center' },
  icon:      { fontSize: 40 },
  cardTitle: { margin: 0, fontSize: 18, fontWeight: 600, color: '#1E293B' },
  cardText:  { margin: 0, fontSize: 14, color: '#64748B', maxWidth: 480, lineHeight: 1.6 },
};
