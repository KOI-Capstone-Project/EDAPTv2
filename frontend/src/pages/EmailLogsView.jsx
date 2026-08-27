// Email Logs: every email this app has tried to send (Send Test Email,
// forgot-password OTP), success or failure — see EmailLog's docstring in
// backend/app/db/models.py for why status is only ever Sent/Failed, never
// a fabricated "Delivered" (plain SMTP can't confirm actual mailbox
// delivery without bounce/webhook infrastructure this app doesn't have).
import { useState, useEffect, useCallback } from 'react';
import api from '../services/api';

const KIND_LABELS = { test: 'Test Email', password_reset: 'Password Reset' };

function fmt(iso) {
  if (!iso) return '—';
  return new Date(iso).toLocaleString('en-AU', { day: '2-digit', month: 'short', year: 'numeric', hour: '2-digit', minute: '2-digit' });
}

function Spinner() {
  return <span style={s.spinner} />;
}

// Body is shown as raw, escaped source rather than rendered HTML — an
// admin-entered test-email body is arbitrary user input, and rendering it
// live (dangerouslySetInnerHTML) would let one admin's saved log entry run
// script in another admin's session when they later view it. Reviewing the
// source is what this panel is actually for (what was sent / why it
// failed), not a live preview.
function DetailPanel({ log, onClose }) {
  if (!log) return null;
  return (
    <div style={s.modalOverlay} onClick={onClose}>
      <div style={s.modalCard} onClick={e => e.stopPropagation()}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 14 }}>
          <h3 style={s.formTitle}>Email #{log.id}</h3>
          <button style={s.cancelLink} onClick={onClose}>Close</button>
        </div>
        <div style={s.detailGrid}>
          <span style={s.detailLabel}>Status</span>
          <span>
            <span style={{ ...s.badge, ...(log.status === 'sent' ? s.badgeSent : s.badgeFailed) }}>
              {log.status === 'sent' ? 'Sent' : 'Failed'}
            </span>
          </span>
          <span style={s.detailLabel}>Sent At</span><span>{fmt(log.sent_at)}</span>
          <span style={s.detailLabel}>From</span><span>{log.from_email}</span>
          <span style={s.detailLabel}>To</span><span>{log.to_email}</span>
          <span style={s.detailLabel}>Subject</span><span>{log.subject || '—'}</span>
          <span style={s.detailLabel}>Kind</span><span>{KIND_LABELS[log.kind] || log.kind}</span>
          <span style={s.detailLabel}>Sent By</span><span>{log.sent_by || 'system'}</span>
          {log.status === 'failed' && (
            <>
              <span style={s.detailLabel}>Failure Reason</span>
              <span style={{ color: '#A32D2D' }}>{log.failure_reason || 'Unknown error'}</span>
            </>
          )}
        </div>
        <p style={s.docsLabel}>Body source {log.is_html ? '(HTML)' : '(plain text)'}</p>
        <pre style={s.codeBlock}>{log.body}</pre>
      </div>
    </div>
  );
}

