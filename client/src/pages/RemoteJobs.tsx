import { Fragment, useMemo, useState } from "react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { useApi } from "@/hooks/useApi";
import { useAuthenticatedUser } from "@/hooks/useAuth";
import { apiRequest } from "@/lib/api";
import { openPathOnHost } from "@/lib/hostOpen";
import { useLocation } from "wouter";
import {
  AlertTriangle,
  Ban,
  CheckCircle2,
  ChevronDown,
  ChevronUp,
  Clock3,
  FolderOpen,
  Loader2,
  RefreshCw,
  Search,
  TerminalSquare,
  Trash2,
} from "lucide-react";
import { toast } from "sonner";

type RemoteJobStatus =
  | "queued"
  | "running"
  | "completed"
  | "failed"
  | "canceled";
type StatusFilter = "all" | "active" | RemoteJobStatus;

interface RemoteJob {
  id: string;
  host: string;
  action: string;
  status: RemoteJobStatus;
  ok: boolean;
  message: string;
  details: string;
  open_path?: string;
  created_by: string;
  created_at: string;
  started_at: string;
  ended_at: string;
  duration_ms: number;
}

interface RemoteJobsData {
  jobs: RemoteJob[];
  total: number;
  running: number;
  failed: number;
  completed: number;
  temp_shares: TempSharesData;
  maintenance_modes: MaintenanceModesData;
}

interface TempShare {
  id: string;
  host: string;
  share_name: string;
  drive: string;
  path: string;
  unc_path: string;
  created_at: string;
  expires_at: string;
  active: boolean;
  expired: boolean;
}

interface TempSharesData {
  shares: TempShare[];
  total: number;
  active: number;
  expired: number;
}

interface MaintenanceMode {
  id: string;
  host: string;
  opened_by: string;
  technician: string;
  contact: string;
  ticket: string;
  reason: string;
  opened_at: string;
  expires_at: string;
  remaining_seconds: number | null;
  protected_users: string[];
  active: boolean;
}

interface MaintenanceModesData {
  modes: MaintenanceMode[];
  total: number;
  active: number;
}

const actionLabels: Record<string, string> = {
  "remote-access": "Remote Access",
  "remote-assistance": "Remote Assistance",
  "computer-management": "Computer Management",
  "restart-spooler": "Restart Spooler",
  "renew-ip": "Renew IP",
  gpupdate: "GPUpdate",
  "force-all-actions": "Force All Actions",
  "clear-sccm-cache": "Clear SCCM Cache",
  "create-temp-c-share": "Create Temp C Share",
  "remove-temp-c-share": "Remove Temp C Share",
};

const statusStyles: Record<RemoteJobStatus, string> = {
  queued:
    "border-zinc-200 bg-zinc-50 text-zinc-700 dark:border-zinc-400/30 dark:bg-zinc-500/10 dark:text-zinc-200",
  running:
    "border-blue-200 bg-blue-50 text-blue-700 dark:border-blue-400/30 dark:bg-blue-500/10 dark:text-blue-200",
  completed:
    "border-emerald-200 bg-emerald-50 text-emerald-700 dark:border-emerald-400/30 dark:bg-emerald-500/10 dark:text-emerald-200",
  failed:
    "border-red-200 bg-red-50 text-red-700 dark:border-red-400/30 dark:bg-red-500/10 dark:text-red-200",
  canceled:
    "border-amber-200 bg-amber-50 text-amber-700 dark:border-amber-400/30 dark:bg-amber-500/10 dark:text-amber-200",
};

function formatDateTime(value?: string) {
  if (!value) return "-";
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return value;
  return new Intl.DateTimeFormat("pt-BR", {
    day: "2-digit",
    month: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  }).format(parsed);
}

function formatDuration(value?: number) {
  if (!value) return "-";
  if (value < 1000) return `${value}ms`;
  return `${(value / 1000).toFixed(1)}s`;
}

function formatRemaining(seconds: number | null) {
  if (seconds === null) return "sem prazo informado";
  const totalMinutes = Math.max(0, Math.ceil(seconds / 60));
  const hours = Math.floor(totalMinutes / 60);
  const minutes = totalMinutes % 60;
  if (hours) return `${hours}h ${minutes.toString().padStart(2, "0")}min`;
  return `${minutes}min`;
}

