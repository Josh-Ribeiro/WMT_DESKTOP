import { useEffect, useMemo, useRef, useState } from "react";
import { useAuthenticatedUser } from "@/hooks/useAuth";
import { useLocation } from "wouter";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Progress } from "@/components/ui/progress";
import { Input } from "@/components/ui/input";
import { apiRequest } from "@/lib/api";
import { toast } from "sonner";
import {
  BarChart2,
  HardDrive,
  Network,
  RefreshCw,
  Thermometer,
  Gauge,
  Activity,
} from "lucide-react";

type TempSensor = {
  name: string;
  type: string;
  celsius: number;
  fahrenheit: number;
};

type PerformanceSample = {
  host: string;
  generated_at: string;
  cpu: { usage_percent: number; queue_length: number };
  memory: {
    total_gb: number;
    used_gb: number;
    free_gb: number;
    usage_percent: number;
  };
  disk: {
    total_gb: number;
    used_gb: number;
    free_gb: number;
    usage_percent: number;
    volumes: Array<{
      name: string;
      label?: string;
      size_gb: number;
      free_gb: number;
      used_gb: number;
      usage_percent: number;
    }>;
  };
  network: {
    bytes_per_sec: number;
    received_bytes_per_sec: number;
    sent_bytes_per_sec: number;
    interfaces: Array<{
      name: string;
      bytes_per_sec: number;
      received_bytes_per_sec: number;
      sent_bytes_per_sec: number;
    }>;
  };
  temperatures: {
    available: boolean;
    message: string;
    sensors: TempSensor[];
  };
};

function formatBytesPerSec(value: number) {
  if (!Number.isFinite(value) || value < 0) return "0 B/s";
  const units = ["B/s", "KB/s", "MB/s", "GB/s", "TB/s"];
  let v = value;
  let i = 0;
  while (v >= 1024 && i < units.length - 1) {
    v /= 1024;
    i += 1;
  }
  return `${v.toFixed(i === 0 ? 0 : 1)} ${units[i]}`;
}

function TemperatureCard({ sensor }: { sensor: TempSensor }) {
  const c = sensor.celsius;
  const tone =
    c >= 90
      ? "bg-red-500/10 text-red-600"
      : c >= 75
        ? "bg-amber-500/10 text-amber-700"
        : "bg-emerald-500/10 text-emerald-700";

  return (
    <Card className={`border-border/70 bg-card/80 p-3 shadow-none ${tone}`}>
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <p className="truncate text-sm font-semibold">
            {sensor.name || "Sensor"}
          </p>
          <p className="mt-0.5 text-xs opacity-80">{sensor.type}</p>
        </div>
        <div className="shrink-0 text-right">
          <p className="text-lg font-bold">{c.toFixed(1)}°C</p>
          <p className="text-xs opacity-80">{sensor.fahrenheit.toFixed(1)}°F</p>
        </div>
      </div>
    </Card>
  );
}

