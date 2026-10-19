import React, { useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { GoogleLogin } from '@react-oauth/google';
import { Capacitor } from '@capacitor/core';
import { GoogleAuth } from '@codetrix-studio/capacitor-google-auth';
import { useAuth } from '../App';
import { api } from '../api/client';
import Logo from '../components/Logo';
import AuthenticatorChallenge from '../components/AuthenticatorChallenge';

export default function Login({ registration = false }) {
  const { loginUser } = useAuth();
  const navigate = useNavigate();
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const [agreed, setAgreed] = useState(false);
  const [challenge, setChallenge] = useState(null);
  function complete(data) { loginUser(data); navigate('/scan'); }
  async function authenticate(action) {
    if (!agreed) { setError('Please agree to the Terms of Service first.'); return; }
    setBusy(true); setError('');
    try { setChallenge(await action()); }
    catch (err) { setError(err.message); }
    finally { setBusy(false); }
  }
  if (challenge) return <AuthenticatorChallenge key={challenge.challenge_token} challenge={challenge} onComplete={complete} onCancel={() => setChallenge(null)} />;
  return <div style={{ maxWidth: 440, margin: '40px auto' }}>
    <div style={{ textAlign: 'center', marginBottom: 24 }}><Logo size={86} glow animated /><h1 className="oswald glow">REVELATOR</h1></div>
    <div className="card">
      <h2 className="oswald">{registration ? 'Create an account' : 'Sign in'}</h2>
      {registration && <p>New accounts require your institutional @lspu.edu.ph Google account. Google Authenticator setup follows sign-in.</p>}
      {!registration && <p>Existing accounts can continue using their email and password or Google sign-in.</p>}
      <label style={{ display: 'block', marginBottom: 16 }}><input type="checkbox" checked={agreed} onChange={e => setAgreed(e.target.checked)} /> I agree to the <Link to="/terms">Terms of Service</Link> and <Link to="/privacy">Privacy Policy</Link>.</label>
      {error && <p role="alert" style={{ color: '#ff8a99' }}>{error}</p>}
      {!registration && <form onSubmit={event => { event.preventDefault(); authenticate(() => api.login(email, password)); }}>
        <label htmlFor="login-email">Email</label><input id="login-email" className="input" type="email" autoComplete="username" required value={email} onChange={e => setEmail(e.target.value)} />
        <label htmlFor="login-password">Password</label><input id="login-password" className="input" type="password" autoComplete="current-password" required value={password} onChange={e => setPassword(e.target.value)} />
        <button className="btn btn-primary" disabled={busy || !agreed} style={{ width: '100%', marginTop: 16 }}>{busy ? 'Signing in…' : 'Sign in'}</button>
        <p>{email.trim() ? <Link to="/forgot-password" state={{ email: email.trim() }}>Recover account</Link> : <button type="button" disabled>Recover account</button>}</p>
      </form>}
      <div style={{ opacity: agreed && !busy ? 1 : 0.5, pointerEvents: agreed && !busy ? 'auto' : 'none', marginTop: 16 }}>
        {Capacitor.isNativePlatform() ? <button className="btn btn-secondary" onClick={() => authenticate(async () => {
          const result = await GoogleAuth.signIn(); return api.googleLogin(result.authentication.idToken);
        })}>Continue with Google</button> : <GoogleLogin onSuccess={response => authenticate(() => api.googleLogin(response.credential))} onError={() => setError('Google sign-in failed')} theme="filled_black" />}
      </div>
      <p style={{ marginTop: 20 }}>{registration ? <Link to="/login">Already registered? Sign in</Link> : <Link to="/register">Create an account</Link>}</p>
    </div>
  </div>;
}
