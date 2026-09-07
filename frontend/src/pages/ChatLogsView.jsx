// Chat Logs: every question asked to the EDAPT Assistant and the answer it
// gave — see ChatLog's docstring in backend/app/db/models.py for why this
// is a separate, dedicated table rather than just the generic AuditLog
// entry the chatbot already wrote before this page existed (that entry
// only ever kept a 120-char-truncated question, no answer, model, or
// token count).
import { useState, useEffect, useCallback } from 'react';
import api from '../services/api';

function fmt(iso) {
  if (!iso) return '—';
  return new Date(iso).toLocaleString('en-AU', { day: '2-digit', month: 'short', year: 'numeric', hour: '2-digit', minute: '2-digit' });
}

function truncate(text, max = 90) {
  if (!text) return '—';
  return text.length > max ? `${text.slice(0, max)}…` : text;
}

function Spinner() {
  return <span style={s.spinner} />;
}

// Same initials-in-a-gradient-circle convention as the sidebar's own user
// avatar (Sidebar.jsx) — this app has no photo-upload feature (User has no
// avatar/photo column at all), so initials are the only "photo" it's ever
// had anywhere. Falls back to the email's first character when no name is
// resolved (a user_uid whose account was since deleted, say).
function initialsFromName(name, fallback) {
  const source = name || fallback || '';
  const initials = source.trim().split(/\s+/).map(w => w[0] || '').join('').toUpperCase().slice(0, 2);
  return initials || '?';
}

function UserAvatar({ name, userUid, size = 30 }) {
  return (
    <span style={{ ...s.avatar, width: size, height: size, fontSize: size * 0.4 }}>
      {initialsFromName(name, userUid)}
    </span>
  );
}

function UserCell({ name, userUid }) {
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
      <UserAvatar name={name} userUid={userUid} />
      <div style={{ minWidth: 0 }}>
        <div style={{ fontWeight: 500, color: '#1A2E40', whiteSpace: 'nowrap' }}>{name || userUid}</div>
        {name && <div style={{ fontSize: 11, color: '#8BA5B8', whiteSpace: 'nowrap' }}>{userUid}</div>}
      </div>
    </div>
  );
}

// Question/answer are shown as raw, escaped source (a <pre> block), not
// rendered HTML — same reasoning as EmailLogsView's DetailPanel: a chat
// answer is free text that could contain anything, and this panel is for
// reviewing what was actually asked/answered, not for live-rendering it.
function DetailPanel({ log, onClose }) {
  if (!log) return null;
  return (
    <div style={s.modalOverlay} onClick={onClose}>
      <div style={s.modalCard} onClick={e => e.stopPropagation()}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 14 }}>
          <h3 style={s.formTitle}>Chat #{log.id}</h3>
          <button style={s.cancelLink} onClick={onClose}>Close</button>
        </div>
        <div style={s.detailGrid}>
          <span style={s.detailLabel}>Asked At</span><span>{fmt(log.asked_at)}</span>
          <span style={s.detailLabel}>User</span>
          <span><UserCell name={log.name} userUid={log.user_uid} /></span>
          <span style={s.detailLabel}>Role</span><span>{log.role || '—'}</span>
          <span style={s.detailLabel}>Study Period</span><span>{log.study_period_used || '—'}</span>
          <span style={s.detailLabel}>Model</span><span>{log.model || '—'}</span>
          <span style={s.detailLabel}>Tokens Used</span><span>{log.tokens_used ?? '—'}</span>
        </div>
        <p style={s.docsLabel}>Question</p>
        <pre style={s.codeBlock}>{log.question}</pre>
        <p style={s.docsLabel}>Answer</p>
        <pre style={s.codeBlock}>{log.answer}</pre>
      </div>
    </div>
  );
}

