import { useEffect, useState } from 'react';
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid,
  Tooltip, ResponsiveContainer, Legend,
} from 'recharts';
import api from '../services/api';

export default function Dashboard() {
  const [summary, setSummary] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError]     = useState(null);

  const user     = (() => {
    try { return JSON.parse(localStorage.getItem('edapt_user') || '{}'); }
    catch { return {}; }
  })();
  const userName = user.name || 'User';

  useEffect(() => {
    api.get('/api/v1/assessments/summary')
      .then(res => setSummary(res.data?.data ?? []))
      .catch(() => setError('Could not load assessment summary.'))
      .finally(() => setLoading(false));
  }, []);

  return (
    <div>
      {/* ── Welcome banner ─────────────────────────────────────── */}
      <div style={s.welcome}>
        <p style={s.welcomeGreeting}>Welcome back,</p>
        <h2 style={s.welcomeName}>{userName}</h2>
        <p style={s.welcomeSub}>Thank you for your work today.</p>
      </div>

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

const s = {
  welcome: {
    background: 'linear-gradient(135deg, #1A2E40 0%, #2E6E8E 100%)',
    borderRadius: 12,
    padding: '20px 28px',
    marginBottom: 28,
    color: '#fff',
  },
  welcomeGreeting: { margin: 0, fontSize: 13, opacity: 0.75, fontWeight: 400 },
  welcomeName:     { margin: '4px 0 0', fontSize: 22, fontWeight: 700 },
  welcomeSub:      { margin: '6px 0 0', fontSize: 13, opacity: 0.65 },
};
