// Auth utilities: localStorage key constants and token/user accessors.

export const STORAGE_TOKEN_KEY = 'edapt_token';
export const STORAGE_USER_KEY  = 'edapt_user';

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

export const logout = () => { localStorage.clear(); window.location.href = '/login'; };
