import React, { useEffect, useState } from 'react';
import { updateProfile as updateAuthProfile } from 'firebase/auth';

import { api } from '../api/client';
import { auth } from '../firebase';
import { useAuth } from '../auth/AuthContext';
import { updateProfile as updateFirestoreProfile } from '../lib/firestore';

export default function Account() {
  const { user, profile } = useAuth();
  const [plans, setPlans] = useState([]);
  const [editing, setEditing] = useState(false);
  const [fullName, setFullName] = useState('');
  const [paymentMethod, setPaymentMethod] = useState('stripe');
  const [msg, setMsg] = useState('');
  const [error, setError] = useState('');

  useEffect(() => {
    api.getPlans().then(d => setPlans(d.plans)).catch(() => {});
  }, []);

  useEffect(() => {
    if (profile?.full_name) setFullName(profile.full_name);
  }, [profile]);

  // Capture redirect from a payment success / cancel
  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    if (params.get('payment') === 'success') {
      setMsg('Payment successful! Plan will update within a few seconds.');
      window.history.replaceState({}, '', '/account');
    } else if (params.get('payment') === 'cancelled') {
      setError('Payment was cancelled.');
      window.history.replaceState({}, '', '/account');
    }
  }, []);

  async function saveProfile() {
    setError('');
    try {
      if (auth.currentUser && fullName !== auth.currentUser.displayName) {
        await updateAuthProfile(auth.currentUser, { displayName: fullName });
      }
      await updateFirestoreProfile(user.uid, { full_name: fullName });
      setEditing(false);
      setMsg('Profile updated.');
      setTimeout(() => setMsg(''), 3000);
    } catch (err) {
      setError(err.message || 'Failed to save profile');
    }
  }

  async function handleUpgrade(planKey) {
    setError('');
    try {
      const data = await api.createCheckout(planKey, paymentMethod);
      if (data.checkout_url) window.location.href = data.checkout_url;
    } catch (err) {
      setError(err.message);
    }
  }

  if (!profile) {
    return <p className="mono" style={{ color: '#6dba85', padding: 24 }}>◌ LOADING…</p>;
  }

  const plan = profile.plan || 'free';
  const limit = { free: 10, pro: -1, premium: -1 }[plan] ?? 10;
  const used = profile.scans_this_month || 0;
  const usage = limit === -1
    ? `${used} scans this month · unlimited`
    : `${used} / ${limit} scans used this month`;

  return (
    <div style={{ maxWidth: 760 }}>
      <p className="classification-bar" style={{ marginBottom: 12 }}>OPERATOR · ACCOUNT · CONTROLS</p>
      <h1 className="oswald glow" style={{ fontSize: 28, letterSpacing: 3, textTransform: 'uppercase', marginBottom: 24, color: '#00ff66' }}>
        Account
      </h1>

      {msg && <Banner color="#00ff66">{msg}</Banner>}
      {error && <Banner color="#ff3344">⚠ {error}</Banner>}

      {/* Profile */}
      <div className="card" style={{ marginBottom: 24 }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 }}>
          <h3 className="oswald" style={{ fontSize: 14, letterSpacing: 2.5, textTransform: 'uppercase', margin: 0, color: '#6dba85' }}>▸ Profile</h3>
          {!editing && (
            <button onClick={() => setEditing(true)} className="btn btn-secondary" style={{ padding: '6px 14px', fontSize: 12 }}>Edit</button>
          )}
        </div>

        <div style={{ display: 'grid', gap: 10, fontSize: 13 }}>
          <Row label="EMAIL" value={profile.email || user?.email || '—'} />
          {editing ? (
            <Row label="NAME" value={
              <input value={fullName} onChange={e => setFullName(e.target.value)}
                style={{ width: '100%', padding: '6px 10px', background: '#0a1605', border: '1px solid #1d3825', borderRadius: 3, color: '#d8ffe6', fontSize: 13, fontFamily: "'JetBrains Mono', monospace" }}
              />
            } />
          ) : (
            <Row label="NAME" value={profile.full_name || '—'} />
          )}
          <Row label="UID" value={<span style={{ fontFamily: "'JetBrains Mono', monospace", fontSize: 11, color: '#3f6e4a' }}>{user?.uid}</span>} />
        </div>

        {editing && (
          <div style={{ display: 'flex', gap: 8, marginTop: 16 }}>
            <button onClick={saveProfile} className="btn btn-primary" style={{ padding: '8px 14px', fontSize: 12 }}>▶ Save</button>
            <button onClick={() => { setEditing(false); setFullName(profile.full_name || ''); }} className="btn btn-secondary" style={{ padding: '8px 14px', fontSize: 12 }}>Cancel</button>
          </div>
        )}
      </div>

      {/* Plan / usage */}
      <div className="card" style={{ marginBottom: 24 }}>
        <h3 className="oswald" style={{ fontSize: 14, letterSpacing: 2.5, textTransform: 'uppercase', margin: '0 0 12px', color: '#6dba85' }}>▸ Plan</h3>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <div>
            <div className="oswald glow" style={{ fontSize: 22, color: '#00ff66', textTransform: 'uppercase', letterSpacing: 4 }}>{plan}</div>
            <div className="mono" style={{ fontSize: 12, color: '#86efac', marginTop: 6 }}>{usage}</div>
          </div>
        </div>
      </div>

      {/* Upgrade */}
      {plan !== 'premium' && plans.length > 0 && (
        <div className="card" style={{ marginBottom: 24 }}>
          <h3 className="oswald" style={{ fontSize: 14, letterSpacing: 2.5, textTransform: 'uppercase', margin: '0 0 12px', color: '#6dba85' }}>▸ Upgrade</h3>

          <div style={{ display: 'flex', gap: 8, marginBottom: 16, fontSize: 12 }}>
            <button onClick={() => setPaymentMethod('stripe')}
              className={paymentMethod === 'stripe' ? 'btn btn-primary' : 'btn btn-secondary'}
              style={{ padding: '8px 14px' }}>Stripe (USD)</button>
            <button onClick={() => setPaymentMethod('paymongo')}
              className={paymentMethod === 'paymongo' ? 'btn btn-primary' : 'btn btn-secondary'}
              style={{ padding: '8px 14px' }}>PayMongo (PHP / GCash / Maya)</button>
          </div>

          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))', gap: 14 }}>
            {plans.filter(p => p.key !== 'free' && p.key !== plan).map(p => (
              <div key={p.key} style={{ border: '1px solid #1d3825', borderRadius: 6, padding: 16, background: '#0a120c' }}>
                <div className="oswald" style={{ fontSize: 18, color: '#d8ffe6', textTransform: 'uppercase', letterSpacing: 2, marginBottom: 6 }}>{p.name}</div>
                <div className="mono glow" style={{ fontSize: 22, color: '#00ff66', marginBottom: 10 }}>${p.price_usd}/mo</div>
                <ul style={{ margin: '0 0 14px', paddingLeft: 18, fontSize: 12, color: '#86efac', lineHeight: 1.6 }}>
                  {p.features.map((f, i) => <li key={i}>{f}</li>)}
                </ul>
                <button onClick={() => handleUpgrade(p.key)} className="btn btn-primary" style={{ width: '100%', padding: '10px 0', fontSize: 12 }}>
                  ▶ Choose {p.name}
                </button>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

function Row({ label, value }) {
  return (
    <div style={{ display: 'grid', gridTemplateColumns: '90px 1fr', gap: 12, alignItems: 'center', padding: '6px 0', borderBottom: '1px solid #112418' }}>
      <span className="mono" style={{ fontSize: 10, letterSpacing: 2, color: '#3f6e4a' }}>{label}</span>
      <span style={{ color: '#d8ffe6' }}>{value}</span>
    </div>
  );
}

function Banner({ color, children }) {
  return (
    <div style={{
      background: `${color}11`, border: `1px solid ${color}`, padding: 12, borderRadius: 2,
      marginBottom: 16, fontSize: 13, color, fontFamily: "'JetBrains Mono', monospace",
    }}>{children}</div>
  );
}
