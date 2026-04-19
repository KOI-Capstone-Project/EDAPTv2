import React, { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import api from './services/api';
import './Signup.css';

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

const Signup = () => {
  const navigate = useNavigate();
  const [formData, setFormData]               = useState({ name: '', email: '', password: '', confirmPassword: '' });
  const [loading, setLoading]                 = useState(false);
  const [error, setError]                     = useState(null);
  const [showPassword, setShowPassword]       = useState(false);
  const [showConfirm, setShowConfirm]         = useState(false);

  const handleChange = (e) => {
    setFormData({ ...formData, [e.target.name]: e.target.value });
    setError(null);
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (formData.password !== formData.confirmPassword) {
      setError('Passwords do not match.');
      return;
    }

    setLoading(true);
    setError(null);

    try {
      await api.post('/api/v1/auth/register', {
        name:     formData.name,
        email:    formData.email,
        password: formData.password,
      });
      navigate('/login', { state: { registered: true } });
    } catch (err) {
      const detail = err.response?.data?.detail;
      setError(detail || 'Registration failed. Please try again.');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="signup-container">
      <div className="signup-card">

        <div className="login-brand">
          <div className="login-brand-icon">E</div>
          <span>EDAPT v2</span>
        </div>

        <div className="signup-header">
          <h2>Create account</h2>
          <p>Join your KOI EDAPT workspace.</p>
        </div>

        <form onSubmit={handleSubmit} className="signup-form">
          <div className="input-group">
            <label htmlFor="name">Full Name</label>
            <input
              type="text"
              id="name"
              name="name"
              placeholder="Sangam Gurung"
              value={formData.name}
              onChange={handleChange}
              autoComplete="name"
              required
            />
          </div>

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
            <label htmlFor="password">Password</label>
            <div className="password-wrapper">
              <input
                type={showPassword ? 'text' : 'password'}
                id="password"
                name="password"
                placeholder="••••••••"
                value={formData.password}
                onChange={handleChange}
                autoComplete="new-password"
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

          <div className="input-group">
            <label htmlFor="confirmPassword">Confirm Password</label>
            <div className="password-wrapper">
              <input
                type={showConfirm ? 'text' : 'password'}
                id="confirmPassword"
                name="confirmPassword"
                placeholder="••••••••"
                value={formData.confirmPassword}
                onChange={handleChange}
                autoComplete="new-password"
                required
              />
              <button
                type="button"
                className="eye-toggle"
                onClick={() => setShowConfirm(v => !v)}
                aria-label={showConfirm ? 'Hide password' : 'Show password'}
              >
                <EyeIcon visible={showConfirm} />
              </button>
            </div>
          </div>

          {error && (
            <div className="signup-error" role="alert">
              <span className="error-icon">⚠</span> {error}
            </div>
          )}

          <button
            type="submit"
            className={`signup-button ${loading ? 'signup-button--loading' : ''}`}
            disabled={loading}
          >
            {loading ? <span className="spinner" /> : 'Create Account'}
          </button>
        </form>

        <p className="signup-footer">
          Already have an account? <a href="/login">Sign in</a>
        </p>
      </div>
    </div>
  );
};

export default Signup;
