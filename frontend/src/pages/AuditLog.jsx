import { useState, useMemo, useEffect, useRef, useCallback } from 'react';
import api from '../services/api';

const STATUS_BADGE = {
  Success: { bg: '#E1F5EE', color: '#0F6E56', border: '#5DCAA5' },
  Alert:   { bg: '#FAEEDA', color: '#633806', border: '#EF9F27' },
  Denied:  { bg: '#FCEBEB', color: '#A32D2D', border: '#F09595' },
  Error:   { bg: '#FCEBEB', color: '#A32D2D', border: '#F09595' },
};

const ACTION_ICON = {
  'Login':            '🔐',
  'Login Failed':     '⚠️',
  'Logout':           '🚪',
  'Data Upload':      '📤',
  'Password Changed': '🔑',
  'User Created':     '👤',
  'User Modified':    '✏️',
  'Access Denied':    '🚫',
  'Data Access':      '👁',
};

const ALL_ACTIONS = Object.keys(ACTION_ICON);

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
  if (!uid) return null;
  if (uid === 'admin' || uid.startsWith('HOT-')) return 'Head of Technology';
  if (uid === 'hos' || uid.startsWith('HOS-')) return 'Head of School';
  if (uid.startsWith('LEC-') || (uid !== 'unknown' && uid.length > 0)) return 'Lecturer';
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

const IconRefresh = ({ spinning }) => (
  <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor"
    strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round"
    style={{ display: 'block', animation: spinning ? 'spin 0.8s linear infinite' : 'none' }}>
    <polyline points="23 4 23 10 17 10"/>
    <path d="M20.49 15a9 9 0 1 1-2.12-9.36L23 10"/>
  </svg>
);

