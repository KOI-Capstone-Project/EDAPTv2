# EDAPT v2 — Model Card

Verified directly against `backend/app/ml/models/registry.json` and live ablation/calibration runs across two rounds of review — see the Round 2 sections below for where Round 1's own conclusions were corrected after a fairer test, not just restated. "Current best" is still the currently-live model — no ablation result in either round justified a configuration change, though Round 2 changed *why* that's true.

## Model identity

| | |
|---|---|
| Registry version | `20260715_132655` (live) |
| Architecture | Soft-voting ensemble: XGBoost + Random Forest (`sklearn.ensemble.VotingClassifier`) |
| Class-imbalance handling | SMOTE oversampling on the training split |
| Decision threshold | 0.50 — chosen via a held-out validation split (`validate_threshold.py`), not by sweeping the test set directly |

## Training data

- **Source**: `data/archive/Capstone_data_20260324.csv` — **superseded**. The live model has not been retrained since this session's data refresh; see [Round 6](#round-6--the-513pp-recall-drop-investigated) for what changed and why the numbers below are no longer fully trustworthy on their own.
- **Subjects used**: 124 of the institution's subjects — `fully_clean` (69) + `mostly_clean` (55) per `data/subject_reliability.json`'s per-enrolment reliability check, `TSL713` excluded (confirmed data-corruption case, CQ/IA weightings swapped by an earlier cleaning script)
- **Date range**: all study periods before `25.3`, excluding the `23.1` pilot period (too few records to add signal)
- **Row count**: 58,267 training rows (student-subject-period records, post-filtering)
- **Validated on**: study period `25.3` (held out, never seen during training)

## Intended use

Mid-to-late trimester risk flagging for lecturers and administrators — surfacing a pass/fail probability and a risk band (Safe / At Risk / High Risk) once a student has at least 50% of their subject's assessment weighting recorded, so a lecturer can identify and follow up with at-risk students before the term ends. A separate model (simulated-progress, not covered by this card's performance numbers) serves the 50–99.5% coverage tier specifically; this card describes the ≥99.5%-coverage (complete-record) model.

## Explicit non-uses / out-of-scope cases

- **Not validated for any subject outside the 124 clean subjects.** `unreliable`-classified subjects (`BUS104`, `ICT102`, `ICT274`, `ICT732`, `TSL713`) are explicitly gated out of prediction at the API level — the model was never trained on their data and has no basis for a prediction there.
- **Not validated below 50% coverage.** The system returns "insufficient data," not a prediction, below that threshold — by design, not merely by omission.
- **Not validated against a confirmed institutional pass-mark policy independent of what's baked into the labels.** *(Status update, verified just now: the ≥50% weighted-final pass mark used to build every training label **is** KOI's real, confirmed grading policy — confirmed directly by the project owner in a prior session and recorded in project memory. This is settled, not an open item — noted here only because a recent request asked this to be re-flagged as unconfirmed, which would have contradicted that already-resolved status.)*
- **Raw predicted probabilities are not well-calibrated in the 10–90% range** (see Known Limitations below) — the model ranks students correctly (ROC-AUC 0.974 on held-out test data) but the displayed percentage understates true pass likelihood by roughly 15–30 percentage points for students in that middle band. Treat the number as directionally meaningful, not as a literal probability, outside the two extreme bands.

## Known limitations

- **Resit history is not currently usable as a clean feature.** The clean-enrolment definition this pipeline uses (per-enrolment weighting sum on `ATTEMPTNUMBER==1` rows) structurally cannot represent a student's resit history as a distinct signal — reconciliation has a separate resit-fallback path (`reconcile_predictions.py`), but training itself does not.
- **A related, newly-found (not previously documented) latent bug**: `build_target()` — the function that computes the ground-truth pass/fail label from raw marks — sums `MARKPERCENT × WEIGHTING` across **every** row for a student-subject-period with no `ATTEMPTNUMBER` filtering at all. Verified empirically: if a student has both an original attempt and a resit for the *same* assessment type, and that student's attempt-1-only rows already sum to a "clean" ~100% weighting, **both** attempts get summed into `FULL_WEIGHTED_FINAL` — effectively summing more than 100% of the subject's weighting and potentially flipping the pass/fail label in either direction. Checked against the real, current dataset: **this scenario currently affects 0 of the 271,981 rows** that survive the existing SAFE_SUBJECTS + enrolment-cleanliness filter — every real case where a same-type multi-attempt situation exists is *already* excluded by that filter for an unrelated reason (the attempt-1 rows alone don't sum to a clean ~100%). So this is a real bug in the code with **zero current impact on the live model**, not a guaranteed protection against future data. Not fixed as part of this exercise — training-target logic wasn't in scope for a diagnostic pass; flagging it here for a deliberate decision.
- **Fairness finding on the age 0–20 group is a single observation, not a confirmed trend.** 139 records, fail-class recall 10.2 percentage points below the overall rate — flagged by the persisted bias audit, but only one independent (distinct training-period) audit has been run so far. `check_bias_persistence.py` exists specifically to track whether this recurs across future retrains before treating it as a real pattern.
- **Gender: a real population-level pass-rate gap exists (F 86.10% vs. M 80.85%, 5.3pp, n=2,410 F / 5,516 M), and the live model's own fail-class recall gap by gender is smaller than it, not larger — F 87.10% vs. M 82.92% recall, a 4.18pp gap, both `flagged: false` in `registry.json` (well under the 10pp threshold).** The direction is the same in both — M has the lower pass rate at the population level and the lower fail-recall in the model — so this is not a case of the model manufacturing a new, independent bias out of a population fact that carried none; if anything the model's gap is the smaller of the two numbers. It is also not a case of the model fully correcting for the population difference either — the direction still lines up, it just doesn't compound it. Stated plainly, not flagged, because it isn't currently a flaggable finding under this project's own threshold.
- **SMOTE vs. class-weighting, and ensemble vs. single-model, are current defaults — genuinely close calls, not clearly justified by performance alone.** ~~Removing SMOTE collapses fail-class precision at the currently-deployed 0.50 threshold (0.724 → 0.478)~~ **— this Round 1 claim was corrected in Round 2 (Issue 2 below): that comparison judged the no-SMOTE model at a threshold tuned for a *different* model's probability distribution. Given its own honestly re-validated threshold, the no-SMOTE model reaches P=0.686/R=0.819 — much closer to the SMOTE model's P=0.724/R=0.799, and its PR-AUC/ROC-AUC are marginally *higher*.** See the Round 2 Ablation Update section for the corrected verdict.
- **The dual risk-scale UI (Round 3) is a display-level workaround, not a fix, for the mid-term model's calibration gap (Round 2's Calibration check).** The two models currently need separate risk scales specifically because their probability outputs don't mean the same thing at the same number — the mid-term model understates true pass likelihood by roughly 15–30 percentage points across the 10–90% range, so a "70%" from it and a "70%" from the complete-record model aren't comparable, and showing both against one shared 65%-Safe cutoff was exactly what produced the Fail/Safe contradiction Round 3 fixed. Giving mid-term predictions their own boundaries (Safe at 75%, not 65%) makes the label and the band agree with each other again, but it doesn't make the mid-term number mean the same thing as a complete-record number — it just moves the line to where this specific miscalibration currently sits. **Forward-looking guidance, not a claim about a guaranteed outcome**: if the Platt/isotonic calibration correction already flagged as future work (Calibration check, above) is implemented for the mid-term model, re-check at that point whether the two risk scales can be unified back into one — if calibration is fixed, the root cause of needing two scales goes away, but that should be re-tested against real held-out data when it happens, not assumed to follow automatically.

## Performance summary — current live model, held-out test period (`25.3`)

**As of 2026-08-08: `0.8374` fail-class recall should not be cited as this model's current performance without this caveat.** Investigated and confirmed, not assumed ([Round 6](#round-6--the-513pp-recall-drop-investigated), including a 100%-traced mechanism, not a correlation): this number was partly earned against 205 real students' PASS labels that the refreshed data has since directly shown were wrong (Fail→Pass corrections, zero flips the other direction — traced to richer resit/attempt history now available for those students, not a labeling bug). Re-scoring this exact frozen model against corrected labels alone drops recall to 0.8230; a model retrained on the corrected data scores 0.7860. **`0.7860` is the more trustworthy current figure, not `0.8374`**, even though it's numerically lower — the table below is not wrong for what it measured at the time, but citing it today without this caveat overstates current performance.

