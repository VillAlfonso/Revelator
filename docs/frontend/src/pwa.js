/*
 * PWA glue: service-worker registration and the "Install app" prompt.
 *
 * Two guards matter here:
 *  - Only in a production build. A service worker in front of the Vite dev
 *    server serves stale modules and makes HMR look broken.
 *  - Only on the web. Inside the Capacitor Android shell the page is served
 *    from a local scheme, where a service worker is pointless and can shadow
 *    the app's own assets.
 */

import { Capacitor } from '@capacitor/core';

const isWeb = !Capacitor.isNativePlatform();

// Chrome fires beforeinstallprompt before React has mounted, so the listener is
// attached at module load and the event is parked here for the UI to pick up.
let deferredPrompt = null;
const listeners = new Set();

function emit() {
  listeners.forEach(fn => {
    try { fn(!!deferredPrompt); } catch { /* a bad subscriber must not break the rest */ }
  });
}

if (isWeb && typeof window !== 'undefined') {
  window.addEventListener('beforeinstallprompt', e => {
    // Suppress Chrome's own mini-infobar so the in-app button is the one path.
    e.preventDefault();
    deferredPrompt = e;
    emit();
  });

  window.addEventListener('appinstalled', () => {
    deferredPrompt = null;
    emit();
  });
}

/** True once the app is running from the home screen rather than a browser tab. */
export function isStandalone() {
  if (typeof window === 'undefined') return false;
  return window.matchMedia('(display-mode: standalone)').matches
      || window.navigator.standalone === true;
}

/** iOS has no install prompt API: Safari requires Share -> Add to Home Screen. */
export function isIos() {
  if (typeof navigator === 'undefined') return false;
  return /iphone|ipad|ipod/i.test(navigator.userAgent)
      || (navigator.platform === 'MacIntel' && navigator.maxTouchPoints > 1);
}

export function canInstall() {
  return !!deferredPrompt;
}

/** Subscribe to install-availability changes. Returns an unsubscribe function. */
export function onInstallAvailable(fn) {
  listeners.add(fn);
  fn(!!deferredPrompt);
  return () => listeners.delete(fn);
}

/** Show the native install dialog. Resolves to 'accepted' | 'dismissed' | 'unavailable'. */
export async function promptInstall() {
  if (!deferredPrompt) return 'unavailable';
  const evt = deferredPrompt;
  // The event is single-use: clear it up front so a double tap cannot reuse it.
  deferredPrompt = null;
  emit();
  evt.prompt();
  const { outcome } = await evt.userChoice;
  return outcome;
}

export function registerServiceWorker() {
  if (!isWeb) return;
  if (!import.meta.env.PROD) return;
  if (!('serviceWorker' in navigator)) return;

  // Captured before registering: on a first-ever install there is no controller
  // and reloading would be pointless churn. Only an UPDATE should refresh.
  const hadController = !!navigator.serviceWorker.controller;
  let reloading = false;

  navigator.serviceWorker.addEventListener('controllerchange', () => {
    if (!hadController || reloading) return;
    reloading = true;
    window.location.reload();
  });

  window.addEventListener('load', () => {
    navigator.serviceWorker.register('/sw.js').catch(() => {
      // Registration failing (private mode, unsupported browser, http origin)
      // must never take the app down: it just means no install/offline support.
    });
  });
}
