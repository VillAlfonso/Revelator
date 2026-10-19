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

function browserIdentity() {
  let id = localStorage.getItem('fg_browser_id');
  if (!id) {
    id = crypto.randomUUID();
    localStorage.setItem('fg_browser_id', id);
  }
  return id;
}

async function request(path, options = {}) {
  const token = getToken();
  const headers = { ...options.headers, 'X-Browser-ID': browserIdentity() };

  if (token && !options.noAuth) {
    headers['Authorization'] = `Bearer ${token}`;
  }

  // Don't set Content-Type for FormData (browser sets it with boundary)
  if (!(options.body instanceof FormData)) {
    headers['Content-Type'] = 'application/json';
  }

  let res = await fetch(`${API_BASE}${path}`, { ...options, headers });

  // If 401, try refreshing the token once
  if (res.status === 401 && !options.noAuth && !options._retried) {
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
    const responseText = await res.text().catch(() => '');
    let detail = '';
    try {
      const parsed = JSON.parse(responseText);
      detail = parsed.detail || parsed.message || '';
    } catch {
      detail = responseText.replace(/<[^>]+>/g, ' ').replace(/\s+/g, ' ').trim();
    }
    throw new Error(detail || `Request failed (HTTP ${res.status})`);
  }

  return res.json();
}

async function tryRefresh() {
  const refresh = getRefreshToken();
  if (!refresh) return false;
  try {
    const res = await fetch(`${API_BASE}/auth/refresh`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'X-Browser-ID': browserIdentity() },
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

async function interceptFetch(path, options = {}) {
  const makeRequest = () => fetch(`${API_BASE}${path}`, {
    ...options,
    headers: {
      ...options.headers,
      Authorization: `Bearer ${getToken() || ''}`,
    },
  });
  let res = await makeRequest();
  if (res.status === 401) {
    if (await tryRefresh()) {
      res = await makeRequest();
    } else {
      clearTokens();
      window.dispatchEvent(new CustomEvent('fg:session-expired'));
      throw new Error('Session expired');
    }
  }
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error(body.detail || `Request failed (HTTP ${res.status})`);
  }
  return res;
}

async function authenticatedDownload(path, filename) {
  const makeRequest = () => fetch(`${API_BASE}${path}`, {
    headers: { Authorization: `Bearer ${getToken() || ''}` },
  });
  let res = await makeRequest();
  if (res.status === 401) {
    if (await tryRefresh()) {
      res = await makeRequest();
    } else {
      clearTokens();
      window.dispatchEvent(new CustomEvent('fg:session-expired'));
      throw new Error('Session expired');
    }
  }
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error(body.detail || `Request failed (HTTP ${res.status})`);
  }
  const url = URL.createObjectURL(await res.blob());
  const link = document.createElement('a');
  link.href = url;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  link.remove();
  window.setTimeout(() => URL.revokeObjectURL(url), 1000);
}

