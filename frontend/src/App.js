import { Routes, Route, Navigate } from 'react-router-dom';
import Layout from './components/Layout';
import ErrorBoundary from './components/ErrorBoundary';

// Pages
import Login              from './pages/Login';
import LecturerDashboard  from './pages/LecturerDashboard';
import AdminDashboard     from './pages/AdminDashboard';
import DataIngestion      from './pages/DataIngestion';
import AuditLog           from './pages/AuditLog';
import LecturerExplorer   from './pages/LecturerExplorer';
import AdminExplorer      from './pages/AdminExplorer';
import SubjectAnalytics   from './pages/SubjectAnalytics';
import UserManagement     from './pages/UserManagement';
import LecturerPredictor  from './pages/LecturerPredictor';
import LecturerAIInsights from './pages/LecturerAIInsights';
import LecturerSettings   from './pages/LecturerSettings';
import AdminSettings      from './pages/AdminSettings';
import AdminPredictor     from './pages/AdminPredictor';

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
    if (user.role !== 'Head of Technology') {
      return <Navigate to="/dashboard/lecturer" replace />;
    }
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

function SettingsPage() {
  const user = getUser();
  return user?.role === 'Head of Technology' ? <AdminSettings /> : <LecturerSettings />;
}

// ── App ───────────────────────────────────────────────────────────────────────

export default function App() {
  return (
    <Routes>
      {/* Public */}
      <Route path="/login" element={<Login />} />

      {/* Root → login */}
      <Route path="/" element={<Navigate to="/login" replace />} />

      {/* Lecturer pages */}
      <Route path="/dashboard/lecturer" element={<Protected><LecturerDashboard /></Protected>} />
      <Route path="/explorer"            element={<Protected><LecturerExplorer /></Protected>} />
      <Route path="/predictor"           element={<Protected><LecturerPredictor /></Protected>} />
      <Route path="/ai-insights"         element={<Protected><LecturerAIInsights /></Protected>} />

      {/* Admin dashboard */}
      <Route path="/dashboard/admin" element={
        <ErrorBoundary>
          <AdminProtected><AdminDashboard /></AdminProtected>
        </ErrorBoundary>
      } />

      {/* Admin-only pages */}
      <Route path="/data-ingestion"     element={<AdminProtected><DataIngestion /></AdminProtected>} />
      <Route path="/audit-log"          element={<AdminProtected><AuditLog /></AdminProtected>} />
      <Route path="/subject-analytics"  element={<AdminProtected><SubjectAnalytics /></AdminProtected>} />
      <Route path="/student-analytics"  element={<AdminProtected><AdminExplorer /></AdminProtected>} />
      <Route path="/predictive-reports" element={<AdminProtected><AdminPredictor /></AdminProtected>} />
      <Route path="/users"              element={<AdminProtected><UserManagement /></AdminProtected>} />

      {/* Shared settings (role-aware) */}
      <Route path="/settings" element={<Protected><SettingsPage /></Protected>} />

      {/* Fallback */}
      <Route path="*" element={<Navigate to="/login" replace />} />
    </Routes>
  );
}
