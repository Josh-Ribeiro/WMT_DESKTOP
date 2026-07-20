import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Sidebar } from '@/components/Sidebar';
import { useAuth } from '@/hooks/useAuth';
import { useLocation } from 'wouter';
import { Activity, CheckCircle2, ClipboardList, Clock3, Copy, Gauge, HardDrive, Loader2, PackageSearch, Play, Printer, RefreshCw, Search, Sparkles, Wrench } from 'lucide-react';

import { useEffect, useRef, useState } from 'react';
import { apiRequest } from '@/lib/api';
import { openPathOnHost, openRemoteToolOnHost } from '@/lib/hostOpen';
import { toast } from 'sonner';

interface LookupResult {
  device_type?: 'workstation' | 'printer' | string;
  online: boolean;
  hostname: string;
  error?: string;
  active_directory?: ActiveDirectoryInfo;
  printer?: PrinterInfo;
  current_user: string;
  manufacturer: string;
  model: string;
  serial_number: string;
  os: string;
  ram_gb: number;
  processor: string;
  last_boot: string;
  storage_total_gb: number;
  storage_free_gb: number;
  ip_address: string;
  mac_address: string;
}

interface PrinterSupply {
  index: string;
  description: string;
  type: string;
  level: string;
  max: string;
  percent?: number | null;
  display_level: string;
}

interface PrinterInfo {
  detected?: boolean;
  name?: string;
  hostname?: string;
  model?: string;
  serial_number?: string;
  location?: string;
  contact?: string;
  page_count?: number;
  status?: string;
  uptime?: string;
  supplies?: PrinterSupply[];
  raw?: {
    sys_descr?: string;
    sys_name?: string;
  };
}

interface ActiveDirectoryInfo {
  found?: boolean;
  name?: string;
  enabled?: string;
  created?: string;
  last_logon?: string;
  distinguished_name?: string;
  organizational_unit?: string;
  error?: string;
}

interface SoftwareCenterUpdate {
  name: string;
  articleId: string;
  bulletinId: string;
  evaluationState: number;
  percentComplete: number;
  errorCode: number;
}

interface SoftwareCenterStatus {
  installed: boolean;
  clientVersion: string;
  serviceStatus: string;
  pendingUpdates: number;
  updates: SoftwareCenterUpdate[];
  ok?: boolean;
  message?: string;
}

interface UpdateJob {
  id: string;
  host: string;
  status: 'queued' | 'running' | 'completed' | 'failed' | 'canceled' | string;
  ok: boolean;
  message: string;
  progress: number;
  pending_updates: number;
  created_at: string;
  started_at: string;
  ended_at: string;
}

interface RecentLookup {
  host: string;
  online: boolean;
  timestamp: string;
}

interface DiagnosticCheck {
  name: string;
  status: 'ok' | 'warn' | 'fail' | string;
  message?: string;
  data?: unknown;
}

interface DiagnosticData {
  host: string;
  generated_at?: string;
  duration_ms?: number;
  checks: DiagnosticCheck[];
  inventory?: {
    os?: Record<string, unknown>;
    computer?: Record<string, unknown>;
    disks?: Array<Record<string, unknown>>;
    bitlocker?: Array<Record<string, unknown>>;
    software?: Array<Record<string, unknown>>;
    cleanup_preview?: Record<string, { items?: number; size_mb?: number; error?: string }>;
    cleanup?: Record<string, string>;
  };
  error?: string;
}

interface DiagnosticJob {
  id: string;
  host: string;
  status: 'queued' | 'running' | 'completed' | 'failed' | 'canceled' | string;
  message?: string;
  error?: string;
  payload?: DiagnosticData | null;
}

interface HistoryEvent {
  id: string;
  kind: string;
  title: string;
  status: string;
  timestamp: string;
  actor?: string;
  detail?: string;
  error?: boolean;
}

interface WorkstationHistoryData {
  events: HistoryEvent[];
}

const quickActions = [
  { key: 'remote access', label: 'Remote Access' },
  { key: 'remote assistance', label: 'Remote Assistance' },
  { key: 'force all actions', label: 'Force All Actions' },
  { key: 'computer management', label: 'Computer Management' },
  { key: 'gpupdate', label: 'GPUpdate' },
  { key: 'restart spooler', label: 'Restart Spooler' },
  { key: 'renew ip', label: 'Renew IP' },
  { key: 'clear sccm cache', label: 'Clear SCCM Cache' },
  { key: 'create temp C share', label: 'Create Temp C Share' },
  { key: 'remove temp C share', label: 'Remove Temp C Share' },
];

type QuickAction = (typeof quickActions)[number];

const SOFTWARE_CENTER_POLL_INTERVAL_MS = 10000;
const localRemoteToolActions = new Set(['remote-access', 'remote-assistance', 'computer-management']);
const lookupLoadingMessages = [
  'Checking network reachability...',
  'Collecting workstation inventory...',
  'Reading Active Directory information...',
  'Preparing diagnostic preview...',
];

function ticketValue(value?: string | number | null) {
  if (value === undefined || value === null || value === '') return 'N/A';
  return String(value);
}

function formatStorageSummary(result: LookupResult) {
  const total = Number(result.storage_total_gb || 0);
  const free = Number(result.storage_free_gb || 0);
  if (!total) return 'N/A';
  const used = Math.max(0, total - free);
  const percent = Math.round((used / total) * 100);
  return `C: ${used} GB usados / ${free} GB livres / ${total} GB total (${percent}% usado)`;
}

function formatTicketDate(value?: string) {
  if (!value) return '';
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return value;
  return new Intl.DateTimeFormat('pt-BR', {
    day: '2-digit',
    month: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  }).format(parsed);
}

function formatHistoryEvent(event: HistoryEvent) {
  const when = formatTicketDate(event.timestamp);
  const status = event.status ? ` [${event.status}]` : '';
  const actor = event.actor ? ` por ${event.actor}` : '';
  const detail = event.detail ? ` - ${event.detail}` : '';
  return `${when ? `${when} - ` : ''}${event.title}${status}${actor}${detail}`;
}

function buildTicketSummary({
  result,
  diagnostic,
  softwareCenter,
  activeUpdateJob,
  historyEvents,
}: {
  result: LookupResult;
  diagnostic: DiagnosticData | null;
  softwareCenter: SoftwareCenterStatus | null;
  activeUpdateJob: UpdateJob | null;
  historyEvents: HistoryEvent[];
}) {
  const osInfo = diagnostic?.inventory?.os || {};
  const uptimeHours = osInfo.uptime_hours;
  const uptime = uptimeHours ? `${String(uptimeHours)}h` : result.last_boot ? `Last boot: ${result.last_boot}` : 'N/A';
  const recentActions = historyEvents.slice(0, 5).map(formatHistoryEvent);

  return [
    `Resumo WMT - ${ticketValue(result.hostname)}`,
    `Hostname: ${ticketValue(result.hostname)}`,
    `Usuário atual: ${ticketValue(result.current_user)}`,
    `IP: ${ticketValue(result.ip_address)}`,
    `MAC: ${ticketValue(result.mac_address)}`,
    `Serial: ${ticketValue(result.serial_number)}`,
    `Modelo: ${ticketValue([result.manufacturer, result.model].filter(Boolean).join(' '))}`,
    `Sistema operacional: ${ticketValue(result.os)}`,
    `Uptime: ${uptime}`,
    `Disco: ${formatStorageSummary(result)}`,
    `SCCM Client: ${softwareCenter?.installed ? 'Instalado' : softwareCenter ? 'Não detectado' : 'Não consultado'}`,
    `SCCM Service: ${ticketValue(softwareCenter?.serviceStatus)}`,
    `SCCM Version: ${ticketValue(softwareCenter?.clientVersion)}`,
    `Updates pendentes: ${softwareCenter?.pendingUpdates ?? 0}`,
    activeUpdateJob ? `Update job ativo: ${activeUpdateJob.id} (${activeUpdateJob.status}, ${activeUpdateJob.progress || 0}%)` : 'Update job ativo: N/A',
    '',
    'Últimas ações:',
    ...(recentActions.length ? recentActions.map((item) => `- ${item}`) : ['- Sem ações recentes registradas para este host.']),
  ].join('\n');
}

