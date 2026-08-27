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
import { useState, useEffect } from 'react';
import api from '../services/api';
import { getErrorMessage } from '../utils/apiError';

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

function pct(v, digits = 1) {
  return v === null || v === undefined ? '—' : `${(v * 100).toFixed(digits)}%`;
}

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

export default function ModelHealth() {
  const [data, setData]       = useState(null);
  const [error, setError]     = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    api.get('/api/admin/model-health')
      .then(r => setData(r.data))
      .catch(e => setError(getErrorMessage(e, 'Could not load model health.')))
      .finally(() => setLoading(false));
  }, []);

  if (loading) return <div style={S.page}><p style={{ color: '#64748B' }}>Loading model health…</p></div>;
  if (error)   return <div style={S.page}><div style={S.err}>{error}</div></div>;
  if (!data)   return null;

  const acc  = data.accuracy || {};
  const fair = data.fairness || {};
  const iv   = data.interventions || {};
  const lm   = data.live_models || {};

  return (
    <div style={S.page}>
      <div style={{ marginBottom: 18 }}>
        <h1 style={S.h1}>Model Health</h1>
        <p style={S.sub}>
          Read-only. Promotion and rollback are CLI-only, behind the
          compare_and_promote gate — deliberately not available here.
        </p>
      </div>

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
                    <td style={S.td}>{v ? pct(v.accuracy, 2) : 'no data'}</td>
                    <td style={S.td}>{v ? pct(v.recall, 2) : '—'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
            <p style={S.note}>{acc.note}</p>
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
  note:      { margin: '10px 0 0', fontSize: 11, color: '#64748B', fontStyle: 'italic',
               lineHeight: 1.6 },
  err:       { padding: 12, background: '#FEE2E2', color: '#991B1B', borderRadius: 8,
               fontSize: 13 },
};
