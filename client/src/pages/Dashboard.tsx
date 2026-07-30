import { useMemo, useState } from "react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader } from "@/components/ui/card";
import { Progress } from "@/components/ui/progress";
import {
  DashboardSkeleton,
  KpiTile,
  StatusBadge,
} from "@/components/dashboard/DashboardWidgets";
import {
  actionLabels,
  activityDescription,
  formatDateTime,
  greeting,
  hiddenRemoteActions,
  hostFromDetails,
  isActiveStatus,
  labelForRemoteAction,
} from "@/components/dashboard/dashboardUtils";
import type { DashboardData } from "@/components/dashboard/types";
import { EmptyState, PageShell, SectionHeading } from "@/components/PageLayout";
import { UniversalSearch } from "@/components/UniversalSearch";
import { useApi } from "@/hooks/useApi";
import { useAuthenticatedUser } from "@/hooks/useAuth";
import { useLocation } from "wouter";
import {
  Activity,
  AlertTriangle,
  ArrowRight,
  CheckCircle2,
  Clock3,
  FileText,
  HardDrive,
  History,
  Inbox,
  ListChecks,
  Loader2,
  MonitorUp,
  RefreshCw,
  Settings,
  Gauge,
  Server,
  ShieldCheck,
  TerminalSquare,
  Users,
  X,
} from "lucide-react";