function diagnosticFromLookup(result: LookupResult): DiagnosticData {
  const total = Number(result.storage_total_gb || 0);
  const free = Number(result.storage_free_gb || 0);
  const usedPercent = total > 0 ? Math.round(((total - free) / total) * 100) : 0;

  return {
    host: result.hostname,
    generated_at: 'Prévia rápida do lookup',
    checks: [
      {
        name: 'Conectividade',
        status: result.online ? 'ok' : 'fail',
        message: result.online ? 'Host respondeu a consulta inicial.' : result.error || 'Host offline ou indisponível.',
      },
      {
        name: 'Active Directory',
        status: result.active_directory?.found ? 'ok' : 'warn',
        message: result.active_directory?.found ? 'Objeto encontrado no AD.' : result.active_directory?.error || 'Sem dados do AD.',
      },
      {
        name: 'Disco',
        status: total && free / total < 0.1 ? 'warn' : 'ok',
        message: total ? `${free} GB livres de ${total} GB (${usedPercent}% usado).` : 'Disco não retornado no lookup.',
      },
    ],
    inventory: {
      os: {
        caption: result.os,
        version: '',
        build: '',
        uptime_hours: '',
      },
      computer: {
        manufacturer: result.manufacturer,
        model: result.model,
        serial_number: result.serial_number,
        logged_user: result.current_user,
        processor: result.processor,
        ram_gb: result.ram_gb,
        ip_address: result.ip_address,
        mac_address: result.mac_address,
        last_boot: result.last_boot,
      },
      disks: total
        ? [
            {
              DeviceID: 'C:',
              FreeGB: free,
              SizeGB: total,
            },
          ]
        : [],
      bitlocker: [],
      software: [],
      cleanup_preview: {},
      cleanup: {},
    },
    error: result.error,
  };
}

function canonicalRemoteAction(action: string) {
  const normalized = action.trim().toLowerCase().replace(/[_-]+/g, ' ').replace(/\s+/g, ' ');
  const aliases: Record<string, string> = {
    'remote access': 'remote-access',
    'remote assistance': 'remote-assistance',
    'force all actions': 'force-all-actions',
    'computer management': 'computer-management',
    gpupdate: 'gpupdate',
    'restart spooler': 'restart-spooler',
    'renew ip': 'renew-ip',
    'reconfigure ip': 'renew-ip',
    'clear sccm cache': 'clear-sccm-cache',
    'admin share': 'admin-share',
    'create temp c share': 'create-temp-c-share',
    'create-temp-c-share': 'create-temp-c-share',
    'remove temp c share': 'remove-temp-c-share',
    'remove-temp-c-share': 'remove-temp-c-share',
  };

  return aliases[normalized] || normalized.replace(/\s+/g, '-');
}

async function openPathWithRetry(path: string, attempts = 12) {
  let lastError: unknown = null;
  for (let attempt = 0; attempt < attempts; attempt += 1) {
    try {
      await openPathOnHost(path);
      return;
    } catch (error) {
      lastError = error;
      if (attempt < attempts - 1) {
        await new Promise((resolve) => window.setTimeout(resolve, 1500));
      }
    }
  }
  throw lastError instanceof Error ? lastError : new Error(`Nao foi possivel abrir ${path}`);
}

function CopyButton({ value, label }: { value?: string | number; label: string }) {
  const copyValue = value ? String(value) : '';

  if (!copyValue) {
    return null;
  }

  return (
    <button
      type="button"
      className="inline-flex h-7 w-7 shrink-0 items-center justify-center rounded-md text-muted-foreground transition-colors hover:bg-muted hover:text-foreground"
      title={`Copiar ${label}`}
      onClick={async () => {
        try {
          await navigator.clipboard.writeText(copyValue);
          toast.success(`${label} copiado`);
        } catch {
          toast.error(`Não foi possível copiar ${label}`);
        }
      }}
    >
      <Copy size={14} />
    </button>
  );
}

function CopyTicketButton({
  result,
  diagnostic,
  softwareCenter,
  activeUpdateJob,
  historyEvents,
}: {
  result: LookupResult;
  diagnostic: DiagnosticData | null;
  softwareCenter: SoftwareCenterStatus | null;
  activeUpdateJob: UpdateJob | null;
  historyEvents: HistoryEvent[];
}) {
  return (
    <Button
      type="button"
      variant="outline"
      className="min-h-10 bg-background/80"
      onClick={async () => {
        try {
          await navigator.clipboard.writeText(buildTicketSummary({ result, diagnostic, softwareCenter, activeUpdateJob, historyEvents }));
          toast.success('Resumo copiado para o ticket', {
            description: result.hostname,
          });
        } catch {
          toast.error('Não foi possível copiar o resumo para o ticket');
        }
      }}
    >
      <ClipboardList size={16} />
      Copiar resumo para ticket
    </Button>
  );
}

function InfoTile({
  label,
  value,
  className = '',
  copyable = false,
}: {
  label: string;
  value?: string | number;
  className?: string;
  copyable?: boolean;
}) {
  return (
    <div className={`min-w-0 rounded-lg bg-muted/35 px-4 py-3 ring-1 ring-border/40 ${className}`}>
      <div className="flex min-w-0 items-center justify-between gap-2">
        <p className="text-[11px] font-semibold uppercase tracking-wide text-muted-foreground">{label}</p>
        {copyable && <CopyButton value={value} label={label} />}
      </div>
      <p className="mt-2 min-h-5 break-words text-sm font-semibold leading-5 text-foreground">{value || 'N/A'}</p>
    </div>
  );
}

function MessageBox({ tone, children }: { tone: 'success' | 'error'; children: React.ReactNode }) {
  const toneClass =
    tone === 'success'
      ? 'bg-emerald-50 text-emerald-700 ring-emerald-200 dark:bg-emerald-950/30 dark:text-emerald-300 dark:ring-emerald-900/50'
      : 'bg-red-50 text-red-700 ring-red-200 dark:bg-red-950/30 dark:text-red-300 dark:ring-red-900/50';

  return (
    <div className={`rounded-lg px-3 py-2 text-xs leading-5 ring-1 ${toneClass}`}>
      <p className="break-words">{children}</p>
    </div>
  );
}

function OfflineInfoCard({ label, value }: { label: string; value?: string }) {
  return (
    <div className="min-w-0 rounded-lg bg-slate-800/70 px-4 py-4 ring-1 ring-slate-700/60">
      <p className="text-[11px] font-bold uppercase tracking-wider text-slate-400">{label}</p>
      <p className="mt-3 min-h-5 break-words text-sm font-bold leading-5 text-slate-100">{value || 'N/A'}</p>
    </div>
  );
}

function OfflineComputerPanel({ result }: { result: LookupResult }) {
  const ad = result.active_directory || {};
  const adName = ad.name || result.hostname;

  return (
    <section className="rounded-xl bg-slate-900/80 p-4 shadow-sm ring-1 ring-slate-700/70">
      <div className="space-y-4">
        <div>
          <p className="text-sm text-red-300">Error</p>
          <p className="mt-1 text-sm font-medium text-red-300">
            {result.error || 'Host is offline or unreachable'}
          </p>
        </div>

        <div className="grid gap-3 md:grid-cols-2">
          <OfflineInfoCard label="AD Name" value={adName} />
          <OfflineInfoCard label="Enabled" value={ad.enabled} />
          <OfflineInfoCard label="Created" value={ad.created} />
          <OfflineInfoCard label="Last Logon" value={ad.last_logon} />
          <OfflineInfoCard label="Organization Unit" value={ad.organizational_unit} />
        </div>
      </div>
    </section>
  );
}

function supplyTone(percent?: number | null) {
  if (percent === null || percent === undefined) return 'bg-muted-foreground';
  if (percent <= 10) return 'bg-red-500';
  if (percent <= 25) return 'bg-amber-500';
  return 'bg-emerald-500';
}

function DonutMetric({ value, label, helper }: { value: number; label: string; helper: string }) {
  const normalized = Math.max(0, Math.min(100, value));
  return (
    <div className="flex items-center gap-4 rounded-lg border border-border/70 bg-card/80 p-4">
      <div
        className="grid size-24 shrink-0 place-items-center rounded-full"
        style={{ background: `conic-gradient(var(--primary) ${normalized * 3.6}deg, color-mix(in oklch, var(--muted) 78%, transparent) 0deg)` }}
      >
        <div className="grid size-16 place-items-center rounded-full bg-card text-center shadow-sm">
          <span className="text-lg font-bold text-foreground">{normalized}%</span>
        </div>
      </div>
      <div className="min-w-0">
        <p className="text-sm font-semibold text-foreground">{label}</p>
        <p className="mt-1 break-words text-xs text-muted-foreground">{helper}</p>
      </div>
    </div>
  );
}

