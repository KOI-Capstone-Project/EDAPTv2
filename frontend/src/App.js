import React from 'react';
import { Routes, Route, NavLink } from 'react-router-dom';
import Dashboard from './pages/Dashboard';
import Predictions from './pages/Predictions';
import './App.css';

function App() {
  return (
    <div className="app">
      <header className="app-header">
        <h1>EDAPT v2 <span>King's Own Institute</span></h1>
        <nav>
          <NavLink to="/" end>Mode 1 — Descriptive</NavLink>
          <NavLink to="/predictions">Mode 2 — Predictive</NavLink>
        </nav>
      </header>

      <main className="app-main">
        <Routes>
          <Route path="/"            element={<Dashboard />} />
          <Route path="/predictions" element={<Predictions />} />
        </Routes>
      </main>
    </div>
  );
}

export default App;
