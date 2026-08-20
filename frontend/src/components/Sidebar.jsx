// Role-aware navigation sidebar with user avatar, nav links, and logout button.
import { useState, useEffect, useCallback } from 'react';
import { NavLink } from 'react-router-dom';
import { getUser, getUserName, getUserInitials } from '../utils/auth';
import { INGEST_LAST_SEEN_KEY, INGEST_JOBS_SEEN_EVENT } from '../utils/ingestNotifications';
import api from '../services/api';

// Ingestion now runs in the background (see DataIngestion.jsx) — confirm
// returns immediately and the actual work finishes later. This is how the
// sidebar surfaces "it's done" without the admin needing to sit on that
// page: poll the shared job list, and badge any job the admin hasn't seen yet.
const INGEST_POLL_INTERVAL_MS = 20000;

function useIngestBadge(enabled) {
  const [badge, setBadge] = useState({ count: 0, hasFailure: false });

  const refresh = useCallback(async () => {
    if (!enabled) return;
    try {
      const res = await api.get('/api/ingest/jobs', { params: { limit: 50 } });
      const lastSeen = Number(localStorage.getItem(INGEST_LAST_SEEN_KEY) || 0);
      const unseen = res.data.jobs.filter(j => j.id > lastSeen && j.status !== 'running');
      setBadge({ count: unseen.length, hasFailure: unseen.some(j => j.status === 'failed') });
    } catch { /* sidebar badge is best-effort — a failed poll just skips this tick */ }
  }, [enabled]);

  useEffect(() => {
    if (!enabled) return;
    refresh();
    const timer = setInterval(refresh, INGEST_POLL_INTERVAL_MS);
    window.addEventListener(INGEST_JOBS_SEEN_EVENT, refresh);
    return () => {
      clearInterval(timer);
      window.removeEventListener(INGEST_JOBS_SEEN_EVENT, refresh);
    };
  }, [enabled, refresh]);

  return badge;
}

// ── Icons ─────────────────────────────────────────────────────────────────────

const I = {
  ChevronLeft: () => (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
      <polyline points="15 18 9 12 15 6"/>
    </svg>
  ),
  ChevronRight: () => (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
      <polyline points="9 18 15 12 9 6"/>
    </svg>
  ),
  Dashboard: () => (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <rect x="3" y="3" width="7" height="7"/><rect x="14" y="3" width="7" height="7"/>
      <rect x="3" y="14" width="7" height="7"/><rect x="14" y="14" width="7" height="7"/>
    </svg>
  ),
  Explorer: () => (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/>
    </svg>
  ),
  Predictor: () => (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <polyline points="22 12 18 12 15 21 9 3 6 12 2 12"/>
    </svg>
  ),
  Ingestion: () => (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <polyline points="16 16 12 12 8 16"/><line x1="12" y1="12" x2="12" y2="21"/>
      <path d="M20.39 18.39A5 5 0 0 0 18 9h-1.26A8 8 0 1 0 3 16.3"/>
    </svg>
  ),
  AuditLog: () => (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/>
      <polyline points="14 2 14 8 20 8"/>
      <line x1="16" y1="13" x2="8" y2="13"/><line x1="16" y1="17" x2="8" y2="17"/>
    </svg>
  ),
  Users: () => (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2"/>
      <circle cx="9" cy="7" r="4"/>
      <path d="M23 21v-2a4 4 0 0 0-3-3.87"/>
      <path d="M16 3.13a4 4 0 0 1 0 7.75"/>
    </svg>
  ),
  Settings: () => (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <circle cx="12" cy="12" r="3"/>
      <path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-4 0v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83-2.83l.06-.06A1.65 1.65 0 0 0 4.68 15a1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1 0-4h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 2.83-2.83l.06.06A1.65 1.65 0 0 0 9 4.68a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 2.83l-.06.06A1.65 1.65 0 0 0 19.4 9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1z"/>
    </svg>
  ),
  AI: () => (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M12 2l2.4 7.4H22l-6.2 4.5 2.4 7.4L12 17l-6.2 4.3 2.4-7.4L2 9.4h7.6z"/>
    </svg>
  ),
  AlertTriangle: () => (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"/>
      <line x1="12" y1="9" x2="12" y2="13"/><line x1="12" y1="17" x2="12.01" y2="17"/>
    </svg>
  ),
  ApiKey: () => (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <circle cx="7.5" cy="15.5" r="5.5"/>
      <path d="M21 2l-9.6 9.6"/><path d="M15.5 7.5l3 3L22 7l-3-3"/>
    </svg>
  ),
  Logout: () => (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4"/>
      <polyline points="16 17 21 12 16 7"/><line x1="21" y1="12" x2="9" y2="12"/>
    </svg>
  ),
};

// ── Nav items per role ────────────────────────────────────────────────────────

