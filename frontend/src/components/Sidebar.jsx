// Role-aware navigation sidebar with user avatar, nav links, and logout button.
import { useState, useEffect, useCallback, useRef } from 'react';
import { NavLink, useLocation } from 'react-router-dom';
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
  Report: () => (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <line x1="18" y1="20" x2="18" y2="10"/><line x1="12" y1="20" x2="12" y2="4"/><line x1="6" y1="20" x2="6" y2="14"/>
    </svg>
  ),
  Shield: () => (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/>
    </svg>
  ),
  Mail: () => (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <rect x="2" y="4" width="20" height="16" rx="2"/>
      <path d="M22 6l-10 7L2 6"/>
    </svg>
  ),
  ChevronDown: () => (
    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
      <polyline points="6 9 12 15 18 9"/>
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

// Reporting/Settings sub-items are shared across roles (built dynamically
// per-user in the component below, since which ones are visible depends on
// role/ACL) — these arrays hold each role's top-level items plus a
// placeholder `{ group: 'reporting' | 'settings' }` marker that gets
// expanded into the right children at render time.

const LECTURER_NAV = [
  { label: 'Dashboard', icon: <I.Dashboard />, to: '/dashboard/lecturer' },
  { label: 'Explorer',  icon: <I.Explorer />,  to: '/explorer'           },
  { label: 'Predictor', icon: <I.Predictor />, to: '/predictor'          },
  { group: 'reporting' },
  { group: 'settings'  },
];

const HOS_NAV = [
  { label: 'Dashboard',      icon: <I.Dashboard />, to: '/dashboard/admin' },
  { group: 'reporting' },
  { label: 'Model Health',   icon: <I.Explorer />,  to: '/model-health'    },
  { label: 'Data Ingestion', icon: <I.Ingestion />, to: '/data-ingestion'  },
  { group: 'settings'  },
];

const ADMIN_NAV_BASE = [
  { label: 'Dashboard',      icon: <I.Dashboard />, to: '/dashboard/admin' },
  { group: 'reporting' },
  { label: 'Model Health',   icon: <I.Explorer />,  to: '/model-health'    },
  { label: 'Data Ingestion', icon: <I.Ingestion />, to: '/data-ingestion'  },
  { group: 'settings'  },
];

// Full reporting children — each role's ACL (route guard) is unchanged,
// this list is filtered to what that role could already reach.
const REPORTING_CHILDREN = [
  { label: 'Subject Analytics',  icon: <I.Explorer />,      to: '/subject-analytics',  roles: ['admin', 'hos']            },
  { label: 'Student Analytics',  icon: <I.Explorer />,      to: '/student-analytics',  roles: ['admin', 'hos']            },
  { label: 'Predictive Reports', icon: <I.Predictor />,     to: '/predictive-reports', roles: ['admin', 'hos']            },
  { label: 'Students at Risk',   icon: <I.AlertTriangle />, to: '/students-at-risk',   roles: ['admin', 'hos', 'lecturer'] },
];

// ── Component ─────────────────────────────────────────────────────────────────

export default function Sidebar() {
  const [collapsed, setCollapsed] = useState(false);
  const location   = useLocation();
  const user       = getUser();
  const isAdmin      = user?.role === 'Head of Technology';
  const isHoS        = user?.role === 'Head of School';
  const roleKey      = isAdmin ? 'admin' : isHoS ? 'hos' : 'lecturer';

  // Same ACL as before per item — this only changes where each link lives
  // in the tree, not who can reach it (route guards in App.js are untouched).
  const reportingChildren = REPORTING_CHILDREN.filter(c => c.roles.includes(roleKey));
  // Email Logs and Audit Logs live under one nested "Logs" group rather than
  // as flat Settings entries — every Head of Technology account is a full
  // administrator, so both are gated on role alone, same as the rest of Settings.
  const logsChildren = [
    ...(isAdmin || isHoS ? [{ label: 'Email Logs', icon: <I.Mail />,     to: '/email-logs' }] : []),
    ...(isAdmin ? [{ label: 'Audit Logs', icon: <I.AuditLog />, to: '/audit-log' }] : []),
  ];
  const settingsChildren  = [
    { label: 'My Profile', icon: <I.Settings />, to: '/settings' },
    ...(isAdmin || isHoS ? [{ label: 'Risk Email Templates', icon: <I.AlertTriangle />, to: '/risk-email-template' }] : []),
    ...(isAdmin || isHoS ? [{ label: 'OAuth Providers', icon: <I.Shield />, to: '/oauth-providers' }] : []),
    ...(isAdmin || isHoS ? [{ label: 'AI Config', icon: <I.AI />, to: '/ai-config' }] : []),
    ...(isAdmin || isHoS ? [{ label: 'Outgoing Mail Servers', icon: <I.Mail />, to: '/mail-servers' }] : []),
    ...(isAdmin ? [{ label: 'API Console', icon: <I.ApiKey />, to: '/api-console' }] : []),
    ...(isAdmin ? [{ label: 'User Management', icon: <I.Users />, to: '/users' }] : []),
    ...(logsChildren.length ? [{ label: 'Logs', icon: <I.AuditLog />, children: logsChildren }] : []),
  ];

  const rawNav = isAdmin ? ADMIN_NAV_BASE : isHoS ? HOS_NAV : LECTURER_NAV;
  const navItems = rawNav.map(item => {
    if (item.group === 'reporting') return { label: 'Reporting', icon: <I.Report />, children: reportingChildren };
    if (item.group === 'settings')  return { label: 'Settings',  icon: <I.Settings />, children: settingsChildren };
    return item;
  });

  // Recurses so a nested group (e.g. Logs inside Settings) counts as active
  // whenever one of its own children matches the current route.
  const isChildActive = children => children.some(c => c.children ? isChildActive(c.children) : location.pathname === c.to);

  // Walks the tree collecting every group (top-level and nested) so their
  // open/closed state can all live in the one flat openGroups map, keyed by
  // each group's (unique) label.
  const collectGroups = items => items.flatMap(item => item.children ? [item, ...collectGroups(item.children)] : []);

  const [openGroups, setOpenGroups] = useState(() => {
    const init = {};
    collectGroups(navItems).forEach(group => { init[group.label] = isChildActive(group.children); });
    return init;
  });

  // Auto-expand whichever group contains the route just navigated to,
  // without forcing shut a group the user opened manually.
  useEffect(() => {
    setOpenGroups(prev => {
      const next = { ...prev };
      collectGroups(navItems).forEach(group => {
        if (isChildActive(group.children)) next[group.label] = true;
      });
      return next;
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [location.pathname]);

  const toggleGroup = label => {
    if (collapsed) { setCollapsed(false); setOpenGroups(prev => ({ ...prev, [label]: true })); return; }
    setOpenGroups(prev => ({ ...prev, [label]: !prev[label] }));
  };

  // Only these two roles can reach Data Ingestion at all (require_head_of_school).
  const ingestBadge = useIngestBadge(isAdmin || isHoS);

  const handleLogout = () => {
    api.post('/api/auth/logout').catch(() => {});
    localStorage.clear();
    window.location.href = '/login';
  };

  const initials = getUserInitials();

  // Cursor-follow spotlight (the soft glow-that-tracks-your-mouse effect
  // popular on AI product sites, e.g. claude.ai's own marketing pages) —
  // written straight to the DOM via CSS custom properties on every
  // mousemove instead of React state, since state would re-render the
  // whole sidebar (nav tree, badges, everything) dozens of times a second
  // just to move a glow.
  const spotlightRef = useRef(null);
  const handleSpotlightMove = (e) => {
    const el = spotlightRef.current;
    if (!el) return;
    const rect = e.currentTarget.getBoundingClientRect();
    el.style.setProperty('--mx', `${e.clientX - rect.left}px`);
    el.style.setProperty('--my', `${e.clientY - rect.top}px`);
  };

  return (
    <aside
      className="sb-root"
      style={{ ...s.sidebar, width: collapsed ? 64 : 220, minWidth: collapsed ? 64 : 220 }}
      onMouseMove={handleSpotlightMove}
    >
      {/* Purely decorative glow — subtle depth behind the brand mark, clipped
          by the sidebar's own overflow:hidden so it never bleeds into content. */}
      <div style={s.glowBlob} aria-hidden="true" />
      {/* Spotlight that follows the cursor while it's over the sidebar —
          fades in/out via the .sb-root:hover rule in the <style> block below. */}
      <div ref={spotlightRef} className="sb-spotlight" aria-hidden="true" />

      {/* ── Brand ──────────────────────────────────────────────────── */}
      <div style={{
        ...s.logo,
        justifyContent: collapsed ? 'center' : 'space-between',
        padding: collapsed ? '0 0 20px' : '0 20px 20px',
      }}>
        {!collapsed && (
          <div style={{ display: 'flex', alignItems: 'center', gap: 10, animation: 'sidebarLabelIn 0.18s ease' }}>
            <div style={s.logoIcon}>E</div>
            <span style={s.logoText}>EDAPT v2</span>
          </div>
        )}
        <button
          onClick={() => setCollapsed(c => !c)}
          className="sb-toggle"
          style={{ ...s.toggleBtn, transform: collapsed ? 'rotate(180deg)' : 'rotate(0deg)' }}
          title={collapsed ? 'Expand sidebar' : 'Collapse sidebar'}
        >
          <I.ChevronLeft />
        </button>
      </div>

      {/* ── Navigation ─────────────────────────────────────────────── */}
      <nav style={s.nav}>
        {navItems.map((item, itemIndex) => {
          if (item.children) {
            const isOpen = !!openGroups[item.label];
            const groupActive = isChildActive(item.children);
            return (
              <div key={item.label} style={{ animation: 'sbItemIn 0.3s ease both', animationDelay: `${itemIndex * 0.04}s` }}>
                <button
                  type="button"
                  onClick={() => toggleGroup(item.label)}
                  className="sb-item"
                  style={{
                    ...s.item, ...s.groupHeader,
                    ...(groupActive && !isOpen ? s.itemActive : {}),
                    justifyContent: collapsed ? 'center' : 'flex-start',
                    padding: collapsed ? '10px 0' : '12px 20px',
                  }}
                  title={collapsed ? item.label : undefined}
                >
                  {groupActive && !isOpen && <span style={s.activeBar} />}
                  <span style={s.icon}>{item.icon}</span>
                  {!collapsed && <span style={{ flex: 1, textAlign: 'left', animation: 'sidebarLabelIn 0.18s ease' }}>{item.label}</span>}
                  {!collapsed && (
                    <span style={{ display: 'flex', transition: 'transform 0.2s ease', transform: isOpen ? 'rotate(0deg)' : 'rotate(-90deg)' }}>
                      <I.ChevronDown />
                    </span>
                  )}
                </button>
                {!collapsed && (
                  <div style={{ display: 'grid', gridTemplateRows: isOpen ? '1fr' : '0fr', transition: 'grid-template-rows 0.25s cubic-bezier(0.4, 0, 0.2, 1)' }}>
                    <div style={{ overflow: 'hidden' }}>
                      <div style={{ ...s.subNav, opacity: isOpen ? 1 : 0, transition: 'opacity 0.2s ease' }}>
                        {item.children.map(child => child.children ? (
                          // Nested group (e.g. Logs under Settings) — only ever rendered
                          // inside an already-expanded, already-visible parent, so it
                          // needs none of the top-level group's collapsed-sidebar handling.
                          <div key={child.label}>
                            <button
                              type="button"
                              onClick={() => toggleGroup(child.label)}
                              className="sb-item"
                              style={{
                                ...s.item, ...s.subItem, ...s.groupHeader,
                                ...(isChildActive(child.children) && !openGroups[child.label] ? s.itemActive : {}),
                              }}
                            >
                              {isChildActive(child.children) && !openGroups[child.label] && <span style={s.activeBar} />}
                              <span style={s.icon}>{child.icon}</span>
                              <span style={{ flex: 1, textAlign: 'left' }}>{child.label}</span>
                              <span style={{
                                display: 'flex', transition: 'transform 0.2s ease',
                                transform: openGroups[child.label] ? 'rotate(0deg)' : 'rotate(-90deg)',
                              }}>
                                <I.ChevronDown />
                              </span>
                            </button>
                            <div style={{
                              display: 'grid',
                              gridTemplateRows: openGroups[child.label] ? '1fr' : '0fr',
                              transition: 'grid-template-rows 0.25s cubic-bezier(0.4, 0, 0.2, 1)',
                            }}>
                              <div style={{ overflow: 'hidden' }}>
                                <div style={{
                                  ...s.subNav, margin: '2px 0 2px 16px',
                                  opacity: openGroups[child.label] ? 1 : 0, transition: 'opacity 0.2s ease',
                                }}>
                                  {child.children.map(grandchild => (
                                    <NavLink
                                      key={grandchild.to}
                                      to={grandchild.to}
                                      className="sb-item"
                                      style={({ isActive }) => ({
                                        ...s.item, ...s.subItem,
                                        ...(isActive ? s.itemActive : {}),
                                      })}
                                    >
                                      {({ isActive }) => (
                                        <>
                                          {isActive && <span style={s.activeBar} />}
                                          <span style={s.icon}>{grandchild.icon}</span>
                                          {grandchild.label}
                                        </>
                                      )}
                                    </NavLink>
                                  ))}
                                </div>
                              </div>
                            </div>
                          </div>
                        ) : (
                          <NavLink
                            key={child.to}
                            to={child.to}
                            className="sb-item"
                            style={({ isActive }) => ({
                              ...s.item, ...s.subItem,
                              ...(isActive ? s.itemActive : {}),
                            })}
                          >
                            {({ isActive }) => (
                              <>
                                {isActive && <span style={s.activeBar} />}
                                <span style={s.icon}>{child.icon}</span>
                                {child.label}
                              </>
                            )}
                          </NavLink>
                        ))}
                      </div>
                    </div>
                  </div>
                )}
              </div>
            );
          }

          const { label, icon, to } = item;
          const showBadge = to === '/data-ingestion' && ingestBadge.count > 0;
          return (
            <NavLink
              key={to}
              to={to}
              className="sb-item"
              style={({ isActive }) => ({
                ...s.item,
                ...(isActive ? s.itemActive : {}),
                justifyContent: collapsed ? 'center' : 'flex-start',
                padding: collapsed ? '10px 0' : '12px 20px',
                position: 'relative',
                animation: 'sbItemIn 0.3s ease both',
                animationDelay: `${itemIndex * 0.04}s`,
              })}
              title={collapsed ? `${label} (${ingestBadge.count} new)` : undefined}
            >
              {({ isActive }) => (
                <>
                  {isActive && <span style={s.activeBar} />}
                  <span style={{ ...s.icon, position: 'relative' }}>
                    {icon}
                    {showBadge && collapsed && (
                      <span style={{
                        ...s.navBadge, ...s.navBadgeCollapsed,
                        ...(ingestBadge.hasFailure ? s.navBadgeFailure : {}),
                        animation: 'sbBadgePulse 1.8s ease-out infinite',
                      }} />
                    )}
                  </span>
                  {!collapsed && <span style={{ animation: 'sidebarLabelIn 0.18s ease' }}>{label}</span>}
                  {!collapsed && showBadge && (
                    <span style={{
                      ...s.navBadge, ...(ingestBadge.hasFailure ? s.navBadgeFailure : {}),
                      animation: 'sbBadgePulse 1.8s ease-out infinite',
                    }}>
                      {ingestBadge.count}
                    </span>
                  )}
                </>
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
          <div style={s.userAvatarWrap} title={collapsed ? getUserName() : undefined}>
            <div style={s.userAvatar}>{initials}</div>
            <span style={s.onlineDot} />
          </div>
          {!collapsed && (
            <div style={{ animation: 'sidebarLabelIn 0.18s ease' }}>
              <div style={s.userName}>{getUserName()}</div>
              <div style={s.userRole}>{user?.role || 'Staff'}</div>
            </div>
          )}
        </div>

        {!collapsed && (
          <button onClick={handleLogout} className="sb-logout" style={{ ...s.logoutBtn, animation: 'sidebarLabelIn 0.18s ease' }}>
            <I.Logout />
            <span>Sign Out</span>
          </button>
        )}
        {collapsed && (
          <button onClick={handleLogout} className="sb-logout" style={{ ...s.logoutBtnCollapsed }} title="Sign Out">
            <I.Logout />
          </button>
        )}
      </div>

      <style>{`
        @keyframes sidebarLabelIn {
          from { opacity: 0; transform: translateX(-4px); }
          to   { opacity: 1; transform: translateX(0); }
        }
        @keyframes sbItemIn {
          from { opacity: 0; transform: translateX(-6px); }
          to   { opacity: 1; transform: translateX(0); }
        }
        @keyframes sbLogoGlow {
          0%, 100% { box-shadow: 0 0 0 0 rgba(74, 155, 196, 0.45); }
          50%      { box-shadow: 0 0 16px 2px rgba(74, 155, 196, 0.45); }
        }
        @keyframes sbBadgePulse {
          0%   { box-shadow: 0 0 0 0 rgba(220, 38, 38, 0.55); }
          70%  { box-shadow: 0 0 0 6px rgba(220, 38, 38, 0); }
          100% { box-shadow: 0 0 0 0 rgba(220, 38, 38, 0); }
        }
        @keyframes sbGlowDrift {
          0%, 100% { transform: translate(0, 0) scale(1); }
          50%      { transform: translate(6px, 10px) scale(1.08); }
        }
        .sb-spotlight {
          position: absolute; inset: 0; z-index: 0; pointer-events: none;
          opacity: 0; transition: opacity 0.4s ease;
          background: radial-gradient(480px circle at var(--mx, 50%) var(--my, 0%),
            rgba(143, 211, 255, 0.10), transparent 55%);
        }
        .sb-root:hover .sb-spotlight { opacity: 1; }

        .sb-item:hover { background: rgba(255, 255, 255, 0.07); transform: translateX(3px) translateY(-1px); box-shadow: 0 4px 10px rgba(0,0,0,0.18); }
        .sb-item { transition: background 0.2s cubic-bezier(0.34, 1.56, 0.64, 1), transform 0.2s cubic-bezier(0.34, 1.56, 0.64, 1), color 0.15s ease, box-shadow 0.2s ease; }
        .sb-item svg { transition: transform 0.25s cubic-bezier(0.34, 1.56, 0.64, 1); }
        .sb-item:hover svg { transform: scale(1.15) rotate(-4deg); }
        .sb-toggle { transition: background 0.15s ease, transform 0.25s cubic-bezier(0.4, 0, 0.2, 1); }
        .sb-toggle:hover { background: rgba(255, 255, 255, 0.08); color: #CBD5E1; }
        .sb-logout { transition: background 0.15s ease, color 0.15s ease, transform 0.15s ease; }
        .sb-logout:hover { background: rgba(220, 38, 38, 0.12); color: #F87171; transform: translateX(2px); }
      `}</style>
    </aside>
  );
}

const s = {
  sidebar: {
    background: 'linear-gradient(180deg, #1D3347 0%, #17293A 60%, #142430 100%)',
    display: 'flex', flexDirection: 'column',
    boxSizing: 'border-box', position: 'relative',
    transition: 'width 0.25s cubic-bezier(0.4, 0, 0.2, 1), min-width 0.25s cubic-bezier(0.4, 0, 0.2, 1)',
    overflow: 'hidden', flexShrink: 0,
    height: '100vh',
    boxShadow: '2px 0 12px rgba(0,0,0,0.15)',
  },
  // Soft, slow-drifting radial glow behind the brand mark — purely
  // decorative, clipped by the sidebar's own overflow:hidden.
  glowBlob: {
    position: 'absolute', top: -60, left: -40, width: 200, height: 200,
    borderRadius: '50%', pointerEvents: 'none', zIndex: 0,
    background: 'radial-gradient(circle, rgba(74,155,196,0.25) 0%, rgba(74,155,196,0) 70%)',
    animation: 'sbGlowDrift 8s ease-in-out infinite',
  },
  logo: {
    display: 'flex', alignItems: 'center',
    borderBottom: '0.5px solid rgba(255,255,255,0.08)',
    padding: '24px 20px 20px',
    marginBottom: 8, position: 'relative', zIndex: 1,
  },
  logoIcon: {
    width: 30, height: 30, borderRadius: 7, flexShrink: 0,
    background: 'linear-gradient(135deg, #2E6E8E 0%, #4A9BC4 100%)',
    display: 'flex', alignItems: 'center', justifyContent: 'center',
    fontWeight: 800, fontSize: 15, color: '#fff',
    animation: 'sbLogoGlow 3.5s ease-in-out infinite',
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
  nav: { flex: 1, display: 'flex', flexDirection: 'column', gap: 2, padding: '4px 8px', overflowY: 'auto', position: 'relative', zIndex: 1 },
  item: {
    display: 'flex', alignItems: 'center', gap: 10,
    borderRadius: 8, fontSize: 13, fontWeight: 500,
    color: '#8BA5B8', textDecoration: 'none', position: 'relative',
    whiteSpace: 'nowrap',
  },
  itemActive: { background: 'linear-gradient(90deg, #2E6E8E 0%, #2C6280 100%)', color: '#fff', boxShadow: '0 2px 8px rgba(46,110,142,0.35)' },
  activeBar: {
    position: 'absolute', left: -8, top: '50%', transform: 'translateY(-50%)',
    width: 3, height: '60%', borderRadius: 3, background: '#8FD3FF',
  },
  icon: { display: 'flex', alignItems: 'center', flexShrink: 0 },
  groupHeader: {
    width: '100%', border: 'none', background: 'none', cursor: 'pointer',
    font: 'inherit',
  },
  subNav: { display: 'flex', flexDirection: 'column', gap: 2, margin: '2px 0 2px 20px' },
  subItem: { padding: '9px 16px', fontSize: 12.5 },
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
    marginTop: 'auto', position: 'relative', zIndex: 1,
  },
  userAvatarWrap: { position: 'relative', flexShrink: 0, display: 'flex' },
  userAvatar: {
    width: 36, height: 36, borderRadius: '50%', flexShrink: 0,
    background: 'linear-gradient(135deg, #2E6E8E 0%, #4A9BC4 100%)',
    display: 'flex', alignItems: 'center', justifyContent: 'center',
    fontSize: 13, fontWeight: 600, color: '#fff',
  },
  onlineDot: {
    position: 'absolute', bottom: -1, right: -1, width: 10, height: 10,
    borderRadius: '50%', background: '#22C55E', border: '2px solid #17293A',
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
