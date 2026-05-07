/**
 * Backend API client. Only used for endpoints that need server-side
 * computation (AI inference, payment session creation). Auth and DB
 * reads happen directly via the Firebase SDK in lib/firestore.js.
 */

import { auth } from '../firebase';

const API_BASE = (import.meta.env.VITE_API_URL || '') + '/api';

async function authHeader() {
  const u = auth.currentUser;
  if (!u) return {};
  const token = await u.getIdToken();
  return { Authorization: `Bearer ${token}` };
}

async function request(path, { method = 'GET', body, noAuth = false } = {}) {
  const headers = {};
  if (!noAuth) Object.assign(headers, await authHeader());
  if (!(body instanceof FormData)) headers['Content-Type'] = 'application/json';
  const res = await fetch(`${API_BASE}${path}`, {
    method, headers,
    body: body instanceof FormData ? body : (body ? JSON.stringify(body) : undefined),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail || 'Request failed');
  }
  return res.json();
}

export const api = {
  // ── Analysis ──
  analyze(file, { category, documentType, modelTier, ...extras } = {}) {
    const form = new FormData();
    form.append('imageFile', file);
    if (category) form.append('category', category);
    if (documentType) form.append('document_type', documentType);
    if (modelTier) form.append('model_tier', modelTier);
    if (extras.suspicionReason) form.append('suspicion_reason', extras.suspicionReason);
    if (extras.areaOfConcern) form.append('area_of_concern', extras.areaOfConcern);
    if (extras.imageSource) form.append('image_source', extras.imageSource);
    if (extras.isForgedBelief) form.append('is_forged_belief', extras.isForgedBelief);
    if (extras.shotType) form.append('shot_type', extras.shotType);
    if (extras.lighting) form.append('lighting', extras.lighting);
    if (extras.physicalClues) form.append('physical_clues', extras.physicalClues);
    return request('/analyze', { method: 'POST', body: form });
  },

  getDocumentTypes() { return request('/document-types', { noAuth: true }); },
  getModelTiers() { return request('/tiers'); },
  getAbout() { return request('/about', { noAuth: true }); },

  // ── Payments ──
  getPlans() { return request('/payments/plans', { noAuth: true }); },
  createCheckout(plan, paymentMethod = 'stripe') {
    return request('/payments/create-checkout', {
      method: 'POST', body: { plan, payment_method: paymentMethod },
    });
  },
  getPaymongoPublicKey() {
    return request('/payments/paymongo-public-key', { noAuth: true });
  },

  health() { return request('/health', { noAuth: true }); },
};