// ── Public API ──────────────────────────────────────
export const api = {
  setSessionLocation(location) {
    return request('/auth/me/session-location', { method: 'PUT', body: JSON.stringify(location) });
  },
  // Auth
  register(email, username, password, full_name) {
    return request('/auth/register', {
      method: 'POST', noAuth: true,
      body: JSON.stringify({ email, username, password, full_name }),
    });
  },

  verifyRegistration(email, code) {
    return request('/auth/verify-registration', {
      method: 'POST', noAuth: true, body: JSON.stringify({ email, code }),
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
  verifyAuthenticator(challenge_token, code) {
    return request('/auth/verify-2fa', { method: 'POST', noAuth: true, body: JSON.stringify({ challenge_token, code }) });
  },
  recoverAccount(email, recovery_code, password) {
    return request('/auth/forgot-password', { method: 'POST', noAuth: true, body: JSON.stringify({ email, recovery_code, password }) });
  },
  adminArchive() { return request('/admin/archive'); },
  adminResetAuthenticator(id, reason) { return request(`/admin/users/${encodeURIComponent(id)}/reset-authenticator`, { method: 'POST', body: JSON.stringify({ reason }) }); },

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

  async changePassword(currentPassword, newPassword) {
    const data = await request('/auth/password', {
      method: 'PUT',
      body: JSON.stringify({ current_password: currentPassword, new_password: newPassword }),
    });
    saveTokens(data.access_token, data.refresh_token);
    return data;
  },

  getMe() {
    return request('/auth/me');
  },

  logout() {
    return request('/auth/logout', { method: 'POST' });
  },

  exportMyData() {
    return authenticatedDownload('/auth/me/export', 'revelator-account-export.zip');
  },

  deleteMyAccount(email, password, confirmation) {
    return request('/auth/me', {
      method: 'DELETE',
      body: JSON.stringify({ email, password, confirmation }),
    });
  },

  getMySessions() {
    return request('/auth/me/sessions');
  },

  revokeMySession(sessionId) {
    return request(`/auth/me/sessions/${encodeURIComponent(sessionId)}`, { method: 'DELETE' });
  },

  revokeOtherSessions() {
    return request('/auth/me/sessions', { method: 'DELETE' });
  },

  getTrustedDevices() {
    return request('/auth/me/trusted-devices');
  },

  revokeTrustedDevice(deviceId) {
    return request(`/auth/me/trusted-devices/${encodeURIComponent(deviceId)}`, { method: 'DELETE' });
  },

  clearLocalSession() {
    clearTokens();
    window.dispatchEvent(new CustomEvent('fg:session-expired'));
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

  deleteScan(scanId) {
    return request(`/history/${encodeURIComponent(scanId)}`, { method: 'DELETE' });
  },

  reportScanFeedback(scanId, message) {
    return request(`/history/${encodeURIComponent(scanId)}/feedback`, {
      method: 'POST',
      body: JSON.stringify({ message }),
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

  adminGetUser(userId) {
    return request(`/admin/users/${userId}`);
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
          role = null, verdict = null, category = null, start_date = null, end_date = null, q = null } = opts;
    const params = new URLSearchParams();
    params.set('limit', limit);
    params.set('offset', offset);
    for (const [k, v] of Object.entries({ kind, action, actor, role, verdict, category, start_date, end_date, q })) {
      if (v) params.set(k, v);
    }
    return request(`/admin/super/logs?${params.toString()}`);
  },

  adminOperations(limit = 100, offset = 0) {
    return request(`/admin/operations?limit=${limit}&offset=${offset}`);
  },

  adminScanImageUrl(scanId) {
    const token = getToken();
    return `${API_BASE}/admin/scans/${encodeURIComponent(scanId)}/image?token=${encodeURIComponent(token || '')}`;
  },

  adminGeminiStatus() {
    return request('/admin/gemini-status');
  },

  async adminInterceptEvents(onEvent, signal) {
    const res = await interceptFetch('/intercept/events', { signal });
    if (!res.body) throw new Error('Live intercept stream is not available in this browser');
    const reader = res.body.getReader();
    const decoder = new TextDecoder();
    let buffer = '';

    while (true) {
      const { value, done } = await reader.read();
      if (done) return;
      buffer += decoder.decode(value, { stream: true });
      let boundary;
      while ((boundary = buffer.indexOf('\n\n')) >= 0) {
        const frame = buffer.slice(0, boundary);
        buffer = buffer.slice(boundary + 2);
        let event = 'message';
        let data = '';
        for (const line of frame.split(/\r?\n/)) {
          if (line.startsWith('event:')) event = line.slice(6).trim();
          if (line.startsWith('data:')) data += line.slice(5).trim();
        }
        if (data) onEvent(event, JSON.parse(data));
      }
    }
  },

  async adminInterceptImage(scanId) {
    const res = await interceptFetch(`/intercept/scans/${encodeURIComponent(scanId)}/image`);
    return URL.createObjectURL(await res.blob());
  },

  adminInterceptDecision(scanId, category, provider = 'gemini') {
    return request(`/intercept/scans/${encodeURIComponent(scanId)}/decision`, {
      method: 'POST',
      body: JSON.stringify({ category, provider }),
    });
  },

  adminInterceptProviderSettings(openaiAllScans) {
    return request('/intercept/provider-settings', {
      method: 'PUT',
      body: JSON.stringify({ openai_all_scans: openaiAllScans }),
    });
  },

  adminInterceptSkip(scanId) {
    return request(`/intercept/scans/${encodeURIComponent(scanId)}/skip`, {
      method: 'POST',
    });
  },


  getAbout() {
    return request('/about', { noAuth: true });
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
