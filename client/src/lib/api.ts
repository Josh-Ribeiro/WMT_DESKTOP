const configuredApiBaseUrl = import.meta.env.VITE_API_BASE_URL?.trim();

// During Vite development, use the local proxy so the browser does not need
// to bypass the backend's production CORS policy. Packaged builds still use
// the explicit production URL from VITE_API_BASE_URL.
export const API_BASE_URL = (
  configuredApiBaseUrl || (import.meta.env.DEV ? "" : "http://127.0.0.1:8000")
).replace(/\/$/, "");

const inflightGetRequests = new Map<string, Promise<unknown>>();
let csrfToken = "";
let csrfRefresh: Promise<boolean> | null = null;

export class UnauthorizedError extends Error {
  constructor(message = "Sessão expirada. Faça login novamente.") {
    super(message);
    this.name = "UnauthorizedError";
  }
}

export function setCsrfToken(value?: string) {
  csrfToken = value || "";
}

export function clearStoredSession() {
  csrfToken = "";
  // Remove credentials/profile left by versions that used localStorage.
  localStorage.removeItem("wmt_user");
  localStorage.removeItem("wmt_token");
  window.dispatchEvent(new Event("wmt:unauthorized"));
}

function isUnsafeMethod(method: string) {
  return !["GET", "HEAD", "OPTIONS"].includes(method);
}

function fetchWithCredentials(
  endpoint: string,
  options: RequestInit,
  method: string,
  headers: Headers
) {
  return fetch(`${API_BASE_URL}${endpoint}`, {
    ...options,
    method,
    headers,
    credentials: "include",
  });
}

async function responseHasInvalidCsrf(response: Response) {
  if (response.status !== 403) return false;
  try {
    const payload = await response.clone().json();
    return payload.detail === "Invalid CSRF token";
  } catch {
    return false;
  }
}

async function refreshCsrfToken() {
  if (!csrfRefresh) {
    csrfRefresh = (async () => {
      const response = await fetchWithCredentials(
        "/api/auth/me",
        {},
        "GET",
        new Headers()
      );
      if (!response.ok) return false;
      const payload = (await response.json()) as { csrf_token?: string };
      setCsrfToken(payload.csrf_token);
      return Boolean(payload.csrf_token);
    })().finally(() => {
      csrfRefresh = null;
    });
  }
  return csrfRefresh;
}

export async function apiFetch(
  endpoint: string,
  options: RequestInit = {}
): Promise<Response> {
  const method = (options.method || "GET").toUpperCase();
  const headers = new Headers(options.headers);

  if (!headers.has("Content-Type") && options.body) {
    headers.set("Content-Type", "application/json");
  }
  if (isUnsafeMethod(method) && csrfToken) {
    headers.set("X-CSRF-Token", csrfToken);
  }

  const response = await fetchWithCredentials(
    endpoint,
    options,
    method,
    headers
  );
  if (
    !isUnsafeMethod(method) ||
    endpoint === "/api/auth/login" ||
    endpoint === "/api/auth/sso" ||
    !(await responseHasInvalidCsrf(response)) ||
    !(await refreshCsrfToken())
  ) {
    return response;
  }

  const retryHeaders = new Headers(options.headers);
  if (!retryHeaders.has("Content-Type") && options.body) {
    retryHeaders.set("Content-Type", "application/json");
  }
  retryHeaders.set("X-CSRF-Token", csrfToken);
  return fetchWithCredentials(endpoint, options, method, retryHeaders);
}

async function performApiRequest<T>(
  endpoint: string,
  options: RequestInit
): Promise<T> {
  const response = await apiFetch(endpoint, options);

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
    const requestId = response.headers.get("X-Request-ID");
    throw new Error(requestId ? `${message} (request ${requestId})` : message);
  }

  if (response.status === 204) {
    return undefined as T;
  }

  return response.json() as Promise<T>;
}

export async function apiRequest<T>(
  endpoint: string,
  options: RequestInit = {}
): Promise<T> {
  const method = (options.method || "GET").toUpperCase();
  if (method !== "GET" || options.body) {
    return performApiRequest<T>(endpoint, options);
  }

  const pending = inflightGetRequests.get(endpoint);
  if (pending) {
    return pending as Promise<T>;
  }

  const request = performApiRequest<T>(endpoint, options);
  inflightGetRequests.set(endpoint, request);
  try {
    return await request;
  } finally {
    if (inflightGetRequests.get(endpoint) === request) {
      inflightGetRequests.delete(endpoint);
    }
  }
}
