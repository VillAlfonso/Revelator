/**
 * Direct Firestore reads/writes for things that don't need the backend.
 * Scan history, profile updates, etc.
 */

import {
  collection, doc, getDoc, getDocs, limit, orderBy, query,
  updateDoc, serverTimestamp, where,
} from 'firebase/firestore';

import { db } from '../firebase';

export async function getProfile(uid) {
  const snap = await getDoc(doc(db, 'users', uid));
  return snap.exists() ? { uid, ...snap.data() } : null;
}

export async function updateProfile(uid, patch) {
  await updateDoc(doc(db, 'users', uid), { ...patch, updated_at: serverTimestamp() });
}

export async function getHistory(uid, n = 50) {
  const q = query(
    collection(db, 'scans'),
    where('user_id', '==', uid),
    orderBy('created_at', 'desc'),
    limit(n),
  );
  const snap = await getDocs(q);
  return snap.docs.map(d => ({ id: d.id, ...d.data() }));
}

export async function getScanDetail(scanId, uid) {
  const snap = await getDoc(doc(db, 'scans', scanId));
  if (!snap.exists()) return null;
  const data = snap.data();
  if (data.user_id !== uid) return null;
  return { id: snap.id, ...data };
}
