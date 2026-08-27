// Two-step forgot-password flow: email entry → 6-digit OTP + new password.
import { useState, useEffect, useRef } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import api from '../services/api';
import { getErrorMessage } from '../utils/apiError';

export default function ForgotPassword() {
  const navigate = useNavigate();

  // step 1 = email entry, step 2 = OTP + new password
  const [step,        setStep]        = useState(1);
  const [email,       setEmail]       = useState('');
  const [digits,      setDigits]      = useState(['', '', '', '', '', '']);
  const [focusedBox,  setFocusedBox]  = useState(-1);
  const [newPassword, setNewPassword] = useState('');
  const [confirmPw,   setConfirmPw]   = useState('');
  const [loading,     setLoading]     = useState(false);
  const [error,       setError]       = useState(null);
  const [success,     setSuccess]     = useState(null);

  const digitRefs = useRef([null, null, null, null, null, null]);

  // countdown timer (seconds remaining)
  const [timeLeft,    setTimeLeft]    = useState(600);
  const [expired,     setExpired]     = useState(false);
  const timerRef = useRef(null);

  const startTimer = () => {
    setTimeLeft(600);
    setExpired(false);
    clearInterval(timerRef.current);
    timerRef.current = setInterval(() => {
      setTimeLeft(prev => {
        if (prev <= 1) {
          clearInterval(timerRef.current);
          setExpired(true);
          return 0;
        }
        return prev - 1;
      });
    }, 1000);
  };

  useEffect(() => () => clearInterval(timerRef.current), []);

  const formatTime = (s) => {
    const m = Math.floor(s / 60);
    const sec = s % 60;
    return `${m}:${sec.toString().padStart(2, '0')}`;
  };

  const handleDigitChange = (i, val) => {
    const digit = val.replace(/\D/g, '').slice(-1);
    const next = [...digits];
    next[i] = digit;
    setDigits(next);
    setError(null);
    if (digit && i < 5) digitRefs.current[i + 1]?.focus();
  };

  const handleDigitKeyDown = (i, e) => {
    if (e.key === 'Backspace' && !digits[i] && i > 0) {
      digitRefs.current[i - 1]?.focus();
    }
  };

  const handlePaste = (startIndex, e) => {
    const text = e.clipboardData.getData('text').replace(/\D/g, '');
    if (!text) return;
    e.preventDefault();
    const next = [...digits];
    for (let i = 0; i < text.length && startIndex + i < 6; i++) {
      next[startIndex + i] = text[i];
    }
    setDigits(next);
    const nextFocus = Math.min(startIndex + text.length, 5);
    digitRefs.current[nextFocus]?.focus();
  };

  const handleSendCode = async (e) => {
    e.preventDefault();
    setLoading(true);
    setError(null);
    try {
      const res = await api.post('/api/auth/forgot-password', { email });
      // dev_otp is returned when email service is not configured
      if (res.data.dev_otp) {
        setSuccess(`Demo mode: your code is ${res.data.dev_otp}`);
      }
      setStep(2);
      startTimer();
    } catch (err) {
      setError(getErrorMessage(err, 'Failed to send reset code. Please try again.'));
    } finally {
      setLoading(false);
    }
  };

  const handleResend = async () => {
    setError(null);
    setSuccess(null);
    setLoading(true);
    try {
      const res = await api.post('/api/auth/forgot-password', { email });
      if (res.data.dev_otp) {
        setSuccess(`Demo mode: your new code is ${res.data.dev_otp}`);
      } else {
        setSuccess('A new reset code has been sent to your email.');
      }
      startTimer();
    } catch (err) {
      setError(getErrorMessage(err, 'Failed to resend code. Please try again.'));
    } finally {
      setLoading(false);
    }
  };

  const handleReset = async (e) => {
    e.preventDefault();
    if (newPassword !== confirmPw) {
      setError('Passwords do not match.');
      return;
    }
    setLoading(true);
    setError(null);
    try {
      await api.post('/api/auth/reset-password', { email, otp: digits.join(''), new_password: newPassword });
      navigate('/login', { state: { message: 'Password reset successfully. Please sign in.' } });
    } catch (err) {
      setError(getErrorMessage(err, 'Reset failed. Please check your code and try again.'));
    } finally {
      setLoading(false);
    }
  };

  return (
    <div style={s.root}>
      <div style={s.card}>
        <div style={s.logoRow}>
          <div style={s.logoIcon}>E</div>
          <span style={s.logoText}>EDAPT v2</span>
        </div>

        <h1 style={s.title}>Reset Password</h1>
        <p style={s.sub}>
          {step === 1
            ? 'Enter your staff email to receive a 6-digit reset code.'
            : `Enter the code sent to ${email}.`}
        </p>

        {success && <div style={s.successBanner}>{success}</div>}
        {error   && <div style={s.errorBanner} role="alert"><span>⚠</span> {error}</div>}

        {step === 1 ? (
          <form onSubmit={handleSendCode} style={s.form}>
            <div style={s.field}>
              <label style={s.label}>Staff Email</label>
              <input
                type="email"
                style={s.input}
                value={email}
                onChange={e => { setEmail(e.target.value); setError(null); }}
                placeholder="you@koi.edu.au"
                autoComplete="email"
                required
              />
            </div>
            <button
              type="submit"
              style={{ ...s.btn, opacity: loading ? 0.75 : 1 }}
              disabled={loading}
            >
              {loading ? 'Sending…' : 'Send Code'}
            </button>
          </form>
        ) : (
          <form onSubmit={handleReset} style={s.form}>
            <div style={s.timerRow}>
              <span style={{ color: expired ? '#DC2626' : '#374151', fontSize: 13 }}>
                Code expires in:
              </span>
              <span style={{ ...s.timer, color: expired ? '#DC2626' : timeLeft <= 60 ? '#B45309' : '#1A2E40' }}>
                {formatTime(timeLeft)}
              </span>
            </div>

            <div style={s.field}>
              <label style={{ ...s.label, textAlign: 'center' }}>Reset Code</label>
              <div style={s.otpRow}>
                {digits.map((d, i) => (
                  <input
                    key={i}
                    ref={el => { digitRefs.current[i] = el; }}
                    type="text"
                    inputMode="numeric"
                    maxLength={1}
                    value={d}
                    style={{
                      ...s.otpBox,
                      borderColor: focusedBox === i ? '#2E6E8E' : '#E2E8F0',
                      boxShadow:   focusedBox === i ? '0 0 0 3px rgba(46,110,142,0.15)' : 'none',
                    }}
                    onChange={e => handleDigitChange(i, e.target.value)}
                    onKeyDown={e => handleDigitKeyDown(i, e)}
                    onPaste={e => handlePaste(i, e)}
                    onFocus={() => setFocusedBox(i)}
                    onBlur={() => setFocusedBox(-1)}
                    autoComplete="off"
                  />
                ))}
              </div>
            </div>

            <div style={s.field}>
              <label style={s.label}>New Password</label>
              <input
                type="password"
                style={s.input}
                value={newPassword}
                onChange={e => { setNewPassword(e.target.value); setError(null); }}
                placeholder="Min 10 chars, upper, lower, digit, special"
                autoComplete="new-password"
                required
              />
            </div>

            <div style={s.field}>
              <label style={s.label}>Confirm New Password</label>
              <input
                type="password"
                style={s.input}
                value={confirmPw}
                onChange={e => { setConfirmPw(e.target.value); setError(null); }}
                placeholder="Re-enter new password"
                autoComplete="new-password"
                required
              />
            </div>

            {expired && (
              <p style={s.expiredMsg}>Code expired. Request a new one.</p>
            )}

            <button
              type="submit"
              style={{ ...s.btn, opacity: (loading || expired || digits.join('').length < 6) ? 0.5 : 1 }}
              disabled={loading || expired || digits.join('').length < 6}
            >
              {loading ? 'Resetting…' : 'Reset Password'}
            </button>

            <button
              type="button"
              style={{ ...s.resendBtn, fontWeight: expired ? 700 : 500 }}
              onClick={handleResend}
              disabled={loading}
            >
              {loading ? 'Sending…' : 'Resend OTP'}
            </button>
          </form>
        )}

        <div style={s.backRow}>
          <Link to="/login" style={s.backLink}>← Back to Sign In</Link>
        </div>
      </div>
    </div>
  );
}