function PrinterDashboard({ result }: { result: LookupResult }) {
  const printer = result.printer || {};
  const supplies = printer.supplies || [];
  const knownSupplies = supplies.filter((item) => typeof item.percent === 'number');
  const averageSupply = knownSupplies.length
    ? Math.round(knownSupplies.reduce((total, item) => total + Number(item.percent || 0), 0) / knownSupplies.length)
    : 0;
  const lowSupplies = knownSupplies.filter((item) => Number(item.percent) <= 25).length;

  return (
    <div className="space-y-4">
      <section className="surface-hero overflow-hidden p-4">
        <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
          <div className="min-w-0">
            <div className="flex flex-wrap items-center gap-2">
              <span className="inline-flex items-center gap-2 rounded-full border border-primary/25 bg-primary/10 px-3 py-1 text-xs font-bold text-primary">
                <Printer size={14} />
                IMPRESSORA
              </span>
              <span className="rounded-full border border-emerald-500/30 bg-emerald-500/10 px-3 py-1 text-xs font-bold text-emerald-600 dark:text-emerald-300">
                ONLINE
              </span>
            </div>
            <div className="mt-3 flex min-w-0 items-start gap-2">
              <h2 className="min-w-0 break-words text-2xl font-bold leading-tight text-foreground">{printer.name || result.hostname}</h2>
              <CopyButton value={printer.name || result.hostname} label="Impressora" />
            </div>
            <p className="mt-1 break-words text-sm text-muted-foreground">{printer.model || 'Modelo não retornado pelo SNMP'}</p>
          </div>

          <div className="grid min-w-0 gap-2 sm:grid-cols-3 lg:min-w-[460px]">
            <InfoTile label="IP/Host" value={result.ip_address || result.hostname} copyable />
            <InfoTile label="Serial" value={printer.serial_number || result.serial_number} copyable />
            <InfoTile label="Local" value={printer.location || '—'} />
          </div>
        </div>
      </section>

      <div className="grid gap-4 lg:grid-cols-[0.85fr_1.15fr]">
        <section className="grid gap-4">
          <DonutMetric
            value={averageSupply}
            label="Média dos suprimentos"
            helper={knownSupplies.length ? `${knownSupplies.length} suprimento(s) com leitura SNMP` : 'Sem leitura percentual de suprimentos'}
          />
          <div className="grid gap-3 sm:grid-cols-2">
            <InfoTile label="Contador" value={printer.page_count ? printer.page_count.toLocaleString('pt-BR') : '—'} />
            <InfoTile label="Baixos" value={`${lowSupplies} suprimento(s)`} />
            <InfoTile label="Status SNMP" value={printer.status || '—'} />
            <InfoTile label="Uptime" value={printer.uptime || '—'} />
          </div>
        </section>

        <section className="rounded-lg border border-border/70 bg-card/90 p-4 shadow-sm">
          <div className="mb-4 flex items-center gap-2">
            <Gauge size={17} className="text-primary" />
            <h3 className="text-base font-semibold text-foreground">Suprimentos</h3>
          </div>
          {supplies.length ? (
            <div className="space-y-3">
              {supplies.map((supply) => {
                const percent = typeof supply.percent === 'number' ? Math.max(0, Math.min(100, supply.percent)) : null;
                return (
                  <div key={`${supply.index}-${supply.description}`} className="rounded-lg border border-border/60 bg-background/50 p-3">
                    <div className="flex items-start justify-between gap-3">
                      <div className="min-w-0">
                        <p className="break-words text-sm font-semibold text-foreground">{supply.description || `Supply ${supply.index}`}</p>
                        <p className="mt-0.5 text-xs text-muted-foreground">{supply.display_level || supply.level || 'Sem nível'}</p>
                      </div>
                      <span className="shrink-0 text-sm font-bold text-foreground">{percent === null ? '—' : `${percent}%`}</span>
                    </div>
                    <div className="mt-3 h-2.5 overflow-hidden rounded-full bg-muted">
                      <div className={`h-full transition-all ${supplyTone(percent)}`} style={{ width: `${percent ?? 100}%`, opacity: percent === null ? 0.35 : 1 }} />
                    </div>
                  </div>
                );
              })}
            </div>
          ) : (
            <div className="rounded-lg border border-dashed border-border/70 px-4 py-8 text-center text-sm text-muted-foreground">
              Nenhum suprimento retornado pelo SNMP.
            </div>
          )}
        </section>
      </div>
    </div>
  );
}

