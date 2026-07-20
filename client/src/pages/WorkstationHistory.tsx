import { useEffect, useMemo, useState } from 'react';
import { Sidebar } from '@/components/Sidebar';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { useAuth } from '@/hooks/useAuth';
import { apiRequest } from '@/lib/api';
import { useLocation } from 'wouter';
import {
  AlertTriangle,
  CheckCircle2,
  Clock3,
  FileText,
  HardDrive,
  History,
  Loader2,
  Monitor,
  RefreshCw,
  Search,
  TerminalSquare,
  Wrench,
} from 'lucide-react';
import { toast } from 'sonner';

interface WorkstationSummary {
  backups: number;
  remote_actions: number;
  diagnostics: number;
  terms: number;
  recent_errors: number;
}

interface HistoryEvent {
  id: string;
  kind: 'backup' | 'remote' | 'diagnostic' | 'terms' | 'audit';
  title: string;
  status: string;
  timestamp: string;
  actor: string;
  detail: string;
  error: boolean;
}

interface HistoryBackup {
  id: string;
  source: string;
  destination: string;
  users: string[];
  status: string;
  start_time: string;
  end_time: string;
  size: string;
  summary?: string;
  message?: string;
}

interface HistoryRemoteAction {
  id: string;
  host: string;
  action: string;
  status: string;
  message: string;
  created_by: string;
  created_at: string;
}

interface HistoryAudit {
  id: string;
  action: string;
  username: string;
  timestamp: string;
  details: Record<string, unknown>;
}

interface WorkstationHistoryData {
  host: string;
  generated_at: string;
  summary: WorkstationSummary;
  backups: HistoryBackup[];
  remote_actions: HistoryRemoteAction[];
  diagnostics: HistoryAudit[];
  terms: HistoryAudit[];
  recent_errors: HistoryEvent[];
  events: HistoryEvent[];
}

const actionLabels: Record<string, string> = {
  'remote-access': 'Remote Access',
  'remote-assistance': 'Remote Assistance',
  'computer-management': 'Computer Management',
  'restart-spooler': 'Restart Spooler',
  'renew-ip': 'Renew IP',
  gpupdate: 'GPUpdate',
  'force-all-actions': 'Force All Actions',
  'clear-sccm-cache': 'Clear SCCM Cache',
  'diagnostics.run': 'Diagnostic log',
  'cleanup.quick': 'Quick cleanup',
  'terms.generate': 'Term generated',
  'terms.print': 'Term printed',
  'backup.create': 'Backup started',
  'backup.precheck': 'Backup pre-check',
  'backup.open_destination': 'Backup destination opened',
};

const hiddenRemoteActions = new Set(['create-temp-c-share', 'remove-temp-c-share']);

function normalizeHost(value: string) {
  return value.trim().replace(/^\\\\/, '').replace(/\\/g, '').toUpperCase();
}

function formatDateTime(value?: string) {
  if (!value) return '-';
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return value;
  return new Intl.DateTimeFormat('pt-BR', {
    day: '2-digit',
    month: '2-digit',
    hour: '2-digit',
    hour12: false,
    minute: '2-digit',
  }).format(parsed);
}

function labelFor(value: string) {
  return actionLabels[value] || value;
}

function eventIcon(kind: HistoryEvent['kind']) {
  if (kind === 'backup') return <HardDrive size={16} />;
  if (kind === 'remote') return <TerminalSquare size={16} />;
  if (kind === 'diagnostic') return <Wrench size={16} />;
  if (kind === 'terms') return <FileText size={16} />;
  return <Clock3 size={16} />;
}

function statusBadgeClass(status: string, error = false) {
  const normalized = status.toLowerCase();
  if (error || normalized === 'failed' || normalized === 'blocked') {
    return 'border-red-200 bg-red-50 text-red-700 dark:border-red-400/30 dark:bg-red-500/10 dark:text-red-200';
  }
  if (normalized === 'running' || normalized === 'queued') {
    return 'border-blue-200 bg-blue-50 text-blue-700 dark:border-blue-400/30 dark:bg-blue-500/10 dark:text-blue-200';
  }
  if (normalized === 'canceled' || normalized === 'warning') {
    return 'border-amber-200 bg-amber-50 text-amber-700 dark:border-amber-400/30 dark:bg-amber-500/10 dark:text-amber-200';
  }
  return 'border-emerald-200 bg-emerald-50 text-emerald-700 dark:border-emerald-400/30 dark:bg-emerald-500/10 dark:text-emerald-200';
}

function StatTile({ label, value }: { label: string; value: number }) {
  return (
    <div className="rounded-md border border-border/70 bg-card px-4 py-3">
      <p className="text-xs font-semibold uppercase text-muted-foreground">{label}</p>
      <p className="mt-1 text-2xl font-semibold text-foreground">{value}</p>
    </div>
  );
}

