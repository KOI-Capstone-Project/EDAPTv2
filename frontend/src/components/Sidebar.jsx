import React, { useState } from 'react';
import { NavLink, useNavigate } from 'react-router-dom';

const IconChevronLeft = () => (
  <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
    <polyline points="15 18 9 12 15 6"/>
  </svg>
);
const IconChevronRight = () => (
  <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
    <polyline points="9 18 15 12 9 6"/>
  </svg>
);
const IconDashboard = () => (
  <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <rect x="3" y="3" width="7" height="7"/><rect x="14" y="3" width="7" height="7"/>
    <rect x="3" y="14" width="7" height="7"/><rect x="14" y="14" width="7" height="7"/>
  </svg>
);
const IconExplorer = () => (
  <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/>
  </svg>
);
const IconPredictor = () => (
  <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <polyline points="22 12 18 12 15 21 9 3 6 12 2 12"/>
  </svg>
);
const IconIngestion = () => (
  <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <polyline points="16 16 12 12 8 16"/><line x1="12" y1="12" x2="12" y2="21"/>
    <path d="M20.39 18.39A5 5 0 0 0 18 9h-1.26A8 8 0 1 0 3 16.3"/>
  </svg>
);
const IconAuditLog = () => (
  <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/>
    <polyline points="14 2 14 8 20 8"/>
    <line x1="16" y1="13" x2="8" y2="13"/>
    <line x1="16" y1="17" x2="8" y2="17"/>
    <polyline points="10 9 9 9 8 9"/>
  </svg>
);
const IconSettings = () => (
  <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <circle cx="12" cy="12" r="3"/>
    <path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-4 0v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83-2.83l.06-.06A1.65 1.65 0 0 0 4.68 15a1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1 0-4h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 2.83-2.83l.06.06A1.65 1.65 0 0 0 9 4.68a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 2.83l-.06.06A1.65 1.65 0 0 0 19.4 9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1z"/>
  </svg>
);
const IconLogout = () => (
  <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4"/>
    <polyline points="16 17 21 12 16 7"/><line x1="21" y1="12" x2="9" y2="12"/>
  </svg>
);

const NAV_ITEMS = [
  { label: 'Dashboard',      icon: <IconDashboard />, to: '/dashboard'      },
  { label: 'Explorer',       icon: <IconExplorer />,  to: '/explorer'       },
  { label: 'Predictor',      icon: <IconPredictor />, to: '/predictions'    },
  { label: 'Data Ingestion', icon: <IconIngestion />, to: '/data-ingestion' },
  { label: 'Audit Log',      icon: <IconAuditLog />,  to: '/audit-log'      },
  { label: 'Settings',       icon: <IconSettings />,  to: '/settings'       },
];

export default function Sidebar() {
  const navigate   = useNavigate();
  const [collapsed, setCollapsed] = useState(false);

  const user = (() => {
    try { return JSON.parse(localStorage.getItem('edapt_user') || '{}'); }
    catch { return {}; }
  })();

  const initials = user.name
    ? user.name.split(' ').map(w => w[0]).join('').slice(0, 2).toUpperCase()
    : 'U';

  const handleLogout = () => {
    localStorage.removeItem('edapt_token');
    localStorage.removeItem('edapt_user');
    navigate('/login');
  };

  return (
    <aside style={{ ...s.sidebar, width: collapsed ? 64 : 220, minWidth: collapsed ? 64 : 220 }}>

      {/* ── Brand / Toggle ───────────────────────────────────── */}
      <div style={{
        ...s.logo,
        justifyContent: collapsed ? 'center' : 'space-between',
        padding: collapsed ? '0 0 28px' : '0 20px 28px',
      }}>
        {!collapsed && (
          <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
            <div style={s.logoIcon}>E</div>
            <span style={s.logoText}>EDAPT v2</span>
          </div>
        )}
        <button
          onClick={() => setCollapsed(c => !c)}
          style={s.toggleBtn}
          title={collapsed ? 'Expand sidebar' : 'Collapse sidebar'}
        >
          {collapsed ? <IconChevronRight /> : <IconChevronLeft />}
        </button>
      </div>

      {/* ── Navigation ───────────────────────────────────────── */}
      <nav style={s.nav}>
        {NAV_ITEMS.map(({ label, icon, to }) => (
          <NavLink
            key={to}
            to={to}
            style={({ isActive }) => ({
              ...s.item,
              ...(isActive ? s.itemActive : {}),
              justifyContent: collapsed ? 'center' : 'flex-start',
              padding: collapsed ? '10px 0' : '9px 12px',
            })}
            title={collapsed ? label : undefined}
          >
            <span style={s.icon}>{icon}</span>
            {!collapsed && label}
          </NavLink>
        ))}
      </nav>

      {/* ── User info ────────────────────────────────────────── */}
      <div style={{
        ...s.userSection,
        padding: collapsed ? '16px 0' : '12px 20px',
        justifyContent: collapsed ? 'center' : 'flex-start',
      }}>
        <div style={s.userAvatar} title={collapsed ? (user.name || 'User') : undefined}>
          {initials}
        </div>
        {!collapsed && (
          <div>
            <div style={s.userName}>{user.name || 'User'}</div>
            <div style={s.userRole}>{user.role || 'staff'}</div>
          </div>
        )}
      </div>

      {/* ── Logout ───────────────────────────────────────────── */}
      <button
        onClick={handleLogout}
        style={{
          ...s.logout,
          justifyContent: collapsed ? 'center' : 'flex-start',
          padding: collapsed ? '9px 0' : '9px 12px',
          margin: collapsed ? '4px 0 0' : '4px 10px 0',
        }}
        title={collapsed ? 'Sign Out' : undefined}
      >
        <IconLogout />
        {!collapsed && <span style={{ marginLeft: 8 }}>Sign Out</span>}
      </button>
    </aside>
  );
}

