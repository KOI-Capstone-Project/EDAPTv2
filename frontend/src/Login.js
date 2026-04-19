import React, { useState, useEffect } from 'react';
import { useNavigate, useLocation } from 'react-router-dom';
import api from './services/api';
import './Login.css';

const EyeIcon = ({ visible }) => visible ? (
  <svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none"
    stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"/>
    <circle cx="12" cy="12" r="3"/>
  </svg>
) : (
  <svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none"
    stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <path d="M17.94 17.94A10.07 10.07 0 0 1 12 20c-7 0-11-8-11-8a18.45 18.45 0 0 1 5.06-5.94"/>
    <path d="M9.9 4.24A9.12 9.12 0 0 1 12 4c7 0 11 8 11 8a18.5 18.5 0 0 1-2.16 3.19"/>
    <line x1="1" y1="1" x2="23" y2="23"/>
  </svg>
);

const Login = () => {
  const navigate  = useNavigate();
  const location  = useLocation();
  const [formData, setFormData]       = useState({ email: '', password: '' });
  const [loading, setLoading]         = useState(false);
  const [error, setError]             = useState(null);
  const [showPassword, setShowPassword] = useState(false);
  const registered = location.state?.registered;

  useEffect(() => {
    if (registered) {
      window.history.replaceState({}, document.title);
    }
  }, [registered]);

  const handleChange = (e) => {
    setFormData({ ...formData, [e.target.name]: e.target.value });
    setError(null); // clear error on keystroke
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    setLoading(true);
    setError(null);

    try {
      // OAuth2 password flow — FastAPI expects form-encoded body
      const params = new URLSearchParams();
      params.append('username', formData.email);   // FastAPI OAuth2 uses "username"
      params.append('password', formData.password);

      const res = await api.post('/api/v1/auth/login', params, {
        headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
      });

      // Persist token so subsequent API calls are authenticated
      localStorage.setItem('access_token', res.data.access_token);

      // Redirect to main dashboard
      navigate('/');
    } catch (err) {
      const detail = err.response?.data?.detail;
      setError(detail || 'Login failed. Please check your credentials.');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="login-container">
      <div className="login-card">

        {/* Logo / brand mark */}
        <div className="login-brand">
          <div className="login-brand-icon">E</div>
          <span>EDAPT v2</span>
        </div>

        <div className="login-header">
          <h2>Welcome back</h2>
          <p>Sign in to your KOI account</p>
        </div>

        {registered && (
          <div className="login-success" role="status">
            Account created! You can now sign in.
          </div>
        )}

        <form onSubmit={handleSubmit} className="login-form">
          <div className="input-group">
            <label htmlFor="email">Email Address</label>
            <input
              type="email"
              id="email"
              name="email"
              placeholder="you@edapt.local"
              value={formData.email}
              onChange={handleChange}
              autoComplete="email"
              required
            />
          </div>

          <div className="input-group">
            <div className="password-label-row">
              <label htmlFor="password">Password</label>
              <a href="/forgot-password" className="forgot-link">Forgot password?</a>
            </div>
            <div className="password-wrapper">
              <input
                type={showPassword ? 'text' : 'password'}
                id="password"
                name="password"
                placeholder="••••••••"
                value={formData.password}
                onChange={handleChange}
                autoComplete="current-password"
                required
              />
              <button
                type="button"
                className="eye-toggle"
                onClick={() => setShowPassword(v => !v)}
                aria-label={showPassword ? 'Hide password' : 'Show password'}
              >
                <EyeIcon visible={showPassword} />
              </button>
            </div>
          </div>

          {error && (
            <div className="login-error" role="alert">
              <span className="error-icon">⚠</span> {error}
            </div>
          )}

          <button
            type="submit"
            className={`login-button ${loading ? 'login-button--loading' : ''}`}
            disabled={loading}
          >
            {loading ? <span className="spinner" /> : 'Sign In'}
          </button>
        </form>

        <p className="login-footer">
          Don't have an account? <a href="/signup">Sign up</a>
        </p>
      </div>
    </div>
  );
};

export default Login;
