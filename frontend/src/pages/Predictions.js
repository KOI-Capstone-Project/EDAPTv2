import React, { useState } from 'react';
import api from '../services/api';

export default function Predictions() {
  const [trimesters]   = useState([{ id: 1, label: 'T3 2025' }]);
  const [trimeId, setTrimeId] = useState(1);
  const [modelVer]     = useState('rf_v1');
  const [results, setResults] = useState(null);
  const [running, setRunning] = useState(false);
  const [error, setError]     = useState(null);

  const runPredictions = async () => {
    setRunning(true);
    setError(null);
    try {
      const res = await api.post('/api/v1/predictions/run', null, {
        params: { trimester_id: trimeId, model_version: modelVer },
      });
      setResults(res.data);
    } catch {
      setError('Prediction run failed. Make sure the backend is running and a model is trained.');
    } finally {
      setRunning(false);
    }
  };

  return (
    <div>
      <h1 className="page-title">Mode 2 — Predictive Analytics</h1>

      <div className="card">
        <h2>Run Pass / Fail Predictions</h2>
        <div style={{ display: 'flex', gap: '1rem', alignItems: 'center', flexWrap: 'wrap' }}>
          <label>
            Trimester&nbsp;
            <select value={trimeId} onChange={e => setTrimeId(Number(e.target.value))}>
              {trimesters.map(t => (
                <option key={t.id} value={t.id}>{t.label}</option>
              ))}
            </select>
          </label>
          <label>Model version: <strong>{modelVer}</strong></label>
          <button
            onClick={runPredictions}
            disabled={running}
            style={{
              background: '#4f8ef7', color: '#fff', border: 'none',
              borderRadius: 8, padding: '0.5rem 1.25rem', cursor: 'pointer',
            }}
          >
            {running ? 'Running…' : 'Run Predictions'}
          </button>
        </div>

        {error && <p style={{ color: 'red', marginTop: '1rem' }}>{error}</p>}

        {results && (
          <pre style={{
            marginTop: '1rem', background: '#f4f6f9',
            padding: '1rem', borderRadius: 8, fontSize: '0.85rem',
            overflowX: 'auto',
          }}>
            {JSON.stringify(results, null, 2)}
          </pre>
        )}
      </div>

      <div className="card">
        <h2>Prediction Results Table</h2>
        <p style={{ color: '#888', fontSize: '0.9rem' }}>
          Results will appear here after running predictions. (coming soon)
        </p>
      </div>
    </div>
  );
}
