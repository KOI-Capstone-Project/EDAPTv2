// Lazily-initialized MSAL singleton for Microsoft sign-in. Only constructed
// when REACT_APP_MICROSOFT_CLIENT_ID is configured — pages that import this
// must not assume Microsoft sign-in is available (see MICROSOFT_ENABLED).
import { PublicClientApplication } from '@azure/msal-browser';

export const MICROSOFT_CLIENT_ID = process.env.REACT_APP_MICROSOFT_CLIENT_ID || '';
export const MICROSOFT_TENANT_ID = process.env.REACT_APP_MICROSOFT_TENANT_ID || 'common';
export const MICROSOFT_ENABLED   = Boolean(MICROSOFT_CLIENT_ID);

export const msalInstance = MICROSOFT_ENABLED
  ? new PublicClientApplication({
      auth: {
        clientId:    MICROSOFT_CLIENT_ID,
        authority:   `https://login.microsoftonline.com/${MICROSOFT_TENANT_ID}`,
        redirectUri: window.location.origin,
      },
      cache: { cacheLocation: 'sessionStorage' },
    })
  : null;

// msal-browser v3 requires an explicit async initialize() before any other
// instance method is called — this memoizes that so callers can just await
// it every time without re-initializing.
let initPromise = null;
export function ensureMsalInitialized() {
  if (!msalInstance) return Promise.resolve();
  if (!initPromise) initPromise = msalInstance.initialize();
  return initPromise;
}
