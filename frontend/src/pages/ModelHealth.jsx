// Model Health — admin-only, READ-ONLY view of whether the deployed models
// are still behaving.
//
// DELIBERATELY READ-ONLY. There is no promote, rollback, or retrain control on
// this page and there should never be one. Promotion stays a considered CLI
// action behind compare_and_promote's >3pp gate, which forces a human to read
// a real comparison and, for a borderline case, type --force with a recorded
// justification. A one-click button here would route around the exact
// safeguard this project built after a model went live ungated with no
// recoverable backup.
//
// Everything rendered comes from GET /api/admin/model-health, which reads the
// real registries and calls the same functions the CLI scripts call — so this
// page cannot disagree with what those scripts report.
//
// Two reading modes, same underlying numbers:
//   - Classical  — plain-English status for a non-technical reader (a Head
//     of School, say): traffic-light verdicts, no "F1"/"precision" jargon,
//     and every caveat the backend already computes (small sample, single
//     observation, not enough data) rendered as prose instead of omitted.
//   - Technical  — the full breakdown: raw metrics, per-version tables,
//     thresholds, feature lists.
// Neither view invents a number or a threshold the other doesn't have —
// they render the exact same API response two different ways, so they
// cannot drift into disagreeing with each other.
import { useState, useEffect } from 'react';
import api from '../services/api';
import { getErrorMessage } from '../utils/apiError';

const VIEW_KEY = 'pref_model_health_view';

function pct(v, digits = 1) {
  return v === null || v === undefined ? '—' : `${(v * 100).toFixed(digits)}%`;
}

// ── Shared bits ─────────────────────────────────────────────────────────────

function Metric({ label, value, hint }) {
  return (
    <div style={{ flex: '1 1 130px', minWidth: 130 }}>
      <div style={{ fontSize: 11, color: '#64748B', marginBottom: 2 }}>{label}</div>
      <div style={{ fontSize: 18, fontWeight: 700, color: '#1A2E40' }}>
        {value === null || value === undefined ? '—' : value}
      </div>
      {hint && <div style={{ fontSize: 10, color: '#94A3B8' }}>{hint}</div>}
    </div>
  );
}

function ViewToggle({ view, onChange }) {
  return (
    <div style={S.toggleWrap}>
      {[
        { id: 'classical', label: 'Classical view', hint: 'Plain-English summary' },
        { id: 'technical',  label: 'Technical view',  hint: 'Full metrics & tables' },
      ].map(opt => (
        <button
          key={opt.id}
          type="button"
          onClick={() => onChange(opt.id)}
          style={{ ...S.toggleBtn, ...(view === opt.id ? S.toggleBtnActive : {}) }}
          title={opt.hint}
        >
          {opt.label}
        </button>
      ))}
    </div>
  );
}

// ══════════════════════════════════════════════════════════════════════════
// Technical view — full detail, one card per section
// ══════════════════════════════════════════════════════════════════════════

