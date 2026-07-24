import { useMemo, useState } from 'react';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Progress } from '@/components/ui/progress';
import { Sidebar } from '@/components/Sidebar';
import { UniversalSearch } from '@/components/UniversalSearch';
import { useApi } from '@/hooks/useApi';
import { useAuth } from '@/hooks/useAuth';
import { useLocation } from 'wouter';
import {
  Activity,
  AlertTriangle,
  ArrowRight,
  CheckCircle2,
  Clock3,
  FileText,
  HardDrive,
  History,
  ListChecks,
  Loader2,
  MonitorUp,
  RefreshCw,
  Settings,
  ShieldCheck,
  TerminalSquare,
  Users,
  X,
} from 'lucide-react';

type JobStatus = 'queued' | 'running' | 'completed' | 'failed' | 'canceled' | string;

interface DashboardActivity {
  id: string;
  action: string;
  username: string;
  details?: Record<string, unknown>;
  timestamp: string;
}

interface DashboardBackupJob {
  id: string;
  source: string;
  destination: string;
  users: number;
  status: JobStatus;
  progress: number;
  start_time: string;
  end_time: string;
  summary: string;
}

interface DashboardRemoteJob {
  id: string;
  host: string;
  action: string;
  status: JobStatus;
  ok: boolean;
  message: string;
  created_by: string;
  created_at: string;
  started_at: string;
  ended_at: string;
  duration_ms: number;
}

interface DashboardUpdateJob {
  id: string;
  host: string;
  status: JobStatus;
  ok: boolean;
  message: string;
  created_by: string;
  created_at: string;
  started_at: string;
  ended_at: string;
  duration_ms: number;
  progress: number;
  pending_updates: number;
}

interface DashboardData {
  terms_today: number;
  active_users: number;
  backup_summary: {
    total: number;
    running: number;
    completed: number;
    failed: number;
    canceled: number;
    finished_today: number;
  };
  remote_summary?: {
    total: number;
    active: number;
    completed: number;
    failed: number;
  };
  update_summary?: {
    total: number;
    active: number;
    completed: number;
    failed: number;
  };
  recent_activities: DashboardActivity[];
  recent_jobs: DashboardBackupJob[];
  recent_remote_jobs?: DashboardRemoteJob[];
  recent_update_jobs?: DashboardUpdateJob[];
}

const actionLabels: Record<string, string> = {
  'auth.login': 'Login local',
  'auth.sso': 'Windows SSO',
  'backup.create': 'Backup iniciado',
  'backup.delete': 'Backup removido',
  'backup.load_users': 'Perfis carregados',
  'backup.open_destination': 'Destino aberto',
  'remote.action': 'Ação remota',
  'remote.job.create': 'Tarefa remota criada',
  'remote.job.cancel': 'Tarefa remota cancelada',
  'software_center.install_updates': 'Updates iniciados',
  'terms.generate': 'Termo DOCX',
  'terms.print': 'Prévia de impressão',
  'diagnostics.run': 'Diagnóstico iniciado',
  'diagnostics.job': 'Diagnóstico registrado',
  'cleanup.quick': 'Limpeza rápida',
};

const remoteActionLabels: Record<string, string> = {
  'remote-access': 'Remote Access',
  'remote-assistance': 'Remote Assistance',
  'computer-management': 'Computer Management',
  'restart-spooler': 'Restart Spooler',
  'renew-ip': 'Renew IP',
  gpupdate: 'GPUpdate',
  'force-all-actions': 'Force All Actions',
  'clear-sccm-cache': 'Clear SCCM Cache',
};

const hiddenRemoteActions = new Set(['create-temp-c-share', 'remove-temp-c-share']);

const statusStyles: Record<string, string> = {
  queued: 'border-zinc-300 bg-zinc-50 text-zinc-700 dark:border-zinc-500/40 dark:bg-zinc-500/10 dark:text-zinc-200',
  running: 'border-blue-300 bg-blue-50 text-blue-700 dark:border-blue-400/40 dark:bg-blue-500/10 dark:text-blue-200',
  completed: 'border-emerald-300 bg-emerald-50 text-emerald-700 dark:border-emerald-400/40 dark:bg-emerald-500/10 dark:text-emerald-200',
  failed: 'border-red-300 bg-red-50 text-red-700 dark:border-red-400/40 dark:bg-red-500/10 dark:text-red-200',
  canceled: 'border-amber-300 bg-amber-50 text-amber-700 dark:border-amber-400/40 dark:bg-amber-500/10 dark:text-amber-200',
};

