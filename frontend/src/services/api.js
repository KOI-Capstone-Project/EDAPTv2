// Thin re-export of the central Axios client defined in src/api/client.js.
// Pages import from here (services/api) so import paths stay consistent across
// the app; the actual auth interceptor and 401-logout logic live in client.js.
export { default } from '../api/client';