export default function EmailLogsView() {
  const [logs, setLogs]       = useState([]);
  const [loading, setLoading] = useState(true);
  const [statusFilter, setStatusFilter] = useState('');
  const [kindFilter, setKindFilter]     = useState('');
  const [detailId, setDetailId] = useState(null);
  const [detail, setDetail]     = useState(null);
  const [detailLoading, setDetailLoading] = useState(false);

  const fetchLogs = useCallback(() => {
    setLoading(true);
    const params = { limit: 100 };
    if (statusFilter) params.status = statusFilter;
    if (kindFilter)   params.kind = kindFilter;
    api.get('/api/email-logs', { params })
      .then(r => setLogs(r.data.logs || []))
      .catch(() => setLogs([]))
      .finally(() => setLoading(false));
  }, [statusFilter, kindFilter]);

  useEffect(() => { fetchLogs(); }, [fetchLogs]);

  const openDetail = (id) => {
    setDetailId(id);
    setDetailLoading(true);
    api.get(`/api/email-logs/${id}`)
      .then(r => setDetail(r.data))
      .catch(() => setDetail(null))
      .finally(() => setDetailLoading(false));
  };
  const closeDetail = () => { setDetailId(null); setDetail(null); };

  return (
    <div>
      <style>{`@keyframes mailSpin { to { transform: rotate(360deg); } }`}</style>

      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 24, flexWrap: 'wrap', gap: 12 }}>
        <div>
          <h1 style={s.pageTitle}>Email Logs</h1>
          <p style={s.pageSub}>Every email EDAPT has tried to send, and whether it succeeded</p>
        </div>
        <div style={{ display: 'flex', gap: 10 }}>
          <select style={s.select} value={statusFilter} onChange={e => setStatusFilter(e.target.value)}>
            <option value="">All statuses</option>
            <option value="sent">Sent</option>
            <option value="failed">Failed</option>
          </select>
          <select style={s.select} value={kindFilter} onChange={e => setKindFilter(e.target.value)}>
            <option value="">All kinds</option>
            <option value="test">Test Email</option>
            <option value="password_reset">Password Reset</option>
          </select>
        </div>
      </div>

      <div style={s.tableWrapper}>
        <table style={s.table}>
          <thead>
            <tr style={s.thead}>
              {['Sent At', 'From', 'To', 'Subject', 'Kind', 'Status', ''].map(col => (
                <th key={col} style={s.th}>{col}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {loading ? (
              <tr><td colSpan={7} style={{ padding: '50px 0', textAlign: 'center' }}><Spinner /></td></tr>
            ) : logs.length === 0 ? (
              <tr>
                <td colSpan={7} style={{ padding: 0, border: 'none' }}>
                  <div style={{ textAlign: 'center', padding: '50px 20px', color: '#8BA5B8' }}>
                    <div style={{ fontSize: 32, marginBottom: 12 }}>📭</div>
                    <div style={{ fontSize: 14, fontWeight: 500, color: '#1A2E40', marginBottom: 4 }}>No emails logged yet</div>
                    <div style={{ fontSize: 13 }}>Send a test email from Outgoing Mail Servers to see one here</div>
                  </div>
                </td>
              </tr>
            ) : logs.map((log, i) => (
              <tr key={log.id} style={{ background: i % 2 === 0 ? '#fff' : '#F8FAFB' }}>
                <td style={{ ...s.td, whiteSpace: 'nowrap' }}>{fmt(log.sent_at)}</td>
                <td style={s.td}>{log.from_email}</td>
                <td style={s.td}>{log.to_email}</td>
                <td style={s.td}>{log.subject || '—'}</td>
                <td style={s.td}>{KIND_LABELS[log.kind] || log.kind}</td>
                <td style={s.td}>
                  <span style={{ ...s.badge, ...(log.status === 'sent' ? s.badgeSent : s.badgeFailed) }}>
                    {log.status === 'sent' ? 'Sent' : 'Failed'}
                  </span>
                </td>
                <td style={s.td}>
                  <button style={s.iconBtnNeutral} onClick={() => openDetail(log.id)}>View</button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {detailId != null && (
        detailLoading
          ? <div style={s.modalOverlay}><div style={s.modalCard}><Spinner /></div></div>
          : <DetailPanel log={detail} onClose={closeDetail} />
      )}
    </div>
  );
}

const s = {
  pageTitle: { margin: '0 0 4px', fontSize: 24, fontWeight: 500, color: '#1A2E40' },
  pageSub:   { margin: 0, fontSize: 13, color: '#5A7A8A' },

  select: {
    height: 36, padding: '0 12px', borderRadius: 8, border: '0.5px solid #C5D2DC',
    fontSize: 13, color: '#1A2E40', background: '#fff', cursor: 'pointer', outline: 'none',
  },

  spinner: {
    display: 'inline-block', width: 20, height: 20, borderRadius: '50%',
    border: '3px solid #F0F4F8', borderTopColor: '#2E6E8E', animation: 'mailSpin 0.8s linear infinite',
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
  td: { padding: '12px 16px', color: '#1A2E40', borderBottom: '0.5px solid #F0F4F8', verticalAlign: 'middle' },

  badge: { display: 'inline-block', padding: '3px 10px', borderRadius: 20, border: '0.5px solid', fontSize: 12, fontWeight: 500 },
  badgeSent:   { background: '#E1F5EE', color: '#0F6E56', borderColor: '#5DCAA5' },
  badgeFailed: { background: '#FCEBEB', color: '#A32D2D', borderColor: '#F09595' },

  iconBtnNeutral: { padding: '5px 12px', borderRadius: 6, border: '0.5px solid #DDE4EA', background: '#fff', fontSize: 12, fontWeight: 500, color: '#2E6E8E', cursor: 'pointer' },
  cancelLink: { background: 'none', border: 'none', cursor: 'pointer', fontSize: 13, color: '#5A7A8A', textDecoration: 'underline', fontWeight: 500 },

  modalOverlay: {
    position: 'fixed', inset: 0, background: 'rgba(26,46,64,0.5)',
    display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 1000,
  },
  modalCard: {
    background: '#fff', borderRadius: 12, padding: '20px 24px',
    width: '90%', maxWidth: 560, maxHeight: '80vh', overflowY: 'auto',
  },
  formTitle: { margin: 0, fontSize: 15, fontWeight: 500, color: '#1A2E40' },
  detailGrid: { display: 'grid', gridTemplateColumns: '120px 1fr', gap: '8px 12px', fontSize: 13, marginBottom: 16 },
  detailLabel: { color: '#8BA5B8', fontWeight: 600 },

  docsLabel: { fontSize: 11, fontWeight: 600, color: '#8BA5B8', textTransform: 'uppercase', letterSpacing: 0.5, margin: '14px 0 6px' },
  codeBlock: {
    background: '#F0F4F8', borderRadius: 8, padding: '10px 12px',
    fontFamily: "'SF Mono','Fira Code',monospace", fontSize: 11.5, color: '#1A2E40',
    whiteSpace: 'pre-wrap', wordBreak: 'break-word', margin: 0, overflowX: 'auto', maxHeight: 260, overflowY: 'auto',
  },
};
