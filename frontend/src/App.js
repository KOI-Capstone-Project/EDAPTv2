// EDAPT v2 Frontend — route configuration and auth guards.
// Protected routes require valid JWT token. Public routes: /login and /forgot-password only.

import { Routes, Route, Navigate } from 'react-router-dom';
import Layout from './components/Layout';
import ErrorBoundary from './components/ErrorBoundary';

// Pages
import Login              from './pages/Login';
import ForgotPassword     from './pages/ForgotPassword';
import LecturerDashboard  from './pages/LecturerDashboard';
import AdminDashboard     from './pages/AdminDashboard';
import DataIngestion      from './pages/DataIngestion';
import AuditLog           from './pages/AuditLog';
import LecturerExplorer   from './pages/LecturerExplorer';
import AdminExplorer      from './pages/AdminExplorer';
import SubjectAnalytics   from './pages/SubjectAnalytics';
import UserManagement     from './pages/UserManagement';
import LecturerPredictor  from './pages/LecturerPredictor';
import LecturerSettings   from './pages/LecturerSettings';
import AdminSettings      from './pages/AdminSettings';
import AdminPredictor     from './pages/AdminPredictor';

// Auth utilities
import { getToken, getUser } from './utils/auth';

// ── Route guards ──────────────────────────────────────────────────────────────

function getUser() {
  try { return JSON.parse(localStorage.getItem('edapt_user') || '{}'); }
  catch { return {}; }
}

function PrivateRoute({ children }) {
  if (!getToken()) return <Navigate to="/login" replace />;
  return children;
}

function AdminRoute({ children }) {
  const token = localStorage.getItem('edapt_token');
  if (!token) return <Navigate to="/login" replace />;
  try {
    const user = JSON.parse(localStorage.getItem('edapt_user') || 'null');
    if (!user) return <Navigate to="/login" replace />;
    if (user.role !== 'Head of Technology' && user.role !== 'Head of School') {
      return <Navigate to="/dashboard/lecturer" replace />;
    }
    return children;
  } catch {
    return <Navigate to="/login" replace />;
  }
}

function HoTOnlyRoute({ children }) {
  const token = localStorage.getItem('edapt_token');
  if (!token) return <Navigate to="/login" replace />;
  try {
    const user = JSON.parse(localStorage.getItem('edapt_user') || 'null');
    if (!user) return <Navigate to="/login" replace />;
    if (user.role === 'Head of School') return <Navigate to="/dashboard/admin" replace />;
    if (user.role !== 'Head of Technology') return <Navigate to="/dashboard/lecturer" replace />;
    return children;
  } catch {
    return <Navigate to="/login" replace />;
  }
}

function AdminRoute({ children }) {
  const token = localStorage.getItem('edapt_token');
  if (!token) return <Navigate to="/login" replace />;
  const user = getUser();
  if (user.role !== 'administrator') return <Navigate to="/dashboard" replace />;
  return children;
}

function Protected({ children }) {
  return <PrivateRoute><Layout>{children}</Layout></PrivateRoute>;
}

function AdminProtected({ children }) {
  return <AdminRoute><Layout>{children}</Layout></AdminRoute>;
}

function HoTOnlyProtected({ children }) {
  return <HoTOnlyRoute><Layout>{children}</Layout></HoTOnlyRoute>;
}

function SettingsPage() {
  const user = getUser();
  return (user?.role === 'Head of Technology' || user?.role === 'Head of School')
    ? <AdminSettings />
    : <LecturerSettings />;
}

// ── App ───────────────────────────────────────────────────────────────────────

export default function App() {
  return (
    <Routes>
      {/* Public */}
      <Route path="/login"           element={<Login />} />
      <Route path="/forgot-password" element={<ForgotPassword />} />

      {/* Root → login */}
      <Route path="/" element={<Navigate to="/login" replace />} />

      {/* Lecturer pages */}
      <Route path="/dashboard/lecturer" element={<Protected><LecturerDashboard /></Protected>} />
      <Route path="/explorer"            element={<Protected><LecturerExplorer /></Protected>} />
      <Route path="/predictor"           element={<Protected><LecturerPredictor /></Protected>} />

      {/* Admin dashboard */}
      <Route path="/dashboard/admin" element={
        <ErrorBoundary>
          <AdminProtected><AdminDashboard /></AdminProtected>
        </ErrorBoundary>
      } />

      {/* Admin-only pages */}
      <Route path="/data-ingestion"     element={<AdminProtected><DataIngestion /></AdminProtected>} />
      <Route path="/audit-log"          element={<HoTOnlyProtected><AuditLog /></HoTOnlyProtected>} />
      <Route path="/subject-analytics"  element={<AdminProtected><SubjectAnalytics /></AdminProtected>} />
      <Route path="/student-analytics"  element={<AdminProtected><AdminExplorer /></AdminProtected>} />
      <Route path="/predictive-reports" element={<AdminProtected><AdminPredictor /></AdminProtected>} />
      <Route path="/users"              element={<HoTOnlyProtected><UserManagement /></HoTOnlyProtected>} />

      {/* Shared settings (role-aware) */}
      <Route path="/settings" element={<Protected><SettingsPage /></Protected>} />

      {/* Fallback */}
      <Route path="*" element={<Navigate to="/login" replace />} />
    </Routes>
  );
}