const LECTURER_NAV = [
  { label: 'Dashboard',        icon: <I.Dashboard />,     to: '/dashboard/lecturer' },
  { label: 'Explorer',         icon: <I.Explorer />,      to: '/explorer'           },
  { label: 'Predictor',        icon: <I.Predictor />,     to: '/predictor'          },
  { label: 'Students at Risk', icon: <I.AlertTriangle />, to: '/students-at-risk'   },
  { label: 'Settings',         icon: <I.Settings />,      to: '/settings'           },
];

const HOS_NAV = [
  { label: 'Dashboard',          icon: <I.Dashboard />,     to: '/dashboard/admin'    },
  { label: 'Subject Analytics',  icon: <I.Explorer />,      to: '/subject-analytics'  },
  { label: 'Model Health',       icon: <I.Explorer />,      to: '/model-health'       },
  { label: 'Student Analytics',  icon: <I.Explorer />,      to: '/student-analytics'  },
  { label: 'Predictive Reports', icon: <I.Predictor />,     to: '/predictive-reports' },
  { label: 'Students at Risk',   icon: <I.AlertTriangle />, to: '/students-at-risk'   },
  { label: 'Data Ingestion',     icon: <I.Ingestion />,     to: '/data-ingestion'     },
  { label: 'Settings',           icon: <I.Settings />,      to: '/settings'           },
];

const ADMIN_NAV_BASE = [
  { label: 'Dashboard',          icon: <I.Dashboard />,     to: '/dashboard/admin'       },
  { label: 'Subject Analytics',  icon: <I.Explorer />,      to: '/subject-analytics'     },
  { label: 'Model Health',       icon: <I.Explorer />,      to: '/model-health'          },
  { label: 'Student Analytics',  icon: <I.Explorer />,      to: '/student-analytics'     },
  { label: 'Predictive Reports', icon: <I.Predictor />,     to: '/predictive-reports'    },
  { label: 'Students at Risk',   icon: <I.AlertTriangle />, to: '/students-at-risk'      },
  { label: 'Data Ingestion',     icon: <I.Ingestion />,     to: '/data-ingestion'        },
  { label: 'API Console',        icon: <I.ApiKey />,        to: '/api-console'          },
];
const ADMIN_NAV_SUPER = [
  { label: 'Audit Log',      icon: <I.AuditLog />, to: '/audit-log' },
  { label: 'User Management', icon: <I.Users />,   to: '/users'     },
];
const ADMIN_NAV_SETTINGS = { label: 'Settings', icon: <I.Settings />, to: '/settings' };

// ── Component ─────────────────────────────────────────────────────────────────