const s = {
  root: {
    minHeight: '100vh',
    background: '#F0F4F8',
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    fontFamily: "'Inter','Segoe UI',sans-serif",
    padding: 24,
  },
  card: {
    background: '#fff',
    borderRadius: 16,
    padding: '40px 40px 36px',
    width: '100%',
    maxWidth: 420,
    boxShadow: '0 4px 24px rgba(0,0,0,0.07)',
    border: '0.5px solid #DDE4EA',
  },
  logoRow: {
    display: 'flex',
    alignItems: 'center',
    gap: 10,
    marginBottom: 28,
    justifyContent: 'center',
  },
  logoIcon: {
    width: 36, height: 36, borderRadius: 9,
    background: 'linear-gradient(135deg, #2E6E8E, #4f8ef7)',
    display: 'flex', alignItems: 'center', justifyContent: 'center',
    fontWeight: 800, fontSize: 18, color: '#fff',
  },
  logoText: { fontSize: 16, fontWeight: 700, color: '#1A2E40', letterSpacing: 0.5 },
  title: {
    margin: '0 0 6px',
    fontSize: 22,
    fontWeight: 700,
    color: '#1A2E40',
    textAlign: 'center',
  },
  sub: {
    margin: '0 0 24px',
    fontSize: 13,
    color: '#64748B',
    textAlign: 'center',
    lineHeight: 1.6,
  },
  form: { display: 'flex', flexDirection: 'column', gap: 16 },
  field: { display: 'flex', flexDirection: 'column', gap: 6 },
  label: { fontSize: 13, fontWeight: 500, color: '#374151' },
  input: {
    width: '100%',
    padding: '11px 14px',
    border: '1.5px solid #E2E8F0',
    borderRadius: 8,
    fontSize: 14,
    color: '#1E293B',
    background: '#F8FAFC',
    outline: 'none',
    boxSizing: 'border-box',
  },
  otpRow: {
    display: 'flex',
    gap: 8,
    justifyContent: 'center',
  },
  otpBox: {
    width: 48,
    height: 56,
    textAlign: 'center',
    fontSize: 22,
    fontWeight: 700,
    border: '1.5px solid #E2E8F0',
    borderRadius: 8,
    background: '#F8FAFC',
    color: '#1E293B',
    outline: 'none',
    caretColor: '#2E6E8E',
    boxSizing: 'border-box',
    transition: 'border-color 0.15s, box-shadow 0.15s',
    cursor: 'text',
  },
  btn: {
    width: '100%',
    padding: '13px',
    background: '#2E6E8E',
    color: '#fff',
    border: 'none',
    borderRadius: 8,
    fontSize: 15,
    fontWeight: 600,
    cursor: 'pointer',
    marginTop: 4,
  },
  resendBtn: {
    width: '100%',
    padding: '11px',
    background: 'transparent',
    color: '#2E6E8E',
    border: '1.5px solid #2E6E8E',
    borderRadius: 8,
    fontSize: 14,
    cursor: 'pointer',
  },
  timerRow: {
    display: 'flex',
    justifyContent: 'space-between',
    alignItems: 'center',
    background: '#F8FAFC',
    border: '1px solid #E2E8F0',
    borderRadius: 8,
    padding: '10px 14px',
  },
  timer: {
    fontSize: 18,
    fontWeight: 700,
    fontVariantNumeric: 'tabular-nums',
  },
  expiredMsg: {
    margin: 0,
    fontSize: 13,
    color: '#DC2626',
    fontWeight: 500,
    textAlign: 'center',
  },
  successBanner: {
    background: '#F0FDF4',
    border: '1px solid #BBF7D0',
    color: '#166534',
    borderRadius: 8,
    padding: '10px 14px',
    fontSize: 13,
    marginBottom: 8,
  },
  errorBanner: {
    display: 'flex', alignItems: 'center', gap: 8,
    background: '#FEF2F2',
    border: '1px solid #FECACA',
    color: '#DC2626', borderRadius: 8,
    padding: '10px 14px', fontSize: 13, fontWeight: 500,
    marginBottom: 8,
  },
  backRow: { textAlign: 'center', marginTop: 24 },
  backLink: { fontSize: 13, color: '#2E6E8E', textDecoration: 'none' },
};