export default function ChatLogsView() {
  const [logs, setLogs]       = useState([]);
  const [loading, setLoading] = useState(true);
  const [users, setUsers]     = useState([]);
  const [userFilter, setUserFilter] = useState('');
  const [detailId, setDetailId] = useState(null);
  const [detail, setDetail]     = useState(null);
  const [detailLoading, setDetailLoading] = useState(false);

  useEffect(() => {
    api.get('/api/chat-logs/users').then(r => setUsers(r.data.users || [])).catch(() => setUsers([]));
  }, []);

  const fetchLogs = useCallback(() => {
    setLoading(true);
    const params = { limit: 100 };
    if (userFilter) params.user_uid = userFilter;
    api.get('/api/chat-logs', { params })
      .then(r => setLogs(r.data.logs || []))
      .catch(() => setLogs([]))
      .finally(() => setLoading(false));
  }, [userFilter]);

  useEffect(() => { fetchLogs(); }, [fetchLogs]);

  const openDetail = (id) => {
    setDetailId(id);
    setDetailLoading(true);
    api.get(`/api/chat-logs/${id}`)
      .then(r => setDetail(r.data))
      .catch(() => setDetail(null))
      .finally(() => setDetailLoading(false));
  };
  const closeDetail = () => { setDetailId(null); setDetail(null); };

  return (
    <div>
      <style>{`@keyframes chatLogSpin { to { transform: rotate(360deg); } }`}</style>

      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 24, flexWrap: 'wrap', gap: 12 }}>
        <div>
          <h1 style={s.pageTitle}>Chat Logs</h1>
          <p style={s.pageSub}>Every question asked to the EDAPT Assistant, and the answer it gave</p>
        </div>
        <select style={s.select} value={userFilter} onChange={e => setUserFilter(e.target.value)}>
          <option value="">All users</option>
          {users.map(u => (
            <option key={u.user_uid} value={u.user_uid}>
              {u.name || u.user_uid}{u.role ? ` (${u.role})` : ''} — {u.count} {u.count === 1 ? 'question' : 'questions'}
            </option>
          ))}
        </select>
      </div>

      <div style={s.tableWrapper}>
        <table style={s.table}>
          <thead>
            <tr style={s.thead}>
              {['Asked At', 'User', 'Role', 'Question', 'Study Period', 'Tokens', ''].map(col => (
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
                    <div style={{ fontSize: 32, marginBottom: 12 }}>💬</div>
                    <div style={{ fontSize: 14, fontWeight: 500, color: '#1A2E40', marginBottom: 4 }}>No chat questions logged yet</div>
                    <div style={{ fontSize: 13 }}>Ask the EDAPT Assistant a question to see one here</div>
                  </div>
                </td>
              </tr>
            ) : logs.map((log, i) => (
              <tr key={log.id} style={{ background: i % 2 === 0 ? '#fff' : '#F8FAFB' }}>
                <td style={{ ...s.td, whiteSpace: 'nowrap' }}>{fmt(log.asked_at)}</td>
                <td style={s.td}><UserCell name={log.name} userUid={log.user_uid} /></td>
                <td style={s.td}>{log.role || '—'}</td>
                <td style={s.td}>{truncate(log.question)}</td>
                <td style={s.td}>{log.study_period_used || '—'}</td>
                <td style={s.td}>{log.tokens_used ?? '—'}</td>
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
    maxWidth: 320,
  },

  spinner: {
    display: 'inline-block', width: 20, height: 20, borderRadius: '50%',
    border: '3px solid #F0F4F8', borderTopColor: '#2E6E8E', animation: 'chatLogSpin 0.8s linear infinite',
  },

  // Same gradient-circle-with-initials convention as the sidebar's own
  // user avatar (components/Sidebar.jsx) — this app has no photo upload
  // feature, so initials are the closest thing to a "photo" it has.
  avatar: {
    display: 'inline-flex', alignItems: 'center', justifyContent: 'center',
    borderRadius: '50%', flexShrink: 0,
    background: 'linear-gradient(135deg, #2E6E8E 0%, #4A9BC4 100%)',
    color: '#fff', fontWeight: 600, lineHeight: 1,
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
    whiteSpace: 'pre-wrap', wordBreak: 'break-word', margin: 0, overflowX: 'auto', maxHeight: 220, overflowY: 'auto',
  },
};
