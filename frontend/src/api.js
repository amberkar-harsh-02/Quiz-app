// In dev the API runs separately on port 8000. In production the web server forwards
// <site>/quiz-app/api/ to the backend, so the API lives next to the app.
export const API_URL = import.meta.env.VITE_API_URL
  || (import.meta.env.PROD ? `${window.location.origin}${import.meta.env.BASE_URL}api` : 'http://127.0.0.1:8000');
export const WS_URL = API_URL.replace(/^http/, 'ws');
// Server paths such as a question's "/images/<id>" -> full URL for <img src>
export const assetUrl = (path) => (path ? `${API_URL}${path}` : null);

const TOKEN_KEY = 'kahoot_token';

export const getToken = () => localStorage.getItem(TOKEN_KEY);
export const setToken = (token) => localStorage.setItem(TOKEN_KEY, token);
export const clearToken = () => localStorage.removeItem(TOKEN_KEY);

// Downloads a file that needs sign-in (e.g. an analytics PDF) and saves it with the server's file name
export async function apiDownload(path, fallbackName) {
  const res = await fetch(`${API_URL}${path}`, { headers: { Authorization: `Bearer ${getToken()}` } });
  if (!res.ok) {
    const data = await res.json().catch(() => null);
    throw new Error(typeof data?.detail === 'string' ? data.detail : `Download failed (${res.status})`);
  }
  const match = /filename="([^"]+)"/.exec(res.headers.get('Content-Disposition') || '');
  const url = URL.createObjectURL(await res.blob());
  const link = document.createElement('a');
  link.href = url;
  link.download = match?.[1] || fallbackName;
  link.click();
  URL.revokeObjectURL(url);
}

// Decoded JWT payload ({ sub, is_professor, exp }), or null if missing or expired
export function readToken() {
  const token = getToken();
  if (!token) return null;
  try {
    const payload = JSON.parse(atob(token.split('.')[1].replace(/-/g, '+').replace(/_/g, '/')));
    if (payload.exp && payload.exp * 1000 < Date.now()) throw new Error('expired');
    return payload;
  } catch {
    clearToken();
    return null;
  }
}

// fetch() with the bearer token attached. Throws an Error carrying the server's `detail` on
// non-2xx responses. An expired session sends the user back to the sign-in page.
export async function apiFetch(path, options = {}) {
  const token = getToken();
  const headers = { ...options.headers };
  if (token) headers.Authorization = `Bearer ${token}`;
  if (options.body && !(options.body instanceof FormData) && !(options.body instanceof URLSearchParams)) {
    headers['Content-Type'] = 'application/json';
  }

  const res = await fetch(`${API_URL}${path}`, { ...options, headers });
  const data = await res.json().catch(() => null);

  if (res.status === 401 && token) {
    clearToken();
    window.location.assign(import.meta.env.BASE_URL);
  }
  if (!res.ok) {
    const detail = typeof data?.detail === 'string'
      ? data.detail
      : data?.detail?.[0]?.msg ?? `Request failed (${res.status})`;
    throw new Error(detail);
  }
  return data;
}
