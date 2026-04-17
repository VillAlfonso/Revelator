import React, { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { useAuth } from '../App';
import { api } from '../api/client';

export default function Dashboard() {
  const { user } = useAuth();
  const [history, setHistory] = useState([]);
  const [stats, setStats] = useState({ total: 0, forged: 0, suspicious: 0, genuine: 0 });

  useEffect(() => {
    api.getHistory(5).then(data => {
      setHistory(data.scans);
      api.getHistory(1000, 0).then(all => {
        const s = { total: all.total, forged: 0, suspicious: 0, genuine: 0 };
        all.scans.forEach(scan => { if (s[scan.verdict] !== undefined) s[scan.verdict]++; });
        setStats(s);
      });
    }).catch(() => {});
  }, []);

  const planLimits = { free: 10, basic: 100, pro: 1000 };
  const limit = planLimits[user?.plan] || 10;
  const used = user?.scans_this_month || 0;
  const pct = Math.min((used / limit) * 100, 100);

  return (
    <div>
      <div style={{ marginBottom: 32 }}>
        <h1 className="oswald" style={{ fontSize: 26, letterSpacing: 2, textTransform: 'uppercase' }}>
          Dashboard
        </h1>
        <p style={{ color: '#a3a3a3', marginTop: 4 }}>
          Welcome back, <span style={{ color: '#f5c518' }}>{user?.full_name || user?.username}</span>
        </p>
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))', gap: 16, marginBottom: 32 }}>
        <div className="card" style={{ textAlign: 'center' }}>
          <div className="mono" style={{ fontSize: 32, fontWeight: 700, color: '#f5c518' }}>{stats.total}</div>
          <div style={{ fontSize: 12, color: '#a3a3a3', textTransform: 'uppercase', letterSpacing: 1, marginTop: 4 }}>Total Scans</div>
        </div>
        <div className="card" style={{ textAlign: 'center' }}>
          <div className="mono" style={{ fontSize: 32, fontWeight: 700, color: '#dc2626' }}>{stats.forged}</div>
          <div style={{ fontSize: 12, color: '#a3a3a3', textTransform: 'uppercase', letterSpacing: 1, marginTop: 4 }}>Forged</div>
        </div>
        <div className="card" style={{ textAlign: 'center' }}>
          <div className="mono" style={{ fontSize: 32, fontWeight: 700, color: '#f97316' }}>{stats.suspicious}</div>
          <div style={{ fontSize: 12, color: '#a3a3a3', textTransform: 'uppercase', letterSpacing: 1, marginTop: 4 }}>Suspicious</div>
        </div>
        <div className="card" style={{ textAlign: 'center' }}>
          <div className="mono" style={{ fontSize: 32, fontWeight: 700, color: '#22c55e' }}>{stats.genuine}</div>
          <div style={{ fontSize: 12, color: '#a3a3a3', textTransform: 'uppercase', letterSpacing: 1, marginTop: 4 }}>Genuine</div>
        </div>
      </div>

      <div className="card" style={{ marginBottom: 32 }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 12 }}>
          <span className="oswald" style={{ textTransform: 'uppercase', letterSpacing: 1.5, fontSize: 14 }}>Monthly Usage</span>
          <span className="mono" style={{ fontSize: 13, color: '#a3a3a3' }}>
            {used} / {limit} scans ({user?.plan} plan)
          </span>
        </div>
        <div style={{ background: '#1a1a1a', borderRadius: 4, height: 8, overflow: 'hidden' }}>
          <div style={{
            width: `${pct}%`, height: '100%', borderRadius: 4,
            background: pct > 90 ? '#dc2626' : pct > 70 ? '#f97316' : '#f5c518',
            transition: 'width 0.5s',
          }} />
        </div>
        {pct >= 90 && (
          <p style={{ fontSize: 13, color: '#f97316', marginTop: 8 }}>
            Running low on scans. <Link to="/account">Upgrade your plan</Link>
          </p>
        )}
      </div>

      <div style={{ textAlign: 'center', marginBottom: 32 }}>
        <Link to="/scan">
          <button className="btn btn-primary" style={{ fontSize: 16, padding: '18px 48px' }}>
            New Scan
          </button>
        </Link>
      </div>

      <div className="card">
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 }}>
          <h2 className="oswald" style={{ fontSize: 16, letterSpacing: 2, textTransform: 'uppercase' }}>Recent Scans</h2>
          <Link to="/history" style={{ fontSize: 13 }}>View all</Link>
        </div>
        {history.length === 0 ? (
          <p style={{ color: '#525252', textAlign: 'center', padding: 24 }}>No scans yet. Start by scanning a document.</p>
        ) : (
          <div>
            {history.map(scan => (
              <div key={scan.scan_id} style={{
                display: 'flex', justifyContent: 'space-between', alignItems: 'center',
                padding: '12px 0', borderBottom: '1px solid #262626',
              }}>
                <div>
                  <span className="mono" style={{ fontSize: 13, color: '#a3a3a3' }}>{scan.scan_id}</span>
                  <span style={{ marginLeft: 12, fontSize: 14 }}>{scan.filename}</span>
                </div>
                <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
                  <span className={`badge badge-${scan.verdict}`}>{scan.verdict}</span>
                  <span className="mono" style={{ fontSize: 12, color: '#525252' }}>
                    {new Date(scan.created_at).toLocaleDateString()}
                  </span>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
