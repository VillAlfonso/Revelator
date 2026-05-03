import React, { useEffect, useState, useCallback } from 'react';
import { api } from '../api/client';
import { useAuth } from '../App';

const PLANS = ['free', 'basic', 'pro'];

const labelStyle = { fontSize: 11, color: '#86efac', textTransform: 'uppercase', letterSpacing: 1, marginBottom: 4, display: 'block' };

export default function Admin() {
  const { user: me } = useAuth();
  const [tab, setTab] = useState('users'); // 'users' or 'promo'
  const [users, setUsers] = useState([]);
  const [total, setTotal] = useState(0);
  const [stats, setStats] = useState(null);
  const [q, setQ] = useState('');
  const [planFilter, setPlanFilter] = useState('');
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [editing, setEditing] = useState(null); // user object being edited
  const [saving, setSaving] = useState(false);
  const [deleteId, setDeleteId] = useState(null);
  const [codes, setCodes] = useState([]);
  const [codesLoading, setCodesLoading] = useState(false);
  const [generatingCode, setGeneratingCode] = useState(false);
  const [newCode, setNewCode] = useState({ code: '', plan: 'pro', max_uses: '10', expires_in_days: '' });

  const load = useCallback(async () => {
    setLoading(true);
    setError('');
    try {
      const [list, s] = await Promise.all([
        api.adminListUsers({ q, plan: planFilter }),
        api.adminStats(),
      ]);
      setUsers(list.users);
      setTotal(list.total);
      setStats(s);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }, [q, planFilter]);

  const loadCodes = useCallback(async () => {
    setCodesLoading(true);
    setError('');
    try {
      const data = await api.adminListCodes();
      setCodes(data.codes || []);
    } catch (err) {
      setError(err.message);
    } finally {
      setCodesLoading(false);
    }
  }, []);

  useEffect(() => { load(); }, [load]);
  useEffect(() => { if (tab === 'promo') loadCodes(); }, [tab, loadCodes]);

  async function saveEdit() {
    setSaving(true);
    setError('');
    try {
      const patch = {
        plan: editing.plan,
        is_admin: editing.is_admin,
        is_active: editing.is_active,
        full_name: editing.full_name,
        username: editing.username,
        email: editing.email,
      };
      if (editing._password) patch.password = editing._password;
      await api.adminUpdateUser(editing.id, patch);
      setEditing(null);
      await load();
    } catch (err) {
      setError(err.message);
    } finally {
      setSaving(false);
    }
  }

  async function confirmDelete() {
    if (!deleteId) return;
    setError('');
    try {
      await api.adminDeleteUser(deleteId);
      setDeleteId(null);
      await load();
    } catch (err) {
      setError(err.message);
    }
  }

  async function generateCode() {
    if (!newCode.code.trim() || !newCode.max_uses) {
      setError('Code and max uses are required');
      return;
    }
    setGeneratingCode(true);
    setError('');
    try {
      await api.adminGenerateCode(newCode.code, newCode.plan, parseInt(newCode.max_uses), newCode.expires_in_days);
      setNewCode({ code: '', plan: 'pro', max_uses: '10', expires_in_days: '' });
      await loadCodes();
    } catch (err) {
      setError(err.message);
    } finally {
      setGeneratingCode(false);
    }
  }

  async function deactivateCode(codeId) {
    setError('');
    try {
      await api.adminDeactivateCode(codeId);
      await loadCodes();
    } catch (err) {
      setError(err.message);
    }
  }

  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 20, flexWrap: 'wrap', gap: 12 }}>
        <div>
          <p className="classification-bar" style={{ marginBottom: 6 }}>
            CONTROL · ADMIN · CONSOLE
          </p>
          <h1 className="oswald glow" style={{
            fontSize: 26, color: '#00ff66', letterSpacing: 4, textTransform: 'uppercase', margin: 0,
          }}>
            Admin Panel
          </h1>
        </div>
        <span className="mono" style={{ fontSize: 11, color: '#86efac', letterSpacing: 2, textTransform: 'uppercase' }}>
          {total} OPERATOR{total === 1 ? '' : 'S'}
        </span>
      </div>

      {stats && (
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(140px, 1fr))', gap: 12, marginBottom: 20 }}>
          <StatCard label="Total Users" value={stats.total_users} />
          <StatCard label="Total Scans" value={stats.total_scans} />
          <StatCard label="Admins" value={stats.admins} />
          <StatCard label="Free" value={stats.plans.free} />
          <StatCard label="Basic" value={stats.plans.basic} />
          <StatCard label="Pro" value={stats.plans.pro} />
        </div>
      )}

      <div style={{ display: 'flex', gap: 8, marginBottom: 20, borderBottom: '1px solid #1d3825', paddingBottom: 12 }}>
        <button
          className="mono"
          onClick={() => setTab('users')}
          style={{
            padding: '8px 12px', fontSize: 12, background: 'none', border: 'none', cursor: 'pointer',
            color: tab === 'users' ? '#00ff66' : '#86efac',
            textTransform: 'uppercase', letterSpacing: 1,
            borderBottom: tab === 'users' ? '2px solid #00ff66' : 'none',
            marginBottom: '-12px',
          }}
        >
          Users
        </button>
        <button
          className="mono"
          onClick={() => setTab('promo')}
          style={{
            padding: '8px 12px', fontSize: 12, background: 'none', border: 'none', cursor: 'pointer',
            color: tab === 'promo' ? '#00ff66' : '#86efac',
            textTransform: 'uppercase', letterSpacing: 1,
            borderBottom: tab === 'promo' ? '2px solid #00ff66' : 'none',
            marginBottom: '-12px',
          }}
        >
          Promo Codes
        </button>
      </div>

      {tab === 'users' && (
      <div>
      <div className="card" style={{ marginBottom: 16, display: 'flex', gap: 12, flexWrap: 'wrap', alignItems: 'flex-end' }}>
        <div style={{ flex: '1 1 200px' }}>
          <label style={labelStyle}>Search</label>
          <input className="input" value={q} onChange={e => setQ(e.target.value)} placeholder="email, username, name" />
        </div>
        <div style={{ width: 160 }}>
          <label style={labelStyle}>Plan</label>
          <select className="input" value={planFilter} onChange={e => setPlanFilter(e.target.value)}>
            <option value="">All plans</option>
            {PLANS.map(p => <option key={p} value={p}>{p}</option>)}
          </select>
        </div>
        <button className="btn btn-primary" onClick={load} disabled={loading}>
          {loading ? 'Loading...' : 'Refresh'}
        </button>
      </div>

      {error && (
        <div style={{
          background: 'rgba(255,51,68,0.1)', border: '1px solid #ff3344', padding: 12, borderRadius: 2,
          marginBottom: 16, fontSize: 13, color: '#ff8a99',
          fontFamily: "'JetBrains Mono', monospace",
        }}>
          ⚠ {error}
        </div>
      )}

      <div style={{ display: 'grid', gap: 10 }}>
        {users.map(u => (
          <UserRow
            key={u.id}
            user={u}
            isMe={u.id === me?.id}
            onEdit={() => setEditing({ ...u, _password: '' })}
            onDelete={() => setDeleteId(u.id)}
          />
        ))}
        {!loading && users.length === 0 && (
          <div className="card" style={{ textAlign: 'center', color: '#86efac' }}>No users found.</div>
        )}
      </div>

      {editing && (
        <Modal onClose={() => setEditing(null)} title={`Edit user — ${editing.email}`}>
          <div style={{ display: 'grid', gap: 12 }}>
            <Field label="Email"><input className="input" value={editing.email} onChange={e => setEditing({ ...editing, email: e.target.value })} /></Field>
            <Field label="Username"><input className="input" value={editing.username} onChange={e => setEditing({ ...editing, username: e.target.value })} /></Field>
            <Field label="Full name"><input className="input" value={editing.full_name || ''} onChange={e => setEditing({ ...editing, full_name: e.target.value })} /></Field>
            <Field label="Plan">
              <select className="input" value={editing.plan} onChange={e => setEditing({ ...editing, plan: e.target.value })}>
                {PLANS.map(p => <option key={p} value={p}>{p}</option>)}
              </select>
            </Field>
            <Field label="Reset password (optional, min 6 chars)">
              <input className="input" type="password" value={editing._password} onChange={e => setEditing({ ...editing, _password: e.target.value })} placeholder="Leave blank to keep current" />
            </Field>
            <label style={{ display: 'flex', alignItems: 'center', gap: 8, fontSize: 13, color: '#e5e5e5' }}>
              <input type="checkbox" checked={editing.is_admin} onChange={e => setEditing({ ...editing, is_admin: e.target.checked })} disabled={editing.id === me?.id} />
              Admin {editing.id === me?.id && <span style={{ color: '#86efac', fontSize: 11 }}>(cannot remove own)</span>}
            </label>
            <label style={{ display: 'flex', alignItems: 'center', gap: 8, fontSize: 13, color: '#e5e5e5' }}>
              <input type="checkbox" checked={editing.is_active} onChange={e => setEditing({ ...editing, is_active: e.target.checked })} disabled={editing.id === me?.id} />
              Active {editing.id === me?.id && <span style={{ color: '#86efac', fontSize: 11 }}>(cannot deactivate own)</span>}
            </label>
            <div style={{ borderTop: '1px solid #112418', paddingTop: 12, fontSize: 12, color: '#86efac' }}>
              <div>ID: <span style={{ color: '#d8ffe6', fontFamily: 'monospace' }}>{editing.id}</span></div>
              <div>Stripe customer: <span style={{ color: '#d8ffe6', fontFamily: 'monospace' }}>{editing.stripe_customer_id || '—'}</span></div>
              <div>Stripe subscription: <span style={{ color: '#d8ffe6', fontFamily: 'monospace' }}>{editing.stripe_subscription_id || '—'}</span></div>
              <div>Scans this month: <span style={{ color: '#d8ffe6' }}>{editing.scans_this_month}</span></div>
              <div>Created: <span style={{ color: '#d8ffe6' }}>{editing.created_at}</span></div>
            </div>
            <div style={{ display: 'flex', gap: 8, justifyContent: 'flex-end', marginTop: 8 }}>
              <button className="btn" onClick={() => setEditing(null)} disabled={saving}>Cancel</button>
              <button className="btn btn-primary" onClick={saveEdit} disabled={saving}>{saving ? 'Saving...' : 'Save'}</button>
            </div>
          </div>
        </Modal>
      )}

      {deleteId && (
        <Modal onClose={() => setDeleteId(null)} title="Delete user?">
          <p style={{ color: '#e5e5e5', fontSize: 14 }}>
            This permanently deletes the user and all their scan history. This cannot be undone.
          </p>
          <div style={{ display: 'flex', gap: 8, justifyContent: 'flex-end', marginTop: 16 }}>
            <button className="btn" onClick={() => setDeleteId(null)}>Cancel</button>
            <button className="btn btn-danger" onClick={confirmDelete}>Delete</button>
          </div>
        </Modal>
      )}
      </div>
      )}

      {tab === 'promo' && (
      <div>
        <div className="card" style={{ marginBottom: 16, padding: 14 }}>
          <h3 className="oswald" style={{ margin: '0 0 12px 0', fontSize: 16, letterSpacing: 1, textTransform: 'uppercase' }}>Generate Promo Code</h3>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(140px, 1fr))', gap: 12 }}>
            <div>
              <label style={labelStyle}>Code</label>
              <input
                className="input"
                value={newCode.code}
                onChange={e => setNewCode({ ...newCode, code: e.target.value.toUpperCase() })}
                placeholder="e.g., FALL-2024"
              />
            </div>
            <div>
              <label style={labelStyle}>Plan</label>
              <select className="input" value={newCode.plan} onChange={e => setNewCode({ ...newCode, plan: e.target.value })}>
                <option value="free">Free</option>
                <option value="pro">Pro</option>
                <option value="premium">Premium</option>
              </select>
            </div>
            <div>
              <label style={labelStyle}>Max Uses</label>
              <input
                className="input"
                type="number"
                value={newCode.max_uses}
                onChange={e => setNewCode({ ...newCode, max_uses: e.target.value })}
                placeholder="10"
              />
            </div>
            <div>
              <label style={labelStyle}>Expires In (days, optional)</label>
              <input
                className="input"
                type="number"
                value={newCode.expires_in_days}
                onChange={e => setNewCode({ ...newCode, expires_in_days: e.target.value })}
                placeholder="30"
              />
            </div>
          </div>
          <button
            className="btn btn-primary"
            onClick={generateCode}
            disabled={generatingCode}
            style={{ marginTop: 12 }}
          >
            {generatingCode ? 'Generating...' : 'Generate Code'}
          </button>
        </div>

        <h3 className="oswald" style={{ fontSize: 16, letterSpacing: 1, textTransform: 'uppercase', marginBottom: 12 }}>Active Codes</h3>
        {codesLoading && <div className="card" style={{ textAlign: 'center', color: '#86efac' }}>Loading codes...</div>}
        {!codesLoading && codes.length === 0 && <div className="card" style={{ textAlign: 'center', color: '#86efac' }}>No promo codes yet.</div>}
        {codes.map(c => (
          <div key={c.id} className="card" style={{ display: 'flex', gap: 12, alignItems: 'center', justifyContent: 'space-between', marginBottom: 10 }}>
            <div style={{ flex: 1 }}>
              <div style={{ color: '#e5e5e5', fontWeight: 600, fontSize: 14, fontFamily: 'monospace' }}>{c.code}</div>
              <div style={{ color: '#86efac', fontSize: 12, marginTop: 4 }}>
                {c.plan.toUpperCase()} · Uses: {c.uses} · Expires: {c.expires_at} · {c.is_active ? 'Active' : 'Inactive'}
              </div>
            </div>
            <button
              className="btn"
              onClick={() => deactivateCode(c.id)}
              disabled={!c.is_active}
              style={{ borderColor: c.is_active ? '#ff3344' : '#1d3825', color: c.is_active ? '#ff8a99' : '#3f6e4a' }}
            >
              {c.is_active ? 'Deactivate' : 'Deactivated'}
            </button>
          </div>
        ))}
      </div>
      )}
    </div>
  );
}