function formatDateTime(value?: string) {
  if (!value) return 'Sem data';
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return value;
  return new Intl.DateTimeFormat('pt-BR', {
    day: '2-digit',
    month: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  }).format(parsed);
}

function greeting() {
  const hour = new Date().getHours();
  if (hour < 12) return 'Bom dia';
  if (hour < 18) return 'Boa tarde';
  return 'Boa noite';
}

function labelForRemoteAction(action: string) {
  return remoteActionLabels[action] || action || 'Ação remota';
}

function hostFromDetails(details?: Record<string, unknown>) {
  if (!details) return '';
  return String(details.host || details.wk || details.source || details.destination || '').toUpperCase();
}

function activityDescription(activity: DashboardActivity) {
  const details = activity.details || {};

  if (activity.action.startsWith('backup.')) {
    const source = String(details.source || '');
    const destination = String(details.destination || '');
    const count = Number(details.users_count || details.count || 0);
    if (source && destination) return `${source} -> ${destination}${count ? `, ${count} perfil(is)` : ''}`;
    if (source) return `${source}${count ? `, ${count} perfil(is)` : ''}`;
  }

  if (activity.action.startsWith('remote.')) {
    const host = String(details.host || '');
    const action = String(details.action || '');
    const jobId = String(details.job_id || '');
    return [host, labelForRemoteAction(action), jobId].filter(Boolean).join(' - ');
  }

  if (activity.action === 'software_center.install_updates') {
    const host = String(details.host || '');
    return host ? `Host ${host}` : 'Software Center';
  }

  if (activity.action.startsWith('terms.')) {
    const wk = String(details.wk || '');
    const employee = String(details.employee_name || '');
    return [wk, employee].filter(Boolean).join(' - ') || 'Termo gerado';
  }

  return actionLabels[activity.action] || activity.action;
}

function isActiveStatus(status: JobStatus) {
  return status === 'queued' || status === 'running';
}

function StatusBadge({ status }: { status: JobStatus }) {
  return (
    <Badge variant="outline" className={statusStyles[status] || 'border-border'}>
      {isActiveStatus(status) && <Loader2 className="animate-spin" size={13} />}
      {status}
    </Badge>
  );
}

function KpiTile({
  label,
  value,
  helper,
  icon: Icon,
  tone,
}: {
  label: string;
  value: number;
  helper: string;
  icon: typeof Activity;
  tone: string;
}) {
  return (
    <div className="relative overflow-hidden rounded-lg border border-border/70 bg-card/95 px-4 py-3 shadow-sm backdrop-blur">
      <div className={`absolute inset-x-0 top-0 h-1 ${tone.split(' ').find((item) => item.startsWith('bg-')) || 'bg-primary'}`} />
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <p className="text-[11px] font-semibold uppercase tracking-wide text-muted-foreground">{label}</p>
          <p className="mt-2 text-2xl font-semibold text-foreground">{value}</p>
        </div>
        <div className={`rounded-md border p-2 shadow-sm ${tone}`}>
          <Icon size={17} />
        </div>
      </div>
      <p className="mt-3 line-clamp-2 text-xs text-muted-foreground">{helper}</p>
    </div>
  );
}

function EmptyState({ text }: { text: string }) {
  return (
    <div className="rounded-lg border border-dashed border-border/80 px-4 py-8 text-center">
      <p className="text-sm text-muted-foreground">{text}</p>
    </div>
  );
}

function SectionHeader({
  title,
  subtitle,
  action,
}: {
  title: string;
  subtitle?: string;
  action?: React.ReactNode;
}) {
  return (
    <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
      <div className="min-w-0">
        <CardTitle>{title}</CardTitle>
        {subtitle && <p className="mt-1 text-sm text-muted-foreground">{subtitle}</p>}
      </div>
      {action}
    </div>
  );
}

