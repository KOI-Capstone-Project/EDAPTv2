// Risk-band pill and mid-term-estimate tag — shared between any page that
// renders roster rows (PredictorView, StudentsAtRisk) so the same student
// always reads the same risk color/label regardless of which page it's on.

export function RiskBadge({ band, insufficientData }) {
  // A gray "not enough data" badge is deliberately its own branch, not a
  // map[band] fallback — falling through to a risk color (even amber) for a
  // student with no prediction would read as a risk signal that isn't there.
  if (insufficientData) {
    return (
      <span style={{ fontSize: 12, fontWeight: 600, padding: '4px 12px', borderRadius: 20, whiteSpace: 'nowrap', background: '#F1F5F9', color: '#64748B' }}>
        Not enough data yet
      </span>
    );
  }
  const map = {
    Safe:        { bg: '#DCFCE7', color: '#166534' },
    'At Risk':   { bg: '#FEF9C3', color: '#854D0E' },
    'High Risk': { bg: '#FEE2E2', color: '#991B1B' },
  };
  const c = map[band] || map['At Risk'];
  return (
    <span style={{ fontSize: 12, fontWeight: 600, padding: '4px 12px', borderRadius: 20, whiteSpace: 'nowrap', background: c.bg, color: c.color }}>
      {band || '—'}
    </span>
  );
}

export function MidTermTag() {
  return (
    <span
      title="Mid-term estimate — based on partial data"
      style={{
        fontSize: 11, fontWeight: 600, padding: '3px 8px', borderRadius: 20, whiteSpace: 'nowrap',
        background: '#EEF2FF', color: '#4338CA', border: '0.5px solid #C7D2FE',
        display: 'inline-flex', alignItems: 'center', gap: 4,
      }}
    >
      ⏳ Mid-term estimate
    </span>
  );
}