export default function Dashboard() {
  const user = useAuthenticatedUser();
  const [, navigate] = useLocation();
  const { data, loading, error, refetch } = useApi<DashboardData>(
    "/api/dashboard",
    {
      refetchInterval: 10000,
    }
  );
  const [dismissedAttentionIds, setDismissedAttentionIds] = useState<
    Set<string>
  >(() => {
    try {
      const stored = window.localStorage.getItem(
        "wmt.dashboard.dismissedAttention"
      );
      const parsed = stored ? JSON.parse(stored) : [];
      return new Set(
        Array.isArray(parsed)
          ? parsed.filter((item): item is string => typeof item === "string")
          : []
      );
    } catch {
      return new Set();
    }
  });

  const displayName = user.display_name || user.username;
  const canAccess = (permission: string) =>
    user.permissions?.includes(permission);
  const canBackup = canAccess("backup");
  const backupSummary = canBackup ? data?.backup_summary : undefined;
  const remoteSummary = data?.remote_summary;
  const updateSummary = data?.update_summary;
  const backupJobs = canBackup ? data?.recent_jobs || [] : [];
  const remoteJobs = (data?.recent_remote_jobs || []).filter(
    job => !hiddenRemoteActions.has(job.action)
  );
  const updateJobs = data?.recent_update_jobs || [];
  const runningBackups = backupSummary?.running || 0;
  const failedBackups = backupSummary?.failed || 0;
  const activeRemote = remoteSummary?.active || 0;
  const failedRemote = remoteSummary?.failed || 0;
  const activeUpdates = updateSummary?.active || 0;
  const failedUpdates = updateSummary?.failed || 0;
  const totalActive = activeRemote + activeUpdates + runningBackups;
  const totalAttention = failedBackups + failedRemote + failedUpdates;
  const completedOperations =
    (backupSummary?.completed || 0) +
    (remoteSummary?.completed || 0) +
    (updateSummary?.completed || 0);
  const finishedOperations = completedOperations + totalAttention;
  const successRate = finishedOperations
    ? Math.round((completedOperations / finishedOperations) * 100)
    : 100;
  const healthLabel =
    totalAttention > 0
      ? "Ação necessária"
      : totalActive > 0
        ? "Operação em andamento"
        : "Ambiente estável";

  const navigateToHost = (host: string) => {
    const normalized = host.trim().toUpperCase();
    navigate(
      normalized
        ? `/monitor?host=${encodeURIComponent(normalized)}`
        : "/monitor"
    );
  };

  const activeWork = useMemo(() => {
    const backupItems = backupJobs
      .filter(job => isActiveStatus(job.status))
      .map(job => ({
        id: job.id,
        kind: "Backup",
        title: `${job.source || "Origem"} -> ${job.destination || "Destino"}`,
        detail: `${job.users} perfil(is) - ${job.summary || "Backup em andamento"}`,
        status: job.status,
        progress: job.progress || 0,
        date: job.start_time,
        path: "/backup",
      }));

    const remoteItems = remoteJobs
      .filter(job => isActiveStatus(job.status))
      .map(job => ({
        id: job.id,
        kind: "Task",
        title: `${job.host || "Host"} - ${labelForRemoteAction(job.action)}`,
        detail: job.message || "Tarefa remota em andamento",
        status: job.status,
        progress: null,
        date: job.started_at || job.created_at,
        path: "/tasks",
      }));

    const updateItems = updateJobs
      .filter(job => isActiveStatus(job.status))
      .map(job => ({
        id: job.id,
        kind: "Update",
        title: `${job.host || "Host"} - SCCM Updates`,
        detail:
          job.message || `${job.pending_updates || 0} update(s) pendente(s)`,
        status: job.status,
        progress: job.progress || 0,
        date: job.started_at || job.created_at,
        path: job.host
          ? `/monitor?host=${encodeURIComponent(job.host)}`
          : "/monitor",
      }));

    return [...updateItems, ...remoteItems, ...backupItems].slice(0, 7);
  }, [backupJobs, remoteJobs, updateJobs]);

  const dismissAttentionItem = (itemId: string) => {
    setDismissedAttentionIds(current => {
      const next = new Set(current);
      next.add(itemId);
      const storedIds = Array.from(next).slice(-200);
      window.localStorage.setItem(
        "wmt.dashboard.dismissedAttention",
        JSON.stringify(storedIds)
      );
      return new Set(storedIds);
    });
  };

  const reviewFailures = () => {
    window.requestAnimationFrame(() => {
      const section = document.getElementById("dashboard-attention");
      section?.scrollIntoView({ behavior: "smooth", block: "start" });
      section?.focus({ preventScroll: true });
    });
  };

  const attentionItems = useMemo(() => {
    const backupItems = backupJobs
      .filter(job => job.status === "failed")
      .map(job => ({
        id: `backup-${job.id}`,
        title: `Backup falhou: ${job.source || "Origem"} -> ${job.destination || "Destino"}`,
        detail: job.summary || "Verifique o log do backup.",
        path: "/backup",
        date: job.end_time || job.start_time,
      }));

    const remoteItems = remoteJobs
      .filter(job => job.status === "failed")
      .map(job => ({
        id: `remote-${job.id}`,
        title: `Task falhou: ${job.host || "Host"}`,
        detail: job.message || labelForRemoteAction(job.action),
        path: "/tasks",
        date: job.ended_at || job.created_at,
      }));

    const updateItems = updateJobs
      .filter(job => job.status === "failed")
      .map(job => ({
        id: `update-${job.id}`,
        title: `Update falhou: ${job.host || "Host"}`,
        detail: job.message || "Verifique o Software Center/SCCM Client.",
        path: job.host
          ? `/monitor?host=${encodeURIComponent(job.host)}`
          : "/monitor",
        date: job.ended_at || job.created_at,
      }));

    return [...updateItems, ...remoteItems, ...backupItems]
      .filter(item => !dismissedAttentionIds.has(item.id))
      .slice(0, 7);
  }, [backupJobs, dismissedAttentionIds, remoteJobs, updateJobs]);

  const recentOperations = useMemo(() => {
    const operations = [
      ...backupJobs.map(job => ({
        id: `backup-${job.id}`,
        type: "Backup",
        title: `${job.source || "Origem"} → ${job.destination || "Destino"}`,
        detail: `${job.users} perfil(is)${job.summary ? ` · ${job.summary}` : ""}`,
        status: job.status,
        date: job.end_time || job.start_time,
        path: "/backup",
      })),
      ...remoteJobs.map(job => ({
        id: `remote-${job.id}`,
        type: "Task remota",
        title: `${job.host || "Host não informado"} · ${labelForRemoteAction(job.action)}`,
        detail: job.message || "Ação remota registrada",
        status: job.status,
        date: job.ended_at || job.started_at || job.created_at,
        path: "/tasks",
      })),
      ...updateJobs.map(job => ({
        id: `update-${job.id}`,
        type: "Update",
        title: job.host || "Host não informado",
        detail:
          job.message || `${job.pending_updates || 0} update(s) pendente(s)`,
        status: job.status,
        date: job.ended_at || job.started_at || job.created_at,
        path: job.host
          ? `/monitor?host=${encodeURIComponent(job.host)}`
          : "/monitor",
      })),
    ];
    return operations
      .filter(operation => operation.status !== "queued" || operation.date)
      .sort(
        (a, b) =>
          new Date(b.date || 0).getTime() - new Date(a.date || 0).getTime()
      )
      .slice(0, 8);
  }, [backupJobs, remoteJobs, updateJobs]);

  const trendMax = Math.max(
    1,
    ...(data?.trends?.days || []).map(day => day.total)
  );

  const recentHosts = useMemo(() => {
    const hosts = [
      ...updateJobs.map(job => job.host),
      ...remoteJobs.map(job => job.host),
      ...(data?.recent_activities || []).map(activity =>
        hostFromDetails(activity.details)
      ),
    ]
      .map(host =>
        String(host || "")
          .trim()
          .toUpperCase()
      )
      .filter(Boolean);

    return Array.from(new Set(hosts)).slice(0, 8);
  }, [data?.recent_activities, remoteJobs, updateJobs]);

  return (
    <PageShell>
      <section className="wmt-header relative z-30 overflow-visible rounded-xl border p-5 text-slate-100 shadow-lg sm:p-6 lg:p-7">
        <div className="pointer-events-none absolute inset-0 overflow-hidden rounded-[inherit]">
          <div className="absolute -right-24 -top-24 size-72 rounded-full bg-primary/20 blur-3xl" />
          <div className="absolute -bottom-28 left-1/3 size-64 rounded-full bg-primary/10 blur-3xl" />
        </div>
        <div className="relative z-10 grid gap-6 lg:grid-cols-[minmax(0,1fr)_minmax(300px,0.8fr)] lg:items-end">
          <div className="min-w-0">
            <div className="mb-4 flex flex-wrap items-center gap-2 text-xs font-medium text-slate-400">
              <span className="inline-flex items-center gap-1.5 rounded-full border border-emerald-400/30 bg-emerald-400/10 px-2.5 py-1 text-emerald-300">
                <span className="size-1.5 rounded-full bg-emerald-400" />{" "}
                Sistema conectado
              </span>
              <span className="inline-flex items-center gap-1.5">
                <Clock3 size={13} /> Atualização automática em 10s
              </span>
            </div>
            <p className="text-sm font-medium text-blue-300">
              {greeting()}, operador
            </p>
            <h1 className="mt-1 break-words text-3xl font-semibold tracking-tight text-white sm:text-4xl">
              {displayName}
            </h1>
            <p className="mt-3 max-w-2xl text-sm leading-6 text-slate-400">
              Central de operações do WMT. Monitore a saúde do ambiente, execute
              rotinas e resolva pendências em um único lugar.
            </p>
            <div className="mt-5 flex flex-wrap items-center gap-2">
              <Badge
                variant="outline"
                className="border-blue-400/30 bg-blue-400/10 text-blue-200"
              >
                <ShieldCheck size={13} />{" "}
                {user.auth_source === "windows"
                  ? "Windows SSO"
                  : "Sessão local"}
              </Badge>
              <Badge
                variant="outline"
                className="border-slate-700 bg-slate-900 text-slate-300 capitalize"
              >
                {user.role}
              </Badge>
            </div>
          </div>
          <div className="min-w-0 rounded-lg border border-white/10 bg-white/[0.06] p-3 shadow-inner">
            <p className="mb-2 text-[11px] font-semibold uppercase tracking-[0.14em] text-slate-400">
              Busca rápida
            </p>
            <UniversalSearch />
            <p className="mt-2 text-xs text-slate-500">
              Procure por hostname, usuário ou número de patrimônio.
            </p>
          </div>
        </div>
      </section>

      {loading && !data ? (
        <DashboardSkeleton />
      ) : error ? (
        <div
          role="alert"
          className="flex flex-col gap-4 rounded-lg border border-red-300 bg-red-50 p-5 text-red-900 dark:border-red-400/30 dark:bg-red-500/10 dark:text-red-100 sm:flex-row sm:items-center sm:justify-between"
        >
          <div className="flex items-start gap-3">
            <AlertTriangle className="mt-0.5 shrink-0" size={19} />
            <div>
              <p className="text-sm font-semibold">
                Não foi possível carregar o Dashboard
              </p>
              <p className="mt-1 text-sm text-red-800/80 dark:text-red-100/75">
                {error}
              </p>
            </div>
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
            Tentar novamente
          </Button>
        </div>
      ) : (
        <>
          <section
            aria-label="Indicadores operacionais"
            className="grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-5"
          >
            <KpiTile
              icon={ListChecks}
              label="Ativas"
              value={totalActive}
              helper={`${activeRemote} remota(s), ${activeUpdates} update(s), ${runningBackups} backup(s)`}
              tone="border-blue-300 bg-blue-50 text-blue-700 dark:border-blue-400/40 dark:bg-blue-500/10 dark:text-blue-200"
            />
            <KpiTile
              icon={AlertTriangle}
              label="Atenção"
              value={totalAttention}
              helper={`${failedRemote} task(s), ${failedUpdates} update(s), ${failedBackups} backup(s)`}
              tone="border-red-300 bg-red-50 text-red-700 dark:border-red-400/40 dark:bg-red-500/10 dark:text-red-200"
            />
            <KpiTile
              icon={MonitorUp}
              label="Updates"
              value={activeUpdates}
              helper={`${failedUpdates} falha(s), ${updateSummary?.completed || 0} concluído(s)`}
              tone="border-cyan-300 bg-cyan-50 text-cyan-700 dark:border-cyan-400/40 dark:bg-cyan-500/10 dark:text-cyan-200"
            />
            <KpiTile
              icon={HardDrive}
              label="Backups hoje"
              value={backupSummary?.finished_today || 0}
              helper={`${runningBackups} rodando, ${failedBackups} falha(s)`}
              tone="border-emerald-300 bg-emerald-50 text-emerald-700 dark:border-emerald-400/40 dark:bg-emerald-500/10 dark:text-emerald-200"
            />
            <KpiTile
              icon={FileText}
              label="Termos"
              value={data?.terms_today || 0}
              helper={`${data?.active_users || 0} usuário(s) ativo(s)`}
              tone="border-violet-300 bg-violet-50 text-violet-700 dark:border-violet-400/40 dark:bg-violet-500/10 dark:text-violet-200"
            />
          </section>

          <section
            aria-label="Saúde operacional"
            className={`rounded-lg border p-4 shadow-sm ${
              totalAttention > 0
                ? "border-red-300/70 bg-red-50/80 dark:border-red-400/30 dark:bg-red-500/10"
                : "border-emerald-300/70 bg-emerald-50/80 dark:border-emerald-400/30 dark:bg-emerald-500/10"
            }`}
          >
            <div className="flex flex-col gap-4 lg:flex-row lg:items-center lg:justify-between">
              <div className="flex min-w-0 items-start gap-3">
                <div className="mt-0.5 flex size-10 shrink-0 items-center justify-center rounded-lg bg-background/80 shadow-sm">
                  {totalAttention > 0 ? (
                    <AlertTriangle
                      className="text-red-600 dark:text-red-300"
                      size={19}
                    />
                  ) : (
                    <Gauge
                      className="text-emerald-600 dark:text-emerald-300"
                      size={19}
                    />
                  )}
                </div>
                <div className="min-w-0">
                  <div className="flex flex-wrap items-center gap-2">
                    <h2 className="text-sm font-semibold text-foreground">
                      {healthLabel}
                    </h2>
                    <Badge variant="outline">
                      Taxa de sucesso: {successRate}%
                    </Badge>
                  </div>
                  <p className="mt-1 text-sm text-muted-foreground">
                    {totalAttention > 0
                      ? `${totalAttention} operação(ões) falharam e precisam de revisão.`
                      : totalActive > 0
                        ? `${totalActive} operação(ões) estão sendo processadas agora.`
                        : "Não há falhas abertas ou operações aguardando execução."}
                  </p>
                </div>
              </div>
              <div className="flex flex-wrap gap-2">
                {totalAttention > 0 && (
                  <Button size="sm" onClick={reviewFailures}>
                    <AlertTriangle size={15} /> Revisar falhas
                  </Button>
                )}
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => refetch()}
                  disabled={loading}
                >
                  <RefreshCw
                    className={loading ? "animate-spin" : ""}
                    size={15}
                  />
                  Atualizar agora
                </Button>
              </div>
            </div>
          </section>

          <Card className="rounded-lg border-border/70 shadow-none">
            <CardHeader>
              <SectionHeading
                title="Ritmo operacional"
                description="Volume e resultado das operações nos últimos sete dias."
              />
            </CardHeader>
            <CardContent>
              <div className="grid min-h-40 grid-cols-7 items-end gap-2 sm:gap-4">
                {(data?.trends?.days || []).map(day => (
                  <div
                    key={day.date}
                    className="flex min-w-0 flex-col items-center gap-2"
                  >
                    <div className="flex h-28 w-full items-end justify-center gap-1 rounded-md bg-muted/30 px-1 pt-2">
                      <div
                        className="w-1/2 rounded-t-sm bg-primary transition-all"
                        style={{
                          height: `${Math.max(5, (day.completed / trendMax) * 100)}%`,
                        }}
                        title={`${day.completed} concluída(s)`}
                      />
                      <div
                        className="w-1/2 rounded-t-sm bg-red-500/80 transition-all"
                        style={{
                          height: `${Math.max(5, (day.failed / trendMax) * 100)}%`,
                        }}
                        title={`${day.failed} falha(s)`}
                      />
                    </div>
                    <span className="text-[11px] text-muted-foreground">
                      {day.label}
                    </span>
                    <span className="text-xs font-semibold text-foreground">
                      {day.total}
                    </span>
                  </div>
                ))}
              </div>
              {!data?.trends?.days?.length && (
                <EmptyState
                  icon={Activity}
                  title="Sem dados históricos"
                  description="As métricas aparecerão após as primeiras operações registradas."
                  className="min-h-28"
                />
              )}
              <div className="mt-3 flex flex-wrap gap-4 text-xs text-muted-foreground">
                <span className="inline-flex items-center gap-1.5">
                  <span className="size-2 rounded-full bg-primary" /> Concluídas
                </span>
                <span className="inline-flex items-center gap-1.5">
                  <span className="size-2 rounded-full bg-red-500/80" /> Falhas
                </span>
              </div>
            </CardContent>
          </Card>

          <div className="grid grid-cols-1 gap-5 xl:grid-cols-[minmax(0,1.35fr)_minmax(320px,0.65fr)]">
            <div className="space-y-5">
              <Card className="rounded-lg border-border/70 shadow-none">
                <CardHeader>
                  <SectionHeading
                    title="Agora no WMT"
                    description="Operações que estão ativas ou abertas neste momento."
                    action={
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
                        Atualizar
                      </Button>
                    }
                  />
                </CardHeader>
                <CardContent className="space-y-3">
                  {activeWork.length ? (
                    activeWork.map(item => (
                      <button
                        key={`${item.kind}-${item.id}`}
                        type="button"
                        className="interactive-row w-full p-4 text-left"
                        onClick={() => navigate(item.path)}
                      >
                        <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
                          <div className="min-w-0">
                            <div className="flex flex-wrap items-center gap-2">
                              <Badge variant="outline">{item.kind}</Badge>
                              <StatusBadge status={item.status} />
                            </div>
                            <p className="mt-2 break-words text-sm font-semibold text-foreground">
                              {item.title}
                            </p>
                            <p className="mt-1 line-clamp-2 text-sm text-muted-foreground">
                              {item.detail}
                            </p>
                          </div>
                          <span className="shrink-0 text-xs text-muted-foreground">
                            {formatDateTime(item.date)}
                          </span>
                        </div>
                        {typeof item.progress === "number" && (
                          <div className="mt-3">
                            <Progress value={item.progress} className="h-2" />
                            <p className="mt-1 text-right text-xs text-muted-foreground">
                              {item.progress}%
                            </p>
                          </div>
                        )}
                      </button>
                    ))
                  ) : (
                    <EmptyState
                      icon={CheckCircle2}
                      title="Nenhuma operação em execução"
                      description="As próximas tarefas ativas aparecerão aqui automaticamente."
                    />
                  )}
                </CardContent>
              </Card>

              <Card
                id="dashboard-attention"
                tabIndex={-1}
                className="scroll-mt-6 rounded-lg border-border/70 shadow-none focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
              >
                <CardHeader>
                  <SectionHeading
                    title="Precisa de atenção"
                    description="Falhas recentes para resolver sem precisar procurar em cada tela."
                  />
                </CardHeader>
                <CardContent className="space-y-3">
                  {attentionItems.length ? (
                    attentionItems.map(item => (
                      <div
                        key={item.id}
                        className="relative overflow-hidden rounded-lg border border-red-300/60 bg-red-50/80 shadow-sm dark:border-red-400/30 dark:bg-red-500/10"
                      >
                        <button
                          type="button"
                          className="w-full p-3 pr-12 text-left transition-colors hover:bg-red-100/60 dark:hover:bg-red-500/10"
                          onClick={() => navigate(item.path)}
                        >
                          <div className="flex items-start gap-3">
                            <AlertTriangle
                              className="mt-0.5 shrink-0 text-red-600 dark:text-red-300"
                              size={17}
                            />
                            <div className="min-w-0">
                              <p className="break-words text-sm font-semibold text-red-800 dark:text-red-200">
                                {item.title}
                              </p>
                              <p className="mt-1 line-clamp-2 text-xs text-red-700/80 dark:text-red-200/80">
                                {item.detail}
                              </p>
                              <p className="mt-2 text-xs text-red-700/70 dark:text-red-200/70">
                                {formatDateTime(item.date)}
                              </p>
                            </div>
                          </div>
                        </button>
                        <button
                          type="button"
                          className="absolute right-2 top-2 flex size-8 items-center justify-center rounded-md text-red-700/70 transition-colors hover:bg-red-200/70 hover:text-red-900 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-red-500 dark:text-red-200/70 dark:hover:bg-red-400/20 dark:hover:text-red-100"
                          title="Excluir falha da lista"
                          aria-label={`Excluir falha da lista: ${item.title}`}
                          onClick={() => dismissAttentionItem(item.id)}
                        >
                          <X size={17} />
                        </button>
                      </div>
                    ))
                  ) : (
                    <div className="rounded-lg border border-emerald-300 bg-emerald-50 p-4 text-sm text-emerald-800 dark:border-emerald-400/30 dark:bg-emerald-500/10 dark:text-emerald-200">
                      <div className="flex items-center gap-2">
                        <ShieldCheck size={17} />
                        Sem falhas recentes em operações acompanhadas.
                      </div>
                    </div>
                  )}
                </CardContent>
              </Card>
            </div>

            <div className="space-y-5">
              <Card className="rounded-lg border-border/70 shadow-none">
                <CardHeader>
                  <SectionHeading
                    title="Hosts recentes"
                    description="Acesso rápido aos equipamentos vistos nas operações."
                  />
                </CardHeader>
                <CardContent className="space-y-2">
                  {recentHosts.length ? (
                    recentHosts.map(host => (
                      <button
                        key={host}
                        type="button"
                        className="flex w-full items-center justify-between gap-3 rounded-lg border border-border/70 bg-card/70 px-3 py-2 text-left transition-colors hover:bg-muted/40"
                        onClick={() => navigateToHost(host)}
                      >
                        <span className="min-w-0 truncate text-sm font-semibold text-foreground">
                          {host}
                        </span>
                        <ArrowRight
                          size={15}
                          className="shrink-0 text-muted-foreground"
                        />
                      </button>
                    ))
                  ) : (
                    <EmptyState
                      icon={MonitorUp}
                      title="Nenhum host recente"
                      description="Equipamentos consultados e usados em operações aparecerão aqui."
                      className="min-h-28"
                    />
                  )}
                </CardContent>
              </Card>

              <Card className="rounded-lg border-border/70 shadow-none">
                <CardHeader>
                  <SectionHeading
                    title="Atalhos operacionais"
                    description="Entradas rápidas para as rotinas mais usadas."
                  />
                </CardHeader>
                <CardContent className="grid gap-2">
                  {canAccess("monitor") && (
                    <Button
                      variant="outline"
                      className="min-h-12 justify-between bg-card/80 px-4"
                      onClick={() => navigate("/monitor")}
                    >
                      <span className="inline-flex items-center gap-2">
                        <MonitorUp size={17} /> Monitor
                      </span>
                      <ArrowRight size={16} />
                    </Button>
                  )}
                  {canAccess("tasks") && (
                    <Button
                      variant="outline"
                      className="min-h-12 justify-between bg-card/80 px-4"
                      onClick={() => navigate("/tasks")}
                    >
                      <span className="inline-flex items-center gap-2">
                        <TerminalSquare size={17} /> Remote Tasks
                      </span>
                      <ArrowRight size={16} />
                    </Button>
                  )}
                  {canAccess("history") && (
                    <Button
                      variant="outline"
                      className="min-h-12 justify-between bg-card/80 px-4"
                      onClick={() => navigate("/history")}
                    >
                      <span className="inline-flex items-center gap-2">
                        <History size={17} /> Histórico
                      </span>
                      <ArrowRight size={16} />
                    </Button>
                  )}
                  {canAccess("backup") && (
                    <Button
                      variant="outline"
                      className="min-h-12 justify-between bg-card/80 px-4"
                      onClick={() => navigate("/backup")}
                    >
                      <span className="inline-flex items-center gap-2">
                        <HardDrive size={17} /> Backup
                      </span>
                      <ArrowRight size={16} />
                    </Button>
                  )}
                  {canAccess("terms") && (
                    <Button
                      variant="outline"
                      className="min-h-12 justify-between bg-card/80 px-4"
                      onClick={() => navigate("/terms")}
                    >
                      <span className="inline-flex items-center gap-2">
                        <FileText size={17} /> Termos
                      </span>
                      <ArrowRight size={16} />
                    </Button>
                  )}
                </CardContent>
              </Card>
            </div>
          </div>

          <Card className="rounded-lg border-border/70 shadow-none">
            <CardHeader>
              <SectionHeading
                title="Operações recentes"
                description="Últimas execuções de backup, tarefas remotas e atualizações, em uma única fila."
                action={
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={() => navigate("/history")}
                  >
                    Ver histórico <ArrowRight size={15} />
                  </Button>
                }
              />
            </CardHeader>
            <CardContent>
              {recentOperations.length ? (
                <div className="grid gap-2 lg:grid-cols-2">
                  {recentOperations.map(operation => (
                    <button
                      key={operation.id}
                      type="button"
                      className="interactive-row flex min-w-0 items-center gap-3 p-3 text-left"
                      onClick={() => navigate(operation.path)}
                    >
                      <div className="flex size-9 shrink-0 items-center justify-center rounded-md border border-border bg-muted/70">
                        {operation.type === "Backup" ? (
                          <HardDrive size={16} />
                        ) : operation.type === "Update" ? (
                          <MonitorUp size={16} />
                        ) : (
                          <TerminalSquare size={16} />
                        )}
                      </div>
                      <div className="min-w-0 flex-1">
                        <div className="flex flex-wrap items-center gap-2">
                          <span className="text-[11px] font-semibold uppercase tracking-wide text-muted-foreground">
                            {operation.type}
                          </span>
                          <StatusBadge status={operation.status} />
                        </div>
                        <p className="mt-1 truncate text-sm font-medium text-foreground">
                          {operation.title}
                        </p>
                        <p className="truncate text-xs text-muted-foreground">
                          {operation.detail}
                        </p>
                      </div>
                      <span className="shrink-0 text-xs text-muted-foreground">
                        {formatDateTime(operation.date)}
                      </span>
                    </button>
                  ))}
                </div>
              ) : (
                <EmptyState
                  icon={Server}
                  title="Nenhuma operação registrada"
                  description="Quando uma rotina for executada, o resultado aparecerá aqui."
                />
              )}
            </CardContent>
          </Card>

          <Card className="rounded-lg border-border/70 shadow-none">
            <CardHeader className="flex flex-row items-start justify-between gap-3">
              <SectionHeading
                title="Atividade recente"
                description="Eventos relevantes registrados pelo WMT."
              />
              {user.role === "admin" && (
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => navigate("/admin/users")}
                >
                  <Users size={15} />
                  Users
                </Button>
              )}
            </CardHeader>
            <CardContent>
              {data?.recent_activities?.length ? (
                <div className="grid gap-3 lg:grid-cols-2">
                  {data.recent_activities.slice(0, 8).map(activity => {
                    const host = hostFromDetails(activity.details);
                    return (
                      <button
                        key={activity.id}
                        type="button"
                        disabled={!host}
                        className="flex gap-3 rounded-lg border border-border/70 bg-card/70 p-3 text-left transition-colors hover:bg-muted/40 disabled:cursor-default disabled:hover:bg-card/70"
                        onClick={() =>
                          host ? navigateToHost(host) : undefined
                        }
                      >
                        <div className="mt-0.5 flex size-8 shrink-0 items-center justify-center rounded-md border border-border bg-muted">
                          {activity.action.startsWith("terms.") ? (
                            <FileText size={15} />
                          ) : activity.action.startsWith("backup.") ? (
                            <HardDrive size={15} />
                          ) : activity.action.startsWith("remote.") ? (
                            <TerminalSquare size={15} />
                          ) : (
                            <CheckCircle2 size={15} />
                          )}
                        </div>
                        <div className="min-w-0 flex-1">
                          <div className="flex items-start justify-between gap-3">
                            <p className="truncate text-sm font-medium text-foreground">
                              {actionLabels[activity.action] || activity.action}
                            </p>
                            <span className="shrink-0 text-xs text-muted-foreground">
                              {formatDateTime(activity.timestamp)}
                            </span>
                          </div>
                          <p className="mt-0.5 line-clamp-2 text-sm text-muted-foreground">
                            {activityDescription(activity)}
                          </p>
                          <p className="mt-1 text-xs text-muted-foreground">
                            por {activity.username || "system"}
                          </p>
                        </div>
                      </button>
                    );
                  })}
                </div>
              ) : (
                <EmptyState
                  icon={Inbox}
                  title="Nenhuma atividade recente"
                  description="As ações realizadas no WMT serão registradas neste espaço."
                />
              )}
            </CardContent>
          </Card>

          <section className="flex flex-wrap items-center justify-between gap-3 rounded-lg border border-border/70 bg-card px-4 py-3 text-xs text-muted-foreground">
            <span>Dashboard atualiza automaticamente a cada 10s.</span>
            <Button
              variant="ghost"
              size="sm"
              onClick={() => navigate("/account")}
            >
              <Settings size={15} />
              Conta
            </Button>
          </section>
        </>
      )}
    </PageShell>
  );
}
