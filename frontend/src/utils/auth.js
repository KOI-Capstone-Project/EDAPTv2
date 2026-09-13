// Auth utilities: localStorage key constants and token/user accessors.

export const STORAGE_TOKEN_KEY = 'edapt_token';
export const STORAGE_USER_KEY  = 'edapt_user';
// sessionStorage (not localStorage) — deliberately scoped to one browser
// tab's session, not persisted indefinitely across visits like the token/
// user above. Cleared on logout (not just left to expire with the tab) so
// a different staff member signing in on the same tab afterward never
// sees a previous user's chat history — see AIChatbox.jsx.
export const CHAT_HISTORY_KEY = 'edapt_chat_history';

export const getUser = () => {
  try { return JSON.parse(localStorage.getItem(STORAGE_USER_KEY) || 'null'); }
  catch { return null; }
};

export const getToken = () => localStorage.getItem(STORAGE_TOKEN_KEY) || null;

export const getUserName = () => getUser()?.name || 'User';

export const getUserInitials = () => {
  const name = getUserName();
  return name.split(' ').map(n => n[0] || '').join('').toUpperCase().slice(0, 2);
};

export const isAdmin = () => ['Head of Technology', 'Head of School'].includes(getUser()?.role);

export const logout = () => {
  localStorage.clear();
  // Not sessionStorage.clear() — that would also wipe SESSION_EXPIRED_KEY
  // (api/client.js sets it immediately before calling this very function,
  // on a 401) and MSAL's own session-cached tokens (utils/msal.js), so
  // only the one key this app actually needs cleared on logout is removed.
  sessionStorage.removeItem(CHAT_HISTORY_KEY);
  window.location.href = '/login';
};
