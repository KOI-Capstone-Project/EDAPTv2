import { useNavigate } from 'react-router-dom';

export default function PageUnavailable({ role = 'lecturer' }) {
  const navigate = useNavigate();
  const dashboardPath = role === 'admin' ? '/dashboard/admin' : '/dashboard/lecturer';

  return (
    <div style={s.wrap}>
      <div style={s.icon}>🚧</div>
      <h1 style={s.heading}>Page Unavailable</h1>
      <p style={s.sub}>
        Sorry, this page is not available right now.<br />
        We are working on it and will be back soon.
      </p>
      <span style={s.badge}>Coming in next release</span>
      <br />
      <button style={s.btn} onClick={() => navigate(dashboardPath)}>← Go back</button>
    </div>
  );
}

const s = {
  wrap:    { textAlign: 'center', padding: '80px 20px', maxWidth: 480, margin: '0 auto' },
  icon:    { fontSize: 56, marginBottom: 20 },
  heading: { margin: '0 0 12px', fontSize: 26, fontWeight: 700, color: '#1A2E40' },
  sub:     { margin: '0 0 24px', fontSize: 14, color: '#5A7A8A', lineHeight: 1.7 },
  badge: {
    display: 'inline-block', background: '#EFF6FF', color: '#2563EB',
    border: '1px solid #BFDBFE', borderRadius: 20, padding: '4px 14px',
    fontSize: 12, fontWeight: 600, marginBottom: 28,
  },
  btn: {
    display: 'inline-block', marginTop: 8, padding: '10px 24px',
    background: '#2E6E8E', color: '#fff', border: 'none',
    borderRadius: 8, fontSize: 14, fontWeight: 600, cursor: 'pointer',
  },
};