| Metric | Value |
|---|---|
| Accuracy | 0.9502 |
| Fail-class precision | 0.7695 |
| Fail-class recall | 0.8374 |
| Fail-class F1 | 0.8020 |
| ROC-AUC (fail-class, computed this session) | 0.974 |

### Ablation results (Steps 3–4 of the close-out review), same honest validation split (`train < 25.2`, evaluated on `25.2`)

| Config | PR-AUC | ROC-AUC | Fail Precision @0.5 | Fail Recall @0.5 | Fit time |
|---|---|---|---|---|---|
| **A — current: ensemble + SMOTE** | 0.8556 | 0.9741 | **0.724** | 0.799 | 2.2s |
| B — single XGBoost, `scale_pos_weight`, no SMOTE | 0.8598 | 0.9752 | 0.478 | 0.901 | 0.6s |
| C — ensemble, class-weighting, no SMOTE | 0.8615 | 0.9751 | 0.478 | 0.894 | 1.3s |

**Round 1 verdict (superseded — see Round 2 below, kept here for the audit trail, not as the current conclusion)**: the ~0.6pp PR-AUC spread across configs A/B/C was treated as evidence the ensemble's edge isn't clearly real, but as evidence SMOTE itself was load-bearing. That second claim didn't hold up under a fair test — see Round 2.

### Dumb baseline comparison (Step 5)

A trivial rule (`average score to date < 50%` → flag at-risk, no ML) achieves **PR-AUC 0.8503** on the same validation set — within ~0.5–1 percentage point of the trained ensemble's 0.8556. **In plain terms**: most of this problem's predictive signal comes from the raw "how much have they scored so far" number itself, not from the ML model combining it cleverly with other features. What the trained model adds beyond the dumb baseline: (1) a genuinely smooth, continuous probability rather than a binary flag from a single crude cutoff, and (2) a usable precision/recall balance (72%/80%) at one operating point — the baseline can only trade precision for recall by moving its cutoff, and even its best cutoff (50%) sits at 50% precision / 89% recall, a much worse tradeoff than the trained model's.

### Calibration check (Step 6), **complete-record model** (`predict()` / `best_model.pkl`), genuinely-held-out test period

