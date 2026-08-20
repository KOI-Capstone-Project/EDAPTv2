// Google and Microsoft sign-in buttons for the login page. Each provider
// only renders once its client ID is configured — an unset client ID hides
// that button rather than showing one that can only ever fail.
import { useState } from 'react';
import { GoogleLogin, GoogleOAuthProvider } from '@react-oauth/google';
import api from '../services/api';
import { msalInstance, ensureMsalInitialized, MICROSOFT_ENABLED } from '../utils/msal';

const GOOGLE_CLIENT_ID = process.env.REACT_APP_GOOGLE_CLIENT_ID || '';
const GOOGLE_ENABLED   = Boolean(GOOGLE_CLIENT_ID);

const MicrosoftIcon = () => (
  <svg width="16" height="16" viewBox="0 0 21 21" aria-hidden="true">
    <rect x="1"  y="1"  width="9" height="9" fill="#F25022" />
    <rect x="11" y="1"  width="9" height="9" fill="#7FBA00" />
    <rect x="1"  y="11" width="9" height="9" fill="#00A4EF" />
    <rect x="11" y="11" width="9" height="9" fill="#FFB900" />
  </svg>
);

export default function OAuthButtons({ onSuccess, onError, disabled }) {
  const [msLoading, setMsLoading] = useState(false);

  if (!GOOGLE_ENABLED && !MICROSOFT_ENABLED) return null;

  const exchangeToken = async (path, idToken) => {
    const res = await api.post(path, { id_token: idToken });
    onSuccess(res.data);
  };

  const handleGoogleSuccess = async (credentialResponse) => {
    try {
      await exchangeToken('/api/auth/google', credentialResponse.credential);
    } catch (err) {
      onError(err.response?.data?.detail || 'Google sign-in failed. Please try again.');
    }
  };

  const handleMicrosoft = async () => {
    setMsLoading(true);
    try {
      await ensureMsalInitialized();
      const result = await msalInstance.loginPopup({ scopes: ['openid', 'profile', 'email'] });
      await exchangeToken('/api/auth/microsoft', result.idToken);
    } catch (err) {
      if (err?.errorCode !== 'user_cancelled') {
        onError(err.response?.data?.detail || 'Microsoft sign-in failed. Please try again.');
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
        {GOOGLE_ENABLED && (
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
        {MICROSOFT_ENABLED && (
          <button
            type="button"
            style={s.msBtn}
            onClick={handleMicrosoft}
            disabled={disabled || msLoading}
          >
            <MicrosoftIcon />
            {msLoading ? 'Signing in…' : 'Sign in with Microsoft'}
          </button>
        )}
      </div>
    </div>
  );

  return GOOGLE_ENABLED
    ? <GoogleOAuthProvider clientId={GOOGLE_CLIENT_ID}>{body}</GoogleOAuthProvider>
    : body;
}

const s = {
  wrap: { marginTop: 20 },
  divider: { display: 'flex', alignItems: 'center', gap: 10, marginBottom: 16 },
  dividerLine: { flex: 1, height: 1, background: '#E2E8F0' },
  dividerText: { fontSize: 11, color: '#94A3B8', whiteSpace: 'nowrap' },
  row: { display: 'flex', flexDirection: 'column', gap: 10, alignItems: 'stretch' },
  googleWrap: { display: 'flex', justifyContent: 'center' },
  msBtn: {
    display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 10,
    width: '100%', padding: '10px 14px',
    background: '#fff', border: '1.5px solid #E2E8F0', borderRadius: 8,
    fontSize: 14, fontWeight: 500, color: '#1E293B',
    cursor: 'pointer', boxSizing: 'border-box',
  },
};
