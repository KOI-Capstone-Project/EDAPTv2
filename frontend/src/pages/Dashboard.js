import { useEffect, useState } from 'react';
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid,
  Tooltip, ResponsiveContainer, Legend,
} from 'recharts';
import api from '../services/api';
import { getUser } from '../utils/auth';

export default function Dashboard() {
  const user     = getUser();
  const userName = user?.name || 'Lecturer';

  const [summary,  setSummary]  = useState([]);
  const [filters,  setFilters]  = useState({ subjects: [] });
  const [dataInfo, setDataInfo] = useState(null);
  const [loading,  setLoading]  = useState(true);
  const [error,    setError]    = useState(null);

  useEffect(() => {
    Promise.all([
      api.get('/api/summary'),
      api.get('/api/filters'),
      api.get('/api/data'),
    ])
      .then(([sumRes, filRes, datRes]) => {
        setSummary(sumRes.data.data  ?? []);
        setFilters(filRes.data       ?? { subjects: [] });
        setDataInfo({ total: datRes.data.total, columns: datRes.data.columns });
      })
      .catch(() => setError('Could not load dashboard data.'))
      .finally(() => setLoading(false));
  }, []);

  const markData = summary.filter(d => d.avg_mark !== undefined);

  return (
    <div>
      {/* ── Welcome banner ──────────────────────────────────────── */}
      <div style={s.welcome}>
        <p style={s.welcomeGreeting}>Welcome back,</p>
        <h2 style={s.welcomeName}>{userName}</h2>
        <p style={s.welcomeSub}>Thank you for your work today.</p>
      </div>

      <h1 className="page-title">Mode 1 — Descriptive Analytics</h1>

      {/* ── KPI cards ───────────────────────────────────────────── */}
      <div style={s.kpiRow}>
        <div style={s.kpiCard}>
          <p style={s.kpiLabel}>My Records</p>
          <p style={s.kpiValue}>{dataInfo?.total != null ? dataInfo.total.toLocaleString() : '—'}</p>
          <p style={s.kpiSub}>filtered rows</p>
        </div>
        <div style={s.kpiCard}>
          <p style={s.kpiLabel}>My Subjects</p>
          <p style={s.kpiValue}>{filters.subjects.length || '—'}</p>
          <p style={s.kpiSub}>assigned classes</p>
        </div>
        <div style={s.kpiCard}>
          <p style={s.kpiLabel}>Subjects Listed</p>
          <div style={s.subjectChips}>
            {filters.subjects.length > 0
              ? filters.subjects.map(s => <span key={s} style={s2.chip}>{s}</span>)
              : <span style={{ color: '#94A3B8', fontSize: 13 }}>None yet</span>
            }
          </div>
        </div>
      </div>

      {/* ── Bar chart ───────────────────────────────────────────── */}
      <div className="card">
        <h2>Average Mark % by Subject</h2>
        {loading && <p>Loading…</p>}
        {error   && <p style={{ color: '#DC2626' }}>{error}</p>}
        {!loading && !error && markData.length === 0 && (
          <p style={{ color: '#888', fontSize: 14 }}>
            No data yet — ask your administrator to ingest the dataset, then refresh.
          </p>
        )}
        {markData.length > 0 && (
          <ResponsiveContainer width="100%" height={320}>
            <BarChart data={markData} margin={{ top: 8, right: 24, left: 0, bottom: 40 }}>
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

      {/* ── Enrolment count ─────────────────────────────────────── */}
      {!loading && summary.length > 0 && (
        <div className="card">
          <h2>Enrolment Count by Subject</h2>
          <ResponsiveContainer width="100%" height={260}>
            <BarChart data={summary} margin={{ top: 8, right: 24, left: 0, bottom: 40 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="#eee" />
              <XAxis dataKey="subject_code" angle={-35} textAnchor="end" tick={{ fontSize: 12 }} />
              <YAxis tick={{ fontSize: 12 }} />
              <Tooltip />
              <Legend verticalAlign="top" />
              <Bar dataKey="row_count" name="Enrolments" fill="#2E6E8E" radius={[4, 4, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </div>
      )}

      <div className="card">
        <h2>Trimester-on-Trimester Growth</h2>
        <p style={{ color: '#888', fontSize: '0.9rem' }}>
          Chart will render here once trimester data is loaded. (coming soon)
        </p>
      </div>
    </div>
  );
}

const s = {
  welcome: {
    background: 'linear-gradient(135deg, #1A2E40 0%, #2E6E8E 100%)',
    borderRadius: 12, padding: '20px 28px', marginBottom: 28, color: '#fff',
  },
  welcomeGreeting: { margin: 0, fontSize: 13, opacity: 0.75 },
  welcomeName:     { margin: '4px 0 0', fontSize: 22, fontWeight: 700 },
  welcomeSub:      { margin: '6px 0 0', fontSize: 13, opacity: 0.65 },

  kpiRow:  { display: 'flex', gap: 16, marginBottom: 24, flexWrap: 'wrap' },
  kpiCard: {
    flex: 1, minWidth: 140,
    background: '#fff', border: '0.5px solid #DDE4EA',
    borderRadius: 12, padding: '18px 20px',
  },
  kpiLabel: { margin: '0 0 8px', fontSize: 11, fontWeight: 600, color: '#94A3B8', textTransform: 'uppercase', letterSpacing: 0.6 },
  kpiValue: { margin: '0 0 4px', fontSize: 30, fontWeight: 700, color: '#1E293B', letterSpacing: -1 },
  kpiSub:   { margin: 0, fontSize: 12, color: '#94A3B8' },
  subjectChips: { display: 'flex', flexWrap: 'wrap', gap: 6, marginTop: 4 },
};

// separate object to avoid the `s` variable collision in JSX map
const s2 = {
  chip: {
    background: '#EFF6FF', border: '1px solid #BFDBFE',
    color: '#1D4ED8', borderRadius: 6, padding: '3px 8px',
    fontSize: 11, fontWeight: 500,
    fontFamily: "'SF Mono','Fira Code',monospace",
  },
};
