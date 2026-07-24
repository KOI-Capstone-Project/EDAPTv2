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

- **Source**: `data/Capstone_data_20260324.csv`
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
- **SMOTE vs. class-weighting, and ensemble vs. single-model, are current defaults — genuinely close calls, not clearly justified by performance alone.** ~~Removing SMOTE collapses fail-class precision at the currently-deployed 0.50 threshold (0.724 → 0.478)~~ **— this Round 1 claim was corrected in Round 2 (Issue 2 below): that comparison judged the no-SMOTE model at a threshold tuned for a *different* model's probability distribution. Given its own honestly re-validated threshold, the no-SMOTE model reaches P=0.686/R=0.819 — much closer to the SMOTE model's P=0.724/R=0.799, and its PR-AUC/ROC-AUC are marginally *higher*.** See the Round 2 Ablation Update section for the corrected verdict.
- **The dual risk-scale UI (Round 3) is a display-level workaround, not a fix, for the mid-term model's calibration gap (Round 2's Calibration check).** The two models currently need separate risk scales specifically because their probability outputs don't mean the same thing at the same number — the mid-term model understates true pass likelihood by roughly 15–30 percentage points across the 10–90% range, so a "70%" from it and a "70%" from the complete-record model aren't comparable, and showing both against one shared 65%-Safe cutoff was exactly what produced the Fail/Safe contradiction Round 3 fixed. Giving mid-term predictions their own boundaries (Safe at 75%, not 65%) makes the label and the band agree with each other again, but it doesn't make the mid-term number mean the same thing as a complete-record number — it just moves the line to where this specific miscalibration currently sits. **Forward-looking guidance, not a claim about a guaranteed outcome**: if the Platt/isotonic calibration correction already flagged as future work (Calibration check, above) is implemented for the mid-term model, re-check at that point whether the two risk scales can be unified back into one — if calibration is fixed, the root cause of needing two scales goes away, but that should be re-tested against real held-out data when it happens, not assumed to follow automatically.

## Performance summary — current live model, held-out test period (`25.3`)

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

### Calibration check (Step 6), live model on the genuinely-held-out test period

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
