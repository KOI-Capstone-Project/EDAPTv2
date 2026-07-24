# EDAPT v2 — Model Methodology (Plain-Language Summary)

> A non-technical explanation of what algorithms the prediction system uses, what settings they run with, and how a prediction actually gets made. For the full technical validation (accuracy numbers, ablation tests, calibration, limitations), see [`model_card.md`](model_card.md).

---

## 1. The models used

The system uses **two different prediction methods together**, like getting a second opinion, rather than relying on just one.

| Model | Plain description |
|---|---|
| **XGBoost** | Builds hundreds of small decision rules, one after another, where each new rule is built specifically to fix the mistakes the previous ones made. Good at picking up subtle patterns. |
| **Random Forest** | Builds hundreds of independent decision trees, each trained on a different random slice of the data, then takes a majority vote among them. Good at being stable and not overreacting to unusual individual cases. |

Both give a probability (e.g. "78% likely to pass") rather than a flat yes/no. The final prediction is the **average of both models' probabilities** ("soft voting").

**Why two models instead of one?** Tested directly, head-to-head: a single XGBoost model scores about the same on general accuracy, but the two-model combination correctly identifies **3.5 percentage points more of the students who actually go on to fail** — confirmed twice, on two separate time periods. In a system meant to flag at-risk students early, catching more real at-risk cases outweighs the two approaches being otherwise similar overall.

There are, in fact, **two separate versions of this two-model setup**:

| | Used when | Trained on |
|---|---|---|
| **Main model** | A student has essentially all their assessments recorded (subject is complete or nearly complete) | Real, fully-graded historical student records |
| **Mid-term model** | A student only has some assessments recorded so far (a subject still in progress) | Synthetic "snapshots" built by taking real completed records and simulating what they looked like partway through, since genuine mid-term historical records don't exist in the dataset |

---

## 2. Handling imbalance: most students pass

In the real data, passing students greatly outnumber failing ones. Left alone, a model trained on that would learn "just guess pass every time" and still look fairly accurate on paper — while being useless at its actual job of flagging risk.

Two safeguards are used together:

- **SMOTE**: before training, additional *synthetic* examples of failing students are generated (mathematically interpolated between real failing students' data points, not invented from nothing), so the model sees a more balanced picture while learning.
- **Balanced class weighting**: the Random Forest half is separately told to penalize itself more heavily for missing a failing student, as a second layer of protection against the "just predict pass" shortcut.

---

## 3. What information the model looks at (its inputs)

Ten pieces of information per student, per subject, are fed in:

1. Mark on the first tracked assessment
2. Weighting of the first tracked assessment (how much it counts toward the final grade)
3. That assessment's actual contribution to the final grade (mark × weighting)
4. Mark on the second tracked assessment
5. Weighting of the second tracked assessment
6. That assessment's contribution
7. Weighted score so far, scaled up to a projected total
8. What percentage of the subject's total grade is covered by marks received so far
9. How historically difficult that specific subject is (its typical fail rate)
10. Which trimester/study period it is

**No demographic information** (age, gender, country) is used to make the prediction itself. Those fields are only used afterward, separately, to check that the model isn't systematically less accurate for any particular group — a fairness check, not an input to the prediction.

---

## 4. The tuning settings ("dials") on each model

| Setting | XGBoost | Random Forest | What it controls, in plain terms |
|---|---|---|---|
| Number of trees | 200 | 200 | How many decision rules it builds and combines |
| Max depth | 4 | 6 | How many yes/no questions deep each individual tree can go — kept shallow on purpose so it learns general patterns instead of memorizing noise |
| Learning rate | 0.05 | — (not applicable to Random Forest) | How large a correction each new tree makes — small and cautious, to avoid overreacting to any single mistake |
| Imbalance handling | via SMOTE (data-level fix, applied before either model trains) | `class_weight="balanced"` (model-level fix, applied during training) | Two separate, independent safeguards against ignoring failing students |

---

## 5. How a prediction actually gets decided

1. **Coverage check first.** The system checks how much of the subject's total grade is actually covered by marks entered so far.
   - **99.5% or more covered** → treated as a complete record → **main model** used.
   - **50% to 99.5% covered** → treated as a genuine mid-term estimate → **mid-term model** used, and the result is clearly labeled as a mid-term estimate, not a final call.
   - **Under 50% covered** → not enough information to predict responsibly → **no prediction is made at all**, rather than guessing from too little data.

2. **Both sub-models score the student**, each producing a probability of passing. Their two probabilities are averaged into one final probability.

3. **The probability is converted into a Pass/Fail call using a decision threshold** — the point at which the system switches from calling something "Pass" to calling it "Fail." This threshold is **not a guess or an arbitrary round number**: it was chosen by testing different candidate values against real, held-back data the model hadn't been tuned on, and picking the one that performed best honestly.
   - Main model threshold: **50%**
   - Mid-term model threshold: **25%** — deliberately different from the main model, because the mid-term model's numbers behave differently (see the note below) and 50% was the wrong cutoff for it specifically when tested.

4. **The probability is also converted into a Safe / At Risk / High Risk label** for the dashboard, so staff get an intuitive read, not just a raw percentage. Because the two models use different decision thresholds, they also use **slightly different Safe/At Risk/High Risk cutoffs**, so a given percentage always means the same real-world risk level regardless of which model produced it:

   | Band | Main model (complete record) | Mid-term model |
   |---|---|---|
   | High Risk | 0 – 39% | 0 – 39% |
   | At Risk | 40 – 64% | 40 – 74% |
   | Safe | 65 – 100% | 75 – 100% |

5. **A plain-language explanation is attached to every prediction** (via SHAP), showing the top 3 real factors that pushed that specific student's score up or down — not a generic statement, a genuine breakdown of that individual's numbers.

---

## An honest caveat worth telling stakeholders

The model correctly **ranks** students by risk — it's reliable at telling you who's more at risk than whom. Its raw percentage number, however, is not perfectly precise in the middle of the range (roughly 10–90%): it tends to understate how likely a student actually is to pass. A predicted "73%" is a meaningful signal of relative risk, but shouldn't be read as a literal "73 times out of 100." This is a known, documented limitation — see the Calibration section of [`model_card.md`](model_card.md) — not something glossed over.