export default function Dashboard() {
  const { user, logout } = useAuth();
  const [, navigate] = useLocation();
  const { data, loading, error, refetch } = useApi<DashboardData>('/api/dashboard', {
    refetchInterval: 10000,
  });
  const [dismissedAttentionIds, setDismissedAttentionIds] = useState<Set<string>>(() => {
    try {
      const stored = window.localStorage.getItem('wmt.dashboard.dismissedAttention');
      const parsed = stored ? JSON.parse(stored) : [];
      return new Set(Array.isArray(parsed) ? parsed.filter((item): item is string => typeof item === 'string') : []);
    } catch {
      return new Set();
    }
  });

  const handleLogout = async () => {
    await logout();
    navigate('/login');
  };

  if (!user) {
    navigate('/login');
    return null;
  }

  const displayName = user.display_name || user.username;
  const canAccess = (permission: string) => user.permissions?.includes(permission);
  const canBackup = canAccess('backup');
  const backupSummary = canBackup ? data?.backup_summary : undefined;
  const remoteSummary = data?.remote_summary;
  const updateSummary = data?.update_summary;
  const backupJobs = canBackup ? data?.recent_jobs || [] : [];
  const remoteJobs = (data?.recent_remote_jobs || []).filter((job) => !hiddenRemoteActions.has(job.action));
  const updateJobs = data?.recent_update_jobs || [];
  const runningBackups = backupSummary?.running || 0;
  const failedBackups = backupSummary?.failed || 0;
  const activeRemote = remoteSummary?.active || 0;
  const failedRemote = remoteSummary?.failed || 0;
  const activeUpdates = updateSummary?.active || 0;
  const failedUpdates = updateSummary?.failed || 0;
  const totalActive = activeRemote + activeUpdates + runningBackups;
  const totalAttention = failedBackups + failedRemote + failedUpdates;

  const navigateToHost = (host: string) => {
    const normalized = host.trim().toUpperCase();
    navigate(normalized ? `/monitor?host=${encodeURIComponent(normalized)}` : '/monitor');
  };

  const activeWork = useMemo(() => {
    const backupItems = backupJobs
      .filter((job) => isActiveStatus(job.status))
      .map((job) => ({
        id: job.id,
        kind: 'Backup',
        title: `${job.source || 'Origem'} -> ${job.destination || 'Destino'}`,
        detail: `${job.users} perfil(is) - ${job.summary || 'Backup em andamento'}`,
        status: job.status,
        progress: job.progress || 0,
        date: job.start_time,
        path: '/backup',
      }));

    const remoteItems = remoteJobs
      .filter((job) => isActiveStatus(job.status))
      .map((job) => ({
        id: job.id,
        kind: 'Task',
        title: `${job.host || 'Host'} - ${labelForRemoteAction(job.action)}`,
        detail: job.message || 'Tarefa remota em andamento',
        status: job.status,
        progress: null,
        date: job.started_at || job.created_at,
        path: '/tasks',
      }));

    const updateItems = updateJobs
      .filter((job) => isActiveStatus(job.status))
      .map((job) => ({
        id: job.id,
        kind: 'Update',
        title: `${job.host || 'Host'} - SCCM Updates`,
        detail: job.message || `${job.pending_updates || 0} update(s) pendente(s)`,
        status: job.status,
        progress: job.progress || 0,
        date: job.started_at || job.created_at,
        path: job.host ? `/monitor?host=${encodeURIComponent(job.host)}` : '/monitor',
      }));

    return [...updateItems, ...remoteItems, ...backupItems].slice(0, 7);
  }, [backupJobs, remoteJobs, updateJobs]);

  const dismissAttentionItem = (itemId: string) => {
    setDismissedAttentionIds((current) => {
      const next = new Set(current);
      next.add(itemId);
      const storedIds = Array.from(next).slice(-200);
      window.localStorage.setItem('wmt.dashboard.dismissedAttention', JSON.stringify(storedIds));
      return new Set(storedIds);
    });
  };

  const attentionItems = useMemo(() => {
    const backupItems = backupJobs
      .filter((job) => job.status === 'failed')
      .map((job) => ({
        id: job.id,
        title: `Backup falhou: ${job.source || 'Origem'} -> ${job.destination || 'Destino'}`,
        detail: job.summary || 'Verifique o log do backup.',
        path: '/backup',
        date: job.end_time || job.start_time,
      }));

    const remoteItems = remoteJobs
      .filter((job) => job.status === 'failed')
      .map((job) => ({
        id: job.id,
        title: `Task falhou: ${job.host || 'Host'}`,
        detail: job.message || labelForRemoteAction(job.action),
        path: '/tasks',
        date: job.ended_at || job.created_at,
      }));

    const updateItems = updateJobs
      .filter((job) => job.status === 'failed')
      .map((job) => ({
        id: job.id,
        title: `Update falhou: ${job.host || 'Host'}`,
        detail: job.message || 'Verifique o Software Center/SCCM Client.',
        path: job.host ? `/monitor?host=${encodeURIComponent(job.host)}` : '/monitor',
        date: job.ended_at || job.created_at,
      }));

    return [...updateItems, ...remoteItems, ...backupItems]
      .filter((item) => !dismissedAttentionIds.has(item.id))
      .slice(0, 7);
  }, [backupJobs, dismissedAttentionIds, remoteJobs, updateJobs]);

  const recentHosts = useMemo(() => {
    const hosts = [
      ...updateJobs.map((job) => job.host),
      ...remoteJobs.map((job) => job.host),
      ...(data?.recent_activities || []).map((activity) => hostFromDetails(activity.details)),
    ]
      .map((host) => String(host || '').trim().toUpperCase())
      .filter(Boolean);

    return Array.from(new Set(hosts)).slice(0, 8);
  }, [data?.recent_activities, remoteJobs, updateJobs]);

  return (
    <div className="flex h-screen bg-background">
      <Sidebar user={user.username} permissions={user.permissions} onLogout={handleLogout} />

      <main className="min-w-0 flex-1 overflow-auto">
        <div className="mx-auto flex w-full max-w-7xl flex-col gap-5 p-6 lg:p-8">
          <section className="surface-hero relative z-30 overflow-visible p-5">
            <div className="flex flex-col gap-5 xl:flex-row xl:items-end xl:justify-between">
              <div className="min-w-0">
                <div className="mb-3 flex flex-wrap items-center gap-2">
                  <Badge variant="outline" className="border-blue-300 bg-blue-50 text-blue-700 dark:border-blue-400/40 dark:bg-blue-500/10 dark:text-blue-200">
                    {user.auth_source === 'windows' ? 'Windows SSO' : 'Sessão local'}
                  </Badge>
                  <Badge variant="outline" className="capitalize">
                    {user.role}
                  </Badge>
                  <span className="inline-flex items-center gap-1 text-xs text-muted-foreground">
                    <Clock3 size={13} />
                    Atualiza a cada 10s
                  </span>
                </div>
                <h1 className="text-2xl font-semibold tracking-normal text-foreground">
                  {greeting()}, {displayName}
                </h1>
                <p className="mt-1 max-w-3xl text-sm text-muted-foreground">
                  Painel operacional para ver o que está rodando, o que falhou e onde agir primeiro.
                </p>
              </div>

              <UniversalSearch />
            </div>
          </section>

          {loading && !data ? (
            <div className="flex items-center justify-center py-20">
              <Loader2 className="animate-spin text-muted-foreground" size={32} />
            </div>
          ) : error ? (
            <div className="rounded-lg border border-red-300 bg-red-50 p-4 text-sm text-red-800 dark:border-red-400/30 dark:bg-red-500/10 dark:text-red-200">
              {error}
            </div>
          ) : (
            <>
              <div className="grid grid-cols-1 gap-3 md:grid-cols-2 xl:grid-cols-5">
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
              </div>

              <div className="grid grid-cols-1 gap-5 xl:grid-cols-[minmax(0,1.35fr)_minmax(320px,0.65fr)]">
                <div className="space-y-5">
                  <Card className="rounded-lg border-border/70 shadow-none">
                    <CardHeader>
                      <SectionHeader
                        title="Agora no WMT"
                        subtitle="Operações que estão ativas ou abertas neste momento."
                        action={
                          <Button variant="outline" size="sm" onClick={() => refetch()} disabled={loading}>
                            {loading ? <Loader2 className="animate-spin" size={15} /> : <RefreshCw size={15} />}
                            Atualizar
                          </Button>
                        }
                      />
                    </CardHeader>
                    <CardContent className="space-y-3">
                      {activeWork.length ? (
                        activeWork.map((item) => (
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
                                <p className="mt-2 break-words text-sm font-semibold text-foreground">{item.title}</p>
                                <p className="mt-1 line-clamp-2 text-sm text-muted-foreground">{item.detail}</p>
                              </div>
                              <span className="shrink-0 text-xs text-muted-foreground">{formatDateTime(item.date)}</span>
                            </div>
                            {typeof item.progress === 'number' && (
                              <div className="mt-3">
                                <Progress value={item.progress} className="h-2" />
                                <p className="mt-1 text-right text-xs text-muted-foreground">{item.progress}%</p>
                              </div>
                            )}
                          </button>
                        ))
                      ) : (
                        <EmptyState text="Nada em execução agora." />
                      )}
                    </CardContent>
                  </Card>

                  <Card className="rounded-lg border-border/70 shadow-none">
                    <CardHeader>
                      <SectionHeader
                        title="Precisa de atenção"
                        subtitle="Falhas e itens vencidos para resolver antes de procurar em cada tela."
                      />
                    </CardHeader>
                    <CardContent className="space-y-3">
                      {attentionItems.length ? (
                        attentionItems.map((item) => (
                          <div key={item.id} className="relative overflow-hidden rounded-lg border border-red-300/60 bg-red-50/80 shadow-sm dark:border-red-400/30 dark:bg-red-500/10">
                            <button
                              type="button"
                              className="w-full p-3 pr-12 text-left transition-colors hover:bg-red-100/60 dark:hover:bg-red-500/10"
                              onClick={() => navigate(item.path)}
                            >
                              <div className="flex items-start gap-3">
                                <AlertTriangle className="mt-0.5 shrink-0 text-red-600 dark:text-red-300" size={17} />
                                <div className="min-w-0">
                                  <p className="break-words text-sm font-semibold text-red-800 dark:text-red-200">{item.title}</p>
                                  <p className="mt-1 line-clamp-2 text-xs text-red-700/80 dark:text-red-200/80">{item.detail}</p>
                                  <p className="mt-2 text-xs text-red-700/70 dark:text-red-200/70">{formatDateTime(item.date)}</p>
                                </div>
                              </div>
                            </button>
                            <button
                              type="button"
                              className="absolute right-2 top-2 flex size-8 items-center justify-center rounded-md text-red-700/70 transition-colors hover:bg-red-200/70 hover:text-red-900 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-red-500 dark:text-red-200/70 dark:hover:bg-red-400/20 dark:hover:text-red-100"
                              title="Fechar notificação"
                              aria-label={`Fechar notificação: ${item.title}`}
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
                      <SectionHeader title="Hosts recentes" subtitle="Acesso rápido aos equipamentos vistos nas operações." />
                    </CardHeader>
                    <CardContent className="space-y-2">
                      {recentHosts.length ? (
                        recentHosts.map((host) => (
                          <button
                            key={host}
                            type="button"
                            className="flex w-full items-center justify-between gap-3 rounded-lg border border-border/70 bg-card/70 px-3 py-2 text-left transition-colors hover:bg-muted/40"
                            onClick={() => navigateToHost(host)}
                          >
                            <span className="min-w-0 truncate text-sm font-semibold text-foreground">{host}</span>
                            <ArrowRight size={15} className="shrink-0 text-muted-foreground" />
                          </button>
                        ))
                      ) : (
                        <EmptyState text="Nenhum host recente ainda." />
                      )}
                    </CardContent>
                  </Card>

                  <Card className="rounded-lg border-border/70 shadow-none">
                    <CardHeader>
                      <SectionHeader title="Atalhos operacionais" subtitle="Entradas rápidas para as rotinas mais usadas." />
                    </CardHeader>
                    <CardContent className="grid gap-2">
                      {canAccess('monitor') && (
                        <Button variant="outline" className="min-h-12 justify-between bg-card/80 px-4" onClick={() => navigate('/monitor')}>
                          <span className="inline-flex items-center gap-2"><MonitorUp size={17} /> Monitor</span>
                          <ArrowRight size={16} />
                        </Button>
                      )}
                      {canAccess('tasks') && (
                        <Button variant="outline" className="min-h-12 justify-between bg-card/80 px-4" onClick={() => navigate('/tasks')}>
                          <span className="inline-flex items-center gap-2"><TerminalSquare size={17} /> Remote Tasks</span>
                          <ArrowRight size={16} />
                        </Button>
                      )}
                      {canAccess('history') && (
                        <Button variant="outline" className="min-h-12 justify-between bg-card/80 px-4" onClick={() => navigate('/history')}>
                          <span className="inline-flex items-center gap-2"><History size={17} /> Histórico</span>
                          <ArrowRight size={16} />
                        </Button>
                      )}
                      {canAccess('backup') && (
                        <Button variant="outline" className="min-h-12 justify-between bg-card/80 px-4" onClick={() => navigate('/backup')}>
                          <span className="inline-flex items-center gap-2"><HardDrive size={17} /> Backup</span>
                          <ArrowRight size={16} />
                        </Button>
                      )}
                      {canAccess('terms') && (
                        <Button variant="outline" className="min-h-12 justify-between bg-card/80 px-4" onClick={() => navigate('/terms')}>
                          <span className="inline-flex items-center gap-2"><FileText size={17} /> Termos</span>
                          <ArrowRight size={16} />
                        </Button>
                      )}
                    </CardContent>
                  </Card>
                </div>
              </div>

              <Card className="rounded-lg border-border/70 shadow-none">
                <CardHeader className="flex flex-row items-start justify-between gap-3">
                  <SectionHeader title="Atividade recente" subtitle="Eventos úteis do audit log, em versão compacta." />
                  {user.role === 'admin' && (
                    <Button variant="outline" size="sm" onClick={() => navigate('/admin/users')}>
                      <Users size={15} />
                      Users
                    </Button>
                  )}
                </CardHeader>
                <CardContent>
                  {data?.recent_activities?.length ? (
                    <div className="grid gap-3 lg:grid-cols-2">
                      {data.recent_activities.slice(0, 8).map((activity) => {
                        const host = hostFromDetails(activity.details);
                        return (
                          <button
                            key={activity.id}
                            type="button"
                            className="flex gap-3 rounded-lg border border-border/70 bg-card/70 p-3 text-left transition-colors hover:bg-muted/40"
                            onClick={() => (host ? navigateToHost(host) : undefined)}
                          >
                            <div className="mt-0.5 flex size-8 shrink-0 items-center justify-center rounded-md border border-border bg-muted">
                              {activity.action.startsWith('terms.') ? <FileText size={15} /> : activity.action.startsWith('backup.') ? <HardDrive size={15} /> : activity.action.startsWith('remote.') ? <TerminalSquare size={15} /> : <CheckCircle2 size={15} />}
                            </div>
                            <div className="min-w-0 flex-1">
                              <div className="flex items-start justify-between gap-3">
                                <p className="truncate text-sm font-medium text-foreground">
                                  {actionLabels[activity.action] || activity.action}
                                </p>
                                <span className="shrink-0 text-xs text-muted-foreground">{formatDateTime(activity.timestamp)}</span>
                              </div>
                              <p className="mt-0.5 line-clamp-2 text-sm text-muted-foreground">{activityDescription(activity)}</p>
                              <p className="mt-1 text-xs text-muted-foreground">por {activity.username || 'system'}</p>
                            </div>
                          </button>
                        );
                      })}
                    </div>
                  ) : (
                    <EmptyState text="Nenhuma atividade recente." />
                  )}
                </CardContent>
              </Card>

              <section className="flex flex-wrap items-center justify-between gap-3 rounded-lg border border-border/70 bg-card px-4 py-3 text-xs text-muted-foreground">
                <span>Dashboard atualiza automaticamente a cada 10s.</span>
                <Button variant="ghost" size="sm" onClick={() => navigate('/account')}>
                  <Settings size={15} />
                  Conta
                </Button>
              </section>
            </>
          )}
        </div>
      </main>
    </div>
  );
}
