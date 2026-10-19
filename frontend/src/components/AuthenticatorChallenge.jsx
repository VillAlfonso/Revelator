import React, { useState } from 'react';
import { api } from '../api/client';

export default function AuthenticatorChallenge({ challenge, onComplete, onCancel }) {
  const [code, setCode] = useState('');
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState(null);
  const [saved, setSaved] = useState(false);
  async function verify(event) {
    event.preventDefault(); setBusy(true); setError('');
    try {
      const data = await api.verifyAuthenticator(challenge.challenge_token, code.trim());
      if (data.recovery_codes) setResult(data);
      else onComplete(data);
    } catch (err) { setError(err.message); }
    finally { setBusy(false); }
  }
  return <div className="card" style={{ maxWidth: 480, margin: '40px auto', color: '#d8ffe6' }}>
    <h2 className="oswald">{result ? 'Save your recovery codes' : challenge.setup_required ? 'Set up Google Authenticator' : 'Authenticator verification'}</h2>
    {result ? <>
      <p>Store these codes somewhere safe. Each works once. They are shown only now and can restore access if you lose your phone.</p>
      <pre style={{ userSelect: 'all', whiteSpace: 'pre-wrap' }}>{result.recovery_codes.join('\n')}</pre>
      <label><input type="checkbox" checked={saved} onChange={e => setSaved(e.target.checked)} /> I saved my recovery codes</label>
      <button className="btn btn-primary" disabled={!saved} onClick={() => onComplete(result)}>Continue</button>
    </> : <>
      <p>{challenge.email}</p>
      {challenge.setup_required && <>
        <p>In Google Authenticator, choose Add account and scan this QR code, or enter the setup key as a time-based key.</p>
        <img src={challenge.qr_image} alt="Authenticator setup QR code" style={{ width: 240, maxWidth: '100%' }} />
        <p style={{ overflowWrap: 'anywhere', userSelect: 'all' }}>Setup key: {challenge.setup_key}</p>
      </>}
      <form onSubmit={verify}>
        <label htmlFor="authenticator-code">{challenge.setup_required ? 'Six-digit app code' : 'App code or unused recovery code'}</label>
        <input id="authenticator-code" className="input" autoComplete="one-time-code" autoFocus required maxLength={64} value={code} onChange={e => setCode(e.target.value)} />
        {error && <p role="alert" style={{ color: '#ff8a99' }}>{error}</p>}
        <button className="btn btn-primary" disabled={busy}>{busy ? 'Verifying…' : 'Verify'}</button>
        <button className="btn btn-secondary" type="button" disabled={busy} onClick={onCancel}>Back to sign in</button>
      </form>
    </>}
  </div>;
}
