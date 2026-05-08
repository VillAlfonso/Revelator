/**
 * AuthContext — bridges Firebase Auth + the Firestore user-profile doc.
 *
 * Exposed:
 *   user      — Firebase auth user (or null)
 *   profile   — Firestore `users/{uid}` doc (plan, scans_this_month, …)
 *   loading   — true while we're resolving the initial auth state
 *   getIdToken — async helper for API calls
 *   logout
 */

import React, { createContext, useContext, useEffect, useState } from 'react';
import { onAuthStateChanged, signOut } from 'firebase/auth';
import { doc, onSnapshot, setDoc, serverTimestamp } from 'firebase/firestore';

import { auth, db } from '../firebase';

const AuthContext = createContext(null);
export function useAuth() { return useContext(AuthContext); }

async function ensureProfile(user) {
  const ref = doc(db, 'users', user.uid);
  await setDoc(
    ref,
    {
      email: user.email || '',
      full_name: user.displayName || '',
      photo_url: user.photoURL || '',
      // initial fields only set on first write thanks to merge:true
      plan: 'free',
      scans_this_month: 0,
      scan_reset_date: serverTimestamp(),
      created_at: serverTimestamp(),
      updated_at: serverTimestamp(),
    },
    { merge: true },
  );
}

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null);
  const [profile, setProfile] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let unsubProfile = null;

    const unsubAuth = onAuthStateChanged(auth, async (u) => {
      if (unsubProfile) { unsubProfile(); unsubProfile = null; }
      setUser(u || null);
      if (!u) {
        setProfile(null);
        setLoading(false);
        return;
      }
      await ensureProfile(u);
      unsubProfile = onSnapshot(doc(db, 'users', u.uid), (snap) => {
        setProfile(snap.exists() ? { uid: u.uid, ...snap.data() } : null);
        setLoading(false);
      }, (err) => {
        console.error('Profile listener error:', err);
        setLoading(false);
      });
    });

    return () => {
      unsubAuth();
      if (unsubProfile) unsubProfile();
    };
  }, []);

  async function getIdToken() {
    if (!auth.currentUser) return null;
    return auth.currentUser.getIdToken();
  }

  async function logout() {
    await signOut(auth);
  }

  return (
    <AuthContext.Provider value={{ user, profile, loading, getIdToken, logout }}>
      {children}
    </AuthContext.Provider>
  );
}
