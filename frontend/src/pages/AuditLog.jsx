import React, { useState, useMemo, useEffect } from 'react';
import api from '../services/api';

const STATUS_BADGE = {
  Success: { bg: '#ECFDF5', color: '#059669', border: '#A7F3D0' },
  Alert:   { bg: '#FFFBEB', color: '#D97706', border: '#FDE68A' },
  Denied:  { bg: '#FEF2F2', color: '#DC2626', border: '#FECACA' },
  Error:   { bg: '#FFF1F2', color: '#E11D48', border: '#FECDD3' },
};

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
  const [filterUID, setFilterUID]       = useState('');
  const [filterAction, setFilterAction] = useState('');
  const [filterStatus, setFilterStatus] = useState('');
  const [logs, setLogs]                 = useState([]);
  const [total, setTotal]               = useState(0);
  const [loading, setLoading]           = useState(true);
  const [fetchError, setFetchError]     = useState(null);

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
      <div style={s.topRow}>
        <div>
          <h1 style={s.pageTitle}>Audit Log</h1>
          <p style={s.pageSubtitle}>System event history — filterable by user and action type</p>
        </div>
        <div style={s.ethicsBadge}>
          <span style={s.ethicsCheck}><IconCheck /></span>
          Certified Ethical — Verified
        </div>
      </div>

      <div style={s.filterRow}>
        <select style={s.select} value={filterUID} onChange={e => setFilterUID(e.target.value)}>
          <option value="">All Users</option>
          <option value="Lecturer">Lecturer</option>
          <option value="Head of Technology">Head of Technology</option>
        </select>

        <select style={s.select} value={filterAction} onChange={e => setFilterAction(e.target.value)}>
          <option value="">All Action Types</option>
          <option value="Login">Login</option>
          <option value="Login Failed">Login Failed</option>
          <option value="Access Denied">Access Denied</option>
          <option value="Data Upload">Data Upload</option>
          <option value="Data Processed">Data Processed</option>
          <option value="Prediction Run">Prediction Run</option>
        </select>

        <select style={s.select} value={filterStatus} onChange={e => setFilterStatus(e.target.value)}>
          <option value="">All Status</option>
          <option value="Success">Success</option>
          <option value="Alert">Alert</option>
          <option value="Denied">Denied</option>
          <option value="Error">Error</option>
        </select>
      </div>

      <div style={s.card}>
        <div style={s.tableWrapper}>
          <table style={s.table}>
            <thead>
              <tr>
                {['Event_ID', 'Timestamp', 'User_UID', 'Action_Type', 'Status', 'Detail'].map(col => (
                  <th key={col} style={s.th}>{col}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {loading ? (
                <tr><td colSpan={6} style={s.emptyCell}>Loading…</td></tr>
              ) : fetchError ? (
                <tr><td colSpan={6} style={{ ...s.emptyCell, color: '#DC2626' }}>{fetchError}</td></tr>
              ) : filtered.length === 0 ? (
                <tr><td colSpan={6} style={s.emptyCell}>No events match the selected filters.</td></tr>
              ) : (
                filtered.map((row, i) => {
                  const badge = STATUS_BADGE[row.status] || STATUS_BADGE.Error;
                  return (
                    <tr key={row.event_id} style={i % 2 === 0 ? s.trEven : s.trOdd}>
                      <td style={{ ...s.td, ...s.tdMono }}>{row.event_id}</td>
                      <td style={{ ...s.td, ...s.tdMono, whiteSpace: 'nowrap' }}>{row.timestamp}</td>
                      <td style={{ ...s.td, ...s.tdMono }}>{row.user_uid}</td>
                      <td style={s.td}>{row.action_type}</td>
                      <td style={s.td}>
                        <span style={{ ...s.badge, background: badge.bg, color: badge.color, borderColor: badge.border }}>
                          {row.status}
                        </span>
                      </td>
                      <td style={{ ...s.td, ...s.tdDetail }}>{row.detail}</td>
                    </tr>
                  );
                })
              )}
            </tbody>
          </table>
        </div>

        <div style={s.footer}>
          Showing <strong>{filtered.length}</strong> of <strong>{total}</strong> events
        </div>
      </div>
    </div>
  );
}

const s = {
  topRow:       { display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 28 },
  pageTitle:    { margin: '0 0 6px', fontSize: 26, fontWeight: 700, color: '#1E293B' },
  pageSubtitle: { margin: 0, fontSize: 14, color: '#64748B' },

  ethicsBadge: {
    display: 'flex', alignItems: 'center', gap: 7,
    background: '#EEF9F5', border: '1px solid #A7F3D0',
    color: '#059669', borderRadius: 20,
    padding: '7px 16px', fontSize: 13, fontWeight: 600,
    whiteSpace: 'nowrap', alignSelf: 'center',
  },
  ethicsCheck: {
    display: 'flex', alignItems: 'center', justifyContent: 'center',
    width: 20, height: 20, borderRadius: '50%',
    background: '#059669', color: '#fff', flexShrink: 0,
  },

  filterRow: { display: 'flex', gap: 12, marginBottom: 24, flexWrap: 'wrap' },
  select: {
    padding: '9px 36px 9px 14px',
    background: '#2E6E8E', color: '#fff', border: 'none',
    borderRadius: 8, fontSize: 13, fontWeight: 500, cursor: 'pointer',
    appearance: 'none',
    backgroundImage: `url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='12' height='12' viewBox='0 0 24 24' fill='none' stroke='white' stroke-width='2.5' stroke-linecap='round' stroke-linejoin='round'%3E%3Cpolyline points='6 9 12 15 18 9'/%3E%3C/svg%3E")`,
    backgroundRepeat: 'no-repeat', backgroundPosition: 'right 12px center',
    minWidth: 180,
  },

  card:         { background: '#fff', border: '0.5px solid #DDE4EA', borderRadius: 10, overflow: 'hidden' },
  tableWrapper: { overflowX: 'auto' },
  table:        { width: '100%', borderCollapse: 'collapse', fontSize: 13 },
  th: {
    padding: '12px 16px', textAlign: 'left',
    fontSize: 11, fontWeight: 700, color: '#94A3B8',
    textTransform: 'uppercase', letterSpacing: 0.6,
    background: '#F8FAFC', borderBottom: '1px solid #E2E8F0', whiteSpace: 'nowrap',
  },
  trEven:   { background: '#fff' },
  trOdd:    { background: '#F8FAFC' },
  td:       { padding: '12px 16px', color: '#334155', borderBottom: '1px solid #F1F5F9', verticalAlign: 'middle' },
  tdMono:   { fontFamily: "'SF Mono','Fira Code',monospace", fontSize: 12, color: '#475569' },
  tdDetail: { color: '#64748B', maxWidth: 320 },
  emptyCell: { padding: '32px 16px', textAlign: 'center', color: '#94A3B8', fontStyle: 'italic' },

  badge: {
    display: 'inline-block', padding: '3px 10px',
    borderRadius: 12, border: '1px solid',
    fontSize: 12, fontWeight: 600, letterSpacing: 0.3,
  },

  footer: {
    padding: '12px 20px', borderTop: '1px solid #E2E8F0',
    fontSize: 13, color: '#64748B', background: '#F8FAFC',
  },
};
