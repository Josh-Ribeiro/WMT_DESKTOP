import { useState, useEffect, useCallback, useRef } from "react";
import { apiRequest } from "@/lib/api";

interface UseApiOptions {
  skip?: boolean;
  refetchInterval?: number;
  pauseWhenHidden?: boolean;
}

interface UseApiResult<T> {
  data: T | null;
  loading: boolean;
  error: string | null;
  refetch: () => Promise<void>;
}

export function useApi<T>(
  endpoint: string,
  options: UseApiOptions = {}
): UseApiResult<T> {
  const [data, setData] = useState<T | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const requestRef = useRef<Promise<void> | null>(null);
  const requestEndpointRef = useRef<string | null>(null);
  const mountedRef = useRef(true);

  const fetchData = useCallback(
    async (background = false) => {
      if (requestRef.current && requestEndpointRef.current === endpoint) {
        return requestRef.current;
      }

      const request = (async () => {
        try {
          if (!background) {
            setLoading(true);
          }
          setError(null);

          const result = await apiRequest<T>(endpoint);
          if (mountedRef.current) {
            setData(result);
          }
        } catch (err) {
          if (mountedRef.current) {
            setError(err instanceof Error ? err.message : "Unknown error");
          }
        } finally {
          if (!background && mountedRef.current) {
            setLoading(false);
          }
        }
      })();

      requestRef.current = request;
      requestEndpointRef.current = endpoint;
      try {
        await request;
      } finally {
        if (requestRef.current === request) {
          requestRef.current = null;
          requestEndpointRef.current = null;
        }
      }
    },
    [endpoint]
  );

  useEffect(() => {
    mountedRef.current = true;
    if (options.skip) return;

    void fetchData();

    if (options.refetchInterval) {
      let timeoutId: ReturnType<typeof setTimeout> | undefined;
      const scheduleRefresh = () => {
        if (timeoutId) clearTimeout(timeoutId);
        timeoutId = setTimeout(refresh, options.refetchInterval);
      };
      const refresh = async () => {
        if (options.pauseWhenHidden !== false && document.hidden) {
          scheduleRefresh();
          return;
        }
        await fetchData(true);
        scheduleRefresh();
      };
      scheduleRefresh();
      const handleVisibility = () => {
        if (!document.hidden) {
          if (timeoutId) clearTimeout(timeoutId);
          void fetchData(true).finally(scheduleRefresh);
        }
      };
      document.addEventListener("visibilitychange", handleVisibility);
      return () => {
        mountedRef.current = false;
        if (timeoutId) clearTimeout(timeoutId);
        document.removeEventListener("visibilitychange", handleVisibility);
      };
    }

    return () => {
      mountedRef.current = false;
    };
  }, [
    fetchData,
    options.skip,
    options.refetchInterval,
    options.pauseWhenHidden,
  ]);

  return { data, loading, error, refetch: () => fetchData() };
}
