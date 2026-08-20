// Risk-band pill and mid-term-estimate tag — shared between any page that
// renders roster rows (PredictorView, StudentsAtRisk) so the same student
// always reads the same risk color/label regardless of which page it's on.

// At-Risk floor is fixed (see predictor._compute_risk_band) — only the
// Safe floor moves with the live model's own decision threshold, which is
// why that one's passed in per-row/result rather than hardcoded here too.
const AT_RISK_FLOOR = 40;
const BORDERLINE_MARGIN = 5; // percentage points

// A "Safe" at 66% and a "Safe" at 95% render identically today, even
// though the first is one weak assessment away from "At Risk" and the
// second isn't — this is what flags that gap instead of letting a
// borderline case quietly look as settled as a comfortable one.
export function isBorderlineRisk(band, probability, safeFloor = 65) {
  if (probability == null) return false;
  if (band === 'Safe')      return probability < safeFloor + BORDERLINE_MARGIN;
  if (band === 'At Risk')   return probability < AT_RISK_FLOOR + BORDERLINE_MARGIN || probability > safeFloor - BORDERLINE_MARGIN;
  if (band === 'High Risk') return probability > AT_RISK_FLOOR - BORDERLINE_MARGIN;
  return false;
}

// Same fallback PredictorView's single-result detail view already used —
// factored out so roster rows (which carry estimate_type but not their own
// safe_floor_percent) can derive the same per-row default.
export function resolveSafeFloor(row) {
  return row?.safe_floor_percent ?? (row?.estimate_type === 'mid-term estimate' ? 75 : 65);
}

export function RiskBadge({ band, insufficientData, probability, safeFloor }) {
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
  const borderline = isBorderlineRisk(band, probability, safeFloor);
  return (
    <span style={{ display: 'inline-flex', alignItems: 'center', gap: 5, fontSize: 12, fontWeight: 600, padding: '4px 12px', borderRadius: 20, whiteSpace: 'nowrap', background: c.bg, color: c.color }}>
      {band || '—'}
      {borderline && (
        <span
          title={`Borderline — within ${BORDERLINE_MARGIN} points of the ${band} boundary. A small change in marks or attendance could move this student into a different risk band.`}
          style={{ fontSize: 10, lineHeight: 1 }}
        >
          ⚠
        </span>
      )}
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
