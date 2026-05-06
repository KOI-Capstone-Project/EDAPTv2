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
import Predictions        from './pages/Predictions';
import LecturerPredictor  from './pages/LecturerPredictor';
import LecturerSettings   from './pages/LecturerSettings';

// Auth utilities
import { getToken } from './utils/auth';

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

// ── App ───────────────────────────────────────────────────────────────────────

export default function App() {
  return (
    <Routes>
      {/* Public */}
      <Route path="/login"  element={<Login />} />

      {/* Root → login */}
      <Route path="/" element={<Navigate to="/login" replace />} />

      {/* Lecturer dashboard */}
      <Route path="/dashboard/lecturer" element={
        <Protected><LecturerDashboard /></Protected>
      } />

      {/* Admin dashboard */}
      <Route path="/dashboard/admin" element={
        <ErrorBoundary>
          <AdminProtected>
            <AdminDashboard />
          </AdminProtected>
        </ErrorBoundary>
      } />

      {/* Shared protected pages */}
      <Route path="/predictions" element={<Protected><Predictions /></Protected>} />
      <Route path="/predictor"   element={<Protected><LecturerPredictor /></Protected>} />
      <Route path="/settings"    element={<Protected><LecturerSettings /></Protected>} />

      {/* Lecturer explorer */}
      <Route path="/explorer" element={<Protected><LecturerExplorer /></Protected>} />

      {/* Admin-only pages */}
      <Route path="/data-ingestion"    element={<AdminProtected><DataIngestion /></AdminProtected>} />
      <Route path="/audit-log"         element={<AdminProtected><AuditLog /></AdminProtected>} />
      <Route path="/analytics/subjects" element={<AdminProtected><SubjectAnalytics /></AdminProtected>} />
      <Route path="/student-analytics" element={<AdminProtected><AdminExplorer /></AdminProtected>} />
      <Route path="/users"             element={<AdminProtected><UserManagement /></AdminProtected>} />

      {/* Fallback */}
      <Route path="*" element={<Navigate to="/login" replace />} />
    </Routes>
  );
}
