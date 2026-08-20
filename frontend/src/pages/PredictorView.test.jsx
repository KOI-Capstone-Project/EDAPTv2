// Regression test for the Assessment Breakdown "Total" mismatch bug:
// the table listed every recorded assessment item's contribution, but the
// "Total" row rendered result.partial_weighted_score — which, for a
// complete-record prediction, is predictor.compute_partial_score()'s
// top-2-highest-weighted-items feature (a deliberate, narrower ML input),
// not the sum of everything shown in the table above it. A 5-item
// breakdown summing to 50 was displaying a "Total" of 30.
//
// PredictionResultPanel is the single component both the real-student
// detail view and the What-If simulator render through (see its own
// "Shared result rendering" comment in PredictorView.jsx) — one component,
// tested directly, covers both flows structurally rather than needing two
// separate UI-driven tests.
import { render, screen } from '@testing-library/react';
import { PredictionResultPanel } from './PredictorView';

// Reads every rendered per-item Contribution cell and sums them exactly as
// a user reading the table would — not a re-derivation from raw props —
// so this fails the same way a human eyeballing the table would notice.
function sumDisplayedContributions() {
  const cells = screen.getAllByTestId('assessment-contribution');
  return cells.reduce((sum, cell) => sum + parseFloat(cell.textContent), 0);
}

function displayedTotal() {
  return parseFloat(screen.getByTestId('assessment-total').textContent);
}

describe('PredictionResultPanel — Assessment Breakdown Total', () => {
  test('real Predictor detail flow: ACC200/23.3 (FE 12/50, ME 18/20, CP 5/15, GR 10/10, TX 5/5)', () => {
    // Exact reported case. Individual contributions: 12 + 18 + 5 + 10 + 5 = 50.
    // partial_weighted_score is included here at its real, buggy-if-displayed
    // value (30 = top-2-by-weight FE+ME only, the actual ML feature for this
    // complete-record prediction) to prove the fix no longer renders it as
    // "Total" — if it did, this test would see 30, not 50.
    const result = {
      subject: 'ACC200',
      study_period: '23.3',
      probability: 62.0,
      prediction: 'Pass',
      risk_band: 'Safe',
      total_weight_recorded: 100,
      partial_weighted_score: 30, // top-2-by-weight (FE 12 + ME 18) — NOT the table's total
      assessments_used: [
        { type: 'FE', mark_percent: 24.0,        weighting: 50 }, // 12/50 -> 24% -> contribution 12.0
        { type: 'ME', mark_percent: 90.0,        weighting: 20 }, // 18/20 -> 90% -> contribution 18.0
        { type: 'CP', mark_percent: 33.333333,   weighting: 15 }, // 5/15  -> contribution 5.0
        { type: 'GR', mark_percent: 100.0,       weighting: 10 }, // 10/10 -> contribution 10.0
        { type: 'TX', mark_percent: 100.0,       weighting: 5 },  // 5/5   -> contribution 5.0
      ],
    };

    render(<PredictionResultPanel result={result} geminiLoading={false} geminiInsight={null} />);

    expect(displayedTotal()).toBeCloseTo(50.0, 1);
    expect(displayedTotal()).toBeCloseTo(sumDisplayedContributions(), 1);
  });

  test('What-If simulator flow: a different, 3-item complete-record scenario', () => {
    // A separate scenario (different subject, different item count/weights)
    // to confirm the invariant holds generally, not just for the one
    // reported case — and that it still diverges from partial_weighted_score
    // whenever more than the top-2-by-weight items are present.
    // Contributions: A 48.0 + B 10.0 + C 15.0 = 73.0. Top-2-by-weight (A+B) = 58.
    const result = {
      subject: 'ICT205',
      study_period: '25.3',
      probability: 71.0,
      prediction: 'Pass',
      risk_band: 'Safe',
      total_weight_recorded: 100,
      partial_weighted_score: 58, // top-2-by-weight (A 48 + B 10) — NOT the table's total
      assessments_used: [
        { type: 'A', mark_percent: 80.0, weighting: 60 }, // contribution 48.0
        { type: 'B', mark_percent: 40.0, weighting: 25 }, // contribution 10.0
        { type: 'C', mark_percent: 100.0, weighting: 15 }, // contribution 15.0
      ],
    };

    render(<PredictionResultPanel result={result} geminiLoading={false} geminiInsight={null} />);

    expect(displayedTotal()).toBeCloseTo(73.0, 1);
    expect(displayedTotal()).toBeCloseTo(sumDisplayedContributions(), 1);
  });

  test('mid-term estimate (partial coverage): Total still matches the displayed rows', () => {
    // Genuinely partial case (2 of 5 items) — partial_weighted_score for
    // this tier is computed server-side by compute_simulated_partial_score()
    // as the sum of ALL recorded items, so it already agrees with the table
    // here. Included so the invariant is verified across all three coverage
    // tiers, not just the complete-record case that exposed the bug.
    const result = {
      subject: 'ICT205',
      study_period: '25.3',
      probability: 70.7,
      prediction: 'Pass',
      risk_band: 'Safe',
      estimate_type: 'mid-term estimate',
      total_weight_recorded: 50,
      partial_weighted_score: 37, // IA 24.0 + OQ 13.0 -- sum of all recorded items for this tier
      assessments_used: [
        { type: 'IA', mark_percent: 80.0, weighting: 30 }, // contribution 24.0
        { type: 'OQ', mark_percent: 65.0, weighting: 20 }, // contribution 13.0
      ],
    };

    render(<PredictionResultPanel result={result} geminiLoading={false} geminiInsight={null} />);

    expect(displayedTotal()).toBeCloseTo(37.0, 1);
    expect(displayedTotal()).toBeCloseTo(sumDisplayedContributions(), 1);
  });
});
