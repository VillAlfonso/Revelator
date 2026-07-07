/**
 * API client for Revelator backend.
 * Handles auth tokens automatically.
 */

const API_BASE = (import.meta.env.VITE_API_URL || '') + '/api';

function getToken() {
  return localStorage.getItem('fg_access_token');
}

function getRefreshToken() {
  return localStorage.getItem('fg_refresh_token');
}

function saveTokens(access, refresh) {
  localStorage.setItem('fg_access_token', access);
  localStorage.setItem('fg_refresh_token', refresh);
}

function clearTokens() {
  localStorage.removeItem('fg_access_token');
  localStorage.removeItem('fg_refresh_token');
  localStorage.removeItem('fg_user');
}

// ── Remembered-device tokens (skip 2FA) ─────────────────
// Stored per-email so several accounts can share one browser without
// clobbering each other's trust.
function deviceKey(email) {
  return `fg_device_token:${(email || '').trim().toLowerCase()}`;
}
function getDeviceToken(email) {
  return localStorage.getItem(deviceKey(email)) || null;
}
function saveDeviceToken(email, token) {
  if (token) localStorage.setItem(deviceKey(email), token);
}

async function request(path, options = {}) {
  const token = getToken();
  const headers = { ...options.headers };

  if (token && !options.noAuth) {
    headers['Authorization'] = `Bearer ${token}`;
  }

  // Don't set Content-Type for FormData (browser sets it with boundary)
  if (!(options.body instanceof FormData)) {
    headers['Content-Type'] = 'application/json';
  }

  let res = await fetch(`${API_BASE}${path}`, { ...options, headers });

  // If 401, try refreshing the token once
  if (res.status === 401 && !options._retried) {
    const refreshed = await tryRefresh();
    if (refreshed) {
      headers['Authorization'] = `Bearer ${getToken()}`;
      res = await fetch(`${API_BASE}${path}`, { ...options, headers, _retried: true });
    } else {
      clearTokens();
      window.dispatchEvent(new CustomEvent('fg:session-expired'));
      throw new Error('Session expired');
    }
  }

  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail || 'Request failed');
  }

  return res.json();
}

async function tryRefresh() {
  const refresh = getRefreshToken();
  if (!refresh) return false;
  try {
    const res = await fetch(`${API_BASE}/auth/refresh`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ refresh_token: refresh }),
    });
    if (!res.ok) return false;
    const data = await res.json();
    saveTokens(data.access_token, data.refresh_token);
    return true;
  } catch {
    return false;
  }
}

// ── Public API ──────────────────────────────────────