export default function Sidebar() {
  const [collapsed, setCollapsed] = useState(false);
  const user       = getUser();
  const isAdmin      = user?.role === 'Head of Technology';
  const isHoS        = user?.role === 'Head of School';
  const isSuperAdmin = user?.email === 'admin';
  const navItems     = isAdmin
    ? [...ADMIN_NAV_BASE, ...(isSuperAdmin ? ADMIN_NAV_SUPER : []), ADMIN_NAV_SETTINGS]
    : isHoS
      ? HOS_NAV
      : LECTURER_NAV;

  // Only these two roles can reach Data Ingestion at all (require_head_of_school).
  const ingestBadge = useIngestBadge(isAdmin || isHoS);

  const handleLogout = () => {
    api.post('/api/auth/logout').catch(() => {});
    localStorage.clear();
    window.location.href = '/login';
  };

  const initials = getUserInitials();

  return (
    <aside style={{ ...s.sidebar, width: collapsed ? 64 : 220, minWidth: collapsed ? 64 : 220 }}>

      {/* ── Brand ──────────────────────────────────────────────────── */}
      <div style={{
        ...s.logo,
        justifyContent: collapsed ? 'center' : 'space-between',
        padding: collapsed ? '0 0 20px' : '0 20px 20px',
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
          {collapsed ? <I.ChevronRight /> : <I.ChevronLeft />}
        </button>
      </div>

      {/* ── Navigation ─────────────────────────────────────────────── */}
      <nav style={s.nav}>
        {navItems.map(({ label, icon, to }) => {
          const showBadge = to === '/data-ingestion' && ingestBadge.count > 0;
          return (
            <NavLink
              key={to}
              to={to}
              style={({ isActive }) => ({
                ...s.item,
                ...(isActive ? s.itemActive : {}),
                justifyContent: collapsed ? 'center' : 'flex-start',
                padding: collapsed ? '10px 0' : '12px 20px',
                position: 'relative',
              })}
              title={collapsed ? `${label} (${ingestBadge.count} new)` : undefined}
            >
              <span style={{ ...s.icon, position: 'relative' }}>
                {icon}
                {showBadge && collapsed && (
                  <span style={{ ...s.navBadge, ...s.navBadgeCollapsed, ...(ingestBadge.hasFailure ? s.navBadgeFailure : {}) }} />
                )}
              </span>
              {!collapsed && label}
              {!collapsed && showBadge && (
                <span style={{ ...s.navBadge, ...(ingestBadge.hasFailure ? s.navBadgeFailure : {}) }}>
                  {ingestBadge.count}
                </span>
              )}
            </NavLink>
          );
        })}
      </nav>

      {/* ── User info + Sign Out ────────────────────────────────────── */}
      <div style={{
        ...s.bottomSection,
        padding: collapsed ? '16px 0' : '16px 20px',
        alignItems: collapsed ? 'center' : 'flex-start',
      }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: collapsed ? 0 : 12 }}>
          <div style={s.userAvatar} title={collapsed ? getUserName() : undefined}>
            {initials}
          </div>
          {!collapsed && (
            <div>
              <div style={s.userName}>{getUserName()}</div>
              <div style={s.userRole}>{user?.role || 'Staff'}</div>
            </div>
          )}
        </div>

        {!collapsed && (
          <button onClick={handleLogout} style={s.logoutBtn}>
            <I.Logout />
            <span>Sign Out</span>
          </button>
        )}
        {collapsed && (
          <button onClick={handleLogout} style={{ ...s.logoutBtnCollapsed }} title="Sign Out">
            <I.Logout />
          </button>
        )}
      </div>
    </aside>
  );
}

const s = {
  sidebar: {
    background: '#1A2E40',
    display: 'flex', flexDirection: 'column',
    boxSizing: 'border-box',
    transition: 'width 0.2s ease, min-width 0.2s ease',
    overflow: 'hidden', flexShrink: 0,
    height: '100vh',
  },
  logo: {
    display: 'flex', alignItems: 'center',
    borderBottom: '0.5px solid rgba(255,255,255,0.08)',
    padding: '24px 20px 20px',
    marginBottom: 8,
  },
  logoIcon: {
    width: 30, height: 30, borderRadius: 7, flexShrink: 0,
    background: '#2E6E8E',
    display: 'flex', alignItems: 'center', justifyContent: 'center',
    fontWeight: 800, fontSize: 15, color: '#fff',
  },
  logoText: {
    fontSize: 14, fontWeight: 700, color: '#fff',
    letterSpacing: '2px', whiteSpace: 'nowrap', textTransform: 'uppercase',
  },
  toggleBtn: {
    background: 'none', border: 'none', cursor: 'pointer',
    color: '#4A6880', display: 'flex', alignItems: 'center',
    padding: 4, borderRadius: 6, flexShrink: 0,
  },
  nav: { flex: 1, display: 'flex', flexDirection: 'column', gap: 2, padding: '4px 8px', overflowY: 'auto' },
  item: {
    display: 'flex', alignItems: 'center', gap: 10,
    borderRadius: 8, fontSize: 13, fontWeight: 500,
    color: '#8BA5B8', textDecoration: 'none',
    transition: 'background 0.15s, color 0.15s', whiteSpace: 'nowrap',
  },
  itemActive: { background: '#2E6E8E', color: '#fff' },
  icon: { display: 'flex', alignItems: 'center', flexShrink: 0 },
  navBadge: {
    marginLeft: 'auto', display: 'inline-flex', alignItems: 'center', justifyContent: 'center',
    minWidth: 18, height: 18, padding: '0 5px', borderRadius: 999,
    background: '#2E6E8E', color: '#fff', fontSize: 10.5, fontWeight: 700, lineHeight: 1,
  },
  navBadgeFailure: { background: '#DC2626' },
  navBadgeCollapsed: {
    position: 'absolute', top: -4, right: -6, minWidth: 8, width: 8, height: 8, padding: 0,
  },

  bottomSection: {
    display: 'flex', flexDirection: 'column',
    borderTop: '0.5px solid #2E4A60',
    marginTop: 'auto',
  },
  userAvatar: {
    width: 36, height: 36, borderRadius: '50%', flexShrink: 0,
    background: '#2E6E8E',
    display: 'flex', alignItems: 'center', justifyContent: 'center',
    fontSize: 13, fontWeight: 600, color: '#fff',
  },
  userName: { fontSize: 13, fontWeight: 600, color: '#CBD5E1', whiteSpace: 'nowrap' },
  userRole: { fontSize: 11, color: '#4A6880', marginTop: 2, whiteSpace: 'nowrap' },

  logoutBtn: {
    display: 'flex', alignItems: 'center', gap: 8,
    borderRadius: 8, border: 'none', cursor: 'pointer',
    fontSize: 13, fontWeight: 500, color: '#4A6880',
    background: 'none', padding: '8px 0', width: '100%',
  },
  logoutBtnCollapsed: {
    display: 'flex', alignItems: 'center', justifyContent: 'center',
    borderRadius: 8, border: 'none', cursor: 'pointer',
    color: '#4A6880', background: 'none', padding: '8px 0', width: '100%', marginTop: 8,
  },
};