function labelForAction(action: string) {
  return actionLabels[action] || action;
}

function statusClass(status: string) {
  return statusStyles[status as RemoteJobStatus] || statusStyles.queued;
}

function isActive(job: RemoteJob) {
  return job.status === "queued" || job.status === "running";
}

function openPathForJob(job: RemoteJob) {
  if (job.open_path) return job.open_path;
  if (job.action === "create-temp-c-share") return `\\\\${job.host}\\TempC$`;
  return "";
}

function statusIcon(status: RemoteJobStatus) {
  if (status === "running" || status === "queued")
    return <Loader2 className="animate-spin" size={15} />;
  if (status === "failed") return <AlertTriangle size={15} />;
  if (status === "canceled") return <Ban size={15} />;
  return <CheckCircle2 size={15} />;
}

function StatTile({
  label,
  value,
  tone = "",
}: {
  label: string;
  value: number;
  tone?: string;
}) {
  return (
    <div className="rounded-lg border border-border/70 bg-card px-4 py-3">
      <p className="text-xs font-semibold uppercase text-muted-foreground">
        {label}
      </p>
      <p className={`mt-1 text-2xl font-semibold ${tone}`}>{value}</p>
    </div>
  );
}

export default function RemoteJobs() {
  const user = useAuthenticatedUser();
  const [, navigate] = useLocation();
  const { data, loading, error, refetch } = useApi<RemoteJobsData>(
    "/api/remote-jobs",
    {
      refetchInterval: 3000,
    }
  );
  const [expandedJobId, setExpandedJobId] = useState<string | null>(null);
  const [cancellingJobId, setCancellingJobId] = useState<string | null>(null);
  const [removingShareId, setRemovingShareId] = useState<string | null>(null);
  const [query, setQuery] = useState("");
  const [statusFilter, setStatusFilter] = useState<StatusFilter>("active");
  const [visibleCount, setVisibleCount] = useState(25);

  const jobs = data?.jobs || [];
  const activeJobs = jobs.filter(isActive);
  const canceled = jobs.filter(job => job.status === "canceled").length;

  const filteredJobs = useMemo(() => {
    const normalizedQuery = query.trim().toLowerCase();
    return jobs.filter(job => {
      const matchesStatus =
        statusFilter === "all"
          ? true
          : statusFilter === "active"
            ? isActive(job)
            : job.status === statusFilter;
      if (!matchesStatus) return false;
      if (!normalizedQuery) return true;
      return [
        job.id,
        job.host,
        job.action,
        labelForAction(job.action),
        job.created_by,
        job.message,
      ]
        .join(" ")
        .toLowerCase()
        .includes(normalizedQuery);
    });
  }, [jobs, query, statusFilter]);

  const visibleJobs = filteredJobs.slice(0, visibleCount);
  const activeTempShares = (data?.temp_shares?.shares || []).filter(
    share => share.active && share.share_name.toLowerCase() === "tempc$"
  );
  const activeMaintenanceModes = data?.maintenance_modes?.modes || [];

  const cancelJob = async (jobId: string) => {
    setCancellingJobId(jobId);
    try {
      await apiRequest(`/api/remote-jobs/${encodeURIComponent(jobId)}/cancel`, {
        method: "POST",
      });
      toast.success("Remote task canceled", { description: jobId });
      await refetch();
    } catch (err) {
      toast.error("Não foi possível cancelar", {
        description: err instanceof Error ? err.message : jobId,
      });
    } finally {
      setCancellingJobId(null);
    }
  };

  const openJobPath = async (job: RemoteJob) => {
    const path = openPathForJob(job);
    if (!path) return;
    try {
      await openPathOnHost(path);
      toast.success("Pasta aberta", { description: path });
    } catch (err) {
      toast.error("Não foi possível abrir a pasta", {
        description: err instanceof Error ? err.message : path,
      });
    }
  };

  const openTempShare = async (share: TempShare) => {
    const path = share.unc_path || `\\\\${share.host}\\${share.share_name}`;
    try {
      await openPathOnHost(path);
      toast.success("Temp C share aberto", { description: path });
    } catch (err) {
      toast.error("Não foi possível abrir o Temp C share", {
        description: err instanceof Error ? err.message : path,
      });
    }
  };

  const removeTempShare = async (share: TempShare) => {
    const id = share.id || `${share.host}:${share.share_name}`;
    setRemovingShareId(id);
    try {
      await apiRequest(
        `/api/temp-shares/${encodeURIComponent(share.host)}/${encodeURIComponent(share.share_name)}`,
        { method: "DELETE" }
      );
      toast.success("Temp C share removido", { description: share.unc_path });
      await refetch();
    } catch (err) {
      toast.error("Não foi possível remover o Temp C share", {
        description: err instanceof Error ? err.message : share.unc_path,
      });
    } finally {
      setRemovingShareId(null);
    }
  };

  return (
    <div className="flex min-h-0 min-w-0 flex-1 overflow-hidden bg-background">
      <main className="h-full min-w-0 flex-1 overflow-auto">
        <div className="mx-auto flex w-full max-w-7xl flex-col gap-5 p-6 lg:p-8">
          <section className="wmt-header flex flex-col gap-4 rounded-xl border p-5 text-slate-100 shadow-lg md:flex-row md:items-center md:justify-between">
            <div className="min-w-0">
              <h1 className="text-2xl font-semibold tracking-normal text-white">
                Remote Tasks
              </h1>
              <p className="mt-1 text-sm text-slate-400">
                Fila ativa e histórico das ações remotas.
              </p>
            </div>
            <Button
              variant="outline"
              onClick={() => refetch()}
              disabled={loading}
              className="w-fit"
            >
              {loading ? (
                <Loader2 className="animate-spin" size={16} />
              ) : (
                <RefreshCw size={16} />
              )}
              Refresh
            </Button>
          </section>

          <div className="grid grid-cols-2 gap-3 lg:grid-cols-5">
            <StatTile label="Total" value={data?.total || 0} />
            <StatTile
              label="Ativas"
              value={activeJobs.length}
              tone="text-blue-600"
            />
            <StatTile
              label="Concluídas"
              value={data?.completed || 0}
              tone="text-emerald-600"
            />
            <StatTile
              label="Falhas"
              value={data?.failed || 0}
              tone="text-red-600"
            />
            <StatTile
              label="Canceladas"
              value={canceled}
              tone="text-amber-600"
            />
          </div>

          <div className="grid items-start gap-5 xl:grid-cols-2">
            <Card className="rounded-lg border-border/70 shadow-none">
              <CardHeader className="flex flex-row items-center justify-between gap-3 px-4 py-3">
                <div>
                  <CardTitle className="text-base">
                    Temp C shares ativos
                  </CardTitle>
                  <p className="mt-0.5 text-xs text-muted-foreground">
                    Compartilhamentos temporários disponíveis agora.
                  </p>
                </div>
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => refetch()}
                  disabled={loading}
                >
                  {loading ? (
                    <Loader2 className="animate-spin" size={15} />
                  ) : (
                    <RefreshCw size={15} />
                  )}
                  Refresh
                </Button>
              </CardHeader>
              <CardContent className="px-4 pb-4">
                {activeTempShares.length ? (
                  <div className="grid gap-3">
                    {activeTempShares.map(share => {
                      const id =
                        share.id || `${share.host}:${share.share_name}`;
                      const path =
                        share.unc_path ||
                        `\\\\${share.host}\\${share.share_name}`;
                      return (
                        <div
                          key={id}
                          className="rounded-lg border border-border/70 bg-muted/20 p-3"
                        >
                          <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
                            <div className="min-w-0">
                              <div className="flex flex-wrap items-center gap-2">
                                <Badge
                                  variant="outline"
                                  className="border-emerald-200 bg-emerald-50 text-emerald-700 dark:border-emerald-400/30 dark:bg-emerald-500/10 dark:text-emerald-200"
                                >
                                  ativo
                                </Badge>
                                <span className="font-semibold text-foreground">
                                  {share.host}
                                </span>
                                <span className="text-sm text-muted-foreground">
                                  {share.share_name}
                                </span>
                              </div>
                              <p className="mt-1.5 break-words text-sm font-medium text-foreground">
                                {path}
                              </p>
                              <p className="mt-0.5 text-xs text-muted-foreground">
                                Expira em {formatDateTime(share.expires_at)}
                              </p>
                            </div>
                            <div className="flex shrink-0 flex-wrap gap-2">
                              <Button
                                variant="outline"
                                size="sm"
                                onClick={() => openTempShare(share)}
                              >
                                <FolderOpen size={14} />
                                Open
                              </Button>
                              <Button
                                variant="outline"
                                size="sm"
                                className="border-red-300 text-red-700 hover:bg-red-50 dark:border-red-400/40 dark:text-red-200"
                                disabled={removingShareId === id}
                                onClick={() => removeTempShare(share)}
                              >
                                {removingShareId === id ? (
                                  <Loader2 className="animate-spin" size={14} />
                                ) : (
                                  <Trash2 size={14} />
                                )}
                                Excluir
                              </Button>
                            </div>
                          </div>
                        </div>
                      );
                    })}
                  </div>
                ) : (
                  <div className="rounded-lg border border-dashed border-border/70 px-4 py-8 text-center text-sm text-muted-foreground">
                    Nenhum Temp C share ativo agora.
                  </div>
                )}
              </CardContent>
            </Card>

            <Card className="rounded-lg border-border/70 shadow-none">
              <CardHeader className="px-4 py-3">
                <CardTitle className="text-base">
                  Modos de manutenção ativos
                </CardTitle>
                <p className="mt-0.5 text-xs text-muted-foreground">
                  Estações protegidas, responsável e tempo restante.
                </p>
              </CardHeader>
              <CardContent className="px-4 pb-4">
                {activeMaintenanceModes.length ? (
                  <div className="grid gap-3">
                    {activeMaintenanceModes.map(mode => (
                      <div
                        key={mode.id || mode.host}
                        className="rounded-lg border border-amber-300/70 bg-amber-50/60 p-3 dark:border-amber-400/30 dark:bg-amber-500/5"
                      >
                        <div className="flex flex-wrap items-center gap-2">
                          <Badge
                            variant="outline"
                            className="border-amber-300 bg-amber-100 text-amber-800 dark:border-amber-400/40 dark:bg-amber-500/10 dark:text-amber-200"
                          >
                            <Clock3 size={13} />
                            {formatRemaining(mode.remaining_seconds)}
                          </Badge>
                          <span className="font-semibold text-foreground">
                            {mode.host}
                          </span>
                          {mode.ticket && (
                            <span className="text-xs text-muted-foreground">
                              Chamado {mode.ticket}
                            </span>
                          )}
                        </div>
                        <p className="mt-2 line-clamp-2 text-sm text-foreground">
                          {mode.reason || "Motivo não informado"}
                        </p>
                        <div className="mt-2 grid gap-x-4 gap-y-0.5 text-xs text-muted-foreground sm:grid-cols-2">
                          <span>
                            Aberto por:{" "}
                            <strong className="text-foreground">
                              {mode.technician || mode.opened_by}
                            </strong>
                          </span>
                          <span>
                            Encerra em: {formatDateTime(mode.expires_at)}
                          </span>
                          {mode.contact && <span>Contato: {mode.contact}</span>}
                          <span>
                            Usuários protegidos:{" "}
                            {mode.protected_users?.length || 0}
                          </span>
                        </div>
                      </div>
                    ))}
                  </div>
                ) : (
                  <div className="rounded-lg border border-dashed border-border/70 px-4 py-8 text-center text-sm text-muted-foreground">
                    Nenhum modo de manutenção ativo agora.
                  </div>
                )}
              </CardContent>
            </Card>
          </div>

          {activeJobs.length > 0 && (
            <section className="space-y-3">
              <div className="flex items-center justify-between gap-3">
                <h2 className="text-sm font-semibold uppercase tracking-wide text-muted-foreground">
                  Em execução
                </h2>
                <span className="text-xs text-muted-foreground">
                  {activeJobs.length} tarefa(s)
                </span>
              </div>
              <div className="grid gap-3 lg:grid-cols-2">
                {activeJobs.slice(0, 4).map(job => (
                  <div
                    key={job.id}
                    className="rounded-lg border border-blue-400/30 bg-blue-500/5 p-4"
                  >
                    <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
                      <div className="min-w-0">
                        <div className="flex flex-wrap items-center gap-2">
                          <Badge
                            variant="outline"
                            className={statusClass(job.status)}
                          >
                            {statusIcon(job.status)}
                            {job.status}
                          </Badge>
                          <span className="break-words text-sm font-semibold text-foreground">
                            {labelForAction(job.action)}
                          </span>
                          <span className="text-sm text-muted-foreground">
                            on
                          </span>
                          <span className="break-words text-sm font-semibold text-foreground">
                            {job.host}
                          </span>
                        </div>
                        <p className="mt-2 break-words text-sm text-muted-foreground">
                          {job.message || "Executando..."}
                        </p>
                        {openPathForJob(job) && (
                          <p className="mt-1 break-words text-xs font-medium text-foreground">
                            {openPathForJob(job)}
                          </p>
                        )}
                        <p className="mt-2 text-xs text-muted-foreground">
                          {job.id} • {formatDateTime(job.created_at)} •{" "}
                          {job.created_by || "system"}
                        </p>
                      </div>
                      <Button
                        variant="outline"
                        size="sm"
                        className="w-fit border-amber-300 text-amber-700 hover:bg-amber-50 dark:border-amber-400/40 dark:text-amber-200"
                        disabled={cancellingJobId === job.id}
                        onClick={() => cancelJob(job.id)}
                      >
                        {cancellingJobId === job.id ? (
                          <Loader2 className="animate-spin" size={15} />
                        ) : (
                          <Ban size={15} />
                        )}
                        Cancel
                      </Button>
                      {openPathForJob(job) && (
                        <Button
                          variant="outline"
                          size="sm"
                          className="w-fit"
                          onClick={() => openJobPath(job)}
                        >
                          <FolderOpen size={15} />
                          Open
                        </Button>
                      )}
                    </div>
                  </div>
                ))}
              </div>
            </section>
          )}

          <Card className="rounded-lg border-border/70 shadow-none">
            <CardHeader className="gap-4">
              <div className="flex flex-col gap-3 xl:flex-row xl:items-center xl:justify-between">
                <CardTitle>Histórico</CardTitle>
                <div className="flex flex-col gap-2 sm:flex-row sm:items-center">
                  <div className="relative min-w-0 sm:w-72">
                    <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
                    <Input
                      value={query}
                      onChange={event => {
                        setQuery(event.target.value);
                        setVisibleCount(25);
                      }}
                      className="pl-9"
                      placeholder="Buscar por host, ID ou ação"
                    />
                  </div>
                  <Tabs
                    value={statusFilter}
                    onValueChange={value => {
                      setStatusFilter(value as StatusFilter);
                      setVisibleCount(25);
                    }}
                  >
                    <TabsList className="w-full sm:w-fit">
                      <TabsTrigger value="active">Ativas</TabsTrigger>
                      <TabsTrigger value="failed">Falhas</TabsTrigger>
                      <TabsTrigger value="completed">OK</TabsTrigger>
                      <TabsTrigger value="all">Tudo</TabsTrigger>
                    </TabsList>
                  </Tabs>
                </div>
              </div>
            </CardHeader>
            <CardContent>
              {loading && !data ? (
                <div className="flex items-center justify-center py-16">
                  <Loader2
                    className="animate-spin text-muted-foreground"
                    size={30}
                  />
                </div>
              ) : error ? (
                <div className="rounded-lg border border-red-200 bg-red-50 p-4 text-sm text-red-800 dark:border-red-400/30 dark:bg-red-500/10 dark:text-red-200">
                  {error}
                </div>
              ) : visibleJobs.length ? (
                <div className="space-y-4">
                  <div className="rounded-lg border border-border/70">
                    <Table>
                      <TableHeader>
                        <TableRow>
                          <TableHead>Status</TableHead>
                          <TableHead>Ação</TableHead>
                          <TableHead>Host</TableHead>
                          <TableHead>Criado</TableHead>
                          <TableHead>Duração</TableHead>
                          <TableHead className="text-right">Ações</TableHead>
                        </TableRow>
                      </TableHeader>
                      <TableBody>
                        {visibleJobs.map(job => {
                          const expanded = expandedJobId === job.id;
                          return (
                            <Fragment key={job.id}>
                              <TableRow key={job.id}>
                                <TableCell>
                                  <Badge
                                    variant="outline"
                                    className={statusClass(job.status)}
                                  >
                                    {statusIcon(job.status)}
                                    {job.status}
                                  </Badge>
                                </TableCell>
                                <TableCell className="max-w-[260px]">
                                  <div className="min-w-0">
                                    <p className="truncate font-medium text-foreground">
                                      {labelForAction(job.action)}
                                    </p>
                                    <p className="truncate text-xs text-muted-foreground">
                                      {job.message || job.id}
                                    </p>
                                  </div>
                                </TableCell>
                                <TableCell className="font-medium">
                                  {job.host}
                                </TableCell>
                                <TableCell>
                                  <div className="inline-flex items-center gap-1 text-xs text-muted-foreground">
                                    <Clock3 size={13} />
                                    {formatDateTime(job.created_at)}
                                  </div>
                                </TableCell>
                                <TableCell className="text-xs text-muted-foreground">
                                  {formatDuration(job.duration_ms)}
                                </TableCell>
                                <TableCell>
                                  <div className="flex justify-end gap-2">
                                    {isActive(job) && (
                                      <Button
                                        variant="outline"
                                        size="sm"
                                        className="border-amber-300 text-amber-700 hover:bg-amber-50 dark:border-amber-400/40 dark:text-amber-200"
                                        disabled={cancellingJobId === job.id}
                                        onClick={() => cancelJob(job.id)}
                                      >
                                        {cancellingJobId === job.id ? (
                                          <Loader2
                                            className="animate-spin"
                                            size={14}
                                          />
                                        ) : (
                                          <Ban size={14} />
                                        )}
                                      </Button>
                                    )}
                                    {openPathForJob(job) && (
                                      <Button
                                        variant="outline"
                                        size="sm"
                                        onClick={() => openJobPath(job)}
                                      >
                                        <FolderOpen size={14} />
                                        Open
                                      </Button>
                                    )}
                                    <Button
                                      variant="outline"
                                      size="sm"
                                      onClick={() =>
                                        setExpandedJobId(
                                          expanded ? null : job.id
                                        )
                                      }
                                      disabled={!job.details}
                                    >
                                      <TerminalSquare size={14} />
                                      {expanded ? (
                                        <ChevronUp size={14} />
                                      ) : (
                                        <ChevronDown size={14} />
                                      )}
                                    </Button>
                                  </div>
                                </TableCell>
                              </TableRow>
                              {expanded && job.details && (
                                <TableRow key={`${job.id}-details`}>
                                  <TableCell
                                    colSpan={6}
                                    className="bg-muted/30"
                                  >
                                    <pre className="max-h-64 overflow-auto rounded-md bg-background p-3 text-xs leading-relaxed text-muted-foreground">
                                      {job.details}
                                    </pre>
                                  </TableCell>
                                </TableRow>
                              )}
                            </Fragment>
                          );
                        })}
                      </TableBody>
                    </Table>
                  </div>

                  <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
                    <p className="text-xs text-muted-foreground">
                      Mostrando {visibleJobs.length} de {filteredJobs.length}{" "}
                      tarefa(s) filtradas.
                    </p>
                    {visibleJobs.length < filteredJobs.length && (
                      <Button
                        variant="outline"
                        size="sm"
                        onClick={() => setVisibleCount(value => value + 25)}
                      >
                        Mostrar mais
                      </Button>
                    )}
                  </div>
                </div>
              ) : (
                <div className="py-16 text-center">
                  <p className="text-sm font-medium text-foreground">
                    Nenhuma tarefa encontrada.
                  </p>
                  <p className="mt-1 text-sm text-muted-foreground">
                    Ajuste o filtro ou execute uma ação no Monitor.
                  </p>
                </div>
              )}
            </CardContent>
          </Card>
        </div>
      </main>
    </div>
  );
}