function DiagnosticPanel({
  data,
  onRefresh,
  onCleanup,
  quickActions,
  remoteActionLoading,
  onRemoteAction,
  refreshing,
  cleaning,
}: {
  data: DiagnosticData;
  onRefresh: () => void;
  onCleanup: () => void;
  quickActions: QuickAction[];
  remoteActionLoading: string | null;
  onRemoteAction: (action: string) => void;
  refreshing: boolean;
  cleaning: boolean;
}) {
  const inventory = data.inventory || {};
  const os = inventory.os || {};
  const computer = inventory.computer || {};
  const disks = inventory.disks || [];
  const software = inventory.software || [];
  const bitlocker = inventory.bitlocker || [];
  const cleanupPreview = inventory.cleanup_preview || {};
  const cleanup = inventory.cleanup || {};
  const inventoryWarnings = (inventory as { errors?: string[] }).errors || [];
  const [softwareQuery, setSoftwareQuery] = useState('');
  const normalizedSoftwareQuery = softwareQuery.trim().toLowerCase();
  const filteredSoftware = normalizedSoftwareQuery
    ? software.filter((app) =>
        [app.DisplayName, app.DisplayVersion, app.Publisher, app.InstallDate]
          .map((value) => String(value || '').toLowerCase())
          .join(' ')
          .includes(normalizedSoftwareQuery),
      )
    : software;
  const visibleSoftware = filteredSoftware.slice(0, 80);

  return (
    <section className="space-y-4 rounded-xl bg-card p-4 shadow-sm ring-1 ring-border/40">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
        <div>
          <p className="text-[11px] font-semibold uppercase tracking-wide text-muted-foreground">Diagnostic log</p>
          <h3 className="mt-1 text-base font-semibold text-foreground">Pacote visual de diagnóstico</h3>
          <p className="mt-1 text-xs text-muted-foreground">
            {data.generated_at ? `Gerado em ${data.generated_at}` : 'Coleta recente'}{data.duration_ms ? ` • ${(data.duration_ms / 1000).toFixed(1)}s` : ''}
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <Button variant="outline" size="sm" disabled={refreshing} onClick={onRefresh}>
            <PackageSearch size={16} className={refreshing ? 'mr-2 animate-pulse' : 'mr-2'} />
            {refreshing ? 'Consultando...' : 'Inventário detalhado'}
          </Button>
          <Button variant="outline" size="sm" disabled={cleaning} onClick={onCleanup}>
            {cleaning ? <Loader2 size={16} className="mr-2 animate-spin" /> : <Wrench size={16} className="mr-2" />}
            Limpeza
          </Button>
          <span className="w-fit rounded-full border border-border/70 px-3 py-1 text-xs font-semibold text-muted-foreground">{data.host}</span>
        </div>
      </div>

      {data.error && <MessageBox tone="error">{data.error}</MessageBox>}
      {inventoryWarnings.length > 0 && (
        <MessageBox tone="error">{inventoryWarnings.slice(0, 2).join(' | ')}</MessageBox>
      )}

      <div className="grid gap-4 xl:grid-cols-[0.9fr_1.1fr]">
        <div className="space-y-3">
          <div className="rounded-lg bg-muted/30 p-3 ring-1 ring-border/40">
            <div className="mb-3 flex items-center gap-2">
              <Activity size={16} className="text-muted-foreground" />
              <p className="text-sm font-semibold text-foreground">Sistema</p>
            </div>
            <div className="grid gap-2 text-xs text-muted-foreground">
              <p><span className="font-semibold text-foreground">Windows:</span> {String(os.caption || '—')}</p>
              <p><span className="font-semibold text-foreground">Versão:</span> {String(os.version || '—')} build {String(os.build || '—')}</p>
              <p><span className="font-semibold text-foreground">Uptime:</span> {String(os.uptime_hours || '—')}h</p>
              <p><span className="font-semibold text-foreground">Usuário:</span> {String(computer.logged_user || '—')}</p>
            </div>
          </div>

          <div className="rounded-lg bg-muted/30 p-3 ring-1 ring-border/40">
            <div className="mb-3 flex items-center gap-2">
              <HardDrive size={16} className="text-muted-foreground" />
              <p className="text-sm font-semibold text-foreground">Discos e BitLocker</p>
            </div>
            <div className="space-y-2">
              {disks.length ? disks.map((disk, index) => (
                <div key={`${String(disk.DeviceID)}-${index}`} className="rounded-md bg-background px-3 py-2 text-xs ring-1 ring-border/40">
                  <p className="font-semibold text-foreground">{String(disk.DeviceID || 'Disco')}</p>
                  <p className="text-muted-foreground">{String(disk.FreeGB || 0)} GB livres de {String(disk.SizeGB || 0)} GB</p>
                </div>
              )) : <p className="text-xs text-muted-foreground">Nenhum disco retornado.</p>}
              {bitlocker.length ? bitlocker.map((item, index) => (
                <div key={`${String(item.MountPoint)}-${index}`} className="rounded-md bg-background px-3 py-2 text-xs ring-1 ring-border/40">
                  <p className="font-semibold text-foreground">{String(item.MountPoint || 'Volume')}</p>
                  <p className="text-muted-foreground">Status: {String(item.VolumeStatus || '—')} • Proteção: {String(item.ProtectionStatus || '—')}</p>
                </div>
              )) : <p className="text-xs text-muted-foreground">BitLocker não retornou volumes.</p>}
            </div>
          </div>

          <div className="rounded-lg bg-muted/30 p-3 ring-1 ring-border/40">
            <div className="mb-3 min-w-0">
              <h4 className="text-sm font-semibold text-foreground">Quick Actions</h4>
              <p className="mt-1 break-words text-xs text-muted-foreground">Operações frequentes para conexão e suporte.</p>
            </div>

            <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
              {quickActions.map((item) => (
                <Button
                  key={item.key}
                  variant="outline"
                  disabled={remoteActionLoading === item.key}
                  className="min-h-10 whitespace-normal rounded-lg border-border/80 bg-background/90 px-3 py-2 text-center text-xs font-semibold leading-5 shadow-sm hover:bg-accent/50"
                  onClick={() => onRemoteAction(item.key)}
                >
                  {remoteActionLoading === item.key ? 'Enviando...' : item.label}
                </Button>
              ))}
            </div>
          </div>
        </div>

        <div className="space-y-3">
          <div className="rounded-lg bg-muted/30 p-3 ring-1 ring-border/40">
            <div className="mb-3 flex flex-col gap-3">
              <div className="flex items-center gap-2">
                <PackageSearch size={16} className="text-muted-foreground" />
                <p className="text-sm font-semibold text-foreground">Softwares instalados</p>
                <span className="rounded-full bg-background px-2 py-0.5 text-xs text-muted-foreground ring-1 ring-border/40">
                  {normalizedSoftwareQuery ? `${filteredSoftware.length}/${software.length}` : software.length}
                </span>
              </div>
              {software.length > 0 && (
                <div className="relative">
                  <Search className="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-muted-foreground" />
                  <Input
                    value={softwareQuery}
                    onChange={(event) => setSoftwareQuery(event.target.value)}
                    placeholder="Pesquisar aplicativo ou versão"
                    className="h-9 bg-background pl-9 text-sm"
                  />
                </div>
              )}
            </div>
            <div className="max-h-56 overflow-auto rounded-md bg-background ring-1 ring-border/40">
              {refreshing ? (
                <div className="space-y-3 p-3">
                  <div className="flex items-center gap-2 text-xs text-muted-foreground">
                    <Loader2 size={14} className="animate-spin" />
                    Consultando softwares instalados...
                  </div>
                  <div className="space-y-2">
                    {[0, 1, 2].map((item) => (
                      <div key={item} className="h-8 animate-pulse rounded-md bg-muted/60" />
                    ))}
                  </div>
                </div>
              ) : visibleSoftware.length ? visibleSoftware.map((app, index) => (
                <div key={`${String(app.DisplayName)}-${index}`} className="grid grid-cols-[minmax(0,1fr)_110px] gap-2 border-b px-3 py-2 text-xs last:border-0">
                  <span className="truncate font-medium text-foreground">{String(app.DisplayName || '—')}</span>
                  <span className="truncate text-right text-muted-foreground">{String(app.DisplayVersion || '—')}</span>
                </div>
              )) : software.length ? (
                <div className="p-3 text-xs text-muted-foreground">
                  Nenhum aplicativo encontrado para "{softwareQuery.trim()}".
                </div>
              ) : (
                <div className="p-3 text-xs text-muted-foreground">
                  <p>Softwares não são carregados na coleta rápida.</p>
                  <p className="mt-1">Clique em Inventário detalhado para consultar programas instalados.</p>
                </div>
              )}
            </div>
          </div>

          <div className="rounded-lg bg-muted/30 p-3 ring-1 ring-border/40">
            <div className="mb-3 flex items-center gap-2">
              {cleaning ? <Loader2 size={16} className="animate-spin text-muted-foreground" /> : <Sparkles size={16} className="text-muted-foreground" />}
              <p className="text-sm font-semibold text-foreground">Limpeza rápida</p>
            </div>
            <div className="grid gap-2 md:grid-cols-2">
              {cleaning && (
                <div className="rounded-md bg-background px-3 py-2 text-xs text-muted-foreground ring-1 ring-border/40 md:col-span-2">
                  <div className="flex items-center gap-2">
                    <Loader2 size={14} className="animate-spin" />
                    Calculando e executando limpeza...
                  </div>
                  <div className="mt-3 grid gap-2 sm:grid-cols-2">
                    {[0, 1].map((item) => (
                      <div key={item} className="h-10 animate-pulse rounded-md bg-muted/60" />
                    ))}
                  </div>
                </div>
              )}
              {Object.entries(cleanupPreview).slice(0, 8).map(([path, info]) => (
                <div key={path} className="min-w-0 rounded-md bg-background px-3 py-2 text-xs ring-1 ring-border/40">
                  <p className="truncate font-semibold text-foreground" title={path}>{path}</p>
                  <p className="text-muted-foreground">{info.error || `${info.items || 0} item(s), ${info.size_mb || 0} MB`}</p>
                </div>
              ))}
              {Object.entries(cleanup).map(([path, status]) => (
                <div key={`cleanup-${path}`} className="min-w-0 rounded-md bg-emerald-500/10 px-3 py-2 text-xs text-emerald-700 ring-1 ring-emerald-500/30 dark:text-emerald-300">
                  <p className="truncate font-semibold" title={path}>{path}</p>
                  <p>{status}</p>
                </div>
              ))}
              {!Object.keys(cleanupPreview).length && !Object.keys(cleanup).length && (
                <p className="text-xs text-muted-foreground">A prévia de limpeza é calculada ao clicar em Limpeza.</p>
              )}
            </div>
          </div>
        </div>
      </div>
    </section>
  );
}