export const api = {
  // Auth
  register(email, username, password, full_name) {
    return request('/auth/register', {
      method: 'POST', noAuth: true,
      body: JSON.stringify({ email, username, password, full_name }),
    });
  },

  login(email, password) {
    return request('/auth/login', {
      method: 'POST', noAuth: true,
      body: JSON.stringify({ email, password, device_token: getDeviceToken(email) }),
    });
  },

  // Finish an email-2FA login. On success the server may return a device_token
  // to remember this browser; stash it so next time skips the code.
  async verify2fa(email, code, rememberDevice = false) {
    const data = await request('/auth/verify-2fa', {
      method: 'POST', noAuth: true,
      body: JSON.stringify({ email, code, remember_device: rememberDevice }),
    });
    if (data && data.device_token) saveDeviceToken(email, data.device_token);
    return data;
  },

  resend2fa(email) {
    return request('/auth/resend-2fa', {
      method: 'POST', noAuth: true,
      body: JSON.stringify({ email }),
    });
  },

  setTwoFactor(enabled) {
    return request('/auth/2fa', { method: 'PUT', body: JSON.stringify({ enabled }) });
  },

  googleLogin(idToken) {
    return request('/auth/google', {
      method: 'POST', noAuth: true,
      body: JSON.stringify({ id_token: idToken }),
    });
  },

  resendVerification(email) {
    return request('/auth/resend-verification', {
      method: 'POST', noAuth: true,
      body: JSON.stringify({ email }),
    });
  },

  forgotPassword(email) {
    return request('/auth/forgot-password', {
      method: 'POST', noAuth: true,
      body: JSON.stringify({ email }),
    });
  },

  resetPassword(token, password) {
    return request('/auth/reset-password', {
      method: 'POST', noAuth: true,
      body: JSON.stringify({ token, password }),
    });
  },

  getMe() {
    return request('/auth/me');
  },

  updateMe(data) {
    return request('/auth/me', { method: 'PUT', body: JSON.stringify(data) });
  },

  setApiKey(apiKey) {
    return request('/auth/api-key', { method: 'PUT', body: JSON.stringify({ api_key: apiKey }) });
  },

  // Multi-key management
  listApiKeys() {
    return request('/auth/api-keys');
  },
  addApiKey(apiKey, label) {
    return request('/auth/api-keys', { method: 'POST', body: JSON.stringify({ api_key: apiKey, label }) });
  },
  deleteApiKey(keyId) {
    return request(`/auth/api-keys/${keyId}`, { method: 'DELETE' });
  },
  activateApiKey(keyId) {
    return request(`/auth/api-keys/${keyId}/activate`, { method: 'PUT' });
  },
  updateApiKey(keyId, patch) {
    return request(`/auth/api-keys/${keyId}`, { method: 'PUT', body: JSON.stringify(patch) });
  },

  // Analysis
  getCategories() {
    return request('/categories');
  },

  analyze(file, category, documentType, extras = {}, signal) {
    const form = new FormData();
    form.append('imageFile', file);
    if (category) form.append('category', category);
    if (documentType) form.append('document_type', documentType);
    if (extras.suspicionReason) form.append('suspicion_reason', extras.suspicionReason);
    if (extras.areaOfConcern) form.append('area_of_concern', extras.areaOfConcern);
    if (extras.imageSource) form.append('image_source', extras.imageSource);
    if (extras.isForgedBelief) form.append('is_forged_belief', extras.isForgedBelief);
    if (extras.shotType) form.append('shot_type', extras.shotType);
    if (extras.lighting) form.append('lighting', extras.lighting);
    if (extras.physicalClues) form.append('physical_clues', extras.physicalClues);
    return request('/analyze', { method: 'POST', body: form, signal });
  },

  getDocumentTypes() {
    return request('/document-types', { noAuth: true });
  },

  preliminary(file) {
    const form = new FormData();
    form.append('imageFile', file);
    return request('/preliminary', { method: 'POST', body: form });
  },

  // History
  getHistory(limit = 50, offset = 0) {
    return request(`/history?limit=${limit}&offset=${offset}`);
  },

  getScanDetail(scanId) {
    return request(`/history/${scanId}`);
  },

  updateScanNotes(scanId, notes) {
    return request(`/history/${encodeURIComponent(scanId)}/notes`, {
      method: 'PUT',
      body: JSON.stringify({ notes }),
    });
  },

  getScanImageUrl(scanId) {
    const token = getToken();
    return `${API_BASE}/history/${encodeURIComponent(scanId)}/image?token=${encodeURIComponent(token || '')}`;
  },

  // Payments
  getPlans() {
    return request('/payments/plans');
  },

  createCheckout(plan, paymentMethod = 'stripe') {
    if (paymentMethod === 'paymongo') {
      return request('/payments/paymongo-checkout', {
        method: 'POST', body: JSON.stringify({ plan, payment_method: 'paymongo' }),
      });
    }
    return request('/payments/create-checkout', {
      method: 'POST', body: JSON.stringify({ plan, payment_method: 'stripe' }),
    });
  },

  getPaymongoPublicKey() {
    return request('/payments/paymongo-public-key', { noAuth: true });
  },

  verifySession(sessionId, provider = 'stripe') {
    const params = new URLSearchParams({ provider });
    if (sessionId) params.set('session_id', sessionId);
    return request(`/payments/verify-session?${params.toString()}`);
  },

  cancelSubscription() {
    return request('/payments/cancel', { method: 'POST' });
  },

  // Rooms
  listRooms() {
    return request('/rooms');
  },
  myRooms() {
    return request('/rooms/mine/list');
  },
  createRoom(name, description = '') {
    return request('/rooms', { method: 'POST', body: JSON.stringify({ name, description }) });
  },
  getRoom(id) {
    return request(`/rooms/${encodeURIComponent(id)}`);
  },
  updateRoom(id, patch) {
    return request(`/rooms/${encodeURIComponent(id)}`, { method: 'PUT', body: JSON.stringify(patch) });
  },
  deleteRoom(id) {
    return request(`/rooms/${encodeURIComponent(id)}`, { method: 'DELETE' });
  },
  regenerateRoomCode(id) {
    return request(`/rooms/${encodeURIComponent(id)}/regenerate-code`, { method: 'POST' });
  },
  removeRoomMember(roomId, userId) {
    return request(`/rooms/${encodeURIComponent(roomId)}/members/${encodeURIComponent(userId)}`, { method: 'DELETE' });
  },
  joinRoom(code) {
    return request('/rooms/join', { method: 'POST', body: JSON.stringify({ code }) });
  },

  // Admin
  adminListUsers({ q = '', plan = '', role = '', limit = 50, offset = 0 } = {}) {
    const params = new URLSearchParams();
    if (q) params.set('q', q);
    if (plan) params.set('plan', plan);
    if (role) params.set('role', role);
    params.set('limit', limit);
    params.set('offset', offset);
    return request(`/admin/users?${params.toString()}`);
  },

  // Roles
  listRoles() {
    return request('/roles');
  },
  createRole(payload) {
    return request('/roles', { method: 'POST', body: JSON.stringify(payload) });
  },
  updateRole(roleId, patch) {
    return request(`/roles/${roleId}`, { method: 'PUT', body: JSON.stringify(patch) });
  },
  deleteRole(roleId) {
    return request(`/roles/${roleId}`, { method: 'DELETE' });
  },
  assignUserRole(userId, role) {
    return request(`/roles/users/${userId}/role`, { method: 'PUT', body: JSON.stringify({ role }) });
  },

  adminGetUser(userId) {
    return request(`/admin/users/${userId}`);
  },

  adminUpdateUser(userId, patch) {
    return request(`/admin/users/${userId}`, { method: 'PUT', body: JSON.stringify(patch) });
  },

  adminDeleteUser(userId) {
    return request(`/admin/users/${userId}`, { method: 'DELETE' });
  },

  adminStats() {
    return request('/admin/stats');
  },

  // Admin actions (ban/unban users)
  adminBanUser(userId) {
    return request(`/admin/users/${userId}/ban`, { method: 'POST' });
  },

  adminUnbanUser(userId) {
    return request(`/admin/users/${userId}/unban`, { method: 'POST' });
  },

  adminPromoteAdmin(userId) {
    return request(`/admin/users/${userId}/promote-admin`, { method: 'POST' });
  },

  adminDemoteAdmin(userId) {
    return request(`/admin/users/${userId}/demote-admin`, { method: 'POST' });
  },

  // Audit logs (admin + super admin)
  adminViewLogs(opts = {}) {
    const { limit = 200, offset = 0, kind = null, action = null, actor = null,
            role = null, verdict = null, start_date = null, end_date = null, q = null } = opts;
    const params = new URLSearchParams();
    params.set('limit', limit);
    params.set('offset', offset);
    for (const [k, v] of Object.entries({ kind, action, actor, role, verdict, start_date, end_date, q })) {
      if (v) params.set(k, v);
    }
    return request(`/admin/super/logs?${params.toString()}`);
  },

  adminScanImageUrl(scanId) {
    const token = getToken();
    return `${API_BASE}/admin/scans/${encodeURIComponent(scanId)}/image?token=${encodeURIComponent(token || '')}`;
  },

  adminGeminiStatus() {
    return request('/admin/gemini-status');
  },

  getAbout() {
    return request('/about', { noAuth: true });
  },

  getPromptAnalysis() {
    return request('/prompt-analysis', { noAuth: true });
  },

  getSystemAccuracy() {
    return request('/prompt-analysis/accuracy', { noAuth: true });
  },

  // Health
  health() {
    return request('/health', { noAuth: true });
  },

  // Token helpers
  saveTokens,
  clearTokens,
  getToken,
};