function ModelCard({ model }) {
  if (!model || !model.live) {
    return (
      <div style={S.card}>
        <p style={S.cardTitle}>{model?.family || 'model'}</p>
        <p style={{ fontSize: 13, color: '#B45309' }}>
          {model?.error || 'No live version registered.'}
        </p>
      </div>
    );
  }
  const m = model.metrics || {};
  return (
    <div style={S.card}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline', flexWrap: 'wrap', gap: 8 }}>
        <p style={S.cardTitle}>{model.family}</p>
        <code style={S.version}>{model.version}</code>
      </div>

      <div style={{ display: 'flex', gap: 16, flexWrap: 'wrap', margin: '14px 0' }}>
        <Metric label="Accuracy"       value={m.accuracy != null ? m.accuracy.toFixed(4) : null} />
        <Metric label="Fail precision" value={m.fail_precision != null ? m.fail_precision.toFixed(4) : null} />
        <Metric label="Fail recall"    value={m.fail_recall != null ? m.fail_recall.toFixed(4) : null} />
        <Metric label="Fail F1"        value={m.fail_f1 != null ? m.fail_f1.toFixed(4) : null} />
        <Metric label="Fail support"   value={m.fail_support != null ? Math.round(m.fail_support).toLocaleString() : null} />
      </div>

      <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 12 }}>
        <tbody>
          <tr><td style={S.k}>Trained on</td><td style={S.v}>{model.trained_on || '—'}</td></tr>
          <tr><td style={S.k}>Validated on</td><td style={S.v}>{model.validated_on || '—'}</td></tr>
          <tr><td style={S.k}>Trained at</td><td style={S.v}>{model.trained_at ? new Date(model.trained_at).toLocaleString() : '—'}</td></tr>
          <tr><td style={S.k}>Promoted at</td><td style={S.v}>{model.promoted_at ? new Date(model.promoted_at).toLocaleString() : '—'}</td></tr>
          <tr><td style={S.k}>Training rows</td><td style={S.v}>{model.train_row_count != null ? model.train_row_count.toLocaleString() : 'not recorded'}</td></tr>
          <tr>
            <td style={S.k}>Decision threshold</td>
            <td style={S.v}>
              serving <strong>{model.decision_threshold_serving ?? '—'}</strong>
              {' · '}registered <strong>{model.decision_threshold_registered ?? '—'}</strong>
              {model.threshold_matches_registry === false && (
                // Not necessarily a bug: the complete-record sweep suggested
                // 0.475, inside this project's noise band, so 0.50 stayed
                // deployed. Surfaced rather than hidden so the difference is
                // a visible decision instead of a silent one.
                <span style={{ color: '#B45309', marginLeft: 6 }}>
                  ⚠ differ — the deployed value is what serves traffic
                </span>
              )}
            </td>
          </tr>
          <tr>
            <td style={S.k}>Features</td>
            <td style={S.v}>
              {model.n_features} <span style={{ color: '#94A3B8' }}>({model.features_source})</span>
            </td>
          </tr>
        </tbody>
      </table>
    </div>
  );
}