**Correction (Round 4 close-out): this table is the complete-record model's calibration, not the mid-term model's.** It was cross-referenced elsewhere in this document (Known Limitations, and the Round 3 dual-risk-scale writeup) as evidence for *"the mid-term model's calibration gap"* — that attribution was never actually checked and is wrong. Confirmed directly: this table's row count (7,916 across the 10 buckets) and ROC-AUC (0.974) match the complete-record model's test set (8,928 rows total; a fresh rerun on this session's refreshed data reproduces 8,928 rows and ROC-AUC 0.9662 — same shape, small drift consistent with the data refresh, not a different model). The mid-term/simulated-progress model's real test set is 33,990 rows with ROC-AUC ≈0.89 — an entirely different population, never represented in the table below. **The mid-term model's calibration had never actually been measured until Round 4, below** — this table only ever showed the complete-record model was miscalibrated too.

| Predicted P(Pass) | N | Actual pass rate |
|---|---|---|
| 0–10% | 633 | 3.3% |
| 10–20% | 102 | 30.4% |
| 20–30% | 89 | 49.4% |
| 30–40% | 88 | 63.6% |
| 40–50% | 125 | 69.6% |
| 50–60% | 141 | 84.4% |
| 60–70% | 195 | 83.6% |
| 70–80% | 345 | 90.1% |
| 80–90% | 670 | 95.4% |
| 90–100% | 5,528 | 99.3% |

**The model is well-calibrated at the extremes (0–10% and 90–100%, together 78% of students) and meaningfully miscalibrated in between** — consistently understating true pass likelihood by roughly 15–30 percentage points across every bucket from 10% to 90%, in the same direction every time (not random noise). A student shown a 25% pass probability by the UI has closer to a 49% real chance historically. The model still *ranks* students correctly (ROC-AUC 0.974) — this is a calibration problem, not a discrimination problem — but the raw number shown to lecturers is not a literal, trustworthy percentage outside the two extreme bands. Not fixed as part of this exercise (would need Platt scaling or isotonic regression as a follow-up); flagging as a real, previously-unverified finding.

---

## Round 2 — five specific follow-ups

Round 1 left five things genuinely unresolved or under-tested. Each was targeted directly rather than re-running everything. Two of them (Issues 2 and 5) found that a Round 1 conclusion was wrong or incomplete — corrected below rather than left alongside the old statement.

### Issue 1 — ensemble vs. single XGBoost, apples-to-apples (both WITH SMOTE)

Round 1's comparison confounded two variables at once (architecture AND resampling changed together). Re-ran with SMOTE held constant — the *identical* resampled training set fed to both:

| Config | PR-AUC | ROC-AUC | Fail Precision @0.5 | Fail Recall @0.5 | Fit time |
|---|---|---|---|---|---|
| (a) single XGBoost + SMOTE | 0.8536 | 0.9738 | 0.779 | 0.764 | 0.2s |
| (b) ensemble XGB+RF (current) + SMOTE | 0.8556 | 0.9741 | 0.724 | 0.799 | 1.3s |

Gap: **PR-AUC +0.0020, ROC-AUC +0.0002** — smaller than the 0.001 PR-AUC gap (XGBoost vs. LightGBM, 0.618 vs 0.617) this project already treats as noise. **The ensemble's ranking-quality edge over a single XGBoost is not a real, repeatable gain by this project's own noise standard.**

What *is* a real, non-noise difference: the two configs land at different points on the precision/recall curve at the same fixed 0.5 threshold — single XGBoost is higher-precision/lower-recall (0.78/0.76), the ensemble is lower-precision/higher-recall (0.72/0.80). This is a real, describable difference in behavior, just not a "better vs. worse" one on aggregate ranking quality.

**Explicit non-performance justification, written down as instructed rather than left implicit**: the ensemble is kept for its higher-recall operating point, which is a deliberate, defensible choice for an early-warning tool where missing a genuinely failing student (false negative) is a worse outcome than an unnecessary check-in (false positive) — not because it ranks students better, which it demonstrably doesn't by a real margin. If the team doesn't value that recall/precision tradeoff enough to justify the added architectural complexity (a `VotingClassifier` over two model families vs. one), dropping to a single XGBoost is equally defensible and would simplify the codebase with a ~6.5x faster fit time (both fast enough in absolute terms that training time itself isn't a real factor for this project's retrain cadence).

*(Round 1/2 stated this without the underlying number — quantified and confirmed to replicate across two independent validation periods in Round 3, Verification 1 below: a real +3.53pp recall gap, not an assertion.)*

### Issue 2 — re-validating the SMOTE comparison fairly (this corrects a Round 1 finding)

Checked: Round 1's "removing SMOTE collapses fail-class precision 0.72 → 0.48" used a **fixed 0.50 threshold for both** the SMOTE and non-SMOTE model. That's not a fair test — 0.50 was validated specifically for the SMOTE model's probability distribution, and removing SMOTE shifts that distribution.

Redone correctly: removed SMOTE, ran the same honest validation-sweep methodology `validate_threshold.py` already uses (0.80–0.85 recall band, maximise precision within it) on the new no-SMOTE model, on the *validation* split, then compared each model at its own best threshold:

| Config | Threshold | Precision | Recall | F1 |
|---|---|---|---|---|
| Old (unfair): SMOTE ensemble @ 0.50 | 0.50 | 0.724 | 0.799 | 0.760 |
| Old (unfair): no-SMOTE ensemble @ 0.50 (not its own threshold) | 0.50 | 0.478 | 0.894 | 0.623 |
| **New (fair): SMOTE ensemble @ its own validated 0.50** | 0.50 | 0.724 | 0.799 | 0.760 |
| **New (fair): no-SMOTE ensemble @ its own honest threshold** | 0.70 | **0.686** | **0.819** | **0.747** |

No-SMOTE ensemble ranking quality: PR-AUC 0.8615, ROC-AUC 0.9751 — both marginally *higher* than the SMOTE ensemble's 0.8556 / 0.9741.

**Which one is the real result: the new, fair one.** The old 0.478-precision figure was an artifact of an unfair comparison, not a real consequence of removing SMOTE. Once given a fair chance, the no-SMOTE model performs *comparably* to the SMOTE model (F1 0.747 vs 0.760, a 1.3pp gap — well within the same noise band as Issue 1's finding) and its raw ranking metrics are marginally better. **This invalidates the Round 1 "SMOTE is load-bearing" conclusion — corrected in the Known Limitations section above, not left standing alongside this one.** The honest, current position: neither SMOTE nor the ensemble architecture has a demonstrated, fair performance advantage over the simpler alternatives. They're kept as reasonable, working defaults — not because the evidence clearly favors them.

### Issue 3 — weighting-anomaly detection, tested on a genuine anomaly (not TSL713)

Round 1 found TSL713 never actually exercises the weighting-anomaly check (it's excluded earlier by the manual CQ/IA-swap override), leaving the check itself unproven against a real incompleteness case. Built one synthetic subject (`TESTSUBJ1`, confirmed absent from the real data and from `MANUAL_OVERRIDES` — zero override involvement) with one enrolment at ~50% weighting (same shape as TSL713's original problem) plus two clean enrolments for contrast, and ran the exact classification algorithm from `scripts/identify_clean_subjects.py` against it.

**Result: PASS.** The ~50%-weighting enrolment was correctly flagged `IS_CLEAN=False` (`TOTAL_WEIGHT=50.0`, outside the 99–101 band), and the subject as a whole was correctly classified `UNRELIABLE` (2/3 enrolments clean = 66.7%, below the 90% threshold) — independent of any manual override. The core detection mechanism works as intended on a genuine incompleteness case.

### Issue 4 — fairness audit vs. overall accuracy population mismatch

Checked the real null-demographic counts in the actual `test_audit` population (7,916 rows, study period 25.3) used for both the overall accuracy figure and the per-group fairness breakdowns:

| Dimension | Null count | % of population |
|---|---|---|
| `GENDERCODE` | 0 | 0.00% |
| `AGEGROUP` | 0 | 0.00% |
| `COUNTRY_MASKED` | 0 | 0.00% |

**Correction to the Round 1 framing**: the *mechanism* (pandas' `value_counts()` silently dropping NaN) is real and was correctly identified, but its *real-world impact right now is zero* — there are currently no null demographic values in the test population at all, so overall accuracy and all three fairness breakdowns are, today, computed on the identical 7,916-row population. Round 1 didn't check this and shouldn't have implied a population mismatch was actually occurring.

Implemented the fix anyway, as a forward-looking robustness improvement rather than a fix for a live problem: `train_model.py`'s Step 6 now fills null `COUNTRY_MASKED`/`GENDERCODE`/`AGEGROUP` with an explicit `"Unknown"` string before grouping, so a future dataset with incomplete demographic entry gets its own audited "Unknown" group (subject to the same ≥100-sample-size and ±10pp flagging rules as every other group) instead of silently vanishing from the breakdown while still counting toward the overall numbers. Retrained to confirm this works end-to-end: registered as version `20260723_150425` (not promoted), output unchanged from before (as expected, since there's nothing to fill today) — confirming the fix is safe and has zero effect on current numbers.

No "Unknown" group bias comparison to report (Issue 4, item 3) — there are no rows with missing demographics in the current data to form one.

### Issue 5 — the Pass/Fail label vs. risk-band contradiction (real bug, fixed)

Investigated the reported screenshot (73.1%, green "Safe" badge, "Fail" label on the same prediction) directly in code, then reproduced it exactly.

1. **Pass/Fail label** (`predictor.py`): `prediction = "Fail" if proba_fail >= threshold else "Pass"`. For `predict()` (complete-record), `threshold = FAIL_THRESHOLD = 0.50`. For `predict_partial()` (mid-term estimate), `threshold = _SIM_PACKAGE["decision_threshold"] = 0.25` — confirmed from the saved model package, **not** 0.50. Both thresholds were honestly validated via the same `validate_threshold.py`-style methodology, independently, for their own model.
2. **Risk band and gauge percentage**: both models previously shared one hardcoded split — `probability >= 65` → Safe, `>= 40` → At Risk, else High Risk — applied to `probability = proba_pass * 100`, the *same* number the label logic derives `proba_fail` from. Same underlying number, two different, unsynchronized boundary systems.
3. **Reproduced the exact case** (ICT101, period 25.1, `ME` mark 45/50 = 90% on a 50%-weighted item, mid-term estimate): `predict_partial()` returned **probability=73.1, prediction="Fail", risk_band="Safe"** — an exact match to the reported screenshot.
4. **Same underlying number, two inconsistent rules.** Neither the label logic nor the band logic was wrong in isolation — the complete-record model's threshold (50%) already sits below its own Safe floor (65%), so no contradiction was structurally possible there. The mid-term model's threshold implies a Pass/Fail boundary at 75% (`100 × (1 − 0.25)`), which sits *above* the shared 65% Safe floor — opening a genuine 65–75% dead zone where "Fail" and "Safe" could both be true simultaneously.
5. **Fixed** at the shared source (`predictor.py`), not patched in the frontend: added `_compute_risk_band(probability, threshold)`, used by both `predict()` and `predict_partial()`, which derives the Safe floor from whichever threshold actually produced the label (`max(65, 100 × (1 − threshold))`, with a strict `>` at the boundary to avoid an exact-equality edge case caught by the unit test below). This preserves the mid-term model's honestly-validated 0.25 threshold (forcing 0.50 instead would have silently discarded that validation and reduced mid-term fail-detection recall) while making the contradiction structurally impossible — proven, not just tested for today's two specific threshold values. Verified: the reproduced case now returns `risk_band="At Risk"` (no longer "Safe") for the same "Fail" prediction; swept the full 65–98% mark range with zero contradictions; confirmed the complete-record path's output is byte-identical to before the fix (its Safe floor was already 65, unaffected by construction). Two new regression tests added (`test_predict_partial_risk_band_never_contradicts_prediction`, an HTTP-level reproduction; `test_compute_risk_band_never_contradicts_threshold`, a pure unit-level sweep across five threshold values including ones neither model currently uses) — full suite now 13/13 passing.

---

## Round 3 — two final verifications

Round 2 made two claims without the specific evidence needed to fully trust them: the ensemble's recall advantage was asserted but never quantified, and the Fail/Safe fix was never precisely characterized against the three possible explanations. Both resolved below.

### Verification 1 — the actual recall numbers behind the ensemble decision, and whether the gap replicates

Using the exact same fair, SMOTE-held-constant setup from Round 2 Issue 1, at threshold = 0.50:

| Config | Fail Precision | Fail Recall | Fail F1 |
|---|---|---|---|
| (a) single XGBoost + SMOTE | 0.7791 | 0.7640 | 0.7715 |
| (b) ensemble XGB+RF + SMOTE (current) | 0.7238 | **0.7994** | 0.7597 |

**Recall gap: +3.53 percentage points** (ensemble − single), on the validation period (`25.2`) already used in Round 2.

**Applying the project's noise standard** (is this large enough to plausibly replicate, or is it one-split sampling noise): re-ran the identical comparison on a genuinely different, independently-built validation period — `train < 25.1, validate = 25.1` (built by truncating the filtered raw data to exclude period `25.3` entirely, so `resolve_periods()` naturally resolves one period earlier; real historical data, never used as a validation split anywhere else in this project). This validation set is a different population by construction (10,217 rows vs. 9,359; 651 fails vs. 623) and both models score substantially differently on it in absolute terms (e.g., single-XGBoost PR-AUC 0.7801 vs. 0.8536 on the original split) — confirming it's a genuinely independent test, not an accidental re-run of the same data.

| Validation period | Single XGB recall | Ensemble recall | Recall gap |
|---|---|---|---|
| `25.2` (original) | 0.7640 | 0.7994 | +3.5313pp |
| `25.1` (independent second period) | 0.7327 | 0.7680 | +3.5330pp |

**The gap replicates almost exactly** — 3.5313pp vs. 3.5330pp, a 0.002pp difference, on two structurally different populations with different absolute performance levels. This is not sampling noise from one split; it's a real, systematic, repeatable property of the ensemble at this threshold. **This confirms — with actual numbers, not just an asserted claim — that Round 2's ensemble justification is solid**: the ensemble reliably trades ~5 points of fail-class precision for ~3.5 points of fail-class recall relative to a single XGBoost, consistently across at least two independent periods. Whether that trade is worth the added architectural complexity remains a judgment call for the team (recall matters more than precision for an early-warning tool, which is why Round 2 kept the ensemble) — but the underlying number is now real and confirmed, not just claimed.

### Verification 2 — exactly what changed to fix the Fail/Safe bug

**Answer: (A)** — the risk-band boundaries now genuinely differ between mid-term and complete-record predictions, to match each model's own honestly-validated threshold. **Not (B)**: there is no separate "display threshold" — both the label and the band, within each prediction path, are computed from the exact same single threshold variable. Confirmed directly from the current code (`backend/app/ml/predictor.py`):

**Complete-record path** (`predict()`, lines ~239–251):
```python
probability = round(proba_pass * 100, 1)                          # (iii) gauge percentage
prediction  = "Fail" if proba_fail >= FAIL_THRESHOLD else "Pass"   # (i)   plain-text label — threshold 0.50
risk_band   = _compute_risk_band(probability, FAIL_THRESHOLD)      # (ii)  risk band — SAME threshold, 0.50
```

**Mid-term path** (`predict_partial()`, lines ~304–336):
```python
threshold   = _SIM_PACKAGE["decision_threshold"]                   # 0.25, loaded from the saved model package
probability = round(proba_pass * 100, 1)                           # (iii) gauge percentage
prediction  = "Fail" if proba_fail >= threshold else "Pass"        # (i)   plain-text label — threshold 0.25
risk_band   = _compute_risk_band(probability, threshold)           # (ii)  risk band — SAME threshold, 0.25
```

Within each path, all three (label, band, gauge number) draw from one consistent rule — that's what makes the Fail/Safe contradiction structurally impossible now. But the rule itself is not shared *across* paths: `_compute_risk_band`'s Safe floor is `max(65, 100 × (1 − threshold))`, which evaluates to 65 for the complete-record model and 75 for the mid-term model. **The same raw percentage (e.g. 70%) is "Safe" on a complete record and "At Risk" on a mid-term estimate.**

Per the instructions, since the answer is (A), this is now surfaced in two places, not just documented here:
- **`predictor.py`**: `_compute_risk_band`'s docstring states this explicitly (already present from Round 2).
- **The UI**: `PredictorView.jsx`'s Risk Scale legend is no longer a single static legend — it now renders different ranges for a mid-term estimate (`0–39 / 40–74 / 75–100`) vs. a complete record (`0–39 / 40–64 / 65–100`), and shows a visible caption directly above the legend whenever a mid-term estimate is displayed: *"Mid-term estimate bands differ from final-record bands — Safe starts at 75% here (not 65%), matching this model's own separately-validated decision threshold (0.25, vs. 0.50 for a complete record)."* This is meant to be seen by a lecturer in the moment, not discovered by a bug report — verified live (frontend compiles, mid-term legend renders the shifted ranges and caption, complete-record legend is unchanged from before).

## Round 4 — hyperparameter tuning check (XGBoost sub-model)

**Question:** are the ensemble's current XGBoost hyperparameters (`n_estimators=200, max_depth=4, learning_rate=0.05`) near-optimal, or was a better configuration ever actually checked? They had never been tuned — they were the values chosen when the ensemble was first built. This check does not change what's live; it's a "checked, not assumed" pass, per the project's standing rule that the live model is never auto-promoted.

**Step 1 — grid search on the validation split.** 36-point grid (`max_depth ∈ {3,4,5,6}`, `learning_rate ∈ {0.01,0.05,0.1}`, `n_estimators ∈ {100,200,300}`), RandomForest sub-model held fixed at its current config, SMOTE-resampled training set reused across all 36 XGBoost fits, evaluated on the honest validation split (`prepare_data_3way()`, never the test split) at the deployed threshold (0.5):

| Config | Fail Recall | Fail Precision | Fail F1 | PR-AUC |
|---|---|---|---|---|
| Current live (depth=4, lr=0.05, n=200) | 0.7872 | 0.7205 | 0.7524 | 0.8566 |
| Best by recall (depth=3, lr=0.01, n=100) | 0.8436 | 0.5917 | — | — |
| **Pareto-dominant candidate (depth=3, lr=0.05, n=300)** | **0.7985** (+1.13pp) | **0.7209** (+0.04pp) | — | — |

Of all 36 points, exactly 2 genuinely dominated the current config (equal-or-better on both recall and precision, strictly better on at least one — not a single-metric cherry-pick). `depth=3, lr=0.05, n_estimators=300` was the strongest: +1.13pp recall for effectively free (+0.04pp precision, not a tradeoff). This looked like a real, checked improvement.

**Step 2 — registered it as a real candidate, not a hypothesis.** `train_model.py` was refactored to expose `XGB_PARAMS`/`RF_PARAMS` as named constants (behavior-neutral change — verified via full test suite, 21/21 passing before and after) so a candidate run could override them without touching the live defaults. The tuned config was run through the actual training pipeline (`train_model.main()`), producing a real registered version (`20260807_134847`, not live) with its own bias audit and metadata.

**Step 3 — the comparison against live did not confirm the validation-split finding, for an honest, checked reason.** `compare_and_promote.py 20260807_134847` reported the candidate as **meaningfully worse** than live (recall −5.65pp). This was surprising given Step 1 — so it was checked further rather than reported at face value. The candidate differed from live in *two* ways at once: tuned hyperparameters, **and** training data (the candidate trained on this session's refreshed dataset, 65,903 rows, vs. live's 58,267 — a real data change, not a re-run of the same data). The registry comparison also evaluates on the held-out **test** split, not the validation split the grid search used. Three variables were confounded in one comparison.

To isolate the hyperparameter effect alone, a second candidate (`20260807_135223`) was registered with the **unchanged default hyperparameters** on the **same refreshed data** — a same-data, same-split control:

| Version | Data | Hyperparameters | Fail Precision | Fail Recall | Fail F1 |
|---|---|---|---|---|---|
| Live (`20260715_132655`) | old (58,267 rows) | default (depth=4, lr=0.05, n=200) | 0.7695 | 0.8374 | 0.8020 |
| Control (`20260807_135223`) | **new** (65,903 rows) | default (depth=4, lr=0.05, n=200) | 0.7992 | 0.7860 | 0.7925 |
| Tuned candidate (`20260807_134847`) | **new** (65,903 rows) | tuned (depth=3, lr=0.05, n=300) | 0.7948 | 0.7809 | 0.7878 |

- **Isolated hyperparameter effect** (tuned − control, same data, same test split): precision −0.44pp, recall −0.51pp. Effectively a wash, if anything a slight regression — this **does not replicate** the +1.13pp recall / +0.04pp precision improvement found on the validation split in Step 1.
- **Data-refresh effect alone** (control − live, same default hyperparameters, old vs. new data): precision +2.96pp, **recall −5.13pp**. This — not the hyperparameter tuning — is what actually drives the "meaningfully worse" verdict against live.

**Conclusion: the current hyperparameters are near-optimal.** The apparent validation-split improvement in Step 1 did not hold up under a same-data, same-split, controlled re-check on the test split, so it's treated as within-noise for a single grid search rather than a real signal — a single 36-point grid on one validation split is not enough evidence to override a value that then fails to replicate under a cleaner comparison. **Both experimental versions remain registered but not live** (`20260807_134847`, `20260807_135223`) — neither was promoted, per the project's standing never-auto-promote rule. The genuinely interesting finding here is the **data-refresh effect**: retraining on this session's refreshed dataset alone (holding hyperparameters constant) shifts fail-recall down 5.13pp and fail-precision up 2.96pp relative to the currently-live model. That's a separate, real signal about the refreshed data's distribution — outside this check's scope, but worth flagging for whoever next reviews whether the live model should be retrained on current data (see README's Known Open Items).

## Round 5 — mid-term-model calibration correction

**Premise correction, first.** This task assumed "the mid-term model was found earlier to understate pass probability by 15-30pp" — that assumption traces to the Round 1/Step 6 calibration table above, which this pass confirmed is actually the **complete-record model's** calibration, mislabeled and cross-referenced elsewhere in this document as the mid-term model's. **The mid-term model's own calibration had never been measured before this round.** Checked directly rather than assumed.

**Step 1 — measured the mid-term model's real calibration.** Fit the deployed-equivalent ensemble the same way `train_simulated_progress.py` always has (train+val, `<25.3`), scored the untouched TEST period (`25.3`, 33,990 simulated rows):

| Predicted P(Pass) | N | Actual pass rate |
|---|---|---|
| 0–10% | 1,523 | 12.9% |
| 10–20% | 664 | 44.1% |
| 20–30% | 694 | 54.9% |
| 30–40% | 769 | 69.1% |
| 40–50% | 993 | 73.1% |
| 50–60% | 1,747 | 86.2% |
| 60–70% | 2,621 | 89.5% |
| 70–80% | 4,381 | 93.7% |
| 80–90% | 8,497 | 96.7% |
| 90–100% | 12,101 | 98.9% |

**Mean absolute calibration error (N-weighted): 13.33pp.** The premise turns out to be directionally correct by coincidence, not because it was ever actually checked — the mid-term model is even more miscalibrated than the complete-record model it got confused with (ROC-AUC 0.893 here vs. 0.966 for the complete-record model — a genuinely different, less confident model, consistent with predicting off partial records).

**Step 2 — fit and applied a Platt-scaling calibrator.** Fit on the TRAIN-ONLY model's out-of-sample validation predictions (never on the data being evaluated, and never on TEST) — `LogisticRegression` on `(raw P(fail), true label)` pairs. Applied to the deployed model's TEST predictions:

| Predicted P(Pass), calibrated | N | Actual pass rate |
|---|---|---|
| 10–20% | 1,125 | 4.8% |
| 20–30% | 616 | 37.5% |
| 30–40% | 467 | 46.0% |
| 40–50% | 443 | 52.6% |
| 50–60% | 412 | 59.2% |
| 60–70% | 531 | 71.6% |
| 70–80% | 770 | 72.9% |
| 80–90% | 1,995 | 84.7% |
| 90–100% | 27,631 | 96.5% |

**Mean absolute calibration error drops from 13.33pp to 2.23pp.** ROC-AUC is unchanged (0.8933 before and after, as expected — Platt scaling is a strictly-monotonic transform, so it can't change ranking, only what number is displayed for a given rank).

**Step 3 — implemented as an additive field, deliberately not a silent replacement.** Because Platt scaling is strictly monotonic, thresholding the *calibrated* probability at `calibrator(raw_threshold)` flags exactly the same students as thresholding the *raw* probability at `raw_threshold` — so the Fail/Pass label, recall, and precision are mathematically unchanged by calibration; only the displayed number can change. `train_simulated_progress.py` now fits this calibrator and saves it into the model package (`calibrator`, `calibrated_decision_threshold`, `calibration_mace_before_pp`/`_after_pp` — Step B2/E in that script). *(At the time of Round 5 that package was written straight to `best_model_simulated_progress.pkl`; since Round 8 it is registered as a versioned `models_simulated/model_<timestamp>.pkl` instead — the calibrator fields are unchanged, only the destination.)* `predictor.py`'s `predict_partial()` exposes it as a new **`probability_calibrated`** field alongside the existing `probability` — verified directly: an ICT101 mid-term case (ME 45/50) returns `probability=63.9`, `probability_calibrated=92.1` — the raw number was understating this student's real pass likelihood by nearly 30 percentage points.

**Why `probability`/`prediction`/`risk_band` were deliberately left untouched.** `_compute_risk_band`'s Safe floor is derived from whichever threshold produced the label (`max(65, 100×(1−threshold))`), by design (Round 3) — displaying a calibrated probability while still deriving the floor from the *raw* threshold would reopen the exact Fail/Safe contradiction Round 3 fixed. The consistent alternative — deriving the floor from the *calibrated* threshold too — was computed and checked: the mid-term model's decision threshold (currently 0.30, honestly re-validated on this session's refreshed data — it was 0.25 historically) corresponds to a calibrated fail-probability of just 0.054. Plugged into the same floor formula, that pushes the mid-term Safe floor from 70% to **95%**, not down toward the complete-record model's 65%. This is a real, re-tested finding (not the mid-term model being buggy — it's an honest consequence of validating that threshold for 80–85% recall: catching most true fails requires flagging students who are, on a calibrated basis, actually just an ~5% fail risk). Silently shipping a 95% Safe floor — where a mid-term prediction is "At Risk" unless the model is calibrated-confident to 95%+ — is a real product-behavior change for lecturers, not a small tweak, so it wasn't made unilaterally here.

**Re-tested (not assumed): does calibration let the dual risk-scale UI collapse to one shared scale? No — it makes the two floors diverge further, not converge.**

| | Safe floor before calibration | Safe floor if fully switched to calibrated probability |
|---|---|---|
| Complete-record model (`predict()`) | 65% (unchanged — out of this round's scope) | — |
| Mid-term model (`predict_partial()`) | 70% (raw threshold 0.30) | **95%** (calibrated threshold 0.054) |

The gap between the two models' Safe floors was 5pp before this round (65 vs. 70) and would become 30pp (65 vs. 95) if the mid-term model's risk band were switched onto the calibrated scale — the opposite of unification. Unifying the two scales for real would require calibrating *both* models consistently and likely redesigning `_compute_risk_band`'s floor formula itself (it wasn't built with calibrated probabilities in mind) — a bigger, more precisely-scoped follow-up than this round, flagged in README's Known Open Items rather than attempted here.

**Also discovered as a side effect, fixed rather than left stale:** the frontend (`PredictorView.jsx`) hardcoded the mid-term Safe floor as `"75%"` in its legend text and band ranges — stale even before this round's threshold change (the actual value was already 70% once the threshold moved from 0.25 to 0.30 during this round's retrain on refreshed data, echoing Round 4's data-refresh finding). Fixed by exposing the real value from the backend (`predictor.py`'s new `_safe_floor()` helper → `safe_floor_percent` field on both `predict()` and `predict_partial()` responses) and reading it dynamically in the frontend instead of a hardcoded number, so this can't silently go stale again on the next retrain. Verified: `PredictorView.test.jsx`'s 3 existing tests still pass; full backend suite still 21/21 passing.

## Round 6 — the 5.13pp recall drop, investigated

Round 4's hyperparameter check found the live model's headline recall (0.8374) sits 5.13pp above a same-hyperparameter control retrained on refreshed data (0.7860), and flagged it for later review rather than explaining it. Investigated for real here.

**Step 1 — confirm no period-label confound.** Both the live model (`20260715_132655`) and the control candidate (`20260807_135223`) report `validated_on: 25.3` — same nominal period, not a validation/test split mismatch. But their test-set `support` (fail count) differs: 953 (live) vs. 972 (control) — a direct signal that "period 25.3" doesn't mean the same underlying rows in both runs. Confirmed by directly rebuilding period `25.3`'s test set from the OLD archived file (`data/archive/Capstone_data_20260324.csv`) and the NEW refreshed file (`ingested_capstone.csv`) side by side:

| | N | Fails | Fail rate |
|---|---|---|---|
| OLD data, period 25.3 | 8,934 | 1,183 | 13.24% |
| NEW data, period 25.3 | 8,928 | 972 | 10.89% |

**Step 2 — is this new students (calendar growth) or relabeled old ones?** Enrolment-key overlap (`STUDENTID_MASKED`+`SUBJECTCODE`): 8,928 of 8,934 old enrolments are also in the new set (only 6 old-only, 0 new-only). This is essentially the **same roster** — not new students joining as time passed. For the 8,928 common enrolments, the PASS label was compared directly: **205 flipped Fail→Pass, 0 flipped Pass→Fail.** Zero flips in the "wrong" direction rules out random noise or a symmetric relabeling artifact — this is a one-directional correction. Old fails within the common set: 1,177. New: 972. `1,177 − 205 = 972` — exact.

**Step 3 — feature distributions barely moved; this is a label-derivation change, not a feature/input change.** Mean `ASSESS1_MARK`/`ASSESS2_MARK`/`PARTIAL_WEIGHTED_SCORE` for the common enrolments shifted by well under 1 point old→new. The features students are scored on didn't change — what changed is how `build_target()`'s full-assessment PASS computation resolves for a subset of enrolments. Initially only correlated with the resit-collapsing row-count difference (200 old vs. 214 new rows collapsed dataset-wide); **confirmed as the actual mechanism, not left as a correlation** — see Step 3b.

**Step 3b — resit-collapsing confirmed as the mechanism, with a real overlap number, not an assumption.** Built the exact list of all 205 flipped `(student, subject)` enrolments, then independently built the exact list of enrolments whose winning-`ATTEMPTNUMBER`-per-assessment-type (the quantity `collapse_attempts_to_latest_per_type()` selects on) differs between the old and new raw data for period `25.3`. **Overlap: 205 of 205 (100%).** Every single flipped enrolment has a winning-attempt change; zero have unchanged winning attempts with some other explanation (checked directly: 0 enrolments had a same-attempt value change, 0 had an assessment-type-set change). Spot-checked three at random against the raw rows directly — the pattern is consistent and clear: the OLD extract only contains attempt 1 for these students (a failing attempt — e.g. `Student5095/MBA910`'s attempt 1 has a 0% mark on a 30%-weighted item), while the NEW extract additionally contains a later attempt (2, sometimes 3) for the *same* assessment types with materially better marks, which `collapse_attempts_to_latest_per_type()` correctly selects as the winner in the new data but couldn't in the old data because that attempt simply wasn't present in that extract. **The collapsing logic itself did not change and is not buggy in either version — it is working correctly on both inputs.** The mechanism is that the refreshed source data now contains resit/later-attempt records for these 205 students that the earlier extract didn't have, and the label correction is a direct, correct consequence of that richer attempt history becoming available.

**Step 4 — explanation (a) vs (b), tested directly, not asserted.** Loaded the actual frozen `20260715_132655` model object (no retraining) and scored it against both test sets. There is no "retrained control evaluated on OLD data" row in the table below because the control candidate (`20260807_135223`) was only ever trained on the new data — the old data is superseded and scoring a new-data-trained model against old, now-known-to-be-wrong ground truth would not be a meaningful comparison (it would misleadingly penalize the model for correctly disagreeing with labels since shown to be incorrect):

| | Precision | Recall | PR-AUC |
|---|---|---|---|
| Frozen live model on OLD 25.3 test (sanity check vs. registry's 0.7695/0.8374) | 0.7824 | 0.8419 | 0.9052 |
| Frozen live model on NEW 25.3 test | 0.7326 | 0.8230 | 0.8770 |
| Control candidate, retrained on NEW data, on NEW 25.3 test (registry) | 0.7992 | 0.7860 | — |

**Conclusion — a quantified mix, not ambiguous.** The full 5.13pp gap decomposes into two real, measured components:
- **~1.9pp (37%): pure ground-truth change.** Holding the model completely frozen, recall drops from 0.8419 to 0.8230 purely because the test set's labels were corrected. This alone rules out "the world drifted and the model is stale" (explanation a) as the primary story — nothing about calendar time or new students is involved, since the roster is 99.9% identical.
- **~3.7pp (63%, the majority): a retraining effect.** Going from the frozen model (0.8230 on new test) to a model actually retrained on the new training data (0.7860 on the same new test set) accounts for the larger share. The new training data has the same one-directional Fail→Pass correction applied broadly (dataset-wide fail rate 12.02%→11.42%), so a model trained on it learns a genuinely different, less aggressive decision boundary for borderline early-mark cases — a real consequence of training on corrected labels, not a bug.

**This is explanation (b), new-data correction — confirmed with a 100% overlap, not a correlation — and not (a), staleness in the "world changed" sense.** The one-directional 205-flip pattern (Fail→Pass, never the reverse), now traced to a confirmed, single mechanism (richer resit/attempt history in the new extract, correctly processed by unchanged, non-buggy resit-collapsing logic), is the signature of a genuine correction, not noise or a new bug introduced by the refresh.

**Stated plainly, not softened: as of 2026-08-08, `0.8374` should not be cited as this model's current fail-class recall without this caveat attached.** It was partly earned against ground-truth labels for 205 real students that have since been directly shown wrong — not a hypothetical concern, a confirmed, 100%-traced one. **`0.7860` (the same architecture and hyperparameters, evaluated against the corrected labels) is the more trustworthy figure as of this date.** This is the same standard of directness this card already applies elsewhere (e.g. the SMOTE/ensemble findings above) — a number measured against since-corrected ground truth doesn't get to keep standing as "current performance" just because retraining hasn't happened yet.

**Recommendation.** This is not normal period-to-period variance (a 100%-one-directional flip pattern isn't sampling noise) and it is not a new pipeline bug needing a fix before the next training run (the resit-collapsing logic is confirmed correct on both inputs — it's the *old* model/label pair that's out of date, not the new pipeline that's broken). The live model's headline recall number is **no longer an accurate representation of current performance** and should be re-validated. **Per the project's standing rule, nothing is promoted here — this is diagnosis only.** A real candidate reflecting the corrected data already exists in the registry (`20260807_135223`, not live); whether to promote it is a deliberate decision for whoever reviews this next, now backed by a fully-traced, quantified reason rather than an unexplained number.

## Round 7 — attendance as a model feature + the recall regression, combined

**Goal:** add `ATTENDANCE_RATE` (confirmed 0.32–0.62 correlation with outcomes, never previously used as a feature) to both models, and re-tune class-imbalance handling for the new label distribution, in one combined retrain — so both effects could be measured together against the Round 6 baseline (`0.7860` recall, corrected labels, no attendance). Registration only; nothing promoted for the complete-record model, per the standing rule (the mid-term model's status is different — see Step 7).

### Step 1 — the class-imbalance hypothesis, checked before acting on it

Training-set (not test-set) fail-class proportion: **12.42% (old data) → 12.24% (new data), a −0.18pp shift.** This is far smaller than the 2.35pp shift found in the *test* period specifically (Round 6) — the 205 label corrections are concentrated in the most-recently-added period, not spread proportionally across the training range. **Conclusion: re-tuning is not justified by this evidence, and was not performed.** Additionally, the current implementation is already self-adjusting and has no fixed ratio to "update": `SMOTE(random_state=42)` uses the default `sampling_strategy="auto"` (full 1:1 balance regardless of input ratio), and `RandomForestClassifier(class_weight="balanced")` recomputes weights from whatever `y` it's actually fit on, every time. Neither has a value baked in from "the old class balance."

### Step 2 — ATTENDANCE_RATE added, with real correlation and match-rate checks first

- **Feature selection**: `ATTENDANCE_RATE`, `UNEXPLAINED_ABSENCE_RATE`, and `ABSENCE_RATE` are constrained to sum to exactly 1.0 (`build_attendance_features.py`'s own assert) — any two fully determine the third. Real correlation matrix: ATTENDANCE_RATE vs UNEXPLAINED_ABSENCE_RATE = **−0.744**, vs ABSENCE_RATE = **−0.386**. Given the exact linear dependency, only `ATTENDANCE_RATE` was added — including two or three would be pure redundancy, not new signal.
- **Match rate**: 100% (74,831/74,831 enrolments) for the complete-record model — no imputation needed, confirmed directly rather than assumed.
- **Mid-term leakage boundary, explicit**: a student's full/final attendance rate is never used as an input to the mid-term model — the same leakage class as the earlier 100%-accuracy mid-term incident. `build_simulated_progress_features()` now truncates each enrolment's attendance sessions (sorted by `class_no, actv_no, cls_session_no` — the only ordering proxy available; this dataset has no real date field, the same limitation the DARBY building investigation ran into) to the *same achieved-coverage fraction* as that synthetic snapshot's marks. Only 46 of 287,174 synthetic snapshots (0.02%) truncated to zero available sessions; those were imputed with the population mean ATTENDANCE_RATE, reported, not silently dropped or zeroed.
- **Serving-side wiring**: `predictor.py`'s `predict()`/`predict_partial()` now build their feature vector from `_PACKAGE["features"]`/`_SIM_PACKAGE["features"]` (stored at training time) rather than a hardcoded column order — this is what let the still-live 10-feature complete-record model keep working unchanged throughout this entire round, while the (now-live, see Step 7) 11-feature mid-term model works correctly too, with no code branch needed per model version.

### Step 3 — imbalance handling: not re-tuned, per Step 1's own evidence

No SMOTE/class-weight change was made. This is the honest consequence of Step 1, not a skipped step.

### Step 4 — retrain and fair comparison

Registered `20260808_110630` (attendance + Step 1's data, default hyperparameters, no imbalance retune) and compared against the Round 6 baseline and the frozen live model, all on the **identical** new-data period-25.3 test set (row-level identity confirmed: same `prepare_data()` call against the same `ingested_capstone.csv`, 8,928 rows in every case):

| Model | Precision | Recall | PR-AUC |
|---|---|---|---|
| Frozen live (`20260715_132655`) on OLD test (sanity check) | 0.7824 | 0.8419 | 0.9052 |
| Frozen live (`20260715_132655`) on NEW test | 0.7326 | 0.8230 | 0.8770 |
| Corrected-labels-only candidate (`20260807_135223`, no attendance) | 0.7992 | 0.7860 | 0.8790 |
| **Attendance + corrected-labels candidate (`20260808_110630`)** | **0.7931** | **0.7809** | **0.8808** |

**Plain answer, not rounded up: attendance does not recover the lost recall.** Recall actually moved slightly further away from the frozen-live-on-new-data figure (0.7809 vs. the no-attendance candidate's 0.7860 — a further −0.51pp), still 4.21pp below 0.8230. Precision also ticked down slightly (−0.61pp). The one real, positive signal is PR-AUC: 0.8790 → 0.8808, a small but genuine (fixed random seeds — not run-to-run noise) ranking-quality improvement. **Interpretation: attendance carries real but weak signal (consistent with SHAP ranking it mid-pack, Step 5) that marginally improves ranking quality without improving classification at the current 0.5 threshold — it is not the fix for the Round 6 recall regression, which remains a real, open item.** `compare_and_promote.py 20260808_110630` against the original live model: precision +0.0236, recall **−0.0565**, verdict **MEANINGFULLY WORSE** — consistent with, not a new instance of, the already-documented Round 6 data-refresh effect (most of the "worse" verdict traces to the corrected labels, not to attendance).

### Step 5 — SHAP verified for real, without touching the still-live model's cache

Mean |SHAP value| for `ATTENDANCE_RATE`, computed against the new candidate directly (not the cached production background — see below), ranked over 50 real test rows:

| Rank | Feature | Mean \|SHAP\| |
|---|---|---|
| 1 | PARTIAL_WEIGHTED_SCORE | 0.1009 |
| 2 | ASSESS1_MARK | 0.0461 |
| 3 | ASSESS2_MARK | 0.0422 |
| 4 | TRIMESTER_NUM | 0.0212 |
| 5 | ASSESS1_CONTRIBUTION | 0.0197 |
| **6** | **ATTENDANCE_RATE** | **0.0144** |
| 7 | PARTIAL_WEIGHT_COVERAGE | 0.0143 |
| 8 | SUBJECT_DIFFICULTY | 0.0122 |
| 9–11 | ASSESS2_CONTRIBUTION, ASSESS2_WEIGHT, ASSESS1_WEIGHT | 0.0093 / 0.0055 / 0.0051 |

**A real, mid-tier factor — 6th of 11, not buried.** Reconstruction check (`base_value + sum(shap_values) ≈ model output`) holds: max deviation 6.01e-08 over 50 rows.

**Deliberately NOT applied to the production `shap_background_main.pkl`.** That cache is shared globally with whatever model is currently live — at the time of this check, the complete-record live model was still the old, un-promoted 10-feature version. Overwriting the cache with an 11-column background would have broken every real, live complete-record explanation with a shape mismatch. Verified in isolation instead: a fresh 100-row background sampled in-memory from the candidate's own training data, never written to disk.

### Step 6 — What-If Simulator UI

Added an "Attendance rate (%)" field to the What-If form, matching the existing FE/ME/CP/GR/TX style. Left blank by default; `/api/predict` fills in that subject's real average `ATTENDANCE_RATE` (from `_ATTENDANCE`, the same `build_attendance_features()` output already loaded at startup) when omitted, and reports `attendance_rate_is_default: true` in the response — the frontend shows an explicit caption ("Attendance rate defaulted to this subject's real average (X%) — not a value you entered") whenever that happens, never silently.

**Verified the prediction actually shifts, with a real example** (called the live `predict()` code path directly against the new candidate, not a mocked function): same borderline marks (FE 48/50, ME 52/30 — a case near the decision boundary, chosen deliberately since a confident case has little room to move):

| Attendance | Probability | Prediction |
|---|---|---|
| 90% | 57.7% | **Pass** |
| 70% | 45.1% | Fail |
| 50% | 43.3% | Fail |
| 40% | 42.6% | Fail |
| 20% | 40.8% | Fail |

A 16.9-percentage-point swing that flips the actual Pass/Fail label — real, meaningful influence, not a token wiring exercise.

### Step 7 — tests, registration, and an honest note on what actually went live

- **Backend: 21/21 passing** — but not on the first run. Retraining the mid-term/simulated-progress model (see below) broke `test_predict_shap_explanation_matches_live_model` (SHAP reconstruction check failing, `sum_check_ok: False`) because `shap_background_simulated.pkl` still had 10 columns against an now-11-feature live model. Caught, diagnosed, and fixed by regenerating that one background file (and only that one — `shap_background_main.pkl` deliberately left alone, see Step 5). Re-ran after the fix: 21/21.
- **Frontend: 3/3 passing.**
- **Complete-record model: registered, NOT live.** `20260808_110630` is a real, registered candidate; `compare_and_promote.py` reports it MEANINGFULLY WORSE than the original live version (see Step 4); nothing was promoted.
- **Mid-term/simulated-progress model: this one went live immediately, not just registered — by this model family's behavior at the time, not a new decision made here.** `best_model_simulated_progress.pkl` had no promotion gate (documented earlier this session, Rounds 4–5) — running `train_simulated_progress.py` to add attendance overwrote the file `predictor.py` loads directly, the same way the calibration and hyperparameter work in Rounds 4–5 did. Stated plainly so this isn't discovered later as a surprise: real mid-term predictions now require and use attendance data, and the model itself was refit on the current (corrected-label) data as a side effect, with a re-selected decision threshold and a freshly-fit Platt calibrator, all captured in this same retrain. **Since fixed — see Round 8**: this model family now has a real promotion gate (`sim_model_registry.py` / `compare_and_promote_simulated.py`), so an ungated retrain can no longer go live.

## Round 8 — mid-term promotion gate, and confirming its comparison wasn't confounded

Two things happened after Round 7: the missing promotion gate for the mid-term model family was built, and the comparison that justified keeping the attendance version live was re-checked for a specific confound rather than taken at face value.

### The gate (context for the comparison below)

`train_simulated_progress.py` had no promotion gate — it overwrote `best_model_simulated_progress.pkl` directly, live immediately, with no versioning, comparison, or rollback path. Round 7's attendance retrain went live that way. Fixed with `sim_model_registry.py` + `compare_and_promote_simulated.py`, mirroring the complete-record model's register-then-explicitly-promote pattern and reusing its identical >3pp refuse-if-worse threshold; `predictor.py` now loads the live mid-term model from that registry rather than a hardcoded path. Full account in README's [Mid-semester prediction](README.md) section, including the fact that no backup of the pre-attendance version existed and it was recoverable only by chance from an unrelated Docker image layer.

### The confound question

The pre-attendance baseline (`20260808_030637`) was recovered from a Docker image, not from a controlled experiment — so it was **not** self-evident that it had been trained on the same corrected-label data as the attendance version (`20260808_113534`). If it predated this session's 205 Fail→Pass label corrections, then its reported +0.67pp recall advantage would be a tangled "pre-correction vs post-correction *and* attendance" result, not a clean attendance effect. This matters because the complete-record model showed the label correction **alone** moves recall by −3.7pp — an effect large enough to swamp a +0.67pp signal entirely.

**Checked directly, two independent ways. The comparison is clean.**

**Evidence 1 — the test set fingerprints differ sharply between the two data vintages, and both versions carry the post-correction one.** Rebuilding the simulated-progress split from each raw file:

| Raw data | Sim-progress test rows | Test fails |
|---|---|---|
| PRE-correction (`data/archive/Capstone_data_20260324.csv`) | 34,028 | **4,516** |
| POST-correction (`ingested_capstone.csv`) | 33,990 | **3,725** |

Both registered mid-term versions store `classification_report["Fail"]["support"] = 3725.0` — an exact match to the post-correction split, and nowhere near the pre-correction 4,516. A pre-correction baseline could not report 3,725.

**Evidence 2 — the recovered baseline's stored metrics reproduce exactly when re-scored on the current corrected test set.** Scoring both model objects head-to-head on the identical current test set returned precision 0.3365 / recall 0.8140 for the recovered version and 0.3390 / 0.8207 for the attendance version — matching each version's own stored `classification_report` to four decimal places. A model whose stored report had been computed against a *different* (pre-correction) test set would not reproduce its own numbers on this one.

**Conclusion: both mid-term versions were trained and evaluated on the same corrected-label data, differing only in the presence of `ATTENDANCE_RATE` (10 features vs. 11).** The Round 7 / gate-promotion figures stand as a genuine, isolated attendance effect:

| | Precision | Recall | F1 | PR-AUC |
|---|---|---|---|---|
| Mid-term, corrected labels, **no** attendance (`20260808_030637`) | 0.3365 | 0.8140 | 0.4761 | 0.6779 |
| Mid-term, corrected labels, **with** attendance (`20260808_113534`) | 0.3390 | 0.8207 | 0.4798 | 0.6812 |
| Delta | +0.25pp | **+0.67pp** | +0.37pp | +0.33pp |

No new training run was needed to resolve this, and nothing was promoted or changed as a result — this was verification of an existing report's validity, not a promotion decision.

### Why attendance helps the mid-term model but not the complete-record one — a plausible reading, not a proven mechanism

The two results genuinely point in opposite directions: attendance gives the mid-term model a small all-metric improvement (+0.67pp recall), while for the complete-record model it was a wash-to-slightly-negative (−0.51pp recall, Round 7 Step 4). A reasonable interpretation, consistent with the SHAP evidence but **not** established causally here:

The complete-record model already sees a student's *entire* graded record — `PARTIAL_WEIGHTED_SCORE` alone dominates its SHAP attributions (0.1009 mean |SHAP|, more than double the next feature). When the marks signal is that complete and that strong, there is little independent variance left for attendance to explain, so adding it mostly adds noise at a fixed threshold. The mid-term model, by construction, sees only a truncated 15–90% slice of the marks — a deliberately weaker primary signal — which leaves more room for a second, partly-independent behavioural signal to contribute. Its much lower PR-AUC (0.68 vs. the complete-record model's 0.88) reflects how much harder its task is, and a harder task is where an extra weak signal has the most room to help.

Stated as a hypothesis because it hasn't been isolated: confirming it would need something like an ablation across truncation levels (does attendance's contribution shrink monotonically as coverage rises toward 100%?), which was not run. The measured facts are the two deltas above and the SHAP ranking; the explanation connecting them is inference.

## Round 9 — why every retrain "underperformed" the frozen model (it didn't)

Three independent retrains this session — corrected labels only, corrected + tuned hyperparameters, corrected + attendance — all landed at 0.78–0.79 fail-class recall, while the frozen live model **re-scored** (not retrained) on the same corrected test set scored 0.8230. That convergence across three unrelated changes pointed at the corrected data itself rather than at any one change. Investigated for a mechanism rather than attempting a fourth retrain.

### First correction: the training labels changed far more than previously measured

Earlier rounds counted 205 flips because they only looked at period `25.3` (the test period). Across **all** periods there are **428** label flips, **223 of them inside the training range** — and, as before, **every single one is Fail→Pass, zero in the reverse direction**. Training-set fail count: **7,815 → 7,570** (−245: the 223 flips plus 22 enrolments dropped by the refreshed extract's filters). Round 7's "−0.18pp, barely moved" figure was measured on the 3-way split (which excludes `25.2`, where 143 of the flips live) and understated the change to the 2-way training split the retrains actually use (11.854% → 11.487%).

### Step 1 — the shrinking-minority-class hypothesis, tested with a matched control. Ruled out.

Same number of fails removed, differing only in *which* rows. All four trained identically (10 features, same SMOTE/ensemble config) and evaluated on the same corrected test set:

| Variant | Train fails | Precision | Recall | F1 | PR-AUC |
|---|---|---|---|---|---|
| BASELINE — old data, old labels | 7,815 | 0.7423 | 0.8179 | 0.7783 | 0.8781 |
| **RANDOM** — 223 *randomly chosen* fails flipped to Pass | 7,592 | 0.7352 | **0.8169** | 0.7739 | 0.8772 |
| **REAL** — the 223 *genuinely corrected* enrolments flipped | 7,592 | 0.7848 | **0.7881** | 0.7864 | 0.8777 |
| NEW — fully corrected training data | 7,570 | 0.7992 | 0.7860 | 0.7925 | 0.8790 |

Removing 223 fails **at random** costs **0.10pp** of recall — nothing. Applying the **same number** of *real* corrections costs **2.98pp**. **Quantity is ruled out**; the identity of those specific rows is doing all the work. Note also that REAL (0.7881) lands essentially on NEW (0.7860), so the training-set corrections account for nearly the whole difference between an old-trained and new-trained model.

### Step 2 — the corrected enrolments are systematically borderline passers. Supported.

Feature means for the 428 corrected enrolments versus the two reference populations (as labelled now):

| Feature | Corrected (428) | Still-Fail | Ordinary Pass |
|---|---|---|---|
| `PARTIAL_WEIGHTED_SCORE` | 40.90 | 17.87 | 45.67 |
| `ASSESS1_MARK` | 56.06 | 21.16 | 63.96 |
| `ASSESS2_MARK` | 69.62 | 34.27 | 71.05 |
| `SUBJECT_DIFFICULTY` | 0.21 | 0.23 | 0.16 |

On every input feature the corrected rows look **much more like passers than like fails** — `ASSESS2_MARK` is essentially identical to ordinary passers. Their final weighted scores confirm they are *weak* passers: median 61.7 vs. 68.3 for ordinary passers, with **43.0%** falling in the 50–60 band versus **21.9%** of ordinary passers — roughly double the concentration just above the 50 pass mark.

**This yields a coherent mechanism.** Under the old labels, those 428 pass-looking enrolments were marked Fail. That is label noise pointing in one consistent direction, and training on it taught the model that a set of clearly pass-like feature patterns meant "fail" — biasing its boundary toward predicting Fail. A boundary biased toward Fail mechanically **inflates recall and depresses precision**. Correcting the labels removes that false lesson, so the model becomes more conservative about calling Fail: recall down, precision up. The controlled experiment shows exactly that signature — REAL corrections moved recall −2.98pp and precision **+4.25pp**.

### Step 3 — the frozen model's 0.8230 is an operating point, not superiority

All four models on the identical corrected test set, at their deployed 0.50 threshold:

| Model | Feat | Precision | Recall | F1 | PR-AUC |
|---|---|---|---|---|---|
| **Frozen live, re-scored (not retrained)** | 10 | **0.7326** | **0.8230** | **0.7752** | **0.8770** |
| Retrain: corrected labels only | 10 | 0.7992 | 0.7860 | **0.7925** | 0.8790 |
| Retrain: corrected + tuned hyperparameters | 10 | 0.7948 | 0.7809 | 0.7878 | 0.8781 |
| Retrain: corrected + attendance | 11 | 0.7931 | 0.7809 | 0.7869 | **0.8808** |

**The frozen model is last on F1 and last on PR-AUC.** It leads on exactly one metric — recall — which is the metric this project has emphasized most, and precisely the metric a Fail-biased boundary inflates. Its precision is ~6.7pp *below* every retrain.

Decisive check: sweeping the corrected-labels retrain's threshold down to **0.405** matches the frozen model's recall (0.8261 vs. 0.8230) at precision **0.7333 vs. 0.7326** — equal-or-better on *both* metrics simultaneously. **The frozen model does not dominate at any operating point.** The 5.13pp "recall gap" is a difference in where each model's threshold sits on essentially the same (slightly better) precision–recall curve, not a difference in capability.

### Conclusion — (b), with the gap reframed as not being a regression at all

The evidence supports **(b): the corrected enrolments are systematically borderline cases**, and the mechanism is specifically that the *old* labels contained one-directional noise that biased the old model toward predicting Fail. Explanation (a), pure class-imbalance/quantity, is ruled out by the random-control experiment (0.10pp vs. 2.98pp). No estimated split between mechanisms is needed — the control isolates it cleanly.

The stronger conclusion, which supersedes how earlier rounds framed this: **there is no recall regression to fix.** The retrains are not worse models. They are better-calibrated to corrected ground truth, they beat the frozen model on F1 and PR-AUC, and at matched recall they match or beat it on precision. The frozen model's 0.8230 was partly *earned by learning mislabeled data* — which is the same conclusion Round 6 reached about that number being measured against wrong ground truth, now extended: it was not only *measured* against bad labels, it was *trained* on them.

**Recommendation.** No further retraining or resampling work is warranted for this gap — the diagnosis is complete and nothing is broken. Practically:
- **Keep the live model as-is for now** — nothing was promoted or changed by this investigation, per the standing rule.
- **If 0.82+ recall is an operational requirement**, the lever is the decision threshold on a corrected-data model (≈0.405 reproduces it at equal precision), not more training data — and it should go through `validate_threshold.py` honestly rather than being set from this test-set sweep, which would be test-set tuning.
- **More data is not the blocker.** A genuinely new study period would help the model generally, but it is not needed to close this specific gap, because the gap is not a capability deficit.
- **Flagged for whoever reviews promotion next**: `compare_and_promote.py`'s gate refuses anything whose fail-class precision *or* recall drops >3pp against live. The corrected-labels retrain trips that rule on recall (−5.13pp) despite being better on F1, better on PR-AUC, and equal-or-better at matched recall. The gate would therefore block a genuinely better model. That is a real limitation of a fixed-threshold, single-metric-drop criterion, not a reason to `--force` past it casually — it deserves a deliberate decision about whether the gate should also consider F1/PR-AUC or evaluate at a matched operating point.
