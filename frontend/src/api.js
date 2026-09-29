export const API_URL = import.meta.env.VITE_API_URL || 'http://127.0.0.1:8000';
export const WS_URL = API_URL.replace(/^http/, 'ws');

const TOKEN_KEY = 'kahoot_token';

export const getToken = () => localStorage.getItem(TOKEN_KEY);
export const setToken = (token) => localStorage.setItem(TOKEN_KEY, token);
export const clearToken = () => localStorage.removeItem(TOKEN_KEY);

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
    window.location.assign('/');
  }
  if (!res.ok) {
    const detail = typeof data?.detail === 'string' ? data.detail : `Request failed (${res.status})`;
    throw new Error(detail);
  }
  return data;
}
