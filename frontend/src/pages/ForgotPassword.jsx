import React, { useState } from 'react';
import { Link, Navigate, useLocation, useNavigate } from 'react-router-dom';
import { api } from '../api/client';
import { useAuth } from '../App';
import AuthenticatorChallenge from '../components/AuthenticatorChallenge';
import PasswordStrength, { passwordPolicyError } from '../components/PasswordStrength';
export default function ForgotPassword() {
  const location = useLocation();
  const navigate = useNavigate();
  const { loginUser } = useAuth();
  const email = location.state?.email || '';
  const [code, setCode] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const [challenge, setChallenge] = useState(null);
  if (!email) return <Navigate to="/login" replace />;
  if (challenge) return <AuthenticatorChallenge challenge={challenge} onComplete={data => { loginUser(data); navigate('/scan'); }} onCancel={() => navigate('/login')} />;
  return <div className="card" style={{ maxWidth: 440, margin: '40px auto' }}>
    <h2 className="oswald">Recover account</h2>
    <p>Use one of your saved recovery codes to set a password and enroll Authenticator again. All previous sessions and recovery codes will be revoked.</p>
    <p>If you lost every recovery code, contact an administrator for identity verification. No recovery email will be sent.</p>
    <form onSubmit={async event => {
      event.preventDefault(); setError('');
      const validation = passwordPolicyError(password);
      if (validation) { setError(validation); return; }
      setBusy(true);
      try { setChallenge(await api.recoverAccount(email, code, password)); }
      catch (err) { setError(err.message); }
      finally { setBusy(false); }
    }}>
      <label>Email</label><input className="input" value={email} readOnly />
      <label>Unused recovery code</label><input className="input" required autoComplete="off" value={code} onChange={e => setCode(e.target.value)} />
      <label>New password</label><input className="input" type="password" required autoComplete="new-password" value={password} onChange={e => setPassword(e.target.value)} />
      <PasswordStrength password={password} />
      {error && <p role="alert" style={{ color: '#ff8a99' }}>{error}</p>}
      <button className="btn btn-primary" disabled={busy}>Recover and set up Authenticator</button>
    </form>
    <Link to="/login">Back to sign in</Link>
  </div>;
}
