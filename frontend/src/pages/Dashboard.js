import React, { useEffect, useState } from 'react';
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid,
  Tooltip, ResponsiveContainer, Legend,
} from 'recharts';
import api from '../services/api';

export default function Dashboard() {
  const [summary, setSummary] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError]     = useState(null);

  useEffect(() => {
    api.get('/api/v1/assessments/summary')
      .then(res => setSummary(res.data?.data ?? []))
      .catch(() => setError('Could not load assessment summary.'))
      .finally(() => setLoading(false));
  }, []);

  return (
    <div>
      <h1 className="page-title">Mode 1 — Descriptive Analytics</h1>

      <div className="card">
        <h2>Average Mark % by Subject</h2>
        {loading && <p>Loading…</p>}
        {error   && <p style={{ color: 'red' }}>{error}</p>}
        {!loading && !error && summary.length === 0 && (
          <p style={{ color: '#888' }}>No data yet — ingest your dataset to populate this chart.</p>
        )}
        {summary.length > 0 && (
          <ResponsiveContainer width="100%" height={320}>
            <BarChart data={summary} margin={{ top: 8, right: 24, left: 0, bottom: 40 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="#eee" />
              <XAxis dataKey="subject_code" angle={-35} textAnchor="end" tick={{ fontSize: 12 }} />
              <YAxis domain={[0, 100]} unit="%" tick={{ fontSize: 12 }} />
              <Tooltip formatter={v => `${v}%`} />
              <Legend verticalAlign="top" />
              <Bar dataKey="avg_mark" name="Avg Mark %" fill="#4f8ef7" radius={[4, 4, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>
        )}
      </div>

      <div className="card">
        <h2>Trimester-on-Trimester Growth</h2>
        <p style={{ color: '#888', fontSize: '0.9rem' }}>
          Chart will render here once assessment data is loaded. (coming soon)
        </p>
      </div>
    </div>
  );
}
