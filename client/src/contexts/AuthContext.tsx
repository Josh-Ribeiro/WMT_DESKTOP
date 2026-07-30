import {
  createContext,
  type ReactNode,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
} from "react";
import {
  apiFetch,
  apiRequest,
  clearStoredSession,
  setCsrfToken,
} from "@/lib/api";

export interface User {
  username: string;
  role: string;
  permissions: string[];
  display_name?: string;
  email?: string;
  domain?: string;
  groups?: string[];
  auth_source?: string;
}

export interface AuthContextValue {
  user: User | null;
  isAuthenticated: boolean;
  loading: boolean;
  login: (username: string, password: string) => Promise<void>;
  ssoLogin: () => Promise<void>;
  logout: () => Promise<void>;
}

interface AuthPayload extends Partial<User> {
  user?: string;
  csrf_token?: string;
}

const AuthContext = createContext<AuthContextValue | null>(null);

function userFromPayload(data: AuthPayload): User {
  return {
    username: data.user || data.username || "",
    role: data.role || "viewer",
    permissions: data.permissions || [],
    display_name: data.display_name,
    email: data.email,
    domain: data.domain,
    groups: data.groups || [],
    auth_source: data.auth_source || "local",
  };
}

async function authRequest(
  endpoint: string,
  options: RequestInit
): Promise<AuthPayload> {
  const response = await apiFetch(endpoint, options);
  if (!response.ok) {
    let message = "Authentication failed";
    try {
      const payload = await response.json();
      message = payload.detail || message;
    } catch {
      /* keep fallback message */
    }
    const requestId = response.headers.get("X-Request-ID");
    throw new Error(requestId ? `${message} (request ${requestId})` : message);
  }
  return response.json() as Promise<AuthPayload>;
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(true);

  const storeAuth = useCallback((data: AuthPayload) => {
    setCsrfToken(data.csrf_token);
    setUser(userFromPayload(data));
  }, []);

  const ssoLogin = useCallback(async () => {
    try {
      setLoading(true);
      const data = await authRequest("/api/auth/sso", { method: "POST" });
      storeAuth(data);
    } finally {
      setLoading(false);
    }
  }, [storeAuth]);

  useEffect(() => {
    const checkAuth = async () => {
      try {
        const current = await apiRequest<AuthPayload>("/api/auth/me");
        storeAuth(current);
      } catch {
        setCsrfToken();
        setUser(null);
      } finally {
        setLoading(false);
      }
    };
    void checkAuth();
  }, [storeAuth]);

  useEffect(() => {
    const handleUnauthorized = () => {
      setCsrfToken();
      setUser(null);
      setLoading(false);
    };
    window.addEventListener("wmt:unauthorized", handleUnauthorized);
    return () =>
      window.removeEventListener("wmt:unauthorized", handleUnauthorized);
  }, []);

  const login = useCallback(
    async (username: string, password: string) => {
      try {
        setLoading(true);
        const data = await authRequest("/api/auth/login", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ username, password }),
        });
        storeAuth(data);
      } finally {
        setLoading(false);
      }
    },
    [storeAuth]
  );

  const logout = useCallback(async () => {
    try {
      await apiRequest("/api/auth/logout", { method: "POST" });
    } finally {
      setCsrfToken();
      setUser(null);
      clearStoredSession();
    }
  }, []);

  const value = useMemo<AuthContextValue>(
    () => ({
      user,
      isAuthenticated: !!user,
      loading,
      login,
      ssoLogin,
      logout,
    }),
    [loading, login, logout, ssoLogin, user]
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthContextValue {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error("useAuth must be used inside AuthProvider");
  }
  return context;
}