function TechnicalView({ data }) {
  const acc  = data.accuracy || {};
  const fair = data.fairness || {};
  const iv   = data.interventions || {};
  const lm   = data.live_models || {};
  const minN = acc.min_n_for_reliable;

  // A raw n < minN is flagged unreliable by the backend (see `reliable` on
  // each group) — render it visibly muted rather than as a confident number,
  // so a 100% shown on 2 reconciled cases can't be read as a real result.
  const cell = (v, fmt) => {
    if (!v) return <td style={S.td}>no data</td>;
    return (
      <td style={{ ...S.td, ...(v.reliable === false ? S.unreliable : {}) }}>
        {fmt(v)}
        {v.reliable === false && <span title={`Fewer than ${minN} reconciled cases — treat as noise, not a result`}> ⚠</span>}
      </td>
    );
  };

  return (
    <>
      <p style={S.section}>Live models</p>
      <div style={{ display: 'flex', gap: 16, flexWrap: 'wrap' }}>
        <ModelCard model={lm.complete_record} />
        <ModelCard model={lm.mid_term} />
      </div>

      <p style={S.section}>Predicted vs. actual (real reconciled outcomes)</p>
      <div style={S.card}>
        {!acc.overall ? (
          <p style={{ fontSize: 13, color: '#64748B' }}>
            Nothing reconciled yet — run reconcile_predictions.py.
          </p>
        ) : (
          <>
            <div style={{ display: 'flex', gap: 16, flexWrap: 'wrap', marginBottom: 12 }}>
              <Metric label="Reconciled" value={acc.reconciled_count?.toLocaleString()} />
              <Metric label="Accuracy"       value={pct(acc.overall.accuracy, 2)} />
              <Metric label="Fail precision" value={pct(acc.overall.precision, 2)} />
              <Metric label="Fail recall"    value={pct(acc.overall.recall, 2)} />
            </div>
            {acc.overall.reliable === false && (
              <p style={{ ...S.note, color: '#B45309' }}>
                ⚠ Only {acc.overall.n} reconciled case(s) — fewer than the {minN} this project
                treats as enough to trust a percentage. Treat the numbers above as provisional.
              </p>
            )}
            <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 12 }}>
              <thead>
                <tr>
                  <th style={S.th}>Breakdown</th><th style={S.th}>n</th>
                  <th style={S.th}>Accuracy</th><th style={S.th}>Fail recall</th>
                </tr>
              </thead>
              <tbody>
                {[
                  ...Object.entries(acc.by_estimate_type || {}).map(([k, v]) => [`estimate: ${k}`, v]),
                  ...Object.entries(acc.by_model_version || {}).map(([k, v]) => [`version: ${k}`, v]),
                  ...Object.entries(acc.by_reconciliation || {}).map(([k, v]) => [`method: ${k}`, v]),
                ].map(([label, v]) => (
                  <tr key={label}>
                    <td style={S.td}>{label}</td>
                    <td style={S.td}>{v ? v.n.toLocaleString() : '—'}</td>
                    {cell(v, x => pct(x.accuracy, 2))}
                    {cell(v, x => pct(x.recall, 2))}
                  </tr>
                ))}
              </tbody>
            </table>
            <p style={S.note}>
              {acc.note} Rows marked ⚠ have fewer than {minN} reconciled cases.
            </p>
          </>
        )}
      </div>

      <p style={S.section}>Fairness flags across retrains</p>
      <div style={S.card}>
        <div style={{ display: 'flex', gap: 16, flexWrap: 'wrap', marginBottom: 10 }}>
          <Metric label="Independent retrains" value={fair.independent_retrains}
                  hint="distinct trained_on/validated_on pairs" />
          <Metric label="Versions with an audit" value={fair.versions_with_bias_audit} />
          <Metric label="Enough for a trend?" value={fair.enough_for_a_trend ? 'Yes' : 'No'} />
        </div>
        {(fair.flagged_groups || []).length === 0 ? (
          <p style={{ fontSize: 13, color: '#64748B' }}>No group flagged in any audited retrain.</p>
        ) : (
          <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 12 }}>
            <thead>
              <tr><th style={S.th}>Category</th><th style={S.th}>Group</th>
                  <th style={S.th}>Times flagged</th><th style={S.th}>Reason</th></tr>
            </thead>
            <tbody>
              {fair.flagged_groups.map(g => (
                <tr key={`${g.category}:${g.group}`}>
                  <td style={S.td}>{g.category}</td>
                  <td style={S.td}><strong>{g.group}</strong></td>
                  <td style={S.td}>{g.times_flagged} of {fair.independent_retrains}</td>
                  <td style={S.td}>{g.reason || '—'}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
        {/* The single most important sentence on this page: with one
            independent retrain, a flagged group is one observation, not a
            trend. Rendered as a warning so it can't be skimmed past. */}
        <p style={{ ...S.note, color: fair.enough_for_a_trend ? '#64748B' : '#B45309' }}>
          {fair.interpretation}
        </p>
      </div>

      <p style={S.section}>Interventions vs. outcomes</p>
      <div style={S.card}>
        <div style={{ display: 'flex', gap: 16, flexWrap: 'wrap', marginBottom: 10 }}>
          <Metric label="High Risk reconciled" value={iv.high_risk_reconciled} />
          <Metric label="Interventions logged" value={iv.total_interventions_logged} />
          <Metric label="With an action"    value={iv.with_intervention?.n} />
          <Metric label="Without"           value={iv.without_intervention?.n} />
        </div>
        {iv.sufficient_data ? (
          <>
            <p style={{ fontSize: 13, color: '#1A2E40' }}>
              Actual pass rate — with an action: <strong>{pct(iv.with_intervention.pass_rate)}</strong>
              {' · '}without: <strong>{pct(iv.without_intervention.pass_rate)}</strong>
            </p>
            <p style={{ ...S.note, color: '#B45309' }}>
              This is NOT evidence that interventions work. Lecturers choose who to
              contact, so the two groups differ by more than the intervention.
              Treat it as a prompt to design a real evaluation, not a result.
            </p>
          </>
        ) : (
          <p style={{ ...S.note, color: '#B45309' }}>
            Not enough data to compare: both groups need at least
            {' '}{iv.min_group_for_a_rate} students (currently
            {' '}{iv.with_intervention?.n ?? 0} and {iv.without_intervention?.n ?? 0}).
            No percentage is shown, because one computed from these counts would be
            arithmetic rather than evidence.
          </p>
        )}
      </div>
    </>
  );
}

// ══════════════════════════════════════════════════════════════════════════
// Classical view — plain-English status, same numbers, no jargon
// ══════════════════════════════════════════════════════════════════════════

function StatusPill({ level, children }) {
  const colors = {
    green: { bg: '#ECFDF5', border: '#A7F3D0', text: '#065F46' },
    amber: { bg: '#FFFBEB', border: '#FDE68A', text: '#92400E' },
    red:   { bg: '#FEF2F2', border: '#FECACA', text: '#991B1B' },
    info:  { bg: '#EFF6FF', border: '#BFDBFE', text: '#1E40AF' },
  }[level];
  const icon = { green: '✅', amber: '⚠️', red: '⛔', info: 'ℹ️' }[level];
  return (
    <div style={{
      display: 'flex', gap: 10, alignItems: 'flex-start',
      background: colors.bg, border: `1px solid ${colors.border}`, color: colors.text,
      borderRadius: 10, padding: '12px 14px', fontSize: 13.5, lineHeight: 1.55,
    }}>
      <span style={{ fontSize: 16 }}>{icon}</span>
      <span>{children}</span>
    </div>
  );
}

function ClassicalModel({ model, friendlyName, blurb }) {
  if (!model || !model.live) {
    return (
      <div style={S.card}>
        <p style={S.cardTitle}>{friendlyName}</p>
        <StatusPill level="red">
          Not active — {model?.error || 'no version of this model is currently live'}. Predictions of this
          kind cannot be produced right now.
        </StatusPill>
      </div>
    );
  }
  const m = model.metrics || {};
  const lastUpdated = model.promoted_at
    ? new Date(model.promoted_at).toLocaleDateString(undefined, { year: 'numeric', month: 'long', day: 'numeric' })
    : 'an unrecorded date';
  return (
    <div style={S.card}>
      <p style={S.cardTitle}>{friendlyName}</p>
      <p style={{ fontSize: 12.5, color: '#64748B', margin: '2px 0 12px' }}>{blurb}</p>
      <StatusPill level="green">
        Active since {lastUpdated}. When it was last checked against known results, it correctly
        predicted the outcome {pct(m.accuracy, 0)} of the time, and correctly caught{' '}
        {pct(m.fail_recall, 0)} of the students who actually went on to struggle.
      </StatusPill>
      {model.threshold_matches_registry === false && (
        <p style={{ fontSize: 12, color: '#94A3B8', marginTop: 8 }}>
          Note: one internal setting for this model was deliberately kept at its original value
          rather than a very slightly different suggestion from later testing — a considered
          decision, not an oversight.
        </p>
      )}
    </div>
  );
}

function ClassicalView({ data }) {
  const acc  = data.accuracy || {};
  const fair = data.fairness || {};
  const iv   = data.interventions || {};
  const lm   = data.live_models || {};
  const minN = acc.min_n_for_reliable;

  const complete = lm.complete_record;
  const midTerm  = lm.mid_term;
  const bothLive = complete?.live && midTerm?.live;

  const flaggedNow = (fair.flagged_groups || []);
  const confirmedBias = fair.enough_for_a_trend && flaggedNow.length > 0;

  let overallLevel = 'green';
  let overallText = 'Both prediction models are active, and there are no confirmed accuracy or fairness problems.';
  if (!bothLive) {
    overallLevel = 'red';
    overallText = 'Action needed — at least one prediction model is not currently active.';
  } else if (confirmedBias) {
    overallLevel = 'amber';
    overallText = 'Needs attention — a fairness concern has recurred across multiple independent checks (see below).';
  }

  // Real-world accuracy, split the same way the models are (complete-record
  // vs. mid-term) — this is the "since it went live" number, distinct from
  // the "when it was built" number shown per-model above.
  const realComplete = acc.by_estimate_type?.['complete-record'];
  const realMidTerm   = acc.by_estimate_type?.['mid-term estimate'];

  return (
    <>
      <p style={S.section}>Overall status</p>
      <StatusPill level={overallLevel}>{overallText}</StatusPill>

      <p style={S.section}>Are the prediction models running?</p>
      <div style={{ display: 'flex', gap: 16, flexWrap: 'wrap' }}>
        <ClassicalModel
          model={complete} friendlyName="Final Prediction Model"
          blurb="Predicts a student's final pass/fail outcome using their complete record."
        />
        <ClassicalModel
          model={midTerm} friendlyName="Early Warning Model"
          blurb="Predicts likely outcome early in the trimester, from partial/in-progress results."
        />
      </div>

      <p style={S.section}>How accurate have the predictions been in the real world?</p>
      <div style={S.card}>
        {!acc.reconciled_count ? (
          <StatusPill level="info">
            No real-world results have been matched back to predictions yet, so this can't be
            measured yet. This updates automatically as more students' final results come in.
          </StatusPill>
        ) : (
          <>
            <p style={{ fontSize: 13.5, color: '#1A2E40', lineHeight: 1.6, margin: '0 0 10px' }}>
              Out of <strong>{acc.reconciled_count.toLocaleString()}</strong> student outcome(s)
              checked so far, the models were right <strong>{pct(acc.overall?.accuracy, 0)}</strong> of
              the time overall.
            </p>
            {[
              ['Final Prediction Model', realComplete],
              ['Early Warning Model',    realMidTerm],
            ].map(([label, v]) => (
              <p key={label} style={{ fontSize: 13, color: '#334155', margin: '4px 0' }}>
                <strong>{label}:</strong>{' '}
                {!v
                  ? 'no reconciled results yet'
                  : v.reliable === false
                    ? `only ${v.n} result(s) checked so far — too few to draw a conclusion yet`
                    : `right ${pct(v.accuracy, 0)} of the time, across ${v.n.toLocaleString()} checked result(s)`}
              </p>
            ))}
            {acc.overall?.reliable === false && (
              <p style={{ ...S.note, color: '#B45309', marginTop: 8 }}>
                Only {acc.overall.n} result(s) have been checked so far — fewer than the {minN} this
                project treats as enough to trust a percentage. Treat this as an early read, not a
                settled number.
              </p>
            )}
          </>
        )}
      </div>

      <p style={S.section}>Is the model fair to all groups of students?</p>
      <div style={S.card}>
        {fair.independent_retrains < 2 ? (
          <>
            <StatusPill level="info">
              Not yet confirmed either way — only {fair.independent_retrains} independent retraining
              check{fair.independent_retrains === 1 ? ' has' : 's have'} been run so far. This is
              re-checked automatically every time the model is retrained, and confirming fairness
              needs the same group showing up more than once.
            </StatusPill>
            {flaggedNow.length > 0 && (
              <p style={{ ...S.note, marginTop: 10 }}>
                Worth watching: <strong>{flaggedNow.map(g => g.group).join(', ')}</strong> showed a
                difference in this single check. One check alone doesn't prove a pattern — this will
                keep being monitored on future retrains.
              </p>
            )}
          </>
        ) : confirmedBias ? (
          <StatusPill level="amber">
            <strong>{flaggedNow.map(g => `${g.group} (${g.category})`).join(', ')}</strong> {flaggedNow.length === 1 ? 'has' : 'have'} shown
            a recurring pattern of less accurate predictions, across {fair.independent_retrains}{' '}
            independent retraining checks. This should be reviewed by someone who understands the
            model before it's dismissed as coincidence.
          </StatusPill>
        ) : (
          <StatusPill level="green">
            No group of students (by country, gender, or age) has shown a consistent pattern of less
            accurate predictions, across {fair.independent_retrains} independent retraining checks.
          </StatusPill>
        )}
      </div>

      <p style={S.section}>Does extra support actually help?</p>
      <div style={S.card}>
        {iv.sufficient_data ? (
          <>
            <p style={{ fontSize: 13.5, color: '#1A2E40', lineHeight: 1.6, margin: '0 0 10px' }}>
              Students flagged High Risk who received some form of logged support afterwards passed{' '}
              <strong>{pct(iv.with_intervention.pass_rate, 0)}</strong> of the time, versus{' '}
              <strong>{pct(iv.without_intervention.pass_rate, 0)}</strong> for those with no support
              logged.
            </p>
            <StatusPill level="amber">
              This does <strong>not</strong> prove the support caused the difference. Lecturers choose
              who to help, so the two groups aren't a fair comparison — treat this as a reason to look
              closer, not as proof.
            </StatusPill>
          </>
        ) : (
          <StatusPill level="info">
            Not enough logged support actions with a known outcome yet to check this (each group needs
            at least {iv.min_group_for_a_rate} students; currently {iv.with_intervention?.n ?? 0} and{' '}
            {iv.without_intervention?.n ?? 0}).
          </StatusPill>
        )}
      </div>
    </>
  );
}

// ══════════════════════════════════════════════════════════════════════════

export default function ModelHealth() {
  const [data, setData]       = useState(null);
  const [error, setError]     = useState(null);
  const [loading, setLoading] = useState(true);
  const [view, setView]       = useState(() => {
    try { return localStorage.getItem(VIEW_KEY) || 'classical'; } catch { return 'classical'; }
  });

  const changeView = (v) => {
    setView(v);
    try { localStorage.setItem(VIEW_KEY, v); } catch { /* storage unavailable */ }
  };

  useEffect(() => {
    api.get('/api/admin/model-health')
      .then(r => setData(r.data))
      .catch(e => setError(getErrorMessage(e, 'Could not load model health.')))
      .finally(() => setLoading(false));
  }, []);

  if (loading) return <div style={S.page}><p style={{ color: '#64748B' }}>Loading model health…</p></div>;
  if (error)   return <div style={S.page}><div style={S.err}>{error}</div></div>;
  if (!data)   return null;

  return (
    <div style={S.page}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', flexWrap: 'wrap', gap: 12, marginBottom: 18 }}>
        <div>
          <h1 style={S.h1}>Model Health</h1>
          <p style={S.sub}>
            Read-only. Promotion and rollback are CLI-only, behind the
            compare_and_promote gate — deliberately not available here.
          </p>
        </div>
        <ViewToggle view={view} onChange={changeView} />
      </div>

      {view === 'classical' ? <ClassicalView data={data} /> : <TechnicalView data={data} />}

      <p style={{ fontSize: 11, color: '#94A3B8', marginTop: 18 }}>
        Generated {data.generated_at ? new Date(data.generated_at).toLocaleString() : '—'} ·
        read live from the model registries and reconciled predictions on each request.
      </p>
    </div>
  );
}

const S = {
  page:      { padding: 24, maxWidth: 1100 },
  h1:        { margin: 0, fontSize: 24, fontWeight: 800, color: '#1A2E40' },
  sub:       { margin: '4px 0 0', fontSize: 13, color: '#64748B' },
  section:   { margin: '22px 0 8px', fontSize: 12, fontWeight: 700, color: '#475569',
               textTransform: 'uppercase', letterSpacing: 0.5 },
  card:      { flex: '1 1 420px', background: '#FFF', border: '1px solid #E2E8F0',
               borderRadius: 10, padding: 16, boxSizing: 'border-box' },
  cardTitle: { margin: 0, fontSize: 15, fontWeight: 700, color: '#1A2E40',
               textTransform: 'capitalize' },
  version:   { fontSize: 11, background: '#F1F5F9', color: '#475569',
               padding: '2px 8px', borderRadius: 6 },
  k:         { padding: '5px 0', color: '#64748B', width: 160, verticalAlign: 'top' },
  v:         { padding: '5px 0', color: '#1A2E40' },
  th:        { textAlign: 'left', padding: '6px 8px', borderBottom: '1px solid #E2E8F0',
               color: '#64748B', fontWeight: 600 },
  td:        { padding: '6px 8px', borderBottom: '1px solid #F1F5F9', color: '#334155' },
  unreliable:{ color: '#B45309', fontStyle: 'italic' },
  note:      { margin: '10px 0 0', fontSize: 11, color: '#64748B', fontStyle: 'italic',
               lineHeight: 1.6 },
  err:       { padding: 12, background: '#FEE2E2', color: '#991B1B', borderRadius: 8,
               fontSize: 13 },

  toggleWrap: { display: 'flex', gap: 4, background: '#F1F5F9', borderRadius: 10, padding: 4 },
  toggleBtn: {
    padding: '7px 14px', borderRadius: 7, border: 'none', background: 'transparent',
    fontSize: 12.5, fontWeight: 600, color: '#64748B', cursor: 'pointer',
  },
  toggleBtnActive: { background: '#fff', color: '#1A2E40', boxShadow: '0 1px 3px rgba(0,0,0,0.08)' },
};
