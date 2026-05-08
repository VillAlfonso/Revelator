/**
 * Firebase Storage helpers — fetch download URLs for scan images.
 */

import { getDownloadURL, ref } from 'firebase/storage';

import { storage } from '../firebase';

export async function getScanImageUrl(imagePath) {
  if (!imagePath) return null;
  try {
    return await getDownloadURL(ref(storage, imagePath));
  } catch (err) {
    console.warn('Could not load scan image:', err);
    return null;
  }
}
