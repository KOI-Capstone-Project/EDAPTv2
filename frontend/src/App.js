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
import ExplorerView       from './pages/ExplorerView';
import SubjectAnalytics   from './pages/SubjectAnalytics';
import ModelHealth       from './pages/ModelHealth';
import UserManagement     from './pages/UserManagement';
import ApiConsole         from './pages/ApiConsole';
import PredictorView      from './pages/PredictorView';
import StudentsAtRisk     from './pages/StudentsAtRisk';
import SettingsView       from './pages/SettingsView';
import RiskEmailTemplateView from './pages/RiskEmailTemplateView';

// Auth utilities
import { getToken, getUser } from './utils/auth';

// ── Route guards ──────────────────────────────────────────────────────────────

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
  const isLecturer = !(user?.role === 'Head of Technology' || user?.role === 'Head of School');
  return <SettingsView isLecturer={isLecturer} />;
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
      <Route path="/explorer"            element={<Protected><ExplorerView isLecturer={true} /></Protected>} />
      <Route path="/predictor"           element={<Protected><PredictorView isAdmin={false} /></Protected>} />
      {/* Visible to every authenticated role (lecturer, Head of School, Head
          of Technology) — the backend (GET /api/students-at-risk) already
          scopes rows to whatever subjects the requesting user can see, so
          one shared route/guard is enough; no admin-only content lives here. */}
      <Route path="/students-at-risk"    element={<Protected><StudentsAtRisk /></Protected>} />

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
      {/* Admin-only and read-only: exposes no promote/rollback control —
          those stay CLI-only behind the compare_and_promote gate. */}
      <Route path="/model-health"       element={<AdminProtected><ModelHealth /></AdminProtected>} />
      <Route path="/student-analytics"  element={<AdminProtected><ExplorerView isLecturer={false} /></AdminProtected>} />
      <Route path="/predictive-reports" element={<AdminProtected><PredictorView isAdmin={true} /></AdminProtected>} />
      <Route path="/users"              element={<HoTOnlyProtected><UserManagement /></HoTOnlyProtected>} />
      <Route path="/api-console"        element={<HoTOnlyProtected><ApiConsole /></HoTOnlyProtected>} />
      {/* Admin only (HoT or HoS) — matches the backend's require_head_of_school
          gate on GET/PUT /api/risk-email-template. */}
      <Route path="/risk-email-template" element={<AdminProtected><RiskEmailTemplateView /></AdminProtected>} />

      {/* Shared settings (role-aware) */}
      <Route path="/settings" element={<Protected><SettingsPage /></Protected>} />

      {/* Fallback */}
      <Route path="*" element={<Navigate to="/login" replace />} />
    </Routes>
  );
}
