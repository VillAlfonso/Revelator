import React, { useEffect, useState } from 'react';
import { useAuth } from '../App';
import { api } from '../api/client';

export default function Account() {
  const { user, refreshUser } = useAuth();
  const [plans, setPlans] = useState([]);
  const [editing, setEditing] = useState(false);
  const [form, setForm] = useState({ full_name: '', username: '' });
  const [msg, setMsg] = useState('');
  const [error, setError] = useState('');

  useEffect(() => {
    api.getPlans().then(data => setPlans(data.plans)).catch(() => {});
    if (user) setForm({ full_name: user.full_name || '', username: user.username || '' });
  }, [user]);

  // Check for payment redirect
  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    if (params.get('payment') === 'success') {
      setMsg('Payment successful! Your plan will update shortly.');
      refreshUser();
      window.history.replaceState({}, '', '/account');
    } else if (params.get('payment') === 'cancelled') {
      setError('Payment was cancelled.');
      window.history.replaceState({}, '', '/account');
    }
  }, []);

  async function saveProfile() {
    setError('');
    try {
      await api.updateMe(form);
      await refreshUser();
      setEditing(false);
      setMsg('Profile updated.');
      setTimeout(() => setMsg(''), 3000);
    } catch (err) {
      setError(err.message);
    }
  }

  async function handleUpgrade(planId) {
    try {
      const data = await api.createCheckout(planId);
      if (data.checkout_url) {
        window.location.href = data.checkout_url;
      }
    } catch (err) {
      setError(err.message);
    }
  }

  async function handleCancel() {
    if (!confirm('Cancel your subscription? You will keep access until the end of your billing period.')) return;
    try {
      await api.cancelSubscription();
      setMsg('Subscription cancelled. Access continues until end of billing period.');
      refreshUser();
    } catch (err) {
      setError(err.message);
    }
  }

  const planLimits = { free: 10, pro: -1, premium: -1 };
  const userLimit = planLimits[user?.plan] ?? 10;
  const usageDisplay = userLimit === -1
    ? `${user?.scans_this_month || 0} scans this month · unlimited`
    : `${user?.scans_this_month || 0} / ${userLimit} scans used this month`;

  return (
    <div style={{ maxWidth: 700 }}>
      <h1 className="oswald" style={{ fontSize: 26, letterSpacing: 2, textTransform: 'uppercase', marginBottom: 24 }}>Account</h1>

      {msg && (
        <div style={{ background: 'rgba(34,197,94,0.15)', border: '1px solid #22c55e', padding: 12, borderRadius: 4, marginBottom: 16, fontSize: 13, color: '#4ade80' }}>
          {msg}
        </div>
      )}
      {error && (
        <div style={{ background: 'rgba(220,38,38,0.15)', border: '1px solid #dc2626', padding: 12, borderRadius: 4, marginBottom: 16, fontSize: 13, color: '#f87171' }}>
          {error}
        </div>
      )}

      {/* Profile */}
      <div className="card" style={{ marginBottom: 24 }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 }}>
          <h2 className="oswald" style={{ fontSize: 16, letterSpacing: 2, textTransform: 'uppercase' }}>Profile</h2>
          {!editing && (
            <button onClick={() => setEditing(true)} style={{
              background: 'none', border: '1px solid #404040', color: '#a3a3a3',
              padding: '6px 14px', cursor: 'pointer', fontSize: 11, borderRadius: 3,
              fontFamily: "'Oswald', sans-serif", textTransform: 'uppercase', letterSpacing: 1,
            }}>Edit</button>
          )}
        </div>

        {editing ? (
          <div>
            <div style={{ marginBottom: 14 }}>
              <label style={{ fontSize: 12, color: '#a3a3a3', textTransform: 'uppercase', letterSpacing: 1, marginBottom: 6, display: 'block' }}>Full Name</label>
              <input className="input" value={form.full_name} onChange={e => setForm(f => ({ ...f, full_name: e.target.value }))} />
            </div>
            <div style={{ marginBottom: 14 }}>
              <label style={{ fontSize: 12, color: '#a3a3a3', textTransform: 'uppercase', letterSpacing: 1, marginBottom: 6, display: 'block' }}>Username</label>
              <input className="input" value={form.username} onChange={e => setForm(f => ({ ...f, username: e.target.value }))} />
            </div>
            <div style={{ display: 'flex', gap: 12 }}>
              <button className="btn btn-primary" onClick={saveProfile} style={{ padding: '10px 24px' }}>Save</button>
              <button className="btn btn-secondary" onClick={() => setEditing(false)} style={{ padding: '10px 24px' }}>Cancel</button>
            </div>
          </div>
        ) : (
          <div style={{ display: 'grid', gap: 10 }}>
            <div><span style={{ color: '#525252', fontSize: 12, textTransform: 'uppercase', letterSpacing: 1 }}>Email:</span> <span className="mono" style={{ fontSize: 14 }}>{user?.email}</span></div>
            <div><span style={{ color: '#525252', fontSize: 12, textTransform: 'uppercase', letterSpacing: 1 }}>Username:</span> <span style={{ fontSize: 14 }}>{user?.username}</span></div>
            <div><span style={{ color: '#525252', fontSize: 12, textTransform: 'uppercase', letterSpacing: 1 }}>Name:</span> <span style={{ fontSize: 14 }}>{user?.full_name || '-'}</span></div>
            <div><span style={{ color: '#525252', fontSize: 12, textTransform: 'uppercase', letterSpacing: 1 }}>Member since:</span> <span className="mono" style={{ fontSize: 14 }}>{user?.created_at ? new Date(user.created_at).toLocaleDateString() : '-'}</span></div>
          </div>
        )}
      </div>

      {/* Current Plan */}
      <div className="card" style={{ marginBottom: 24, borderColor: '#f5c518' }}>
        <h2 className="oswald" style={{ fontSize: 16, letterSpacing: 2, textTransform: 'uppercase', marginBottom: 12 }}>Current Plan</h2>
        <div style={{ display: 'flex', alignItems: 'center', gap: 16, flexWrap: 'wrap' }}>
          <span className="oswald" style={{ fontSize: 24, color: '#f5c518', textTransform: 'uppercase' }}>{user?.plan}</span>
          <span className="mono" style={{ color: '#a3a3a3', fontSize: 13 }}>
            {usageDisplay}
          </span>
        </div>
        {user?.plan !== 'free' && (
          <button onClick={handleCancel} style={{
            background: 'none', border: 'none', color: '#dc2626', cursor: 'pointer',
            fontSize: 12, fontFamily: "'Oswald', sans-serif", textTransform: 'uppercase',
            letterSpacing: 1, marginTop: 12, padding: 0,
          }}>Cancel Subscription</button>
        )}
      </div>

      {/* Plans */}
      <h2 className="oswald" style={{ fontSize: 16, letterSpacing: 2, textTransform: 'uppercase', marginBottom: 16 }}>Plans</h2>
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))', gap: 16 }}>
        {plans.map(plan => {
          const isCurrent = user?.plan === plan.id;
          const isPremium = plan.id === 'premium';
          return (
            <div key={plan.id} className="card" style={{
              borderColor: isCurrent ? '#f5c518' : (isPremium ? '#8b5cf6' : '#262626'),
              opacity: isCurrent ? 0.7 : 1,
              position: 'relative',
            }}>
              {isPremium && !isCurrent && (
                <span className="mono" style={{
                  position: 'absolute', top: -10, right: 14,
                  background: '#8b5cf6', color: '#fff', fontSize: 9,
                  padding: '3px 8px', borderRadius: 3, letterSpacing: 1.5,
                }}>BEST VALUE</span>
              )}
              <h3 className="oswald" style={{ fontSize: 18, textTransform: 'uppercase', letterSpacing: 2 }}>{plan.name}</h3>
              <div style={{ margin: '12px 0' }}>
                <span className="mono" style={{ fontSize: 28, fontWeight: 700, color: '#f5c518' }}>
                  ${plan.price}
                </span>
                {plan.price > 0 && <span style={{ color: '#525252', fontSize: 13 }}>/mo</span>}
              </div>
              <div className="mono" style={{
                fontSize: 11, color: plan.unlimited ? '#22c55e' : '#a3a3a3',
                marginBottom: 10, letterSpacing: 1.5, textTransform: 'uppercase',
              }}>
                {plan.unlimited ? '∞ Unlimited scans' : `${plan.scans_per_month} scans / month`}
              </div>
              {plan.llm_included && (
                <div className="mono" style={{
                  display: 'inline-block', fontSize: 10, padding: '3px 8px',
                  background: 'rgba(139,92,246,0.2)', color: '#a78bfa',
                  borderRadius: 3, letterSpacing: 1.5, marginBottom: 10,
                }}>
                  ✨ AI EXPLANATION
                </div>
              )}
              <ul style={{ listStyle: 'none', padding: 0, marginBottom: 16 }}>
                {plan.features.map(f => (
                  <li key={f} style={{ padding: '4px 0', fontSize: 13, color: '#d4d4d4', display: 'flex', gap: 6 }}>
                    <span style={{ color: '#22c55e' }}>✓</span><span>{f}</span>
                  </li>
                ))}
              </ul>
              {isCurrent ? (
                <div className="mono" style={{ textAlign: 'center', color: '#f5c518', fontSize: 12, textTransform: 'uppercase', letterSpacing: 1.5 }}>Current Plan</div>
              ) : plan.price > 0 ? (
                <button className="btn btn-primary" onClick={() => handleUpgrade(plan.id)} style={{ width: '100%', padding: '10px' }}>
                  {user?.plan === 'free' ? 'Upgrade' : 'Switch'}
                </button>
              ) : (
                <div className="mono" style={{ textAlign: 'center', color: '#525252', fontSize: 11, textTransform: 'uppercase', letterSpacing: 1.5 }}>
                  Free tier
                </div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}
