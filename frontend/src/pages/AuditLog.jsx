import React, { useState, useMemo, useEffect } from 'react';
import api from '../services/api';

const STATUS_BADGE = {
  Success: { bg: '#E1F5EE', color: '#0F6E56', border: '#5DCAA5' },
  Alert:   { bg: '#FAEEDA', color: '#633806', border: '#EF9F27' },
  Denied:  { bg: '#FCEBEB', color: '#A32D2D', border: '#F09595' },
  Error:   { bg: '#FCEBEB', color: '#A32D2D', border: '#F09595' },
};

function Spinner() {
  return (
    <tr>
      <td colSpan={6} style={{ padding: 0, border: 'none' }}>
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', height: 200 }}>
          <div style={{ width: 32, height: 32, border: '3px solid #F0F4F8', borderTop: '3px solid #2E6E8E', borderRadius: '50%', animation: 'spin 0.8s linear infinite' }} />
        </div>
      </td>
    </tr>
  );
}

function uidRole(uid) {
  if (uid.startsWith('HOT-')) return 'Head of Technology';
  if (uid.startsWith('LEC-')) return 'Lecturer';
  return null;
}

function rowRole(row) {
  return row.role || uidRole(row.user_uid) || '';
}

const IconCheck = () => (
  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor"
    strokeWidth="3" strokeLinecap="round" strokeLinejoin="round">
    <polyline points="20 6 9 17 4 12"/>
  </svg>
);