export default function Monitor() {
  const { user, logout, loading: authLoading } = useAuth();
  const [location, navigate] = useLocation();
  const [lookupHost, setLookupHost] = useState('');
  const [lookupResult, setLookupResult] = useState<LookupResult | null>(null);
  const [lookupLoading, setLookupLoading] = useState(false);
  const [lookupLoadingStep, setLookupLoadingStep] = useState(0);
  const [lookupError, setLookupError] = useState<string | null>(null);
  const [lookupDuration, setLookupDuration] = useState<number | null>(null);
  const [recentLookups, setRecentLookups] = useState<RecentLookup[]>([]);
  const [remoteActionLoading, setRemoteActionLoading] = useState<string | null>(null);
  const [remoteActionMessage, setRemoteActionMessage] = useState<string | null>(null);
  const [remoteActionDetails, setRemoteActionDetails] = useState<string | null>(null);
  const [remoteActionError, setRemoteActionError] = useState<string | null>(null);
  const [softwareCenter, setSoftwareCenter] = useState<SoftwareCenterStatus | null>(null);
  const [softwareCenterLoading, setSoftwareCenterLoading] = useState(false);
  const [softwareCenterInstalling, setSoftwareCenterInstalling] = useState(false);
  const [softwareCenterMonitoring, setSoftwareCenterMonitoring] = useState(false);
  const [softwareCenterMonitorHost, setSoftwareCenterMonitorHost] = useState<string | null>(null);
  const [activeUpdateJob, setActiveUpdateJob] = useState<UpdateJob | null>(null);
  const [softwareCenterMessage, setSoftwareCenterMessage] = useState<string | null>(null);
  const [softwareCenterError, setSoftwareCenterError] = useState<string | null>(null);
  const [diagnostic, setDiagnostic] = useState<DiagnosticData | null>(null);
  const [diagnosticLoading, setDiagnosticLoading] = useState(false);
  const [cleanupLoading, setCleanupLoading] = useState(false);
  const [hostHistory, setHostHistory] = useState<WorkstationHistoryData | null>(null);
  const [hostHistoryLoading, setHostHistoryLoading] = useState(false);
  const [hostHistoryError, setHostHistoryError] = useState<string | null>(null);
  const softwareCenterPollInFlight = useRef(false);
  const updateJobPollFailures = useRef(0);
  const autoLookupHostRef = useRef<string | null>(null);
  const diagnosticRequestRef = useRef(0);

  const handleLogout = async () => {
    await logout();
    navigate('/login');
  };

  const selectedHost = lookupResult?.hostname || lookupHost.trim() || 'localhost';
  const canRunHostActions = user?.role === 'admin' || user?.role === 'operator';

  useEffect(() => {
    if (!lookupLoading) {
      setLookupLoadingStep(0);
      return;
    }

    const interval = window.setInterval(() => {
      setLookupLoadingStep((current) => (current + 1) % lookupLoadingMessages.length);
    }, 1800);

    return () => window.clearInterval(interval);
  }, [lookupLoading]);

  const rememberLookup = (result: LookupResult) => {
    const host = (result.hostname || lookupHost.trim()).toUpperCase();

    setRecentLookups((items) => {
      const next = [
        {
          host,
          online: result.online,
          timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
        },
        ...items.filter((item) => item.host !== host),
      ];

      return next.slice(0, 6);
    });
  };

  const loadSoftwareCenter = async (host: string, options: { silent?: boolean } = {}) => {
    if (!options.silent) {
      setSoftwareCenterLoading(true);
      setSoftwareCenterMessage(null);
      setSoftwareCenterError(null);
    }

    try {
      const result = await apiRequest<SoftwareCenterStatus>(`/api/software-center?host=${encodeURIComponent(host)}`);
      setSoftwareCenter(result);
      if (result.ok === false && result.message) {
        setSoftwareCenterError(result.message);
      } else if (!options.silent) {
        setSoftwareCenterError(null);
      }
      return result;
    } catch (err) {
      setSoftwareCenter(null);
      setSoftwareCenterError(err instanceof Error ? err.message : 'Erro desconhecido ao consultar o Software Center.');
      return null;
    } finally {
      if (!options.silent) {
        setSoftwareCenterLoading(false);
      }
    }
  };

  useEffect(() => {
    if (!softwareCenterMonitoring || !softwareCenterMonitorHost) {
      return;
    }

    const pollSoftwareCenter = async () => {
      if (document.hidden) {
        return;
      }
      if (softwareCenterPollInFlight.current) {
        return;
      }

      softwareCenterPollInFlight.current = true;
      try {
        const result = await loadSoftwareCenter(softwareCenterMonitorHost, { silent: true });
        if (!result || result.ok === false) {
          setSoftwareCenterMonitoring(false);
          return;
        }

        if ((result.pendingUpdates ?? 0) === 0) {
          setSoftwareCenterMonitoring(false);
          setSoftwareCenterMessage('Atualizações concluídas ou sem pendências para este host.');
        }
      } finally {
        softwareCenterPollInFlight.current = false;
      }
    };

    const intervalId = window.setInterval(pollSoftwareCenter, SOFTWARE_CENTER_POLL_INTERVAL_MS);
    void pollSoftwareCenter();

    return () => {
      window.clearInterval(intervalId);
    };
  }, [softwareCenterMonitoring, softwareCenterMonitorHost]);

  useEffect(() => {
    if (!activeUpdateJob || !['queued', 'running'].includes(activeUpdateJob.status)) {
      return;
    }

    const intervalId = window.setInterval(async () => {
      if (document.hidden) {
        return;
      }
      try {
        const job = await apiRequest<UpdateJob>(`/api/update-jobs/${encodeURIComponent(activeUpdateJob.id)}`);
        updateJobPollFailures.current = 0;
        setActiveUpdateJob(job);
        if (!['queued', 'running'].includes(job.status)) {
          setSoftwareCenterMonitoring(false);
          await loadSoftwareCenter(job.host || selectedHost, { silent: true });
          if (job.status === 'completed') {
            setSoftwareCenterMessage(job.message || `Update job ${job.id} concluído.`);
          } else if (job.status === 'failed') {
            setSoftwareCenterError(job.message || `Update job ${job.id} falhou.`);
          }
        }
      } catch (err) {
        updateJobPollFailures.current += 1;
        setSoftwareCenterError(err instanceof Error ? err.message : 'Erro desconhecido ao consultar update job.');
        if (updateJobPollFailures.current >= 3) {
          setActiveUpdateJob(null);
          setSoftwareCenterMonitoring(false);
        }
      }
    }, 5000);

    return () => window.clearInterval(intervalId);
  }, [activeUpdateJob, selectedHost]);

  useEffect(() => {
    if (softwareCenterMonitorHost && softwareCenterMonitorHost !== selectedHost) {
      setSoftwareCenterMonitoring(false);
      setSoftwareCenterMonitorHost(null);
    }
  }, [selectedHost, softwareCenterMonitorHost]);

  const loadDiagnostic = async (host: string, detailed = false) => {
    if (!canRunHostActions) {
      return;
    }
    const requestId = diagnosticRequestRef.current + 1;
    diagnosticRequestRef.current = requestId;
    setDiagnosticLoading(true);
    try {
      const job = await apiRequest<DiagnosticJob>('/api/diagnostics/jobs', {
        method: 'POST',
        body: JSON.stringify({ host, detailed }),
      });
      if (diagnosticRequestRef.current !== requestId) {
        return;
      }
      if (job.status === 'completed' && job.payload) {
        setDiagnostic(job.payload);
        return;
      }

      const startedAt = Date.now();
      let currentJob = job;
      while (Date.now() - startedAt < 120000) {
        await new Promise((resolve) => window.setTimeout(resolve, 900));
        currentJob = await apiRequest<DiagnosticJob>(`/api/diagnostics/jobs/${encodeURIComponent(job.id)}`);
        if (diagnosticRequestRef.current !== requestId) {
          return;
        }
        if (!['queued', 'running'].includes(currentJob.status)) {
          break;
        }
      }

      if (currentJob.status === 'completed' && currentJob.payload) {
        setDiagnostic(currentJob.payload);
      } else {
        setDiagnostic({
          host,
          checks: [],
          error: currentJob.error || currentJob.message || 'Diagnóstico não concluiu dentro do tempo esperado.',
        });
      }
    } catch (err) {
      setDiagnostic({
        host,
        checks: [],
        error: err instanceof Error ? err.message : 'Erro desconhecido ao gerar diagnóstico.',
      });
    } finally {
      if (diagnosticRequestRef.current === requestId) {
        setDiagnosticLoading(false);
      }
    }
  };

  const loadHostHistory = async (host: string) => {
    if (!canRunHostActions) {
      return;
    }
    setHostHistoryLoading(true);
    setHostHistoryError(null);
    try {
      const result = await apiRequest<WorkstationHistoryData>(`/api/workstations/${encodeURIComponent(host)}/history`);
      setHostHistory(result);
    } catch (err) {
      setHostHistory(null);
      setHostHistoryError(err instanceof Error ? err.message : 'Erro desconhecido ao consultar histórico do host.');
    } finally {
      setHostHistoryLoading(false);
    }
  };

  const runQuickCleanup = async () => {
    if (!canRunHostActions) {
      toast.error('Sem permissão para executar limpeza rápida.');
      return;
    }
    setCleanupLoading(true);
    try {
      const result = await apiRequest<DiagnosticData>('/api/quick-cleanup', {
        method: 'POST',
        body: JSON.stringify({ host: selectedHost }),
      });
      setDiagnostic(result);
      toast.success('Limpeza rápida solicitada', { description: selectedHost });
    } catch (err) {
      toast.error('Falha na limpeza rápida', {
        description: err instanceof Error ? err.message : selectedHost,
      });
    } finally {
      setCleanupLoading(false);
    }
  };

  const handleInstallSoftwareCenterUpdates = async () => {
    if (!canRunHostActions) {
      setSoftwareCenterError('Sem permissão para iniciar updates neste host.');
      return;
    }
    setSoftwareCenterInstalling(true);
    setSoftwareCenterMessage(null);
    setSoftwareCenterError(null);

    try {
      const result = await apiRequest<{ ok: boolean; message?: string; job?: UpdateJob; job_id?: string }>('/api/software-center/install', {
        method: 'POST',
        body: JSON.stringify({ host: selectedHost }),
      });

      if (result.ok === false) {
        await loadSoftwareCenter(selectedHost);
        setSoftwareCenterMonitoring(false);
        setSoftwareCenterMonitorHost(null);
        setSoftwareCenterError(result.message || 'Falha ao iniciar atualizações do Software Center.');
      } else {
        await loadSoftwareCenter(selectedHost);
        if (result.job) {
          setActiveUpdateJob(result.job);
        }
        setSoftwareCenterMonitorHost(selectedHost);
        setSoftwareCenterMonitoring(false);
        setSoftwareCenterMessage(result.message || 'Atualizações do Software Center iniciadas.');
      }
    } catch (err) {
      setSoftwareCenterError(err instanceof Error ? err.message : 'Erro desconhecido ao iniciar atualizações.');
    } finally {
      setSoftwareCenterInstalling(false);
    }
  };

  const handleRemoteAction = async (action: string) => {
    if (!canRunHostActions) {
      setRemoteActionError('Sem permissão para executar ações remotas neste host.');
      return;
    }
    const canonicalAction = canonicalRemoteAction(action);
    if (
      canonicalAction === 'renew-ip' &&
      !window.confirm(`Tem certeza que deseja renovar o IP de ${selectedHost}? A conexão de rede pode cair por alguns segundos.`)
    ) {
      return;
    }
    setRemoteActionLoading(action);
    setRemoteActionError(null);
    setRemoteActionMessage(null);
    setRemoteActionDetails(null);

    try {
      if (localRemoteToolActions.has(canonicalAction)) {
        await openRemoteToolOnHost(canonicalAction, selectedHost);
        setRemoteActionMessage(`Abertura local iniciada para ${selectedHost}.`);
        setRemoteActionDetails(null);
        toast.success('Ferramenta aberta no desktop', {
          description: selectedHost,
        });
        void apiRequest('/api/remote-actions', {
          method: 'POST',
          body: JSON.stringify({ host: selectedHost, action: canonicalAction }),
        }).catch(() => undefined);
        return;
      }

      const result = await apiRequest<{ ok: boolean; job_id?: string; status?: string; message: string; details?: string; open_path?: string }>('/api/remote-actions', {
        method: 'POST',
        body: JSON.stringify({ host: selectedHost, action: canonicalAction }),
      });
      if (result.ok) {
        if (canonicalAction === 'admin-share') {
          await openPathOnHost(`\\\\${selectedHost}\\c$`);
        } else if (canonicalAction === 'create-temp-c-share') {
          await openPathWithRetry(result.open_path || `\\\\${selectedHost}\\TempC$`);
        }
        const message = result.job_id
          ? `${result.message} Job: ${result.job_id}.`
          : result.message || 'Ação remota enviada para execução.';
        setRemoteActionMessage(message);
        setRemoteActionDetails(result.details || null);
        toast.success('Remote task created', {
          description: result.job_id ? `${result.job_id} • ${selectedHost}` : selectedHost,
          action: {
            label: 'Open Tasks',
            onClick: () => navigate('/tasks'),
          },
        });
      } else {
        setRemoteActionError(result.message || 'Ação remota falhou.');
        setRemoteActionDetails(result.details || null);
      }
    } catch (err) {
      setRemoteActionError(err instanceof Error ? err.message : 'Erro desconhecido ao executar a ação.');
    } finally {
      setRemoteActionLoading(null);
    }
  };

  const runLookup = async (host: string) => {
    const normalizedHost = host.trim().toUpperCase();

    if (!normalizedHost) {
      setLookupError('Informe um hostname ou IP para pesquisar.');
      return;
    }

    setLookupHost(normalizedHost);
    setLookupLoading(true);
    setLookupError(null);
    setLookupResult(null);
    setLookupDuration(null);
    setSoftwareCenter(null);
    setSoftwareCenterMessage(null);
    setSoftwareCenterError(null);
    setRemoteActionMessage(null);
    setRemoteActionError(null);
    setRemoteActionDetails(null);
    setDiagnostic(null);
    setHostHistory(null);
    setHostHistoryError(null);

    const startedAt = performance.now();

    try {
      const result = await apiRequest<LookupResult>('/api/lookup', {
        method: 'POST',
        body: JSON.stringify({ host: normalizedHost }),
      });
      setLookupResult(result);
      rememberLookup(result);
      if (result.online && result.device_type !== 'printer') {
        const host = result.hostname || normalizedHost;
        setDiagnostic(diagnosticFromLookup({ ...result, hostname: host }));
        void loadSoftwareCenter(host);
        if (canRunHostActions) {
          void loadDiagnostic(host);
          void loadHostHistory(host);
        }
      }
    } catch (err) {
      setLookupError(err instanceof Error ? err.message : 'Erro desconhecido na busca.');
    } finally {
      setLookupDuration(Math.round(performance.now() - startedAt));
      setLookupLoading(false);
    }
  };

  const handleLookup = async (e: React.FormEvent) => {
    e.preventDefault();
    await runLookup(lookupHost);
  };

  useEffect(() => {
    if (authLoading || !user) {
      return;
    }

    const host = new URLSearchParams(window.location.search).get('host')?.trim().toUpperCase();
    if (!host || autoLookupHostRef.current === host) {
      return;
    }

    autoLookupHostRef.current = host;
    void runLookup(host);
  }, [authLoading, location, user]);

  if (authLoading) {
    return null;
  }

  if (!user) {
    navigate('/login');
    return null;
  }

  return (
    <div className="flex h-screen bg-background">
      <Sidebar user={user.username} permissions={user.permissions} onLogout={handleLogout} />

      <main className="min-w-0 flex-1 overflow-auto">
        <div className="mx-auto w-full max-w-7xl space-y-6 p-4 sm:p-6 lg:p-8">
          {/* Header */}
          <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
            <div className="min-w-0">
              <h1 className="text-3xl font-bold text-foreground">Monitor</h1>
              <p className="mt-1 text-sm text-muted-foreground">Real-time workstation monitoring</p>
            </div>
            <Button
              onClick={() => void runLookup(selectedHost)}
              variant="outline"
              size="sm"
              className="w-fit shrink-0"
              disabled={lookupLoading}
            >
              <RefreshCw size={16} className={`mr-2 ${lookupLoading ? 'animate-spin' : ''}`} />
              Refresh
            </Button>
          </div>

          <section className="space-y-5">
            <div className="flex flex-col gap-4 rounded-xl bg-card p-4 shadow-sm ring-1 ring-border/40 xl:flex-row xl:items-end xl:justify-between">
              <div className="min-w-0">
                <h2 className="text-lg font-semibold text-foreground">Lookup de computador</h2>
                <p className="mt-1 text-sm text-muted-foreground">
                  Pesquise um hostname ou IP na rede e veja informações básicas do equipamento.
                </p>
              </div>
              <form onSubmit={handleLookup} className="grid gap-3 sm:grid-cols-[minmax(0,1fr)_auto] xl:min-w-[520px]">
                <Input
                  value={lookupHost}
                  onChange={(e) => setLookupHost(e.target.value.toUpperCase())}
                  placeholder="Ex.: PC-01 ou 192.168.0.10"
                  className="min-w-0"
                />
                <Button type="submit" disabled={lookupLoading} className="min-w-32 sm:w-auto">
                  {lookupLoading ? (
                    'Pesquisando...'
                  ) : (
                    <>
                      <Search size={16} className="mr-2" />
                      Pesquisar
                    </>
                  )}
                </Button>
              </form>
            </div>

              {lookupLoading && (
                <div className="rounded-xl border border-blue-200 bg-blue-50 p-4 text-blue-900 shadow-sm dark:border-blue-400/30 dark:bg-blue-500/10 dark:text-blue-100">
                  <div className="flex items-start gap-3">
                    <Loader2 size={18} className="mt-0.5 shrink-0 animate-spin" />
                    <div className="min-w-0">
                      <p className="text-sm font-semibold">Searching {lookupHost || 'workstation'}...</p>
                      <p className="mt-1 text-sm opacity-85">{lookupLoadingMessages[lookupLoadingStep]}</p>
                    </div>
                  </div>
                  <div className="mt-3 h-1.5 overflow-hidden rounded-full bg-blue-200/70 dark:bg-blue-950">
                    <div
                      className="h-full rounded-full bg-blue-600 transition-all duration-500"
                      style={{ width: `${25 + lookupLoadingStep * 20}%` }}
                    />
                  </div>
                </div>
              )}

              {(lookupDuration !== null || recentLookups.length > 0) && (
                <div className="flex flex-col gap-3 py-1 lg:flex-row lg:items-center lg:justify-between">
                  <div className="flex min-w-0 flex-wrap items-center gap-2">
                    <span className="inline-flex items-center gap-1 text-xs font-medium text-muted-foreground">
                      <Clock3 size={14} />
                      {lookupDuration !== null ? `Última consulta: ${(lookupDuration / 1000).toFixed(1)}s` : 'Sem consulta'}
                    </span>
                    {lookupResult && (
                      <span className={`inline-flex items-center gap-1 rounded-full px-2 py-1 text-xs font-semibold ${
                        lookupResult.online
                          ? 'bg-emerald-500/10 text-emerald-600 dark:text-emerald-300'
                          : 'bg-red-500/10 text-red-600 dark:text-red-300'
                      }`}>
                        <CheckCircle2 size={13} />
                        {lookupResult.online ? 'Coleta concluída' : 'Indisponível'}
                      </span>
                    )}
                  </div>

                  {recentLookups.length > 0 && (
                    <div className="flex min-w-0 flex-wrap gap-2">
                      {recentLookups.map((item) => (
                        <button
                          key={`${item.host}-${item.timestamp}`}
                          type="button"
                          disabled={lookupLoading}
                          className={`max-w-full rounded-full border px-3 py-1 text-xs font-medium transition-colors hover:bg-muted ${
                            item.online
                              ? 'border-emerald-500/30 text-emerald-600 dark:text-emerald-300'
                              : 'border-red-500/30 text-red-600 dark:text-red-300'
                          } disabled:cursor-not-allowed disabled:opacity-60`}
                          title={`Pesquisar ${item.host}`}
                          onClick={() => runLookup(item.host)}
                        >
                          <span className="break-all">{item.host}</span>
                        </button>
                      ))}
                    </div>
                  )}
                </div>
              )}

              {lookupError && (
                <div className="rounded-lg bg-red-50 p-4 ring-1 ring-red-200 dark:bg-red-900/20 dark:ring-red-900/50">
                    <p className="text-red-800 dark:text-red-200">{lookupError}</p>
                </div>
              )}

              {lookupResult && !lookupResult.online && (
                <OfflineComputerPanel result={lookupResult} />
              )}

              {lookupResult && lookupResult.online && lookupResult.device_type === 'printer' && (
                <PrinterDashboard result={lookupResult} />
              )}

              {lookupResult && lookupResult.online && lookupResult.device_type !== 'printer' && (
                <>
                <div className="space-y-4">
                  <section className="surface-hero overflow-hidden p-4">
                    <div className="flex flex-col gap-4 xl:flex-row xl:items-start xl:justify-between">
                      <div className="min-w-0">
                        <div className="flex flex-wrap items-center gap-2">
                          <span className="inline-flex items-center gap-2 rounded-full border border-emerald-500/30 bg-emerald-500/10 px-3 py-1 text-xs font-bold text-emerald-600 dark:text-emerald-300">
                            <CheckCircle2 size={14} />
                            ONLINE
                          </span>
                          <span className="rounded-full border border-primary/25 bg-primary/10 px-3 py-1 text-xs font-bold text-primary">
                            Host Command Center
                          </span>
                          {hostHistoryLoading && (
                            <span className="inline-flex items-center gap-1 rounded-full border border-border/70 bg-background/70 px-3 py-1 text-xs font-medium text-muted-foreground">
                              <Loader2 size={13} className="animate-spin" />
                              Histórico
                            </span>
                          )}
                        </div>
                        <div className="mt-3 flex min-w-0 flex-wrap items-center gap-2">
                          <h2 className="min-w-0 break-words text-2xl font-bold leading-tight text-foreground">{lookupResult.hostname || 'N/A'}</h2>
                          <CopyButton value={lookupResult.hostname} label="Hostname" />
                        </div>
                        <p className="mt-1 break-words text-sm text-muted-foreground">
                          {lookupResult.current_user || 'Usuário não identificado'} · {lookupResult.os || 'Sistema operacional não identificado'}
                        </p>
                      </div>

                      <div className="grid min-w-0 gap-3 xl:min-w-[560px]">
                        <div className="grid gap-2 sm:grid-cols-3">
                          <InfoTile label="IP" value={lookupResult.ip_address} copyable />
                          <InfoTile label="Serial" value={lookupResult.serial_number} copyable />
                          <InfoTile
                            label="SCCM"
                            value={softwareCenterLoading ? 'Consultando...' : softwareCenter?.installed ? 'Instalado' : softwareCenter ? 'Não detectado' : 'Não consultado'}
                          />
                        </div>
                        <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-end">
                          {hostHistoryError && (
                            <span className="text-xs text-amber-600 dark:text-amber-300">
                              Histórico indisponível para o resumo completo.
                            </span>
                          )}
                          <CopyTicketButton
                            result={lookupResult}
                            diagnostic={diagnostic}
                            softwareCenter={softwareCenter}
                            activeUpdateJob={activeUpdateJob}
                            historyEvents={hostHistory?.events || []}
                          />
                        </div>
                      </div>
                    </div>
                  </section>

                  <div className="grid gap-3 lg:grid-cols-[1.05fr_1fr]">
                    <section className="min-w-0 rounded-xl bg-card p-4 shadow-sm ring-1 ring-border/40">
                      <div className="mb-4 flex min-w-0 flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
                        <div className="min-w-0">
                          <p className="text-[11px] font-semibold uppercase tracking-wide text-muted-foreground">Workstation</p>
                          <div className="mt-1 flex min-w-0 items-start gap-2">
                            <h2 className="min-w-0 break-words text-2xl font-bold leading-tight text-foreground">
                              {lookupResult.hostname || '—'}
                            </h2>
                            <CopyButton value={lookupResult.hostname} label="Hostname" />
                          </div>
                          <div className="mt-1 flex min-w-0 items-center gap-2">
                            <p className="min-w-0 break-words text-sm text-muted-foreground">
                              {lookupResult.current_user || 'Usuário não identificado'}
                            </p>
                            <CopyButton value={lookupResult.current_user} label="Usuário atual" />
                          </div>
                        </div>
                        <span className="w-fit rounded-full border border-emerald-500/30 bg-emerald-500/10 px-3 py-1 text-xs font-bold text-emerald-600 dark:text-emerald-300">
                          ONLINE
                        </span>
                      </div>

                      <div className="grid gap-3 sm:grid-cols-2">
                        <InfoTile label="IP Address" value={lookupResult.ip_address} copyable />
                        <InfoTile label="MAC Address" value={lookupResult.mac_address} copyable />
                        <InfoTile label="Last Boot" value={lookupResult.last_boot} className="sm:col-span-2" />
                        <InfoTile
                          label="Organization Unit"
                          value={lookupResult.active_directory?.organizational_unit}
                          className="sm:col-span-2"
                          copyable
                        />
                      </div>
                    </section>

                    <section className="min-w-0 rounded-xl bg-card p-4 shadow-sm ring-1 ring-border/40">
                      <div className="mb-4">
                        <p className="text-[11px] font-semibold uppercase tracking-wide text-muted-foreground">Hardware and OS</p>
                        <h3 className="mt-1 text-base font-semibold text-foreground">Resumo do equipamento</h3>
                      </div>

                      <div className="grid gap-3 sm:grid-cols-2">
                        <InfoTile label="Manufacturer" value={lookupResult.manufacturer} />
                        <InfoTile label="Model" value={lookupResult.model} copyable />
                        <InfoTile label="Serial Number" value={lookupResult.serial_number} copyable />
                        <InfoTile label="RAM" value={lookupResult.ram_gb ? `${lookupResult.ram_gb} GB` : ''} />
                        <InfoTile label="Operating System" value={lookupResult.os} className="sm:col-span-2" copyable />
                        <InfoTile label="Processor" value={lookupResult.processor} className="sm:col-span-2" />
                      </div>
                    </section>
                  </div>

                  <section className="min-w-0 rounded-xl bg-card p-4 shadow-sm ring-1 ring-border/40">
                    <div className="mb-4 flex flex-col gap-1">
                      <p className="text-[11px] font-semibold uppercase tracking-wide text-muted-foreground">Storage</p>
                      <h3 className="text-base font-semibold text-foreground">Disco local C:</h3>
                    </div>

                    <div className="space-y-3 text-sm text-muted-foreground">
                      {(() => {
                        const total = lookupResult.storage_total_gb || 0;
                        const free = lookupResult.storage_free_gb || 0;
                        const used = total > 0 ? total - free : 0;
                        const percent = total > 0 ? Math.round((used / total) * 100) : 0;
                        return (
                          <>
                            <div className="grid gap-2 sm:grid-cols-[1fr_auto] sm:items-center">
                              <div className="flex min-w-0 flex-wrap items-baseline gap-x-2 gap-y-1">
                              <span className="font-semibold text-foreground">{used} GB</span>
                              <span className="text-xs text-muted-foreground">usados</span>
                              </div>
                              <div className="flex min-w-0 flex-wrap items-baseline gap-x-2 gap-y-1 sm:justify-end">
                              <span className="font-semibold text-foreground">{free} GB</span>
                              <span className="text-xs text-muted-foreground">livres</span>
                              </div>
                            </div>
                            <div className="w-full h-3 bg-muted rounded-full overflow-hidden mt-2 mb-1">
                              <div
                                className="h-full bg-primary transition-all"
                                style={{ width: `${percent}%` }}
                              />
                            </div>
                            <div className="flex justify-between text-xs text-muted-foreground">
                              <span>Total: {total} GB</span>
                              <span>{percent}% usado</span>
                            </div>
                          </>
                        );
                      })()}
                    </div>
                  </section>

                  {canRunHostActions && diagnosticLoading && !diagnostic && (
                    <section className="rounded-xl bg-card p-4 shadow-sm ring-1 ring-border/40">
                      <div className="flex items-center gap-2 text-sm text-muted-foreground">
                        <Loader2 size={16} className="animate-spin" />
                        Gerando diagnóstico visual...
                      </div>
                    </section>
                  )}

                  {canRunHostActions && diagnostic && (
                    <DiagnosticPanel
                      data={diagnostic}
                      onRefresh={() => loadDiagnostic(selectedHost, true)}
                      onCleanup={runQuickCleanup}
                      quickActions={quickActions}
                      remoteActionLoading={remoteActionLoading}
                      onRemoteAction={handleRemoteAction}
                      refreshing={diagnosticLoading}
                      cleaning={cleanupLoading}
                    />
                  )}
                </div>

                <section className="space-y-4 border-t border-border/60 pt-5">
                  <div>
                    <h2 className="text-xl font-semibold text-foreground">Remote Actions</h2>
                    <p className="mt-1 text-sm text-muted-foreground">
                      Atalhos rápidos para manutenção e suporte remoto da workstation pesquisada.
                    </p>
                  </div>
                    <div className="grid gap-4">
                      <section className="min-w-0 rounded-xl bg-card p-4 shadow-sm ring-1 ring-border/40">
                        <div className="mb-4 min-w-0">
                          <h3 className="text-base font-semibold text-foreground">Configuration Manager</h3>
                          <p className="mt-1 break-words text-sm text-muted-foreground">Software Center, SCCM client e updates do host selecionado.</p>
                        </div>

                        <div className="space-y-3">
                          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
                            <div className="min-w-0 rounded-lg bg-muted/35 px-3 py-2 ring-1 ring-border/40">
                              <p className="text-xs text-muted-foreground">SCCM Client</p>
                              <p className="mt-1 break-words text-sm font-semibold text-foreground">
                                {softwareCenterLoading ? 'Consultando...' : softwareCenter?.installed ? 'Instalado' : 'Não detectado'}
                              </p>
                            </div>
                            <div className="min-w-0 rounded-lg bg-muted/35 px-3 py-2 ring-1 ring-border/40">
                              <p className="text-xs text-muted-foreground">Versão</p>
                              <p className="mt-1 break-words text-sm font-semibold text-foreground">{softwareCenter?.clientVersion || '—'}</p>
                            </div>
                            <div className="min-w-0 rounded-lg bg-muted/35 px-3 py-2 ring-1 ring-border/40">
                              <p className="text-xs text-muted-foreground">Serviço</p>
                              <p className="mt-1 break-words text-sm font-semibold text-foreground">{softwareCenter?.serviceStatus || '—'}</p>
                            </div>
                            <div className="min-w-0 rounded-lg bg-muted/35 px-3 py-2 ring-1 ring-border/40">
                              <p className="text-xs text-muted-foreground">Updates</p>
                              <p className="mt-1 break-words text-sm font-semibold text-foreground">{softwareCenter?.pendingUpdates ?? 0} pendente(s)</p>
                            </div>
                          </div>

                          <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
                            {canRunHostActions && (
                              <Button
                                className="min-h-10 whitespace-normal px-3 py-2 text-center leading-5"
                                disabled={softwareCenterInstalling || !softwareCenter?.installed}
                                onClick={handleInstallSoftwareCenterUpdates}
                              >
                                {softwareCenterInstalling ? (
                                  <Loader2 size={16} className="mr-2 animate-spin" />
                                ) : (
                                  <Play size={16} className="mr-2" />
                                )}
                                Run Updates
                              </Button>
                            )}
                            <Button
                              className="min-h-10 whitespace-normal px-3 py-2 text-center leading-5"
                              variant="outline"
                              disabled={softwareCenterLoading}
                              onClick={() => loadSoftwareCenter(selectedHost)}
                            >
                              <RefreshCw size={16} className={softwareCenterLoading || softwareCenterMonitoring ? 'mr-2 animate-spin' : 'mr-2'} />
                              Refresh
                            </Button>
                          </div>

                          {softwareCenterMonitoring && (
                            <div className="flex min-w-0 items-center gap-2 rounded-lg bg-blue-500/10 px-3 py-2 text-xs font-medium text-blue-700 ring-1 ring-blue-500/25 dark:text-blue-300">
                              <Loader2 size={14} className="shrink-0 animate-spin" />
                              <span className="break-words">Monitorando progresso automaticamente a cada 10s em {softwareCenterMonitorHost || selectedHost}.</span>
                            </div>
                          )}

                          {activeUpdateJob && (
                            <div className="rounded-lg bg-muted/35 p-3 ring-1 ring-border/40">
                              <div className="flex flex-col gap-2 sm:flex-row sm:items-start sm:justify-between">
                                <div className="min-w-0">
                                  <p className="text-xs font-semibold text-foreground">Update job {activeUpdateJob.id}</p>
                                  <p className="mt-1 break-words text-xs text-muted-foreground">{activeUpdateJob.message || 'Acompanhando SCCM Updates.'}</p>
                                </div>
                                <span className="w-fit rounded-full border border-border/70 px-2 py-1 text-xs font-semibold text-muted-foreground">
                                  {activeUpdateJob.status}
                                </span>
                              </div>
                              <div className="mt-3 h-2 w-full overflow-hidden rounded-full bg-background">
                                <div
                                  className="h-full bg-primary transition-all"
                                  style={{ width: `${Math.max(0, Math.min(100, activeUpdateJob.progress || 0))}%` }}
                                />
                              </div>
                              <p className="mt-1 text-right text-xs text-muted-foreground">{activeUpdateJob.progress || 0}%</p>
                            </div>
                          )}

                          {softwareCenter?.updates && softwareCenter.updates.length > 0 && (
                            <div className="overflow-hidden rounded-lg bg-background ring-1 ring-border/40">
                              <div className="grid grid-cols-[minmax(0,1fr)_78px_68px] gap-2 border-b bg-muted/50 px-3 py-2 text-xs font-medium text-muted-foreground">
                                <span>Update</span>
                                <span>Article</span>
                                <span>Progress</span>
                              </div>
                              {softwareCenter.updates.slice(0, 6).map((update, index) => (
                                <div
                                  key={`${update.articleId || update.name}-${index}`}
                                  className="grid grid-cols-[minmax(0,1fr)_78px_68px] gap-2 border-b px-3 py-2 text-xs last:border-0"
                                >
                                  <span className="truncate text-foreground">{update.name || 'Update sem nome'}</span>
                                  <span className="truncate text-muted-foreground">{update.articleId || update.bulletinId || '—'}</span>
                                  <span className="text-right text-muted-foreground">{update.percentComplete || 0}%</span>
                                </div>
                              ))}
                            </div>
                          )}

                          {!softwareCenterLoading && softwareCenter && softwareCenter.updates?.length === 0 && (
                            <div className="rounded-lg bg-muted/35 px-3 py-2 ring-1 ring-border/40">
                              <p className="text-xs text-muted-foreground">Nenhuma atualização pendente listada para este host.</p>
                            </div>
                          )}

                          {softwareCenterMessage && (
                            <MessageBox tone="success">{softwareCenterMessage}</MessageBox>
                          )}
                          {softwareCenterError && (
                            <MessageBox tone="error">{softwareCenterError}</MessageBox>
                          )}

                          {remoteActionMessage && (
                            <MessageBox tone="success">{remoteActionMessage}</MessageBox>
                          )}
                          {remoteActionError && (
                            <MessageBox tone="error">{remoteActionError}</MessageBox>
                          )}
                          {remoteActionDetails && (
                            <pre className="max-h-40 overflow-auto rounded-lg bg-background px-3 py-2 text-xs leading-5 text-muted-foreground whitespace-pre-wrap break-words ring-1 ring-border/40">
                              {remoteActionDetails}
                            </pre>
                          )}
                        </div>
                      </section>
                    </div>
                </section>
                </>
              )}
          </section>

        </div>
      </main>
    </div>
  );
}
