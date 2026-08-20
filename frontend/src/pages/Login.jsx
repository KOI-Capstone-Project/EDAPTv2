// Staff sign-in page with session-expired banner, email validation, and forgot-password link.
import { useState, useEffect } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import api from '../services/api';
import { getToken, isAdmin, STORAGE_TOKEN_KEY, STORAGE_USER_KEY } from '../utils/auth';
import { SESSION_EXPIRED_KEY } from '../api/client';
import OAuthButtons from '../components/OAuthButtons';

const EyeOpen = () => (
  <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"/>
    <circle cx="12" cy="12" r="3"/>
  </svg>
);
const EyeClosed = () => (
  <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <path d="M17.94 17.94A10.07 10.07 0 0 1 12 20c-7 0-11-8-11-8a18.45 18.45 0 0 1 5.06-5.94"/>
    <path d="M9.9 4.24A9.12 9.12 0 0 1 12 4c7 0 11 8 11 8a18.5 18.5 0 0 1-2.16 3.19"/>
    <line x1="1" y1="1" x2="23" y2="23"/>
  </svg>
);

// Decorative icons shown on the left panel
const icons = [
  <svg key="dash" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round"><rect x="3" y="3" width="7" height="7"/><rect x="14" y="3" width="7" height="7"/><rect x="3" y="14" width="7" height="7"/><rect x="14" y="14" width="7" height="7"/></svg>,
  <svg key="pred" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round"><polyline points="22 12 18 12 15 21 9 3 6 12 2 12"/></svg>,
  <svg key="data" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round"><polyline points="16 16 12 12 8 16"/><line x1="12" y1="12" x2="12" y2="21"/><path d="M20.39 18.39A5 5 0 0 0 18 9h-1.26A8 8 0 1 0 3 16.3"/></svg>,
  <svg key="audit" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/><line x1="16" y1="13" x2="8" y2="13"/><line x1="16" y1="17" x2="8" y2="17"/></svg>,
  <svg key="set" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round"><circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-4 0v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83-2.83l.06-.06A1.65 1.65 0 0 0 4.68 15a1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1 0-4h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 2.83-2.83l.06.06A1.65 1.65 0 0 0 9 4.68a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 2.83l-.06.06A1.65 1.65 0 0 0 19.4 9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1z"/></svg>,
];

function isValidEmail(email) {
  if (!email || email.length > 254) return false;
  const at = email.indexOf('@');
  if (at <= 0 || email.indexOf('@', at + 1) !== -1) return false;
  const local = email.slice(0, at);
  const rest  = email.slice(at + 1);
  if (!/^[a-zA-Z0-9._%+-]+$/.test(local)) return false;
  const dot = rest.lastIndexOf('.');
  if (dot <= 0) return false;
  return rest.slice(dot + 1).length >= 2;
}