export default function AuditLog() {
  const [filterUID,    setFilterUID]    = useState('');
  const [filterAction, setFilterAction] = useState('');
  const [filterStatus, setFilterStatus] = useState('');
  const [logs,         setLogs]         = useState([]);
  const [total,        setTotal]        = useState(0);
  const [loading,      setLoading]      = useState(true);
  const [fetchError,   setFetchError]   = useState(null);

  useEffect(() => {
    api.get('/api/audit-logs')
      .then(res => { setLogs(res.data.data); setTotal(res.data.total); })
      .catch(() => setFetchError('Failed to load audit logs.'))
      .finally(() => setLoading(false));
  }, []);

  const filtered = useMemo(() => logs.filter(row => {
    if (filterUID    && rowRole(row) !== filterUID)      return false;
    if (filterAction && row.action_type !== filterAction) return false;
    if (filterStatus && row.status !== filterStatus)      return false;
    return true;
  }), [logs, filterUID, filterAction, filterStatus]);

  return (
    <div>
      {/* ── Header ──────────────────────────────────────────────────── */}
      <div style={s.topRow}>
        <div>
          <h1 style={s.pageTitle}>Audit Log</h1>
          <p style={s.pageSub}>System event history — filterable by user and action type</p>
        </div>
        <div style={s.ethicsBadge}>
          <span style={s.ethicsCheck}><IconCheck /></span>
          Certified Ethical — Verified
        </div>
      </div>

      {/* ── Filters ─────────────────────────────────────────────────── */}
      <div style={s.filterCard}>
        <div style={s.filterRow}>
          <div style={s.filterGroup}>
            <label style={s.filterLabel}>User Role</label>
            <select style={s.select} value={filterUID} onChange={e => setFilterUID(e.target.value)}>
              <option value="">All Users</option>
              <option value="Lecturer">Lecturer</option>
              <option value="Head of Technology">Head of Technology</option>
            </select>
          </div>
          <div style={s.filterGroup}>
            <label style={s.filterLabel}>Action Type</label>
            <select style={s.select} value={filterAction} onChange={e => setFilterAction(e.target.value)}>
              <option value="">All Actions</option>
              <option value="Login">Login</option>
              <option value="Login Failed">Login Failed</option>
              <option value="Access Denied">Access Denied</option>
              <option value="Data Upload">Data Upload</option>
              <option value="Data Processed">Data Processed</option>
              <option value="Prediction Run">Prediction Run</option>
            </select>
          </div>
          <div style={s.filterGroup}>
            <label style={s.filterLabel}>Status</label>
            <select style={s.select} value={filterStatus} onChange={e => setFilterStatus(e.target.value)}>
              <option value="">All Status</option>
              <option value="Success">Success</option>
              <option value="Alert">Alert</option>
              <option value="Denied">Denied</option>
              <option value="Error">Error</option>
            </select>
          </div>
          <div style={{ alignSelf: 'flex-end' }}>
            <span style={s.resultCount}>
              {loading ? 'Loading…' : `${filtered.length} of ${total} events`}
            </span>
          </div>
        </div>
      </div>

      {/* ── Error ───────────────────────────────────────────────────── */}
      {fetchError && (
        <div style={s.errorBox}>{fetchError}</div>
      )}

      {/* ── Table ───────────────────────────────────────────────────── */}
      <div style={s.tableWrapper}>
        <div style={{ overflowX: 'auto' }}>
          <table style={s.table}>
            <thead>
              <tr style={s.thead}>
                {['Event ID', 'Timestamp', 'User UID', 'Action Type', 'Status', 'Detail'].map(col => (
                  <th key={col} style={s.th}>{col}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {loading ? (
                <Spinner />
              ) : filtered.length === 0 ? (
                <tr>
                  <td colSpan={6} style={{ padding: 0, border: 'none' }}>
                    <div style={{ textAlign: 'center', padding: '60px 20px', color: '#8BA5B8' }}>
                      <div style={{ fontSize: 32, marginBottom: 12 }}>📭</div>
                      <div style={{ fontSize: 14, fontWeight: 500, color: '#1A2E40', marginBottom: 4 }}>No events found</div>
                      <div style={{ fontSize: 13 }}>Try adjusting your filters</div>
                    </div>
                  </td>
                </tr>
              ) : filtered.map((row, i) => {
                const badge = STATUS_BADGE[row.status] || STATUS_BADGE.Error;
                return (
                  <tr key={row.event_id} style={{ background: i % 2 === 0 ? '#fff' : '#F8FAFB' }}>
                    <td style={{ ...s.td, ...s.tdMono }}>{row.event_id}</td>
                    <td style={{ ...s.td, ...s.tdMono, whiteSpace: 'nowrap' }}>{row.timestamp}</td>
                    <td style={{ ...s.td, ...s.tdMono }}>{row.user_uid}</td>
                    <td style={s.td}>{row.action_type}</td>
                    <td style={s.td}>
                      <span style={{ ...s.badge, background: badge.bg, color: badge.color, borderColor: badge.border }}>
                        {row.status}
                      </span>
                    </td>
                    <td style={{ ...s.td, color: '#5A7A8A', maxWidth: 320 }}>{row.detail}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}

const s = {
  topRow:   { display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 24 },
  pageTitle: { margin: '0 0 4px', fontSize: 24, fontWeight: 500, color: '#1A2E40' },
  pageSub:   { margin: 0, fontSize: 13, color: '#5A7A8A' },

  ethicsBadge: {
    display: 'flex', alignItems: 'center', gap: 7,
    background: '#E1F5EE', border: '0.5px solid #5DCAA5',
    color: '#0F6E56', borderRadius: 20,
    padding: '7px 16px', fontSize: 13, fontWeight: 500,
    whiteSpace: 'nowrap', alignSelf: 'center',
  },
  ethicsCheck: {
    display: 'flex', alignItems: 'center', justifyContent: 'center',
    width: 20, height: 20, borderRadius: '50%',
    background: '#0F6E56', color: '#fff', flexShrink: 0,
  },

  filterCard:  { background: '#fff', border: '0.5px solid #DDE4EA', borderRadius: 12, padding: '14px 16px', marginBottom: 20 },
  filterRow:   { display: 'flex', gap: 12, flexWrap: 'wrap', alignItems: 'flex-end' },
  filterGroup: { display: 'flex', flexDirection: 'column', gap: 4 },
  filterLabel: { fontSize: 11, fontWeight: 600, color: '#8BA5B8', textTransform: 'uppercase', letterSpacing: 0.5 },
  select: {
    height: 36, padding: '0 12px', borderRadius: 8,
    border: '0.5px solid #C5D2DC', fontSize: 13, color: '#1A2E40',
    background: '#fff', cursor: 'pointer', minWidth: 180, outline: 'none',
  },
  resultCount: { fontSize: 12, color: '#8BA5B8' },

  errorBox: {
    background: '#FCEBEB', border: '0.5px solid #F09595',
    color: '#A32D2D', borderRadius: 8, padding: '10px 16px', fontSize: 13, marginBottom: 16,
  },

  tableWrapper: { background: '#fff', border: '0.5px solid #DDE4EA', borderRadius: 12, overflow: 'hidden' },
  table:        { width: '100%', borderCollapse: 'collapse', fontSize: 13 },
  thead:        { background: '#F0F4F8' },
  th: {
    padding: '12px 16px', textAlign: 'left',
    fontSize: 11, fontWeight: 500, color: '#5A7A8A',
    textTransform: 'uppercase', letterSpacing: 0.5,
    borderBottom: '0.5px solid #F0F4F8', whiteSpace: 'nowrap',
  },
  td:     { padding: '12px 16px', color: '#1A2E40', borderBottom: '0.5px solid #F0F4F8', verticalAlign: 'middle' },
  tdMono: { fontFamily: "'SF Mono','Fira Code',monospace", fontSize: 12, color: '#5A7A8A' },

  badge: {
    display: 'inline-block', padding: '3px 10px',
    borderRadius: 20, border: '0.5px solid',
    fontSize: 12, fontWeight: 500,
  },
};
