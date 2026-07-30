import { type ReactNode, useCallback, useEffect, useState } from "react";
import { AlertTriangle, Loader2, RefreshCw, Server } from "lucide-react";
import { Button } from "@/components/ui/button";
import { API_BASE_URL, apiFetch } from "@/lib/api";

const EXPECTED_API_VERSION = 1;

type BackendState = "checking" | "ready" | "unavailable" | "incompatible";

interface HealthPayload {
  status?: string;
  service?: string;
  api_version?: number;
  version?: string;
}

export default function BackendGate({ children }: { children: ReactNode }) {
  const [state, setState] = useState<BackendState>("checking");
  const [backendVersion, setBackendVersion] = useState("");

  const checkBackend = useCallback(async () => {
    setState("checking");
    try {
      const response = await apiFetch("/health/ready");
      const payload = (await response.json()) as HealthPayload;
      setBackendVersion(payload.version || "");
      if (
        payload.service !== "wmt-backend" ||
        payload.api_version !== EXPECTED_API_VERSION
      ) {
        setState("incompatible");
        return;
      }
      setState(
        response.ok && payload.status === "ready" ? "ready" : "unavailable"
      );
    } catch {
      setState("unavailable");
    }
  }, []);

  useEffect(() => {
    void checkBackend();
  }, [checkBackend]);

  useEffect(() => {
    if (state === "ready" || state === "incompatible") return;
    const retry = window.setTimeout(() => void checkBackend(), 2500);
    return () => window.clearTimeout(retry);
  }, [checkBackend, state]);

  if (state === "ready") return <>{children}</>;

  const incompatible = state === "incompatible";
  return (
    <div className="flex min-h-screen items-center justify-center bg-background p-6">
      <div className="w-full max-w-lg rounded-xl border bg-card p-7 text-card-foreground shadow-sm">
        <div className="mb-4 flex items-center gap-3">
          {state === "checking" ? (
            <Loader2 className="animate-spin text-primary" size={28} />
          ) : incompatible ? (
            <AlertTriangle className="text-destructive" size={28} />
          ) : (
            <Server className="text-muted-foreground" size={28} />
          )}
          <div>
            <h1 className="text-xl font-semibold">
              {state === "checking"
                ? "Conectando ao backend"
                : incompatible
                  ? "Backend incompatível"
                  : "Backend indisponível"}
            </h1>
            <p className="text-sm text-muted-foreground">
              {incompatible
                ? `O serviço encontrado não é compatível com a API ${EXPECTED_API_VERSION}${backendVersion ? ` (versão ${backendVersion})` : ""}.`
                : `Não foi possível validar o serviço WMT em ${API_BASE_URL || window.location.origin}.`}
            </p>
          </div>
        </div>
        {state !== "checking" && (
          <Button className="gap-2" onClick={() => void checkBackend()}>
            <RefreshCw size={16} />
            Tentar novamente
          </Button>
        )}
      </div>
    </div>
  );
}