function AuditList({ items, empty }: { items: HistoryAudit[]; empty: string }) {
  if (!items.length) {
    return <p className="text-sm text-muted-foreground">{empty}</p>;
  }

  return (
    <div className="space-y-2">
      {items.slice(0, 6).map((item) => (
        <div key={item.id} className="rounded-md border border-border/70 bg-background px-3 py-2 text-sm">
          <div className="flex items-center justify-between gap-3">
            <p className="font-medium text-foreground">{labelFor(item.action)}</p>
            <span className="shrink-0 text-xs text-muted-foreground">{formatDateTime(item.timestamp)}</span>
          </div>
          <p className="mt-1 truncate text-xs text-muted-foreground">
            {item.username || '-'} {item.details?.filename ? `- ${String(item.details.filename)}` : ''}
          </p>
        </div>
      ))}
    </div>
  );
}

export default function WorkstationHistory() {
  const { user, logout, loading: authLoading } = useAuth();
  const [, navigate] = useLocation();
  const initialHost = useMemo(() => new URLSearchParams(window.location.search).get('host') || '', []);
  const [hostInput, setHostInput] = useState(initialHost);
  const [selectedHost, setSelectedHost] = useState(normalizeHost(initialHost));
  const [data, setData] = useState<WorkstationHistoryData | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  const handleLogout = async () => {
    await logout();
    navigate('/login');
  };

  const loadHistory = async (nextHost = selectedHost) => {
    const host = normalizeHost(nextHost || hostInput);
    if (!host) {
      toast.error('Informe uma workstation.');
      return;
    }

    setSelectedHost(host);
    setLoading(true);
    setError('');
    try {
      const result = await apiRequest<WorkstationHistoryData>('/api/workstations/history', {
        method: 'POST',
        body: JSON.stringify({ host }),
      });
      setData(result);
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Failed to load workstation history';
      setError(message);
      toast.error(message);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (initialHost) {
      void loadHistory(initialHost);
    }
  }, [initialHost]);

  if (authLoading) return null;

  if (!user) {
    navigate('/login');
    return null;
  }

  if (!user.permissions?.includes('monitor')) {
    navigate('/dashboard');
    return null;
  }

  const summary = data?.summary;
  const visibleEvents = (data?.events || []).filter((event) => !hiddenRemoteActions.has(event.title));
  const visibleRemoteActions = (data?.remote_actions || []).filter((job) => !hiddenRemoteActions.has(job.action));

  return (
    <div className="flex h-screen bg-background">
      <Sidebar user={user.username} permissions={user.permissions} onLogout={handleLogout} />

      <main className="flex-1 overflow-auto">
        <div className="mx-auto flex max-w-7xl flex-col gap-6 p-6 lg:p-8">
          <header className="flex flex-col gap-4 border-b border-border pb-6 lg:flex-row lg:items-end lg:justify-between">
            <div>
              <h1 className="text-3xl font-bold text-foreground">Workstation History</h1>
              <p className="mt-1 text-sm text-muted-foreground">
                Histórico operacional por WK: backups, ações remotas, diagnósticos e termos.
              </p>
            </div>

            <form
              className="flex w-full gap-2 lg:w-[430px]"
              onSubmit={(event) => {
                event.preventDefault();
                void loadHistory(hostInput);
              }}
            >
              <Input
                value={hostInput}
                onChange={(event) => setHostInput(event.target.value)}
                placeholder="WKS048-35BR"
              />
              <Button className="gap-2" disabled={loading}>
                {loading ? <Loader2 className="animate-spin" size={16} /> : <Search size={16} />}
                Search
              </Button>
            </form>
          </header>

          {error && (
            <div className="rounded-md border border-destructive/40 bg-destructive/10 px-3 py-2 text-sm text-destructive">
              {error}
            </div>
          )}

          {data ? (
            <>
              <section className="grid gap-3 sm:grid-cols-2 lg:grid-cols-5">
                <StatTile label="Backups" value={summary?.backups || 0} />
                <StatTile label="Remote actions" value={visibleRemoteActions.length} />
                <StatTile label="Diagnostics" value={summary?.diagnostics || 0} />
                <StatTile label="Terms" value={summary?.terms || 0} />
                <StatTile label="Errors" value={summary?.recent_errors || 0} />
              </section>

              <section className="grid gap-5 xl:grid-cols-[minmax(0,1fr)_380px]">
                <div className="space-y-5">
                  <Card>
                    <CardHeader className="pb-0">
                      <div className="flex items-center justify-between gap-3">
                        <CardTitle className="flex items-center gap-2">
                          <History size={18} />
                          Timeline - {data.host}
                        </CardTitle>
                        <Button variant="outline" size="sm" className="gap-2" onClick={() => loadHistory(data.host)} disabled={loading}>
                          {loading ? <Loader2 className="animate-spin" size={14} /> : <RefreshCw size={14} />}
                          Refresh
                        </Button>
                      </div>
                    </CardHeader>
                    <CardContent>
                      {visibleEvents.length ? (
                        <div className="divide-y divide-border rounded-md border border-border">
                          {visibleEvents.map((event) => (
                            <div key={`${event.kind}-${event.id}`} className="grid gap-3 p-3 md:grid-cols-[150px_minmax(0,1fr)_auto] md:items-center">
                              <div className="text-sm text-muted-foreground">{formatDateTime(event.timestamp)}</div>
                              <div className="min-w-0">
                                <div className="flex items-center gap-2">
                                  <span className={event.error ? 'text-destructive' : 'text-primary'}>{eventIcon(event.kind)}</span>
                                  <p className="truncate font-medium text-foreground">{labelFor(event.title)}</p>
                                </div>
                                <p className="mt-1 truncate text-sm text-muted-foreground">
                                  {event.detail || event.actor || 'No extra details.'}
                                </p>
                              </div>
                              <Badge variant="outline" className={statusBadgeClass(event.status, event.error)}>
                                {event.status}
                              </Badge>
                            </div>
                          ))}
                        </div>
                      ) : (
                        <div className="flex min-h-28 items-center justify-center rounded-md border border-dashed border-border text-sm text-muted-foreground">
                          Nenhum evento encontrado para esta WK.
                        </div>
                      )}
                    </CardContent>
                  </Card>

                  <div className="grid gap-5 lg:grid-cols-2">
                    <Card>
                      <CardHeader>
                        <CardTitle className="flex items-center gap-2"><HardDrive size={18} /> Backups</CardTitle>
                      </CardHeader>
                      <CardContent className="space-y-2">
                        {data.backups.length ? data.backups.slice(0, 6).map((job) => (
                          <div key={job.id} className="rounded-md border border-border/70 bg-background px-3 py-2 text-sm">
                            <div className="flex items-center justify-between gap-3">
                              <p className="font-medium text-foreground">{`${job.source} -> ${job.destination}`}</p>
                              <Badge variant="outline" className={statusBadgeClass(job.status)}>{job.status}</Badge>
                            </div>
                            <p className="mt-1 text-xs text-muted-foreground">
                              {formatDateTime(job.start_time)} - {job.users?.length || 0} perfil(is) - {job.size || '0 GB'}
                            </p>
                          </div>
                        )) : <p className="text-sm text-muted-foreground">Nenhum backup relacionado.</p>}
                      </CardContent>
                    </Card>

                    <Card>
                      <CardHeader>
                        <CardTitle className="flex items-center gap-2"><TerminalSquare size={18} /> Remote actions</CardTitle>
                      </CardHeader>
                      <CardContent className="space-y-2">
                        {visibleRemoteActions.length ? visibleRemoteActions.slice(0, 6).map((job) => (
                          <div key={job.id} className="rounded-md border border-border/70 bg-background px-3 py-2 text-sm">
                            <div className="flex items-center justify-between gap-3">
                              <p className="font-medium text-foreground">{labelFor(job.action)}</p>
                              <Badge variant="outline" className={statusBadgeClass(job.status)}>{job.status}</Badge>
                            </div>
                            <p className="mt-1 truncate text-xs text-muted-foreground">
                              {formatDateTime(job.created_at)} - {job.message || job.created_by || '-'}
                            </p>
                          </div>
                        )) : <p className="text-sm text-muted-foreground">Nenhuma ação remota relacionada.</p>}
                      </CardContent>
                    </Card>
                  </div>
                </div>

                <aside className="space-y-5">
                  <Card>
                    <CardHeader>
                      <CardTitle className="flex items-center gap-2"><AlertTriangle size={18} /> Erros recentes</CardTitle>
                    </CardHeader>
                    <CardContent>
                      {data.recent_errors.length ? (
                        <div className="space-y-2">
                          {data.recent_errors.map((event) => (
                            <div key={`${event.kind}-${event.id}`} className="rounded-md border border-destructive/30 bg-destructive/10 px-3 py-2 text-sm text-destructive">
                              <p className="font-medium">{labelFor(event.title)}</p>
                              <p className="mt-1 text-xs opacity-90">{formatDateTime(event.timestamp)} - {event.detail || event.status}</p>
                            </div>
                          ))}
                        </div>
                      ) : (
                        <p className="text-sm text-muted-foreground">Nenhum erro recente encontrado.</p>
                      )}
                    </CardContent>
                  </Card>

                  <Card>
                    <CardHeader>
                      <CardTitle className="flex items-center gap-2"><Wrench size={18} /> Diagnósticos</CardTitle>
                    </CardHeader>
                    <CardContent>
                      <AuditList items={data.diagnostics} empty="Nenhum diagnóstico registrado." />
                    </CardContent>
                  </Card>

                  <Card>
                    <CardHeader>
                      <CardTitle className="flex items-center gap-2"><FileText size={18} /> Termos</CardTitle>
                    </CardHeader>
                    <CardContent>
                      <AuditList items={data.terms} empty="Nenhum termo registrado." />
                    </CardContent>
                  </Card>
                </aside>
              </section>
            </>
          ) : (
            <div className="flex min-h-64 items-center justify-center rounded-md border border-dashed border-border text-sm text-muted-foreground">
              <div className="text-center">
                <Monitor className="mx-auto mb-3 text-muted-foreground" size={30} />
                Pesquise uma workstation para carregar o histórico.
              </div>
            </div>
          )}
        </div>
      </main>
    </div>
  );
}