export default function Login() {
  const navigate = useNavigate();

  useEffect(() => {
    if (getToken()) {
      navigate(isAdmin() ? '/dashboard/admin' : '/dashboard/lecturer', { replace: true });
    }
  }, [navigate]);

  const [email,            setEmail]            = useState('');
  const [password,         setPassword]         = useState('');
  const [showPassword,     setShowPassword]     = useState(false);
  const [loading,          setLoading]          = useState(false);
  const [error,            setError]            = useState(null);
  const [emailBlurWarning, setEmailBlurWarning] = useState(null);
  const [sessionExpired,   setSessionExpired]   = useState(false);

  useEffect(() => {
    if (sessionStorage.getItem(SESSION_EXPIRED_KEY) === '1') {
      setSessionExpired(true);
      sessionStorage.removeItem(SESSION_EXPIRED_KEY);
    }
  }, []);

  const handleEmailBlur = () => {
    if (!email) { setEmailBlurWarning(null); return; }
    // Only warn if the input looks like a mistyped email (has @ but fails format check)
    if (email.includes('@') && !isValidEmail(email)) {
      setEmailBlurWarning("This doesn't look like a valid email address.");
    } else {
      setEmailBlurWarning(null);
    }
  };

  const completeLogin = (data) => {
    localStorage.setItem(STORAGE_TOKEN_KEY, data.access_token);
    localStorage.setItem(STORAGE_USER_KEY,  JSON.stringify(data.user));

    if (['Head of Technology', 'Head of School'].includes(data.user.role)) {
      navigate('/dashboard/admin');
    } else {
      navigate('/dashboard/lecturer');
    }
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    setLoading(true);
    setError(null);

    try {
      const res = await api.post('/api/auth/login', { email, password });
      completeLogin(res.data);
    } catch (err) {
      setError(err.response?.data?.detail || 'Sign in failed. Please try again.');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div style={s.root}>

      {/* ── Left panel — branding ─────────────────────────────── */}
      <div style={s.left}>
        <div style={s.brand}>
          <div style={s.logoIcon}>E</div>
          <span style={s.logoText}>EDAPT v2</span>
        </div>

        <div style={s.tagline}>
          <h2 style={s.taglineTitle}>Educational Data Analytics</h2>
          <p style={s.taglineSub}>& Predictive Tool</p>
          <p style={s.taglineDesc}>
            Role-based analytics platform for King's Own Institute staff.
            Secure, anonymised, and audit-logged.
          </p>
        </div>

        <div style={s.iconGrid}>
          {icons.map((icon, i) => (
            <div key={i} style={s.iconDot}>{icon}</div>
          ))}
        </div>

        <p style={s.koi}>King's Own Institute · Capstone 2026</p>
      </div>

      {/* ── Right panel — form ────────────────────────────────── */}
      <div style={s.right}>
        <div style={s.card}>

          <h1 style={s.appTitle}>EDAPT</h1>
          <p style={s.cardTitle}>Staff Sign In</p>
          <p style={s.cardSub}>Enter your credentials to continue</p>

          {sessionExpired && (
            <div style={s.sessionBanner} role="alert">
              ⚠ Your session has expired. Please sign in again.
            </div>
          )}

          <form onSubmit={handleSubmit} style={s.form}>

            <div style={s.field}>
              <label style={s.label}>Staff Email / ID</label>
              <input
                type="text"
                style={s.input}
                value={email}
                onChange={e => { setEmail(e.target.value); setError(null); setEmailBlurWarning(null); }}
                onBlur={handleEmailBlur}
                placeholder="e.g. admin or you@koi.edu.au"
                autoComplete="username"
                required
              />
              {emailBlurWarning && (
                <span style={{ fontSize: 11, color: '#B45309', marginTop: 3, display: 'block' }}>
                  ⚠ {emailBlurWarning}
                </span>
              )}
            </div>

            <div style={s.field}>
              <label style={s.label}>Password</label>
              <div style={s.pwWrap}>
                <input
                  type={showPassword ? 'text' : 'password'}
                  style={{ ...s.input, paddingRight: 44 }}
                  value={password}
                  onChange={e => { setPassword(e.target.value); setError(null); }}
                  placeholder="••••••••"
                  autoComplete="current-password"
                  required
                />
                <button
                  type="button"
                  style={s.eyeBtn}
                  onClick={() => setShowPassword(v => !v)}
                  tabIndex={-1}
                  aria-label={showPassword ? 'Hide password' : 'Show password'}
                >
                  {showPassword ? <EyeOpen /> : <EyeClosed />}
                </button>
              </div>
              <div style={{ textAlign: 'right', marginTop: 4 }}>
                <Link to="/forgot-password" style={s.forgotLink}>Forgot password?</Link>
              </div>
            </div>

            {error && (
              <div style={s.errorBanner} role="alert">
                <span>⚠</span> {error}
              </div>
            )}

            <button
              type="submit"
              style={{ ...s.submitBtn, opacity: loading ? 0.75 : 1 }}
              disabled={loading}
            >
              {loading ? 'Signing in…' : 'Sign In'}
            </button>

          </form>

          <OAuthButtons disabled={loading} onSuccess={completeLogin} onError={setError} />
        </div>
      </div>
    </div>
  );
}

const s = {
  root: {
    display: 'flex',
    height: '100vh',
    fontFamily: "'Inter','Segoe UI',sans-serif",
    overflow: 'hidden',
  },

  /* ── Left panel ── */
  left: {
    width: 360,
    minWidth: 360,
    background: '#1A2E40',
    display: 'flex',
    flexDirection: 'column',
    padding: '48px 36px',
    boxSizing: 'border-box',
  },
  brand: {
    display: 'flex',
    alignItems: 'center',
    gap: 12,
    marginBottom: 48,
  },
  logoIcon: {
    width: 40, height: 40, borderRadius: 10,
    background: 'linear-gradient(135deg, #2E6E8E, #4f8ef7)',
    display: 'flex', alignItems: 'center', justifyContent: 'center',
    fontWeight: 800, fontSize: 20, color: '#fff', flexShrink: 0,
  },
  logoText: { fontSize: 18, fontWeight: 700, color: '#CBD5E1', letterSpacing: 0.5 },

  tagline: { marginBottom: 'auto' },
  taglineTitle: { margin: '0 0 4px', fontSize: 22, fontWeight: 700, color: '#fff', lineHeight: 1.3 },
  taglineSub:   { margin: '0 0 16px', fontSize: 22, fontWeight: 300, color: '#4f8ef7' },
  taglineDesc:  {
    margin: 0, fontSize: 13, color: 'rgba(203,213,225,0.7)',
    lineHeight: 1.7,
  },

  iconGrid: {
    display: 'flex',
    gap: 10,
    margin: '40px 0 32px',
    flexWrap: 'wrap',
  },
  iconDot: {
    width: 40, height: 40, borderRadius: 10,
    background: 'rgba(255,255,255,0.06)',
    border: '1px solid rgba(255,255,255,0.08)',
    display: 'flex', alignItems: 'center', justifyContent: 'center',
    color: 'rgba(148,163,184,0.7)',
  },

  koi: {
    margin: 0,
    fontSize: 11,
    color: 'rgba(100,116,139,0.8)',
    letterSpacing: 0.4,
  },

  /* ── Right panel ── */
  right: {
    flex: 1,
    background: '#F0F4F8',
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    padding: 32,
  },
  card: {
    background: '#fff',
    borderRadius: 16,
    padding: '40px 40px 36px',
    width: '100%',
    maxWidth: 400,
    boxShadow: '0 4px 24px rgba(0,0,0,0.07)',
    border: '0.5px solid #DDE4EA',
  },
  appTitle: {
    margin: '0 0 6px',
    fontSize: 28,
    fontWeight: 800,
    color: '#1A2E40',
    textAlign: 'center',
    letterSpacing: -0.5,
  },
  cardTitle: {
    margin: '0 0 4px',
    fontSize: 16,
    fontWeight: 600,
    color: '#1E293B',
    textAlign: 'center',
  },
  cardSub: {
    margin: '0 0 28px',
    fontSize: 13,
    color: '#64748B',
    textAlign: 'center',
  },

  form:  { display: 'flex', flexDirection: 'column', gap: 18 },
  field: { display: 'flex', flexDirection: 'column', gap: 6 },
  label: { fontSize: 13, fontWeight: 500, color: '#374151' },

  input: {
    width: '100%',
    padding: '11px 14px',
    border: '1.5px solid #E2E8F0',
    borderRadius: 8,
    fontSize: 14,
    color: '#1E293B',
    background: '#F8FAFC',
    outline: 'none',
    boxSizing: 'border-box',
    transition: 'border-color 0.15s',
  },

  pwWrap: { position: 'relative' },
  eyeBtn: {
    position: 'absolute', right: 12, top: '50%', transform: 'translateY(-50%)',
    background: 'none', border: 'none', cursor: 'pointer',
    color: '#94A3B8', display: 'flex', alignItems: 'center', padding: 2,
  },

  sessionBanner: {
    background: '#FFFBEB',
    border: '1px solid #FCD34D',
    color: '#92400E',
    borderRadius: 8,
    padding: '10px 14px',
    fontSize: 13,
    fontWeight: 500,
    marginBottom: 4,
  },

  errorBanner: {
    display: 'flex', alignItems: 'center', gap: 8,
    background: '#FEF2F2',
    border: '1px solid #FECACA',
    color: '#DC2626', borderRadius: 8,
    padding: '10px 14px', fontSize: 13, fontWeight: 500,
  },

  submitBtn: {
    width: '100%',
    padding: '13px',
    background: '#2E6E8E',
    color: '#fff',
    border: 'none',
    borderRadius: 8,
    fontSize: 15,
    fontWeight: 600,
    cursor: 'pointer',
    transition: 'opacity 0.15s',
    marginTop: 4,
  },

  forgotLink: {
    fontSize: 12,
    color: '#2E6E8E',
    textDecoration: 'none',
  },
};
