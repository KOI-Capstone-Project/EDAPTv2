// Lazily-initialized MSAL singleton for Microsoft sign-in. clientId/tenantId
// come from the backend's OAuth provider config (Settings > OAuth Providers,
// fetched at runtime via GET /api/oauth-providers/public) rather than a
// REACT_APP_MICROSOFT_CLIENT_ID build-time env var — the instance is built
// the first time a caller actually has that config in hand, not at module
// load.
import { PublicClientApplication } from '@azure/msal-browser';

let _instance = null;
let _initPromise = null;

// msal-browser v3 requires an explicit async initialize() before any other
// instance method is called — this memoizes both the instance and that
// initialize() call so callers can just await it every time.
export function getMsalInstance(clientId, tenantId) {
  if (!_instance) {
    _instance = new PublicClientApplication({
      auth: {
        clientId,
        authority:   `https://login.microsoftonline.com/${tenantId || 'common'}`,
        redirectUri: window.location.origin,
      },
      cache: { cacheLocation: 'sessionStorage' },
    });
  }
  if (!_initPromise) _initPromise = _instance.initialize();
  return _initPromise.then(() => _instance);
}