export default function HostPerformance() {
  const user = useAuthenticatedUser();
  const [, navigate] = useLocation();

  const hostFromQuery = useMemo(() => {
    const sp = new URLSearchParams(window.location.search);
    return (sp.get("host") || "").trim().toUpperCase();
  }, []);

  const [manualHost, setManualHost] = useState(hostFromQuery || "");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [sample, setSample] = useState<PerformanceSample | null>(null);
  const [autoRefreshing, setAutoRefreshing] = useState(true);
  const requestRef = useRef(0);

  const doFetch = async (targetHost: string) => {
    const normalized = (targetHost || "").trim().toUpperCase();
    if (!normalized) {
      setError("Host é obrigatório.");
      return;
    }

    setLoading(true);
    setError(null);
    const requestId = requestRef.current + 1;
    requestRef.current = requestId;

    try {
      const res = await apiRequest<PerformanceSample>(
        `/api/performance-sample?host=${encodeURIComponent(normalized)}`
      );
      if (requestRef.current !== requestId) return;
      setSample(res);
    } catch (e) {
      if (requestRef.current !== requestId) return;
      setError(
        e instanceof Error
          ? e.message
          : "Erro desconhecido ao coletar performance."
      );
    } finally {
      if (requestRef.current === requestId) setLoading(false);
    }
  };

  useEffect(() => {
    if (!hostFromQuery) return;
    void doFetch(hostFromQuery);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [hostFromQuery]);

  useEffect(() => {
    if (!autoRefreshing) return;
    if (!hostFromQuery) return;

    const id = window.setInterval(() => {
      if (document.hidden) return;
      void doFetch(hostFromQuery);
    }, 8000);

    return () => window.clearInterval(id);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [autoRefreshing, hostFromQuery]);

  const host = hostFromQuery || "";
  const cpuUsage = sample?.cpu?.usage_percent ?? 0;
  const memUsage = sample?.memory?.usage_percent ?? 0;
  const diskUsage = sample?.disk?.usage_percent ?? 0;
  const tempsAvailable = sample?.temperatures?.available ?? false;
  const tempsSensors = sample?.temperatures?.sensors ?? [];

  const volumes = sample?.disk?.volumes ?? [];
  const safeVolumes = Array.isArray(volumes)
    ? volumes.map(v => ({
        name: v?.name ?? "Volume",
        label: v?.label ?? undefined,
        size_gb: Number.isFinite(v?.size_gb as number)
          ? (v.size_gb as number)
          : 0,
        free_gb: Number.isFinite(v?.free_gb as number)
          ? (v.free_gb as number)
          : 0,
        used_gb: Number.isFinite(v?.used_gb as number)
          ? (v.used_gb as number)
          : 0,
        usage_percent: Number.isFinite(v?.usage_percent as number)
          ? (v.usage_percent as number)
          : 0,
      }))
    : [];

  return (
    <div className="flex min-h-0 min-w-0 flex-1 overflow-hidden bg-background">
      <main className="h-full min-w-0 flex-1 overflow-auto">
        <div className="mx-auto w-full max-w-7xl space-y-6 p-4 sm:p-6 lg:p-8">
          <div className="wmt-header flex flex-col gap-4 rounded-xl border p-5 text-slate-100 shadow-lg sm:flex-row sm:items-center sm:justify-between">
            <div className="min-w-0">
              <h1 className="flex items-center gap-2 text-3xl font-bold text-white">
                <BarChart2 size={22} /> Monitor de desempenho
              </h1>
              <p className="mt-1 text-sm text-slate-400">
                CPU, Memória, Disco, Rede e Temperatura (quando disponível)
              </p>
            </div>

            <div className="flex flex-wrap items-center gap-2">
              <Button
                variant="outline"
                size="sm"
                disabled={loading || !host}
                onClick={() => void doFetch(host)}
              >
                {loading ? (
                  <RefreshCw className="mr-2 animate-spin" size={16} />
                ) : (
                  <RefreshCw className="mr-2" size={16} />
                )}
                {loading ? "Coletando..." : "Atualizar"}
              </Button>
              <Button
                variant={autoRefreshing ? "default" : "outline"}
                size="sm"
                disabled={!host}
                onClick={() => setAutoRefreshing(v => !v)}
              >
                {autoRefreshing ? "Auto: ON" : "Auto: OFF"}
              </Button>
            </div>
          </div>

          <Card className="border-border/70 bg-card p-4 shadow-none">
            <div className="grid gap-3 md:grid-cols-[minmax(0,1fr)_auto] md:items-end">
              <div>
                <p className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                  Host
                </p>
                <div className="mt-1 flex gap-2">
                  <Input
                    value={manualHost}
                    onChange={e => setManualHost(e.target.value)}
                    placeholder="Ex.: PC-01 ou 192.168.0.10"
                    className="bg-background"
                  />
                  <Button
                    onClick={() => {
                      const h = manualHost.trim().toUpperCase();
                      if (!h) return;
                      navigate(
                        `/monitor-temps?host=${encodeURIComponent(h)}` as any
                      );
                      setError(null);
                      setSample(null);
                    }}
                    disabled={!manualHost.trim() || loading}
                  >
                    Ir
                  </Button>
                </div>
              </div>
              <div className="text-xs text-muted-foreground">
                {sample?.generated_at
                  ? `Última coleta: ${new Date(sample.generated_at).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}`
                  : "—"}
              </div>
            </div>

            {error && (
              <div className="mt-3 rounded-lg bg-red-50 p-3 text-sm text-red-800 ring-1 ring-red-200 dark:bg-red-950/20 dark:text-red-200">
                {error}
              </div>
            )}
          </Card>

          <div className="grid gap-4 lg:grid-cols-3">
            <Card className="border-border/70 bg-card/90 p-4 shadow-none lg:col-span-1">
              <div className="flex items-center gap-2">
                <Activity size={18} className="text-muted-foreground" />
                <p className="text-sm font-semibold text-foreground">CPU</p>
                <span className="ml-auto rounded-full bg-background px-2 py-0.5 text-xs text-muted-foreground ring-1 ring-border/40">
                  {cpuUsage}%
                </span>
              </div>
              <div className="mt-3">
                <Progress value={cpuUsage} />
                <div className="mt-2 grid grid-cols-2 gap-2 text-xs text-muted-foreground">
                  <div>
                    <p>Uso</p>
                    <p className="font-semibold text-foreground">{cpuUsage}%</p>
                  </div>
                  <div>
                    <p>Queue</p>
                    <p className="font-semibold text-foreground">
                      {sample?.cpu.queue_length ?? 0}
                    </p>
                  </div>
                </div>
              </div>
            </Card>

            <Card className="border-border/70 bg-card/90 p-4 shadow-none lg:col-span-1">
              <div className="flex items-center gap-2">
                <Gauge size={18} className="text-muted-foreground" />
                <p className="text-sm font-semibold text-foreground">Memória</p>
                <span className="ml-auto rounded-full bg-background px-2 py-0.5 text-xs text-muted-foreground ring-1 ring-border/40">
                  {memUsage}%
                </span>
              </div>
              <div className="mt-3">
                <Progress value={memUsage} />
                <div className="mt-2 grid grid-cols-2 gap-2 text-xs text-muted-foreground">
                  <div>
                    <p>Total</p>
                    <p className="font-semibold text-foreground">
                      {sample ? `${sample.memory.total_gb.toFixed(2)} GB` : "—"}
                    </p>
                  </div>
                  <div>
                    <p>Livre</p>
                    <p className="font-semibold text-foreground">
                      {sample ? `${sample.memory.free_gb.toFixed(2)} GB` : "—"}
                    </p>
                  </div>
                </div>
              </div>
            </Card>

            <Card className="border-border/70 bg-card/90 p-4 shadow-none lg:col-span-1">
              <div className="flex items-center gap-2">
                <HardDrive size={18} className="text-muted-foreground" />
                <p className="text-sm font-semibold text-foreground">
                  Disco (total)
                </p>
                <span className="ml-auto rounded-full bg-background px-2 py-0.5 text-xs text-muted-foreground ring-1 ring-border/40">
                  {diskUsage}%
                </span>
              </div>
              <div className="mt-3">
                <Progress value={diskUsage} />
                <div className="mt-2 grid grid-cols-2 gap-2 text-xs text-muted-foreground">
                  <div>
                    <p>Usado</p>
                    <p className="font-semibold text-foreground">
                      {sample ? `${sample.disk.used_gb.toFixed(2)} GB` : "—"}
                    </p>
                  </div>
                  <div>
                    <p>Disponível</p>
                    <p className="font-semibold text-foreground">
                      {sample ? `${sample.disk.free_gb.toFixed(2)} GB` : "—"}
                    </p>
                  </div>
                </div>
              </div>
            </Card>
          </div>

          <div className="grid gap-4 lg:grid-cols-2">
            <Card className="border-border/70 bg-card p-4 shadow-none">
              <div className="flex items-center gap-2">
                <Network size={18} className="text-muted-foreground" />
                <p className="text-sm font-semibold text-foreground">Rede</p>
              </div>

              <div className="mt-3 grid gap-3 sm:grid-cols-3">
                <div className="rounded-lg bg-background/60 p-3 ring-1 ring-border/40">
                  <p className="text-xs text-muted-foreground">Total</p>
                  <p className="mt-1 text-base font-bold">
                    {sample
                      ? formatBytesPerSec(sample.network.bytes_per_sec)
                      : "—"}
                  </p>
                </div>
                <div className="rounded-lg bg-background/60 p-3 ring-1 ring-border/40">
                  <p className="text-xs text-muted-foreground">Recebido</p>
                  <p className="mt-1 text-base font-bold">
                    {sample
                      ? formatBytesPerSec(sample.network.received_bytes_per_sec)
                      : "—"}
                  </p>
                </div>
                <div className="rounded-lg bg-background/60 p-3 ring-1 ring-border/40">
                  <p className="text-xs text-muted-foreground">Enviado</p>
                  <p className="mt-1 text-base font-bold">
                    {sample
                      ? formatBytesPerSec(sample.network.sent_bytes_per_sec)
                      : "—"}
                  </p>
                </div>
              </div>

              <div className="mt-4">
                <p className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                  Interfaces
                </p>
                <div className="mt-2 space-y-2">
                  {(sample?.network.interfaces || []).map(iface => (
                    <div
                      key={iface.name}
                      className="flex items-center justify-between rounded-lg bg-background/50 p-2 text-xs ring-1 ring-border/40"
                    >
                      <div className="min-w-0">
                        <p className="truncate font-medium text-foreground">
                          {iface.name}
                        </p>
                      </div>
                      <div className="text-right text-muted-foreground">
                        <div>{formatBytesPerSec(iface.bytes_per_sec)}</div>
                        <div className="opacity-80">
                          R: {formatBytesPerSec(iface.received_bytes_per_sec)} •
                          S: {formatBytesPerSec(iface.sent_bytes_per_sec)}
                        </div>
                      </div>
                    </div>
                  ))}
                  {!sample?.network.interfaces?.length && (
                    <p className="text-xs text-muted-foreground">
                      Sem dados de interfaces.
                    </p>
                  )}
                </div>
              </div>
            </Card>

            <Card className="border-border/70 bg-card p-4 shadow-none">
              <div className="flex items-center gap-2">
                <HardDrive size={18} className="text-muted-foreground" />
                <p className="text-sm font-semibold text-foreground">
                  Volumetria
                </p>
              </div>

              <div className="mt-4 space-y-2">
                {safeVolumes.slice(0, 8).map(v => (
                  <div
                    key={v.name}
                    className="rounded-lg bg-background/50 p-3 ring-1 ring-border/40"
                  >
                    <div className="flex items-start justify-between gap-2">
                      <div className="min-w-0">
                        <p className="truncate text-sm font-semibold">
                          {v.label || v.name || "Volume"}
                        </p>
                        <p className="text-xs text-muted-foreground">
                          {v.name}
                        </p>
                      </div>
                      <div className="shrink-0 text-right">
                        <p className="text-sm font-bold">{v.usage_percent}%</p>
                        <p className="text-xs text-muted-foreground">
                          {v.free_gb.toFixed(2)} GB livres
                        </p>
                      </div>
                    </div>
                    <div className="mt-2">
                      <Progress value={v.usage_percent} />
                    </div>
                  </div>
                ))}
                {!safeVolumes.length && (
                  <p className="text-xs text-muted-foreground">
                    Sem dados de volumes.
                  </p>
                )}
              </div>
            </Card>
          </div>

          <Card className="border-border/70 bg-card p-4 shadow-none">
            <div className="flex items-center gap-2">
              <Thermometer size={18} className="text-muted-foreground" />
              <p className="text-sm font-semibold text-foreground">
                Temperatura
              </p>
              <span className="ml-auto rounded-full bg-background px-2 py-0.5 text-xs text-muted-foreground ring-1 ring-border/40">
                {tempsAvailable
                  ? `${tempsSensors.length} sensor(es)`
                  : "indisponível"}
              </span>
            </div>

            {sample?.temperatures?.message && (
              <p className="mt-2 text-xs text-muted-foreground">
                {sample.temperatures.message}
              </p>
            )}

            <div className="mt-4 grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
              {tempsAvailable && tempsSensors.length ? (
                tempsSensors.map((s, idx) => (
                  <TemperatureCard key={`${s.name}-${idx}`} sensor={s} />
                ))
              ) : (
                <div className="rounded-lg border border-dashed border-border/70 p-6 text-center text-xs text-muted-foreground">
                  Nenhuma temperatura retornada (WMI/ACPI). Dependendo do
                  modelo, pode não existir.
                </div>
              )}
            </div>
          </Card>
        </div>
      </main>
    </div>
  );
}
