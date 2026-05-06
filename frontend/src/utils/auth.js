export const getUser = () => {
  try { return JSON.parse(localStorage.getItem('edapt_user') || 'null'); }
  catch { return null; }
};

export const getToken = () => localStorage.getItem('edapt_token') || null;

export const getUserName = () => getUser()?.name || 'User';

export const getUserInitials = () => {
  const name = getUserName();
  return name.split(' ').map(n => n[0] || '').join('').toUpperCase().slice(0, 2);
};

export const isAdmin    = () => getUser()?.role === 'Head of Technology';
export const isLecturer = () => getUser()?.role === 'Lecturer';

export const logout = () => { localStorage.clear(); window.location.href = '/login'; };
