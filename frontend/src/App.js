import React from 'react';
import { Routes, Route, NavLink, Navigate } from 'react-router-dom';
import Dashboard from './pages/Dashboard';
import Predictions from './pages/Predictions';
import Signup from './Signup';
import Login from './Login';
import './App.css';

// ── Simple auth guard — redirects to /login if no token found ─────────────
function PrivateRoute({ children }) {
  const token = localStorage.getItem('access_token');
  return token ? children : <Navigate to="/login" replace />;
}

function App() {
  const token = localStorage.getItem('access_token');

  const handleLogout = () => {
    localStorage.removeItem('access_token');
    window.location.href = '/login';
  };

  return (
    <div className="app">
      {/* Only show the nav when the user is logged in */}
      {token && (
        <header className="app-header">
          <h1>EDAPT v2 <span>King's Own Institute</span></h1>
          <nav>
            <NavLink to="/" end>Mode 1 — Descriptive</NavLink>
            <NavLink to="/predictions">Mode 2 — Predictive</NavLink>
            <button
              onClick={handleLogout}
              className="nav-logout-btn"
              title="Sign out"
            >
              Sign Out
            </button>
          </nav>
        </header>
      )}

      <main className="app-main">
        <Routes>
          {/* Public routes */}
          <Route path="/login"  element={<Login />} />
          <Route path="/signup" element={<Signup />} />

          {/* Protected routes */}
          <Route path="/" element={
            <PrivateRoute><Dashboard /></PrivateRoute>
          } />
          <Route path="/predictions" element={
            <PrivateRoute><Predictions /></PrivateRoute>
          } />
        </Routes>
      </main>
    </div>
  );
}

export default App;
