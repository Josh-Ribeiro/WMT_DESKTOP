import { useState, useCallback, useEffect } from 'react';
import { API_BASE_URL, apiRequest, clearStoredSession } from '@/lib/api';

interface User {
  username: string;
  role: string;
  permissions: string[];
  display_name?: string;
  email?: string;
  domain?: string;
  groups?: string[];
  auth_source?: string;
}

interface UseAuthResult {
  user: User | null;
  isAuthenticated: boolean;
  loading: boolean;
  login: (username: string, password: string) => Promise<void>;
  ssoLogin: () => Promise<void>;
  logout: () => Promise<void>;
}

function readStoredUser(): User | null {
  try {
    const stored = localStorage.getItem('wmt_user');
    return stored ? (JSON.parse(stored) as User) : null;
  } catch {
    return null;
  }
}

export function useAuth(): UseAuthResult {
  const [user, setUser] = useState<User | null>(() => readStoredUser());
  const [loading, setLoading] = useState(true);

  const storeAuth = useCallback((data: any) => {
    const userData = {
      username: data.user || data.username,
      role: data.role || 'viewer',
      permissions: data.permissions || [],
      display_name: data.display_name,
      email: data.email,
      domain: data.domain,
      groups: data.groups || [],
      auth_source: data.auth_source || 'local',
    };

    setUser(userData);
    localStorage.setItem('wmt_user', JSON.stringify(userData));
    if (data.access_token) {
      localStorage.setItem('wmt_token', data.access_token);
    }
  }, []);

  const ssoLogin = useCallback(async () => {
    try {
      setLoading(true);

      let response: Response;
      try {
        response = await fetch(`${API_BASE_URL}/api/auth/sso`, {
          method: 'POST',
          credentials: 'include',
        });
      } catch {
        throw new Error(
          `Cannot reach WMT backend at ${API_BASE_URL}. Check if the backend is running or if CORS allows this desktop origin.`
        );
      }

      if (!response.ok) {
        let message = 'Windows SSO is not available';
        try {
          const payload = await response.json();
          message = payload.detail || message;
        } catch {
          /* keep fallback message */
        }
        throw new Error(message);
      }

      const data = await response.json();
      storeAuth(data);
    } finally {
      setLoading(false);
    }
  }, [storeAuth]);

  // Check if user is already logged in
  useEffect(() => {
    const checkAuth = async () => {
      try {
        const storedUser = readStoredUser();
        const token = localStorage.getItem('wmt_token');
        if (storedUser && token) {
          const current = await apiRequest<User & { permissions: string[] }>('/api/auth/me');
          const userData = {
            username: current.username,
            role: current.role,
            permissions: current.permissions || [],
            display_name: current.display_name,
            email: current.email,
            domain: current.domain,
            groups: current.groups || [],
            auth_source: current.auth_source,
          };
          localStorage.setItem('wmt_user', JSON.stringify(userData));
          setUser(userData);
        } else {
          setUser(null);
        }
      } catch {
        clearStoredSession();
        setUser(null);
      } finally {
        setLoading(false);
      }
    };

    checkAuth();
  }, []);

  useEffect(() => {
    const handleUnauthorized = () => {
      setUser(null);
      setLoading(false);
    };

    window.addEventListener('wmt:unauthorized', handleUnauthorized);
    return () => window.removeEventListener('wmt:unauthorized', handleUnauthorized);
  }, []);

  const login = useCallback(async (username: string, password: string) => {
    try {
      setLoading(true);

      const response = await fetch(`${API_BASE_URL}/api/auth/login`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({ username, password }),
        credentials: 'include',
      });

      if (!response.ok) {
        let message = 'Invalid credentials';
        try {
          const payload = await response.json();
          message = payload.detail || message;
        } catch {
          /* keep fallback message */
        }
        throw new Error(message);
      }

      const data = await response.json();
      storeAuth(data);
    } finally {
      setLoading(false);
    }
  }, [storeAuth]);

  const logout = useCallback(async () => {
    try {
      await apiRequest('/api/auth/logout', { method: 'POST' });
    } finally {
      setUser(null);
      clearStoredSession();
    }
  }, []);

  return {
    user,
    isAuthenticated: !!user,
    loading,
    login,
    ssoLogin,
    logout,
  };
}
