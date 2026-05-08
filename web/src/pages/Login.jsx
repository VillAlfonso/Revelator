import React, { useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import {
  signInWithEmailAndPassword, signInWithPopup,
} from 'firebase/auth';

import { auth, googleProvider } from '../firebase';
import { useAuth } from '../auth/AuthContext';

export default function Login() {
  const { user } = useAuth();
  const navigate = useNavigate();
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);

  if (user) { navigate('/scan', { replace: true }); return null; }

  async function handleEmailLogin(e) {
    e.preventDefault();
    setError(''); setLoading(true);
    try {
      await signInWithEmailAndPassword(auth, email.trim(), password);
      navigate('/scan');
    } catch (err) {
      setError(prettyAuthError(err.code));
    } finally {
      setLoading(false);
    }
  }

  async function handleGoogleLogin() {
    setError(''); setLoading(true);
    try {
      await signInWithPopup(auth, googleProvider);
      navigate('/scan');
    } catch (err) {
      setError(prettyAuthError(err.code));
    } finally {
      setLoading(false);
    }
  }

  return (
    <div style={{ maxWidth: 420, margin: '40px auto' }}>
      <div className="card">
        <h2 className="oswald glow" style={{ color: '#00ff66', letterSpacing: 4, fontSize: 24, marginBottom: 24 }}>
          ◆ ACCESS TERMINAL
        </h2>

        <form onSubmit={handleEmailLogin} style={{ display: 'grid', gap: 14 }}>
          <Field label="EMAIL" type="email" value={email} onChange={setEmail} required />
          <Field label="PASSWORD" type="password" value={password} onChange={setPassword} required />
          <button type="submit" className="btn btn-primary" disabled={loading} style={{ padding: '14px 0', marginTop: 8 }}>
            {loading ? '◌ AUTHENTICATING…' : '▶ SIGN IN'}
          </button>
        </form>

        <div style={{ display: 'flex', alignItems: 'center', gap: 10, margin: '20px 0', color: '#3f6e4a' }}>
          <div style={{ flex: 1, borderTop: '1px solid #112418' }} />
          <span className="mono" style={{ fontSize: 10, letterSpacing: 2 }}>OR</span>
          <div style={{ flex: 1, borderTop: '1px solid #112418' }} />
        </div>

        <button type="button" onClick={handleGoogleLogin} disabled={loading}
          className="btn btn-secondary" style={{ width: '100%', padding: '12px 0' }}>
          ⌘ Continue with Google
        </button>

        {error && (
          <div style={{
            background: 'rgba(255,51,68,0.1)', border: '1px solid #ff3344', padding: 12,
            borderRadius: 2, marginTop: 16, fontSize: 12, color: '#ff8a99',
            fontFamily: "'JetBrains Mono', monospace",
          }}>⚠ {error}</div>
        )}

        <p style={{ marginTop: 24, fontSize: 12, color: '#6dba85', textAlign: 'center' }}>
          New here?{' '}
          <Link to="/register" style={{ color: '#00ff66', textShadow: '0 0 8px rgba(0,255,102,0.5)' }}>
            Create an account
          </Link>
        </p>
      </div>
    </div>
  );
}

function Field({ label, value, onChange, ...rest }) {
  return (
    <div>
      <label className="mono" style={{ fontSize: 10, letterSpacing: 2, color: '#6dba85', display: 'block', marginBottom: 6 }}>
        {label}
      </label>
      <input
        value={value}
        onChange={(e) => onChange(e.target.value)}
        style={{
          width: '100%', padding: '12px 14px', background: '#0a1605',
          border: '1px solid #1d3825', borderRadius: 3,
          color: '#d8ffe6', fontSize: 13, fontFamily: "'JetBrains Mono', monospace",
        }}
        {...rest}
      />
    </div>
  );
}

function prettyAuthError(code) {
  const map = {
    'auth/invalid-email': 'Invalid email address.',
    'auth/user-not-found': 'No account with that email.',
    'auth/wrong-password': 'Incorrect password.',
    'auth/invalid-credential': 'Email or password is incorrect.',
    'auth/too-many-requests': 'Too many attempts. Try again later.',
    'auth/popup-closed-by-user': 'Sign-in cancelled.',
    'auth/network-request-failed': 'Network error.',
  };
  return map[code] || 'Sign-in failed.';
}