const s = {
  sidebar: {
    background: '#1A2E40',
    display: 'flex',
    flexDirection: 'column',
    padding: '24px 0',
    boxSizing: 'border-box',
    transition: 'width 0.2s ease, min-width 0.2s ease',
    overflow: 'hidden',
    flexShrink: 0,
  },
  logo: {
    display: 'flex',
    alignItems: 'center',
    borderBottom: '1px solid rgba(255,255,255,0.07)',
    marginBottom: 16,
  },
  logoIcon: {
    width: 32, height: 32, borderRadius: 8, flexShrink: 0,
    background: 'linear-gradient(135deg, #2E6E8E, #4f8ef7)',
    display: 'flex', alignItems: 'center', justifyContent: 'center',
    fontWeight: 800, fontSize: 16, color: '#fff',
  },
  logoText: { fontSize: 14, fontWeight: 600, color: '#CBD5E1', letterSpacing: 0.4, whiteSpace: 'nowrap' },
  toggleBtn: {
    background: 'none', border: 'none', cursor: 'pointer',
    color: '#64748B', display: 'flex', alignItems: 'center',
    padding: 4, borderRadius: 6, flexShrink: 0,
  },
  nav: { flex: 1, display: 'flex', flexDirection: 'column', gap: 2, padding: '0 8px' },
  item: {
    display: 'flex', alignItems: 'center', gap: 10,
    borderRadius: 8, fontSize: 13, fontWeight: 500,
    color: '#94A3B8', textDecoration: 'none',
    transition: 'background 0.15s, color 0.15s', whiteSpace: 'nowrap',
  },
  itemActive: { background: '#2E6E8E', color: '#fff' },
  icon: { display: 'flex', alignItems: 'center', flexShrink: 0 },
  userSection: {
    display: 'flex', alignItems: 'center', gap: 10,
    borderTop: '1px solid rgba(255,255,255,0.07)',
  },
  userAvatar: {
    width: 32, height: 32, borderRadius: '50%', flexShrink: 0,
    background: 'linear-gradient(135deg, #2E6E8E, #4f8ef7)',
    display: 'flex', alignItems: 'center', justifyContent: 'center',
    fontSize: 12, fontWeight: 700, color: '#fff',
  },
  userName: { fontSize: 13, fontWeight: 600, color: '#CBD5E1', whiteSpace: 'nowrap' },
  userRole: { fontSize: 11, color: '#64748B', marginTop: 2, whiteSpace: 'nowrap', textTransform: 'capitalize' },
  logout: {
    display: 'flex', alignItems: 'center',
    borderRadius: 8, background: 'none', border: 'none',
    cursor: 'pointer', fontSize: 13, fontWeight: 500, color: '#64748B',
  },
};
