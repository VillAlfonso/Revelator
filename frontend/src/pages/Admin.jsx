import React, { useEffect, useState, useCallback } from 'react';
import { api } from '../api/client';
import { useAuth } from '../App';
import PromptDashboard from '../components/PromptDashboard';

const PLANS = ['free', 'basic', 'pro'];

const labelStyle = { fontSize: 11, color: '#86efac', textTransform: 'uppercase', letterSpacing: 1, marginBottom: 4, display: 'block' };

export default function Admin() {
  const { user: me } = useAuth();
  const isSuperAdmin = me?.role === "superadmin";
  const [tab, setTab] = useState('users'); // 'users', 'dataset', 'logs'
  const [users, setUsers] = useState([]);
  const [total, setTotal] = useState(0);
  const [stats, setStats] = useState(null);
  const [q, setQ] = useState('');
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [editing, setEditing] = useState(null);
  const [saving, setSaving] = useState(false);
  const [deleteId, setDeleteId] = useState(null);
  const [logs, setLogs] = useState([]);
  const [logsStats, setLogsStats] = useState({ admin_actions_total: 0, scans_total: 0, total: 0 });
  const [logsLoading, setLogsLoading] = useState(false);
  const [logsFilter, setLogsFilter] = useState('all'); // 'all', 'admin', 'scan'
  const [banningUserId, setBanningUserId] = useState(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError('');
    try {
      const [list, s] = await Promise.all([
        api.adminListUsers({ q }),
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
  }, [q]);


  const loadLogs = useCallback(async () => {
    setLogsLoading(true);
    setError('');
    try {
      const kind = logsFilter === 'all' ? null : logsFilter;
      const data = await api.adminViewLogs(200, 0, kind);
      setLogs(data.logs || []);
      setLogsStats({
        admin_actions_total: data.admin_actions_total || 0,
        scans_total: data.scans_total || 0,
        total: data.total || 0,
      });
    } catch (err) {
      setError(err.message);
    } finally {
      setLogsLoading(false);
    }
  }, [logsFilter]);

  useEffect(() => { load(); }, [load]);
  useEffect(() => { if (tab === 'logs') loadLogs(); }, [tab, loadLogs]);

  async function saveEdit() {
    setSaving(true);
    setError('');
    try {
      const patch = {
        is_active: editing.is_active,
        full_name: editing.full_name,
        username: editing.username,
        email: editing.email,
        role: editing.role,
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

  async function banUser(userId) {
    setBanningUserId(userId);
    setError('');
    try {
      await api.adminBanUser(userId);
      await load();
    } catch (err) {
      setError(err.message);
    } finally {
      setBanningUserId(null);
    }
  }

  async function unbanUser(userId) {
    setBanningUserId(userId);
    setError('');
    try {
      await api.adminUnbanUser(userId);
      await load();
    } catch (err) {
      setError(err.message);
    } finally {
      setBanningUserId(null);
    }
  }

  async function promoteUser(userId) {
    setError('');
    try {
      await api.adminPromoteAdmin(userId);
      await load();
    } catch (err) {
      setError(err.message);
    }
  }

  async function demoteUser(userId) {
    setError('');
    try {
      await api.adminDemoteAdmin(userId);
      await load();
    } catch (err) {
      setError(err.message);
    }
  }

  return (
    <div>
      <div style={{ marginBottom: 20 }}>
        <p className="classification-bar" style={{ marginBottom: 6 }}>
          CONTROL · ADMIN · CONSOLE
        </p>
        <h1 className="oswald glow" style={{
          fontSize: 26, color: '#00ff66', letterSpacing: 4, textTransform: 'uppercase', margin: 0,
        }}>
          Admin Panel
        </h1>
      </div>

      {stats && (
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(140px, 1fr))', gap: 12, marginBottom: 20 }}>
          <StatCard label="Total Users" value={stats.total_users} />
          <StatCard label="Admins" value={stats.admins ?? 0} />
          <StatCard label="Super Admins" value={stats.super_admins ?? 0} />
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
          onClick={() => setTab('logs')}
          style={{
            padding: '8px 12px', fontSize: 12, background: 'none', border: 'none', cursor: 'pointer',
            color: tab === 'logs' ? '#00ff66' : '#86efac',
            textTransform: 'uppercase', letterSpacing: 1,
            borderBottom: tab === 'logs' ? '2px solid #00ff66' : 'none',
            marginBottom: '-12px',
          }}
        >
          Audit Logs
        </button>
        <button
          className="mono"
          onClick={() => setTab('prompt')}
          style={{
            padding: '8px 12px', fontSize: 12, background: 'none', border: 'none', cursor: 'pointer',
            color: tab === 'prompt' ? '#00ff66' : '#86efac',
            textTransform: 'uppercase', letterSpacing: 1,
            borderBottom: tab === 'prompt' ? '2px solid #00ff66' : 'none',
            marginBottom: '-12px',
          }}
        >
          Prompt Analytics
        </button>
      </div>

      {tab === 'users' && (
      <div>
      <div className="card" style={{ marginBottom: 16, display: 'flex', gap: 12, flexWrap: 'wrap', alignItems: 'flex-end' }}>
        <div style={{ flex: '1 1 200px' }}>
          <label style={labelStyle}>Search</label>
          <input className="input" value={q} onChange={e => setQ(e.target.value)} placeholder="email, username, name" />
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
            isSuperAdmin={isSuperAdmin}
            onEdit={() => setEditing({ ...u, _password: '' })}
            onDelete={() => setDeleteId(u.id)}
            onBan={() => banUser(u.id)}
            onUnban={() => unbanUser(u.id)}
            onPromote={() => promoteUser(u.id)}
            onDemote={() => demoteUser(u.id)}
            isBanning={banningUserId === u.id}
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
            <Field label="Reset password (optional, min 6 chars)">
              <input className="input" type="password" value={editing._password} onChange={e => setEditing({ ...editing, _password: e.target.value })} placeholder="Leave blank to keep current" />
            </Field>
            <Field label="Role">
              <select className="input" value={editing.role || 'user'} onChange={e => setEditing({ ...editing, role: e.target.value })} disabled={editing.id === me?.id}>
                <option value="user">User</option>
                <option value="admin">Admin</option>
                <option value="superadmin">Super Admin</option>
              </select>
              {editing.id === me?.id && <span style={{ color: '#86efac', fontSize: 11, marginTop: 4, display: 'block' }}>(cannot change own role)</span>}
            </Field>
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

      {tab === 'logs' && (
        <LogsView
          logs={logs}
          logsStats={logsStats}
          loading={logsLoading}
          filter={logsFilter}
          onFilterChange={setLogsFilter}
          onRefresh={loadLogs}
        />
      )}

      {tab === 'prompt' && (
      <div className="card">
        <div style={{ marginBottom: 20 }}>
          <h2 className="oswald" style={{
            fontSize: 13, letterSpacing: 2.5, textTransform: 'uppercase',
            color: '#6dba85', marginBottom: 14, margin: 0,
          }}>
            ▸ How the Analyst Reasons — Live Prompt Analytics
          </h2>
          <p style={{ fontSize: 12, color: '#86efac', marginBottom: 16, lineHeight: 1.6 }}>
            Behind every classification is a prompt that defines 19 forgery categories, branching rules, and
            user-context variables. This dashboard reads the live prompt and shows how each category is
            described, where overlaps exist, and which categories tend to dominate when evidence is ambiguous.
          </p>
        </div>
        <PromptDashboard />
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

function UserRow({ user, isMe, isSuperAdmin, onEdit, onDelete, onBan, onUnban, onPromote, onDemote, isBanning }) {
  const planColor = { free: '#86efac', basic: '#00ffaa', pro: '#00ff66' }[user.plan] || '#86efac';
  const targetIsSuperAdmin = user.role === 'superadmin';
  // Regular admins are read-only. Super admins cannot act on other super admins.
  const canMutate = isSuperAdmin && !targetIsSuperAdmin;
  return (
    <div className="card" style={{ display: 'flex', flexWrap: 'wrap', gap: 12, alignItems: 'center', justifyContent: 'space-between' }}>
      <div style={{ flex: '1 1 240px', minWidth: 0 }}>
        <div style={{ display: 'flex', gap: 8, alignItems: 'center', flexWrap: 'wrap' }}>
          <span style={{ color: '#e5e5e5', fontWeight: 600, fontSize: 14, wordBreak: 'break-all' }}>{user.email}</span>
          {isMe && <Badge color="#00ff66">You</Badge>}
          {["admin","superadmin"].includes(user.role) && <Badge color="#a3e635">{user.role}</Badge>}
          {!user.is_active && <Badge color="#ff3344">Banned</Badge>}
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
      {canMutate && (
        <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', justifyContent: 'flex-end' }}>
          <button className="btn" onClick={onEdit} disabled={isMe} title={isMe ? 'You cannot edit your own account here' : 'Edit user'}>
            Edit
          </button>
          {user.role === 'user' && (
            <button
              className="btn"
              onClick={onPromote}
              style={{ borderColor: '#a78bfa', color: '#c4b5fd' }}
              title="Promote to admin"
            >
              Promote → Admin
            </button>
          )}
          {user.role === 'admin' && (
            <button
              className="btn"
              onClick={onDemote}
              style={{ borderColor: '#a78bfa', color: '#c4b5fd' }}
              title="Demote to regular user"
            >
              Demote → User
            </button>
          )}
          {user.is_active ? (
            <button
              className="btn"
              onClick={onBan}
              disabled={isMe || isBanning}
              style={{ borderColor: isMe ? '#1d3825' : '#ff9500', color: isMe ? '#3f6e4a' : '#ffa500' }}
              title={isMe ? 'You cannot ban your own account' : 'Ban user'}
            >
              {isBanning ? 'Banning...' : 'Ban'}
            </button>
          ) : (
            <button
              className="btn"
              onClick={onUnban}
              disabled={isBanning}
              style={{ borderColor: '#00cc88', color: '#00ff99' }}
              title="Unban user"
            >
              {isBanning ? 'Unbanning...' : 'Unban'}
            </button>
          )}
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
      )}
      {!isSuperAdmin && (
        <span className="mono" style={{ fontSize: 10, color: '#737373', letterSpacing: 1.5, padding: '4px 8px', border: '1px solid #1d3825', borderRadius: 2 }}>
          READ-ONLY
        </span>
      )}
      {isSuperAdmin && targetIsSuperAdmin && !isMe && (
        <span className="mono" style={{ fontSize: 10, color: '#a3e635', letterSpacing: 1.5, padding: '4px 8px', border: '1px solid #a3e635', borderRadius: 2 }}>
          PROTECTED
        </span>
      )}
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


// ─────────────────────────────────────────────────────────────────
// AUDIT LOG VIEW
// ─────────────────────────────────────────────────────────────────

const ACTION_COLORS = {
  ban_user:       '#ff8a99',
  unban_user:     '#86efac',
  promote_admin:  '#c4b5fd',
  demote_admin:   '#ffa040',
  update_user:    '#86efac',
  delete_user:    '#ff8a99',
  user_scan:      '#00ff66',
};

function LogsView({ logs, logsStats, loading, filter, onFilterChange, onRefresh }) {
  return (
    <div>
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(140px, 1fr))', gap: 12, marginBottom: 18 }}>
        <StatCard label="Total Scans" value={logsStats.scans_total ?? 0} />
        <StatCard label="Admin Actions" value={logsStats.admin_actions_total ?? 0} />
        <StatCard label="Total Events" value={logsStats.total ?? 0} />
      </div>

      <div style={{ display: 'flex', gap: 8, alignItems: 'center', marginBottom: 14, flexWrap: 'wrap' }}>
        <span className="mono" style={{ fontSize: 10, color: '#3f6e4a', letterSpacing: 2, textTransform: 'uppercase', marginRight: 4 }}>FILTER</span>
        {[
          { id: 'all',   label: 'All' },
          { id: 'admin', label: 'Admin Actions' },
          { id: 'scan',  label: 'User Scans' },
        ].map(opt => (
          <button
            key={opt.id}
            className="mono"
            onClick={() => onFilterChange(opt.id)}
            style={{
              padding: '6px 12px', fontSize: 11, cursor: 'pointer',
              background: filter === opt.id ? 'rgba(0,255,102,0.1)' : 'transparent',
              border: `1px solid ${filter === opt.id ? '#00ff66' : '#1d3825'}`,
              color: filter === opt.id ? '#00ff66' : '#86efac',
              letterSpacing: 1, textTransform: 'uppercase', borderRadius: 2,
            }}
          >
            {opt.label}
          </button>
        ))}
        <button
          className="btn"
          onClick={onRefresh}
          disabled={loading}
          style={{ marginLeft: 'auto', fontSize: 11 }}
        >
          {loading ? 'Loading...' : 'Refresh'}
        </button>
      </div>

      {loading && <div className="card" style={{ textAlign: 'center', color: '#86efac' }}>Loading logs...</div>}
      {!loading && logs.length === 0 && (
        <div className="card" style={{ textAlign: 'center', color: '#86efac' }}>No log entries.</div>
      )}
      {logs.map(log => (
        <LogRow key={log.id} log={log} />
      ))}
    </div>
  );
}

function LogRow({ log }) {
  const [expanded, setExpanded] = useState(false);
  const isScan = log.kind === 'scan';
  const accent = ACTION_COLORS[log.action] || '#86efac';
  const timestamp = log.created_at ? new Date(log.created_at).toLocaleString() : '';

  return (
    <div className="card" style={{
      marginBottom: 10, padding: 12, borderLeft: `3px solid ${accent}`,
    }}>
      <div
        onClick={() => setExpanded(s => !s)}
        style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', cursor: 'pointer', userSelect: 'none' }}
      >
        <div style={{ display: 'flex', alignItems: 'center', gap: 10, flexWrap: 'wrap', flex: 1, minWidth: 0 }}>
          <span className="mono" style={{
            fontSize: 9, padding: '3px 8px', borderRadius: 2, letterSpacing: 1.5,
            background: `${accent}1a`, color: accent, border: `1px solid ${accent}66`, textTransform: 'uppercase',
          }}>
            {isScan ? 'SCAN' : 'ADMIN'}
          </span>
          <span style={{ color: '#e5e5e5', fontWeight: 600, fontSize: 13 }}>
            {log.actor?.username || '—'}
          </span>
          {log.actor?.role && (
            <span className="mono" style={{ fontSize: 9, color: '#6dba85', letterSpacing: 1.5, textTransform: 'uppercase' }}>
              {log.actor.role}
            </span>
          )}
          <span style={{ color: '#86efac', fontSize: 12 }}>·</span>
          <span style={{ color: '#86efac', fontSize: 12, letterSpacing: 0.5 }}>
            {log.action.replace(/_/g, ' ')}
          </span>
          {log.target && (
            <>
              <span style={{ color: '#3f6e4a', fontSize: 12 }}>→</span>
              <span style={{ color: '#d8ffe6', fontSize: 12 }}>@{log.target.username}</span>
            </>
          )}
          {isScan && log.scan && (
            <>
              <span style={{ color: '#3f6e4a', fontSize: 12 }}>·</span>
              <span className="mono" style={{ fontSize: 11, color: accent, letterSpacing: 1 }}>
                {log.scan.verdict?.toUpperCase()}
              </span>
              <span className="mono" style={{ fontSize: 11, color: '#6dba85' }}>
                {(log.scan.confidence_score * 100).toFixed(0)}%
              </span>
            </>
          )}
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <span style={{ color: '#737373', fontSize: 11, whiteSpace: 'nowrap' }}>{timestamp}</span>
          <span className="mono" style={{ fontSize: 11, color: '#00ff66' }}>{expanded ? '▲' : '▼'}</span>
        </div>
      </div>

      {expanded && (
        <div style={{ marginTop: 12, paddingTop: 12, borderTop: '1px solid #112418' }}>
          {isScan && log.scan ? (
            <ScanLogDetail scan={log.scan} />
          ) : (
            <pre style={{
              color: '#86efac', fontSize: 11, lineHeight: 1.6, fontFamily: "'JetBrains Mono', monospace",
              background: '#000', padding: 10, borderRadius: 2, border: '1px solid #112418',
              whiteSpace: 'pre-wrap', wordBreak: 'break-all', margin: 0,
            }}>
              {JSON.stringify(log.details ?? {}, null, 2)}
            </pre>
          )}
        </div>
      )}
    </div>
  );
}

function ScanLogDetail({ scan }) {
  const imageUrl = scan.has_image ? api.adminScanImageUrl(scan.scan_id) : null;
  const verdictColors = { forged: '#ff3344', suspicious: '#ffa040', no_forgery_detected: '#00ff66', not_a_document: '#737373' };
  const vc = verdictColors[scan.verdict] || '#86efac';

  return (
    <div style={{ display: 'grid', gridTemplateColumns: imageUrl ? '220px 1fr' : '1fr', gap: 16 }}>
      {imageUrl && (
        <div>
          <p className="mono" style={{ fontSize: 9, letterSpacing: 2, color: '#3f6e4a', margin: '0 0 6px', textTransform: 'uppercase' }}>
            Scan Image
          </p>
          <img
            src={imageUrl}
            alt={scan.filename}
            style={{ width: '100%', border: '1px solid #1d3825', borderRadius: 2 }}
          />
          <p className="mono" style={{ fontSize: 10, color: '#6dba85', margin: '6px 0 0', wordBreak: 'break-all' }}>
            {scan.filename}
          </p>
          <p className="mono" style={{ fontSize: 10, color: '#3f6e4a', margin: '2px 0 0' }}>
            {scan.image_width} × {scan.image_height}
          </p>
        </div>
      )}
      <div>
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: 12, marginBottom: 10 }}>
          <Pill label="Scan ID" value={scan.scan_id} mono />
          <Pill label="Verdict" value={scan.verdict?.toUpperCase()} color={vc} />
          <Pill label="Confidence" value={`${(scan.confidence_score * 100).toFixed(1)}%`} />
          {scan.detected_category && <Pill label="Category" value={scan.detected_category} />}
          {scan.certainty_level && <Pill label="Certainty" value={scan.certainty_level} />}
          {scan.document_type && <Pill label="Doc Type" value={scan.document_type} />}
        </div>

        {scan.category_explanation && (
          <div style={{ marginBottom: 10 }}>
            <p className="mono" style={{ fontSize: 9, letterSpacing: 2, color: '#3f6e4a', margin: '0 0 4px', textTransform: 'uppercase' }}>
              Gemini Explanation
            </p>
            <p style={{ color: '#d8ffe6', fontSize: 12, lineHeight: 1.6, margin: 0 }}>{scan.category_explanation}</p>
          </div>
        )}

        {scan.category_evidence?.length > 0 && (
          <div style={{ marginBottom: 10 }}>
            <p className="mono" style={{ fontSize: 9, letterSpacing: 2, color: '#3f6e4a', margin: '0 0 4px', textTransform: 'uppercase' }}>
              Evidence
            </p>
            <ul style={{ margin: 0, paddingLeft: 18, color: '#86efac', fontSize: 12, lineHeight: 1.6 }}>
              {scan.category_evidence.map((e, i) => <li key={i}>{e}</li>)}
            </ul>
          </div>
        )}

        {scan.llm_explanation && (
          <div style={{ marginBottom: 10 }}>
            <p className="mono" style={{ fontSize: 9, letterSpacing: 2, color: '#3f6e4a', margin: '0 0 4px', textTransform: 'uppercase' }}>
              LLM Explanation
            </p>
            <p style={{ color: '#d8ffe6', fontSize: 12, lineHeight: 1.6, margin: 0 }}>{scan.llm_explanation}</p>
          </div>
        )}

        <details style={{ marginTop: 10 }}>
          <summary style={{ cursor: 'pointer', color: '#86efac', fontSize: 11, letterSpacing: 1.5, textTransform: 'uppercase', fontFamily: "'JetBrains Mono', monospace" }}>
            ▸ Full JSON
          </summary>
          <pre style={{
            color: '#86efac', fontSize: 11, lineHeight: 1.6, fontFamily: "'JetBrains Mono', monospace",
            background: '#000', padding: 10, borderRadius: 2, border: '1px solid #112418', marginTop: 8,
            whiteSpace: 'pre-wrap', wordBreak: 'break-all', maxHeight: 360, overflow: 'auto',
          }}>
            {JSON.stringify(scan, null, 2)}
          </pre>
        </details>
      </div>
    </div>
  );
}

function Pill({ label, value, color = '#86efac', mono = false }) {
  return (
    <div style={{ background: '#0a120c', border: '1px solid #112418', padding: '6px 10px', borderRadius: 2 }}>
      <div className="mono" style={{ fontSize: 9, letterSpacing: 1.5, color: '#3f6e4a', textTransform: 'uppercase' }}>
        {label}
      </div>
      <div style={{
        fontSize: 12, color, fontFamily: mono ? "'JetBrains Mono', monospace" : 'inherit',
        marginTop: 2, wordBreak: 'break-all',
      }}>
        {value}
      </div>
    </div>
  );
}
