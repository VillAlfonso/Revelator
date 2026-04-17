import React, { useState, useEffect, createContext, useContext } from 'react';
import { BrowserRouter, Routes, Route, Navigate, Link, useNavigate, useLocation } from 'react-router-dom';
import { api } from './api/client';
import Login from './pages/Login';
import Register from './pages/Register';
import Dashboard from './pages/Dashboard';
import Scan from './pages/Scan';
import History from './pages/History';
import Account from './pages/Account';
import Admin from './pages/Admin';

// ── Auth Context ────────────────────────────────────

const AuthContext = createContext(null);

export function useAuth() {
  return useContext(AuthContext);
}

function AuthProvider({ children }) {
  const [user, setUser] = useState(() => {
    const saved = localStorage.getItem('fg_user');
    return saved ? JSON.parse(saved) : null;
  });
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (api.getToken()) {
      api.getMe()
        .then(u => { setUser(u); localStorage.setItem('fg_user', JSON.stringify(u)); })
        .catch(() => { setUser(null); api.clearTokens(); })
        .finally(() => setLoading(false));
    } else {
      setLoading(false);
    }
  }, []);

  function loginUser(data) {
    api.saveTokens(data.access_token, data.refresh_token);
    setUser(data.user);
    localStorage.setItem('fg_user', JSON.stringify(data.user));
  }

  function logout() {
    api.clearTokens();
    setUser(null);
    localStorage.removeItem('fg_user');
  }

  function refreshUser() {
    return api.getMe().then(u => {
      setUser(u);
      localStorage.setItem('fg_user', JSON.stringify(u));
    });
  }

  return (
    <AuthContext.Provider value={{ user, loading, loginUser, logout, refreshUser }}>
      {children}
    </AuthContext.Provider>
  );
}

function ProtectedRoute({ children }) {
  const { user, loading } = useAuth();
  if (loading) return <div style={{ padding: 40, textAlign: 'center', color: '#a3a3a3' }}>Loading...</div>;
  if (!user) return <Navigate to="/login" replace />;
  return children;
}

function AdminRoute({ children }) {
  const { user, loading } = useAuth();
  if (loading) return <div style={{ padding: 40, textAlign: 'center', color: '#a3a3a3' }}>Loading...</div>;
  if (!user) return <Navigate to="/login" replace />;
  if (!user.is_admin) return <Navigate to="/" replace />;
  return children;
}

// ── Layout ──────────────────────────────────────────

function Layout({ children }) {
  const { user, logout } = useAuth();
  const location = useLocation();

  const navItems = [
    { path: '/scan', label: 'Scan' },
    { path: '/history', label: 'History' },
    { path: '/account', label: 'Account' },
    ...(user?.is_admin ? [{ path: '/admin', label: 'Admin Panel' }] : []),
  ];

  return (
    <div>
      <div className="tape-border" />
      <header style={{
        background: 'linear-gradient(180deg, #111 0%, #0a0a0a 100%)',
        borderBottom: '1px solid #262626',
        padding: '12px 16px',
      }}>
        <div className="container" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <Link to="/" style={{ textDecoration: 'none', display: 'flex', alignItems: 'center', gap: 10 }}>
            <span className="oswald" style={{ fontSize: 22, fontWeight: 700, color: '#f5c518', letterSpacing: 3 }}>
              FORGEGUARD
            </span>
          </Link>
          {user && (
            <nav style={{ display: 'flex', gap: 8, alignItems: 'center', flexWrap: 'wrap' }}>
              {navItems.map(item => (
                <Link
                  key={item.path}
                  to={item.path}
                  style={{
                    padding: '6px 14px',
                    fontSize: 13,
                    fontFamily: "'Oswald', sans-serif",
                    textTransform: 'uppercase',
                    letterSpacing: 1.5,
                    color: location.pathname === item.path ? '#f5c518' : '#a3a3a3',
                    textDecoration: 'none',
                    borderBottom: location.pathname === item.path ? '2px solid #f5c518' : '2px solid transparent',
                  }}
                >
                  {item.label}
                </Link>
              ))}
              <button
                onClick={logout}
                style={{
                  background: 'none', border: '1px solid #404040', color: '#a3a3a3',
                  padding: '6px 14px', cursor: 'pointer', fontSize: 12,
                  fontFamily: "'Oswald', sans-serif", textTransform: 'uppercase',
                  letterSpacing: 1, borderRadius: 4, marginLeft: 8,
                }}
              >
                Logout
              </button>
            </nav>
          )}
        </div>
      </header>
      <main style={{ padding: '24px 0', minHeight: 'calc(100vh - 80px)' }}>
        <div className="container">
          {children}
        </div>
      </main>
    </div>
  );
}

// ── App ─────────────────────────────────────────────

export default function App() {
  return (
    <BrowserRouter>
      <AuthProvider>
        <Layout>
          <Routes>
            <Route path="/login" element={<Login />} />
            <Route path="/register" element={<Register />} />
            <Route path="/" element={<ProtectedRoute><Dashboard /></ProtectedRoute>} />
            <Route path="/scan" element={<ProtectedRoute><Scan /></ProtectedRoute>} />
            <Route path="/history" element={<ProtectedRoute><History /></ProtectedRoute>} />
            <Route path="/account" element={<ProtectedRoute><Account /></ProtectedRoute>} />
            <Route path="/admin" element={<AdminRoute><Admin /></AdminRoute>} />
            <Route path="*" element={<Navigate to="/" replace />} />
          </Routes>
        </Layout>
      </AuthProvider>
    </BrowserRouter>
  );
}
