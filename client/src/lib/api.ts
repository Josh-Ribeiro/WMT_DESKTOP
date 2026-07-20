export const API_BASE_URL = (import.meta.env.VITE_API_BASE_URL || 'http://127.0.0.1:8000').replace(/\/$/, '');
const inflightGetRequests = new Map<string, Promise<unknown>>();

export class UnauthorizedError extends Error {
  constructor(message = 'Sessão expirada. Faça login novamente.') {
    super(message);
    this.name = 'UnauthorizedError';
  }
}

export function getStoredToken() {
  return localStorage.getItem('wmt_token');
}

export function clearStoredSession() {
  localStorage.removeItem('wmt_user');
  localStorage.removeItem('wmt_token');
  window.dispatchEvent(new Event('wmt:unauthorized'));
}

async function performApiRequest<T>(endpoint: string, options: RequestInit): Promise<T> {
  const token = getStoredToken();
  const headers = new Headers(options.headers);

  if (!headers.has('Content-Type') && options.body) {
    headers.set('Content-Type', 'application/json');
  }
  if (token) {
    headers.set('Authorization', `Bearer ${token}`);
  }

  const response = await fetch(`${API_BASE_URL}${endpoint}`, {
    ...options,
    headers,
    credentials: 'include',
  });

  if (!response.ok) {
    if (response.status === 401) {
      clearStoredSession();
      throw new UnauthorizedError();
    }

    let message = `API error: ${response.status}`;
    try {
      const payload = await response.json();
      message = payload.detail || payload.message || message;
    } catch {
      /* keep fallback message */
    }
    throw new Error(message);
  }

  if (response.status === 204) {
    return undefined as T;
  }

  return response.json() as Promise<T>;
}

export async function apiRequest<T>(endpoint: string, options: RequestInit = {}): Promise<T> {
  const method = (options.method || 'GET').toUpperCase();
  if (method !== 'GET' || options.body) {
    return performApiRequest<T>(endpoint, options);
  }

  const requestKey = `${getStoredToken() || ''}:${endpoint}`;
  const pending = inflightGetRequests.get(requestKey);
  if (pending) {
    return pending as Promise<T>;
  }

  const request = performApiRequest<T>(endpoint, options);
  inflightGetRequests.set(requestKey, request);
  try {
    return await request;
  } finally {
    if (inflightGetRequests.get(requestKey) === request) {
      inflightGetRequests.delete(requestKey);
    }
  }
}
