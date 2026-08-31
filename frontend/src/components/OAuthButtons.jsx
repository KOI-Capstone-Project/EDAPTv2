// Google and Microsoft sign-in buttons for the login page. Which providers
// are configured/enabled is fetched at runtime from the backend (Settings >
// OAuth Providers, GET /api/oauth-providers/public) rather than baked in at
// build time — an unconfigured or disabled provider simply doesn't appear,
// the same as an unset client ID used to hide it.
import { useState, useEffect } from 'react';
import { GoogleLogin, GoogleOAuthProvider } from '@react-oauth/google';
import api from '../services/api';
import { getErrorMessage } from '../utils/apiError';
import { getMsalInstance } from '../utils/msal';

const MicrosoftIcon = () => (
  <svg width="16" height="16" viewBox="0 0 21 21" aria-hidden="true">
    <rect x="1"  y="1"  width="9" height="9" fill="#F25022" />
    <rect x="11" y="1"  width="9" height="9" fill="#7FBA00" />
    <rect x="1"  y="11" width="9" height="9" fill="#00A4EF" />
    <rect x="11" y="11" width="9" height="9" fill="#FFB900" />
  </svg>
);

export default function OAuthButtons({ onSuccess, onError, disabled }) {
  const [providers, setProviders] = useState(null); // null = still loading
  const [msLoading, setMsLoading] = useState(false);

  useEffect(() => {
    let cancelled = false;
    api.get('/api/oauth-providers/public')
      .then(r => { if (!cancelled) setProviders(r.data.providers); })
      .catch(() => { if (!cancelled) setProviders([]); });
    return () => { cancelled = true; };
  }, []);

  if (!providers || providers.length === 0) return null;

  const google    = providers.find(p => p.provider === 'google');
  const microsoft = providers.find(p => p.provider === 'microsoft');
  if (!google && !microsoft) return null;

  const exchangeToken = async (path, idToken) => {
    const res = await api.post(path, { id_token: idToken });
    onSuccess(res.data);
  };

  const handleGoogleSuccess = async (credentialResponse) => {
    try {
      await exchangeToken('/api/auth/google', credentialResponse.credential);
    } catch (err) {
      onError(getErrorMessage(err, 'Google sign-in failed. Please try again.'));
    }
  };

  const handleMicrosoft = async () => {
    setMsLoading(true);
    try {
      const instance = await getMsalInstance(microsoft.client_id, microsoft.tenant_id);
      const result = await instance.loginPopup({ scopes: ['openid', 'profile', 'email'] });
      await exchangeToken('/api/auth/microsoft', result.idToken);
    } catch (err) {
      if (err?.errorCode !== 'user_cancelled') {
        // MSAL errors (redirect URI mismatch, popup blocked, consent
        // required, wrong tenant, etc.) carry the real reason in
        // errorCode/errorMessage — the banner only ever shows a generic
        // fallback, so this is the only place that detail is visible.
        console.error('[Microsoft sign-in]', err?.errorCode, err?.errorMessage || err);
        onError(getErrorMessage(err, 'Microsoft sign-in failed. Please try again.'));
      }
    } finally {
      setMsLoading(false);
    }
  };

  const body = (
    <div style={s.wrap}>
      <div style={s.divider}>
        <span style={s.dividerLine} />
        <span style={s.dividerText}>or continue with</span>
        <span style={s.dividerLine} />
      </div>
      <div style={s.row}>
        {google && (
          <div style={s.googleWrap}>
            <GoogleLogin
              onSuccess={handleGoogleSuccess}
              onError={() => onError('Google sign-in failed. Please try again.')}
              theme="outline"
              size="large"
              width="320"
              text="signin_with"
            />
          </div>
        )}
        {microsoft && (
          <button
            type="button"
            style={s.msBtn}
            onClick={handleMicrosoft}
            disabled={disabled || msLoading}
          >
            <span style={s.msIconSlot}><MicrosoftIcon /></span>
            <span style={s.msLabel}>{msLoading ? 'Signing in…' : 'Sign in with Microsoft'}</span>
          </button>
        )}
      </div>
    </div>
  );

  return google
    ? <GoogleOAuthProvider clientId={google.client_id}>{body}</GoogleOAuthProvider>
    : body;
}

const s = {
  wrap: { marginTop: 20 },
  divider: { display: 'flex', alignItems: 'center', gap: 10, marginBottom: 16 },
  dividerLine: { flex: 1, height: 1, background: '#E2E8F0' },
  dividerText: { fontSize: 11, color: '#94A3B8', whiteSpace: 'nowrap' },
  row: { display: 'flex', flexDirection: 'column', gap: 10, alignItems: 'stretch' },
  googleWrap: { display: 'flex', justifyContent: 'center' },
  // Icon pinned in a fixed-width left slot, label centered in the
  // remaining space — matches how Google's own rendered button (theme
  //="outline", size="large") lays itself out, so the two logos land at
  // the same spot regardless of each label's text length, instead of each
  // icon+text pair being centered as one group (which shifts the icon
  // sideways whenever the label is a different length).
  msBtn: {
    display: 'flex', alignItems: 'center',
    width: '100%', height: 40, padding: '0 12px',
    background: '#fff', border: '1px solid #dadce0', borderRadius: 8,
    fontSize: 14, fontWeight: 500, color: '#3c4043',
    cursor: 'pointer', boxSizing: 'border-box',
  },
  msIconSlot: { display: 'flex', alignItems: 'center', justifyContent: 'center', width: 20, flexShrink: 0 },
  msLabel: { flex: 1, textAlign: 'center', paddingRight: 20 },
};
