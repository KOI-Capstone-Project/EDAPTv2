import React from 'react';
import { Routes, Route, NavLink } from 'react-router-dom';
import Dashboard from './pages/Dashboard';
import Predictions from './pages/Predictions';
import Signup from './Signup'; // 1. Import the new Signup component
import './App.css';

function App() {
  return (
    <div className="app">
      <header className="app-header">
        <h1>EDAPT v2 <span>King's Own Institute</span></h1>
        <nav>
          <NavLink to="/" end>Mode 1 — Descriptive</NavLink>
          <NavLink to="/predictions">Mode 2 — Predictive</NavLink>
          {/* 2. Add a navigation link to reach the signup page */}
          <NavLink to="/signup" className="nav-signup">Sign Up</NavLink> 
        </nav>
      </header>

      <main className="app-main">
        <Routes>
          <Route path="/" element={<Dashboard />} />
          <Route path="/predictions" element={<Predictions />} />
          {/* 3. Register the new route so React knows what to render */}
          <Route path="/signup" element={<Signup />} />
        </Routes>
      </main>
    </div>
  );
}

export default App;