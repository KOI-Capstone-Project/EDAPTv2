import React from 'react';
import { Routes, Route, Navigate } from 'react-router-dom';
import Layout from './components/Layout';
import Dashboard from './pages/Dashboard';
import Predictions from './pages/Predictions';
import DataIngestion from './pages/DataIngestion';
import AuditLog from './pages/AuditLog';
import Explorer from './pages/Explorer';
import Settings from './pages/Settings';
import Signup from './Signup';
import Login from './Login';

function PrivateRoute({ children }) {
  const token = localStorage.getItem('edapt_token');
  return token ? children : <Navigate to="/login" replace />;
}

function Protected({ children }) {
  return (
    <PrivateRoute>
      <Layout>{children}</Layout>
    </PrivateRoute>
  );
}

export default function App() {
  return (
    <Routes>
      <Route path="/login"  element={<Login />} />
      <Route path="/signup" element={<Signup />} />
      <Route path="/" element={<Navigate to="/dashboard" replace />} />

      <Route path="/dashboard"      element={<Protected><Dashboard /></Protected>} />
      <Route path="/predictions"    element={<Protected><Predictions /></Protected>} />
      <Route path="/data-ingestion" element={<Protected><DataIngestion /></Protected>} />
      <Route path="/audit-log"      element={<Protected><AuditLog /></Protected>} />
      <Route path="/explorer"       element={<Protected><Explorer /></Protected>} />
      <Route path="/settings"       element={<Protected><Settings /></Protected>} />
    </Routes>
  );
}