function StatCard({ label, value }) {
  return (
    <div className="card" style={{ padding: 14 }}>
      <div className="mono" style={{ fontSize: 10, color: '#3f6e4a', textTransform: 'uppercase', letterSpacing: 2 }}>{label}</div>
      <div className="oswald" style={{
        fontSize: 24, color: '#00ff66', marginTop: 4,
        textShadow: '0 0 10px rgba(0,255,102,0.5)',
        letterSpacing: 1,
      }}>{value}</div>
    </div>
  );
}

function Badge({ children, color }) {
  return (
    <span style={{
      fontSize: 10, fontFamily: "'Oswald', sans-serif", textTransform: 'uppercase', letterSpacing: 1,
      padding: '2px 8px', borderRadius: 3, border: `1px solid ${color}`, color, background: `${color}1a`,
    }}>{children}</span>
  );
}

function UserRow({ user, isMe, onEdit, onDelete }) {
  const planColor = { free: '#86efac', basic: '#00ffaa', pro: '#00ff66' }[user.plan] || '#86efac';
  return (
    <div className="card" style={{ display: 'flex', flexWrap: 'wrap', gap: 12, alignItems: 'center', justifyContent: 'space-between' }}>
      <div style={{ flex: '1 1 240px', minWidth: 0 }}>
        <div style={{ display: 'flex', gap: 8, alignItems: 'center', flexWrap: 'wrap' }}>
          <span style={{ color: '#e5e5e5', fontWeight: 600, fontSize: 14, wordBreak: 'break-all' }}>{user.email}</span>
          {isMe && <Badge color="#00ff66">You</Badge>}
          {user.is_admin && <Badge color="#a3e635">Admin</Badge>}
          {!user.is_active && <Badge color="#ff3344">Disabled</Badge>}
          <Badge color={planColor}>{user.plan}</Badge>
        </div>
        <div style={{ color: '#86efac', fontSize: 12, marginTop: 4 }}>
          @{user.username} {user.full_name && `· ${user.full_name}`}
        </div>
        <div style={{ color: '#737373', fontSize: 11, marginTop: 4, fontFamily: 'monospace', wordBreak: 'break-all' }}>
          {user.id}
        </div>
        <div style={{ color: '#737373', fontSize: 11, marginTop: 2 }}>
          {user.scans_this_month} scans this month · joined {(user.created_at || '').slice(0, 10)}
        </div>
      </div>
      <div style={{ display: 'flex', gap: 8 }}>
        <button className="btn" onClick={onEdit}>Edit</button>
        <button
          className="btn"
          onClick={onDelete}
          disabled={isMe}
          style={{ borderColor: isMe ? '#1d3825' : '#ff3344', color: isMe ? '#3f6e4a' : '#ff8a99' }}
          title={isMe ? 'You cannot delete your own account' : 'Delete user'}
        >
          Delete
        </button>
      </div>
    </div>
  );
}

function Field({ label, children }) {
  return (
    <div>
      <label style={labelStyle}>{label}</label>
      {children}
    </div>
  );
}

function Modal({ title, children, onClose }) {
  return (
    <div
      onClick={onClose}
      style={{
        position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.75)',
        display: 'flex', alignItems: 'flex-start', justifyContent: 'center',
        padding: 24, zIndex: 1000, overflowY: 'auto',
      }}
    >
      <div
        onClick={e => e.stopPropagation()}
        className="card"
        style={{ width: '100%', maxWidth: 520, marginTop: 40 }}
      >
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 }}>
          <h3 className="oswald" style={{ margin: 0, fontSize: 18, letterSpacing: 2, textTransform: 'uppercase' }}>{title}</h3>
          <button onClick={onClose} style={{ background: 'none', border: 'none', color: '#86efac', fontSize: 22, cursor: 'pointer', lineHeight: 1 }}>×</button>
        </div>
        {children}
      </div>
    </div>
  );
}
