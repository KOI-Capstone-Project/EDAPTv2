// Profile photo helpers. Photos are stored server-side (POST/GET/DELETE
// /api/users/.../photo — see the User model's photo/photo_content_type
// columns) rather than in the browser's localStorage, where this used to
// live: a raw, un-resized data: URL from a real phone photo routinely
// exceeded localStorage's ~5-10MB per-origin quota (confirmed live —
// "QuotaExceededError: Setting the value of 'user_photo_admin' exceeded
// the quota") and was never visible to anyone but that one browser anyway.
import { useEffect, useState } from 'react';
import api from '../services/api';

const MAX_DIMENSION = 256;
const JPEG_QUALITY   = 0.85;

// Downscales/re-encodes to a small JPEG before upload — keeps the payload
// (and therefore the DB row) small regardless of the source photo's size,
// and sidesteps the backend's own upload size limit entirely rather than
// just moving the same quota problem server-side.
export function resizeImageToBlob(file, maxDim = MAX_DIMENSION, quality = JPEG_QUALITY) {
  return new Promise((resolve, reject) => {
    const img = new Image();
    const objectUrl = URL.createObjectURL(file);
    img.onload = () => {
      const scale = Math.min(1, maxDim / Math.max(img.width, img.height));
      const w = Math.round(img.width * scale);
      const h = Math.round(img.height * scale);
      const canvas = document.createElement('canvas');
      canvas.width = w;
      canvas.height = h;
      canvas.getContext('2d').drawImage(img, 0, 0, w, h);
      canvas.toBlob(
        blob => { URL.revokeObjectURL(objectUrl); blob ? resolve(blob) : reject(new Error('Could not process image.')); },
        'image/jpeg', quality,
      );
    };
    img.onerror = () => { URL.revokeObjectURL(objectUrl); reject(new Error('Could not read image file.')); };
    img.src = objectUrl;
  });
}

// Fetches a user's photo as an object URL (the API needs a Bearer token
// via axios, so a plain <img src="/api/users/x/photo"> can't authenticate —
// this fetches it as a blob and hands back a local object: URL instead).
// Returns null (not an error) when the user simply has no photo set.
export function usePhotoUrl(userUid) {
  const [url, setUrl] = useState(null);

  useEffect(() => {
    if (!userUid) { setUrl(null); return; }
    let cancelled = false;
    let objectUrl = null;
    api.get(`/api/users/${encodeURIComponent(userUid)}/photo`, { responseType: 'blob' })
      .then(res => {
        if (cancelled) return;
        objectUrl = URL.createObjectURL(res.data);
        setUrl(objectUrl);
      })
      .catch(() => { if (!cancelled) setUrl(null); });
    return () => {
      cancelled = true;
      if (objectUrl) URL.revokeObjectURL(objectUrl);
    };
  }, [userUid]);

  return url;
}