export default function AuditLog() {
  const [filterUID,    setFilterUID]    = useState('');
  const [filterAction, setFilterAction] = useState('');
  const [filterStatus, setFilterStatus] = useState('');
  const [logs,         setLogs]         = useState([]);
  const [total,        setTotal]        = useState(0);
  const [loading,      setLoading]      = useState(true);
  const [refreshing,   setRefreshing]   = useState(false);
  const [fetchError,   setFetchError]   = useState(null);
  const [lastUpdated,  setLastUpdated]  = useState(null);
  const intervalRef = useRef(null);

  const fetchLogs = useCallback((silent = false) => {
    if (silent) setRefreshing(true);
    else setLoading(true);
    setFetchError(null);
    api.get('/api/audit-logs')
      .then(res => {
        setLogs(res.data.data);
        setTotal(res.data.total);
        setLastUpdated(new Date());
      })
      .catch(() => setFetchError('Failed to load audit logs.'))
      .finally(() => { setLoading(false); setRefreshing(false); });
  }, []);

  useEffect(() => {
    fetchLogs(false);
    intervalRef.current = setInterval(() => fetchLogs(true), 30000);
    return () => clearInterval(intervalRef.current);
  }, [fetchLogs]);

  const filtered = useMemo(() => logs.filter(row => {
    if (filterUID    && rowRole(row) !== filterUID)      return false;
    if (filterAction && row.action_type !== filterAction) return false;
    if (filterStatus && row.status !== filterStatus)      return false;
    return true;
  }), [logs, filterUID, filterAction, filterStatus]);

  const fmtTime = (d) => d
    ? d.toLocaleTimeString('en-AU', { hour: '2-digit', minute: '2-digit', second: '2-digit' })
    : '—';

  return (
    <div>
      <style>{`@keyframes spin { to { transform: rotate(360deg); } }`}</style>

      {/* ── Header ──────────────────────────────────────────────────── */}
      <div style={s.topRow}>
        <div>
          <h1 style={s.pageTitle}>Audit Log</h1>
          <p style={s.pageSub}>System event history — filterable by user and action type</p>
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
          <div style={s.refreshInfo}>
            <span style={{ ...s.refreshDot, background: refreshing ? '#2E6E8E' : '#5DCAA5' }} />
            <span style={{ fontSize: 12, color: '#8BA5B8' }}>
              {refreshing ? 'Refreshing…' : `Updated ${fmtTime(lastUpdated)}`}
            </span>
            <button
              style={s.refreshBtn}
              onClick={() => fetchLogs(true)}
              title="Refresh now"
            >
              <IconRefresh spinning={refreshing} />
            </button>
          </div>
          <div style={s.ethicsBadge}>
            <span style={s.ethicsCheck}><IconCheck /></span>
            Certified Ethical — Verified
          </div>
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
              <option value="Head of School">Head of School</option>
            </select>
          </div>
          <div style={s.filterGroup}>
            <label style={s.filterLabel}>Action Type</label>
            <select style={s.select} value={filterAction} onChange={e => setFilterAction(e.target.value)}>
              <option value="">All Actions</option>
              {ALL_ACTIONS.map(a => (
                <option key={a} value={a}>{ACTION_ICON[a]} {a}</option>
              ))}
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
            <button
              style={s.clearBtn}
              onClick={() => { setFilterUID(''); setFilterAction(''); setFilterStatus(''); }}
            >
              Clear filters
            </button>
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
                {['Event ID', 'Timestamp', 'User', 'Action', 'Status', 'Detail'].map(col => (
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
                const badge  = STATUS_BADGE[row.status] || STATUS_BADGE.Error;
                const icon   = ACTION_ICON[row.action_type] || '📋';
                const role   = rowRole(row);
                return (
                  <tr key={row.event_id} style={{ background: i % 2 === 0 ? '#fff' : '#F8FAFB' }}>
                    <td style={{ ...s.td, ...s.tdMono }}>{row.event_id}</td>
                    <td style={{ ...s.td, ...s.tdMono, whiteSpace: 'nowrap' }}>{row.timestamp}</td>
                    <td style={s.td}>
                      <div style={{ fontWeight: 500, fontSize: 13, color: '#1A2E40' }}>{row.user_uid}</div>
                      {role && (
                        <div style={{ fontSize: 11, color: '#8BA5B8', marginTop: 1 }}>{role}</div>
                      )}
                    </td>
                    <td style={s.td}>
                      <span style={{ fontSize: 15, marginRight: 6 }}>{icon}</span>
                      {row.action_type}
                    </td>
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

        {/* ── Footer ────────────────────────────────────────────────── */}
        {!loading && (
          <div style={s.footer}>
            Showing <strong>{filtered.length}</strong> of <strong>{total}</strong> events
            {(filterUID || filterAction || filterStatus) && (
              <span style={{ color: '#8BA5B8' }}> (filtered)</span>
            )}
          </div>
        )}
      </div>
    </div>
  );
}

const s = {
  topRow:   { display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 24, flexWrap: 'wrap', gap: 12 },
  pageTitle: { margin: '0 0 4px', fontSize: 24, fontWeight: 500, color: '#1A2E40' },
  pageSub:   { margin: 0, fontSize: 13, color: '#5A7A8A' },

  refreshInfo: { display: 'flex', alignItems: 'center', gap: 6, background: '#F0F4F8', borderRadius: 20, padding: '5px 12px' },
  refreshDot:  { width: 8, height: 8, borderRadius: '50%', flexShrink: 0, transition: 'background 0.3s' },
  refreshBtn: {
    display: 'flex', alignItems: 'center', justifyContent: 'center',
    width: 24, height: 24, borderRadius: '50%', border: 'none',
    background: 'transparent', cursor: 'pointer', color: '#5A7A8A',
    padding: 0, marginLeft: 2,
  },

  ethicsBadge: {
    display: 'flex', alignItems: 'center', gap: 7,
    background: '#E1F5EE', border: '0.5px solid #5DCAA5',
    color: '#0F6E56', borderRadius: 20,
    padding: '7px 16px', fontSize: 13, fontWeight: 500,
    whiteSpace: 'nowrap',
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
  clearBtn: {
    height: 36, padding: '0 16px', borderRadius: 8,
    border: '0.5px solid #C5D2DC', fontSize: 13, color: '#5A7A8A',
    background: '#fff', cursor: 'pointer',
  },

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

  footer: {
    padding: '10px 16px', fontSize: 12, color: '#5A7A8A',
    borderTop: '0.5px solid #F0F4F8', background: '#FAFBFC',
  },
};
