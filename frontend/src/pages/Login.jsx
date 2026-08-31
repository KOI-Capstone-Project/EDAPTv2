// Staff sign-in page with session-expired banner, email validation, and forgot-password link.
import { useState, useEffect, useRef } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import api from '../services/api';
import { getErrorMessage } from '../utils/apiError';
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
const Spinner = () => (
  <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3" strokeLinecap="round"
    style={{ animation: 'loginSpin 0.7s linear infinite' }}>
    <path d="M12 2a10 10 0 0 1 10 10" opacity="0.9"/>
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
      setError(getErrorMessage(err, 'Sign in failed. Please try again.'));
    } finally {
      setLoading(false);
    }
  };

  // Cursor-follow spotlight behind the sign-in card — same technique as the
  // sidebar's hover glow (written straight to the DOM via a CSS custom
  // property on mousemove, not React state, so it doesn't re-render the
  // form on every pixel of mouse movement).
  const spotlightRef = useRef(null);
  const handleSpotlightMove = (e) => {
    const el = spotlightRef.current;
    if (!el) return;
    const rect = e.currentTarget.getBoundingClientRect();
    el.style.setProperty('--mx', `${e.clientX - rect.left}px`);
    el.style.setProperty('--my', `${e.clientY - rect.top}px`);
  };

  return (
    <div style={s.root}>

      {/* ── Left panel — branding ─────────────────────────────── */}
      <div style={s.left}>
        {/* Decorative drifting glow orbs + scanning grid — purely visual,
            clipped by the panel's own overflow:hidden. */}
        <div style={{ ...s.orb, ...s.orbA }} aria-hidden="true" />
        <div style={{ ...s.orb, ...s.orbB }} aria-hidden="true" />
        <div style={{ ...s.orb, ...s.orbC }} aria-hidden="true" />
        <div style={s.gridOverlay} aria-hidden="true" />

        <div style={{ ...s.brand, position: 'relative', zIndex: 1, animation: 'loginFadeUp 0.5s ease both' }}>
          <div style={s.logoIcon}>E</div>
          <span style={s.logoText}>EDAPT v2</span>
        </div>

        <div style={{ ...s.tagline, position: 'relative', zIndex: 1 }}>
          <h2 style={{ ...s.taglineTitle, animation: 'loginFadeUp 0.5s ease both', animationDelay: '0.08s' }}>Educational Data Analytics</h2>
          <p style={{ ...s.taglineSub, animation: 'loginFadeUp 0.5s ease both', animationDelay: '0.16s' }}>& Predictive Tool</p>
          <p style={{ ...s.taglineDesc, animation: 'loginFadeUp 0.5s ease both', animationDelay: '0.24s' }}>
            Role-based analytics platform for King's Own Institute staff.
            Secure, anonymised, and audit-logged.
          </p>
        </div>

        <div style={{ ...s.iconGrid, position: 'relative', zIndex: 1 }}>
          {icons.map((icon, i) => (
            <div
              key={i}
              className="login-icon-dot"
              style={{ ...s.iconDot, animation: 'loginIconIn 0.4s cubic-bezier(0.34,1.56,0.64,1) both', animationDelay: `${0.3 + i * 0.06}s` }}
            >
              {icon}
            </div>
          ))}
        </div>

        <p style={{ ...s.koi, position: 'relative', zIndex: 1, animation: 'loginFadeUp 0.5s ease both', animationDelay: '0.6s' }}>
          King's Own Institute · Capstone 2026
        </p>
      </div>

      {/* ── Right panel — form ────────────────────────────────── */}
      <div style={s.right} className="login-right-panel" onMouseMove={handleSpotlightMove}>
        <div style={s.dotGrid} aria-hidden="true" />
        <div ref={spotlightRef} className="login-spotlight" aria-hidden="true" />

        <div className="login-card-ring" style={s.cardRing}>
          <div className="login-card-spin" aria-hidden="true" />
          <div style={s.card} className="login-card-inner">

            <h1 style={s.appTitle}>EDAPT</h1>
            <p style={s.cardTitle}>Staff Sign In</p>
            <p style={s.cardSub}>Enter your credentials to continue</p>

            {sessionExpired && (
              <div style={{ ...s.sessionBanner, animation: 'loginBannerIn 0.25s ease' }} role="alert">
                ⚠ Your session has expired. Please sign in again.
              </div>
            )}

            <form onSubmit={handleSubmit} style={s.form}>

              <div style={s.field}>
                <label style={s.label}>Staff Email / ID</label>
                <input
                  type="text"
                  className="login-input"
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
                    className="login-input"
                    style={{ ...s.input, paddingRight: 44 }}
                    value={password}
                    onChange={e => { setPassword(e.target.value); setError(null); }}
                    placeholder="••••••••"
                    autoComplete="current-password"
                    required
                  />
                  <button
                    type="button"
                    className="login-eye-btn"
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
                <div style={{ ...s.errorBanner, animation: 'loginBannerIn 0.25s ease' }} role="alert">
                  <span>⚠</span> {error}
                </div>
              )}

              <button
                type="submit"
                className="login-submit-btn"
                style={{ ...s.submitBtn, opacity: loading ? 0.85 : 1 }}
                disabled={loading}
              >
                <span style={{ display: 'inline-flex', alignItems: 'center', gap: 8, position: 'relative', zIndex: 1 }}>
                  {loading && <Spinner />}
                  {loading ? 'Signing in…' : 'Sign In'}
                </span>
              </button>

            </form>

            <OAuthButtons disabled={loading} onSuccess={completeLogin} onError={setError} />
          </div>
        </div>
      </div>

      <style>{`
        @keyframes loginFadeUp {
          from { opacity: 0; transform: translateY(8px); }
          to   { opacity: 1; transform: translateY(0); }
        }
        @keyframes loginIconIn {
          from { opacity: 0; transform: scale(0.5) translateY(6px); }
          to   { opacity: 1; transform: scale(1) translateY(0); }
        }
        @keyframes loginCardIn {
          from { opacity: 0; transform: translateY(14px) scale(0.98); }
          to   { opacity: 1; transform: translateY(0) scale(1); }
        }
        @keyframes loginBannerIn {
          from { opacity: 0; transform: translateY(-6px); }
          to   { opacity: 1; transform: translateY(0); }
        }
        @keyframes loginOrbDriftA {
          0%, 100% { transform: translate(0, 0) scale(1); }
          50%      { transform: translate(30px, 20px) scale(1.1); }
        }
        @keyframes loginOrbDriftB {
          0%, 100% { transform: translate(0, 0) scale(1); }
          50%      { transform: translate(-24px, 26px) scale(1.06); }
        }
        @keyframes loginOrbDriftC {
          0%, 100% { transform: translate(0, 0) scale(1); }
          50%      { transform: translate(18px, -22px) scale(1.12); }
        }
        @keyframes loginGridPan {
          from { background-position: 0 0; }
          to   { background-position: 48px 48px; }
        }
        @keyframes loginBorderSpin {
          from { transform: rotate(0deg); }
          to   { transform: rotate(360deg); }
        }
        @keyframes sbLogoGlowLogin {
          0%, 100% { box-shadow: 0 0 0 0 rgba(79, 142, 247, 0.5); }
          50%      { box-shadow: 0 0 16px 3px rgba(79, 142, 247, 0.5); }
        }
        @keyframes loginSpin {
          from { transform: rotate(0deg); }
          to   { transform: rotate(360deg); }
        }
        @keyframes loginShimmerSweep {
          from { transform: translateX(-120%) skewX(-15deg); }
          to   { transform: translateX(220%) skewX(-15deg); }
        }

        .login-icon-dot { transition: transform 0.25s cubic-bezier(0.34,1.56,0.64,1), background 0.2s ease, border-color 0.2s ease, color 0.2s ease; }
        .login-icon-dot:hover {
          transform: translateY(-3px) scale(1.08);
          background: rgba(79,142,247,0.16);
          border-color: rgba(79,142,247,0.4);
          color: #8FC4FF;
        }

        .login-spotlight {
          position: absolute; inset: 0; z-index: 0; pointer-events: none;
          opacity: 0; transition: opacity 0.4s ease;
          background: radial-gradient(500px circle at var(--mx, 50%) var(--my, 30%),
            rgba(79, 142, 247, 0.14), transparent 60%);
        }
        .login-right-panel:hover .login-spotlight { opacity: 1; }

        .login-card-spin {
          position: absolute; inset: -80%; z-index: 0;
          background: conic-gradient(from 0deg, #2E6E8E, #4f8ef7 30%, #8b5cf6 55%, #4f8ef7 80%, #2E6E8E 100%);
          animation: loginBorderSpin 8s linear infinite;
        }
        .login-card-inner { position: relative; z-index: 1; }

        .login-input { transition: border-color 0.2s ease, box-shadow 0.2s ease, background 0.2s ease; }
        .login-input:focus { border-color: #4f8ef7 !important; box-shadow: 0 0 0 3px rgba(79,142,247,0.16); background: #fff !important; }

        .login-eye-btn { transition: color 0.15s ease, transform 0.15s ease; }
        .login-eye-btn:hover { color: #4f8ef7; transform: translateY(-50%) scale(1.1); }

        .login-submit-btn {
          position: relative; overflow: hidden;
          transition: transform 0.15s ease, box-shadow 0.2s ease, opacity 0.15s ease;
        }
        .login-submit-btn::after {
          content: ''; position: absolute; top: 0; left: 0; width: 40%; height: 100%;
          background: linear-gradient(120deg, transparent, rgba(255,255,255,0.35), transparent);
          transform: translateX(-120%) skewX(-15deg);
        }
        .login-submit-btn:hover:not(:disabled) { transform: translateY(-1px); box-shadow: 0 6px 18px rgba(46,110,142,0.35); }
        .login-submit-btn:hover:not(:disabled)::after { animation: loginShimmerSweep 0.9s ease; }
        .login-submit-btn:active:not(:disabled) { transform: translateY(0) scale(0.99); }
      `}</style>
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
    background: 'linear-gradient(160deg, #1D3347 0%, #17293A 55%, #142430 100%)',
    display: 'flex',
    flexDirection: 'column',
    padding: '48px 36px',
    boxSizing: 'border-box',
    position: 'relative',
    overflow: 'hidden',
  },
  orb: {
    position: 'absolute', borderRadius: '50%', pointerEvents: 'none', zIndex: 0,
    filter: 'blur(4px)',
  },
  orbA: {
    top: -60, right: -60, width: 220, height: 220,
    background: 'radial-gradient(circle, rgba(79,142,247,0.3) 0%, rgba(79,142,247,0) 70%)',
    animation: 'loginOrbDriftA 9s ease-in-out infinite',
  },
  orbB: {
    bottom: 40, left: -70, width: 200, height: 200,
    background: 'radial-gradient(circle, rgba(139,92,246,0.22) 0%, rgba(139,92,246,0) 70%)',
    animation: 'loginOrbDriftB 11s ease-in-out infinite',
  },
  orbC: {
    top: '40%', left: '50%', width: 160, height: 160,
    background: 'radial-gradient(circle, rgba(46,110,142,0.28) 0%, rgba(46,110,142,0) 70%)',
    animation: 'loginOrbDriftC 10s ease-in-out infinite',
  },
  gridOverlay: {
    position: 'absolute', inset: 0, zIndex: 0, pointerEvents: 'none', opacity: 0.5,
    backgroundImage: `linear-gradient(rgba(255,255,255,0.05) 1px, transparent 1px),
                       linear-gradient(90deg, rgba(255,255,255,0.05) 1px, transparent 1px)`,
    backgroundSize: '48px 48px',
    animation: 'loginGridPan 14s linear infinite',
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
    animation: 'sbLogoGlowLogin 3.2s ease-in-out infinite',
    boxShadow: '0 0 0 0 rgba(79,142,247,0.5)',
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
    cursor: 'default',
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
    position: 'relative',
    overflow: 'hidden',
  },
  dotGrid: {
    position: 'absolute', inset: 0, zIndex: 0, pointerEvents: 'none',
    backgroundImage: 'radial-gradient(rgba(46,110,142,0.12) 1px, transparent 1px)',
    backgroundSize: '22px 22px',
  },
  cardRing: {
    position: 'relative', zIndex: 1, borderRadius: 18, padding: 2,
    isolation: 'isolate', overflow: 'hidden',
    animation: 'loginCardIn 0.45s cubic-bezier(0.16,1,0.3,1) both',
  },
  card: {
    background: '#fff',
    borderRadius: 16,
    padding: '40px 40px 36px',
    width: '100%',
    maxWidth: 400,
    boxShadow: '0 4px 24px rgba(0,0,0,0.07)',
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
    background: 'linear-gradient(135deg, #2E6E8E, #4f8ef7)',
    color: '#fff',
    border: 'none',
    borderRadius: 8,
    fontSize: 15,
    fontWeight: 600,
    cursor: 'pointer',
    marginTop: 4,
  },

  forgotLink: {
    fontSize: 12,
    color: '#2E6E8E',
    textDecoration: 'none',
  },
};
