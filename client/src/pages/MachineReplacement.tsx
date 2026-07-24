import { useEffect, useMemo, useRef, useState } from 'react';
import { renderAsync } from 'docx-preview';
import { ArrowLeft, ArrowRight, CheckCircle2, Clock3, Download, FileText, GitCompare, Loader2, MonitorCheck, Play, Printer, RefreshCw, Users } from 'lucide-react';
import { useLocation } from 'wouter';
import { toast } from 'sonner';
import { Sidebar } from '@/components/Sidebar';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Checkbox } from '@/components/ui/checkbox';
import { Input } from '@/components/ui/input';
import { Progress } from '@/components/ui/progress';
import { API_BASE_URL, getStoredToken, apiRequest } from '@/lib/api';
import { useAuth } from '@/hooks/useAuth';

type CheckStatus = 'ok' | 'warning' | 'blocked';

interface Precheck {
  status: CheckStatus;
  checks: Array<{ name: string; status: CheckStatus; message: string }>;
  estimated_size: string;
  message: string;
  quick?: boolean;
}

interface BackupJob {
  id: string;
  status: string;
  progress: number;
  current_step?: number;
  total_steps?: number;
  eta_seconds?: number | null;
  log?: string;
  message?: string;
  summary?: string;
  failures?: string[];
  validation?: { status?: string; checked_items?: number; failed_items?: number; message?: string };
}

interface DiagnosticJob {
  id: string;
  status: string;
  message?: string;
  error?: string;
  payload?: { inventory?: { software?: Array<Record<string, unknown>> } };
}

interface SoftwareRow {
  name: string;
  sourceVersion: string;
  destinationVersion: string;
  presence: 'both' | 'source' | 'destination';
}

interface GeneratedTerm {
  url: string;
  filename: string;
  blob: Blob;
}

const steps = [
  ['Máquinas', 'Origem, destino e colaborador'],
  ['Perfis', 'Selecionar dados da migração'],
  ['Validação', 'Conectividade e espaço'],
  ['Softwares', 'Comparar origem e destino'],
  ['Cópia', 'Executar e acompanhar'],
  ['Conclusão', 'Validar e gerar termo'],
  ['Resumo', 'Registrar no chamado'],
] as const;

function normalizeHost(value: string) {
  return value.trim().replace(/^\\\\/, '').replace(/\\/g, '').toUpperCase();
}

function isInstallableSoftware(app: Record<string, unknown>) {
  const name = String(app.DisplayName || '').trim().toLowerCase();
  const publisher = String(app.Publisher || '').trim().toLowerCase();
  if (!name) return false;
  const genericPatterns = [
    /^update for /,
    /^security update for /,
    /^hotfix for /,
    /\bkb\d{6,8}\b/,
    /language pack/,
    /driver\b/,
    /runtime\b/,
    /redistributable/,
    /windows software development kit/,
    /windows sdk/,
    /windows app runtime/,
    /microsoft visual c\+\+/,
    /microsoft \.net/,
    /microsoft edge update/,
    /webview2 runtime/,
    /heif image extensions/,
    /web media extensions/,
    /vp9 video extensions/,
    /raw image extension/,
  ];
  if (genericPatterns.some((pattern) => pattern.test(name))) return false;
  if (publisher.includes('microsoft') && (name.startsWith('windows ') || name.startsWith('microsoft windows'))) return false;
  return true;
}

function softwareMap(payload?: DiagnosticJob['payload']) {
  const apps = payload?.inventory?.software || [];
  return new Map(
    apps
      .filter(isInstallableSoftware)
      .map((app) => {
        const name = String(app.DisplayName || '').trim();
        return [name.toLowerCase(), { name, version: String(app.DisplayVersion || '') }] as const;
      })
      .filter(([name]) => Boolean(name)),
  );
}

async function waitForDiagnostic(job: DiagnosticJob): Promise<DiagnosticJob> {
  if (!['queued', 'running'].includes(job.status)) return job;
  const started = Date.now();
  let current = job;
  while (['queued', 'running'].includes(current.status) && Date.now() - started < 120000) {
    await new Promise((resolve) => window.setTimeout(resolve, 1200));
    current = await apiRequest<DiagnosticJob>(`/api/diagnostics/jobs/${encodeURIComponent(job.id)}`);
  }
  return current;
}

export default function MachineReplacement() {
  const { user, logout } = useAuth();
  const [, navigate] = useLocation();
  const [step, setStep] = useState(0);
  const [source, setSource] = useState('');
  const [destination, setDestination] = useState('');
  const [employee, setEmployee] = useState('');
  const [destinationPath, setDestinationPath] = useState('D:\\Backup\\Migration');
  const [profiles, setProfiles] = useState<string[]>([]);
  const [selectedProfiles, setSelectedProfiles] = useState<string[]>([]);
  const [profilesLoading, setProfilesLoading] = useState(false);
  const [precheck, setPrecheck] = useState<Precheck | null>(null);
  const [precheckLoading, setPrecheckLoading] = useState(false);
  const [softwareRows, setSoftwareRows] = useState<SoftwareRow[]>([]);
  const [softwareLoading, setSoftwareLoading] = useState(false);
  const [softwareCompared, setSoftwareCompared] = useState(false);
  const [backupJob, setBackupJob] = useState<BackupJob | null>(null);
  const [copying, setCopying] = useState(false);
  const [copyError, setCopyError] = useState('');
  const [termLoading, setTermLoading] = useState(false);
  const [termGenerated, setTermGenerated] = useState(false);
  const [termDocument, setTermDocument] = useState<GeneratedTerm | null>(null);
  const [termPreviewRendering, setTermPreviewRendering] = useState(false);
  const [reportLoading, setReportLoading] = useState(false);
  const [reportPdfUrl, setReportPdfUrl] = useState('');
  const completedJobRef = useRef('');
  const termPreviewRef = useRef<HTMLDivElement>(null);
  const termStyleRef = useRef<HTMLDivElement>(null);
  const reportFrameRef = useRef<HTMLIFrameElement>(null);

  const handleLogout = async () => {
    await logout();
    navigate('/login');
  };

  const loadProfiles = async () => {
    setProfilesLoading(true);
    try {
      const result = await apiRequest<{ users: string[]; count: number }>('/api/backup/users', {
        method: 'POST',
        body: JSON.stringify({ source: normalizeHost(source) }),
      });
      setProfiles(result.users);
      setSelectedProfiles(result.users);
      toast.success(`${result.count} perfil(is) encontrado(s)`);
    } catch (err) {
      toast.error('Falha ao identificar perfis', { description: err instanceof Error ? err.message : normalizeHost(source) });
    } finally {
      setProfilesLoading(false);
    }
  };

  const runPrecheck = async () => {
    setPrecheckLoading(true);
    try {
      const result = await apiRequest<Precheck>('/api/backup/precheck', {
        method: 'POST',
        body: JSON.stringify({
          source: normalizeHost(source),
          destination: normalizeHost(destination),
          users: selectedProfiles,
          destination_path: destinationPath,
          exclude_patterns: ['*.ost'],
          quick: true,
        }),
      });
      setPrecheck(result);
      if (result.status === 'blocked') toast.error(result.message);
      else if (result.status === 'warning') toast.warning(result.message);
      else toast.success(result.message);
    } catch (err) {
      toast.error('Falha na validação', { description: err instanceof Error ? err.message : 'Erro desconhecido' });
    } finally {
      setPrecheckLoading(false);
    }
  };

  const compareSoftware = async () => {
    setSoftwareLoading(true);
    setSoftwareCompared(false);
    try {
      const create = (host: string) =>
        apiRequest<DiagnosticJob>('/api/diagnostics/jobs', {
          method: 'POST',
          body: JSON.stringify({ host: normalizeHost(host), detailed: true }),
        });
      const [sourceJob, destinationJob] = await Promise.all([create(source), create(destination)]);
      const [sourceResult, destinationResult] = await Promise.all([waitForDiagnostic(sourceJob), waitForDiagnostic(destinationJob)]);
      if (sourceResult.status !== 'completed' || destinationResult.status !== 'completed') {
        throw new Error(sourceResult.error || destinationResult.error || 'Não foi possível coletar os dois inventários.');
      }
      const sourceApps = softwareMap(sourceResult.payload);
      const destinationApps = softwareMap(destinationResult.payload);
      const names = Array.from(new Set([...Array.from(sourceApps.keys()), ...Array.from(destinationApps.keys())])).sort();
      setSoftwareRows(
        names.map((name) => ({
          name: (sourceApps.get(name) || destinationApps.get(name))?.name || name,
          sourceVersion: sourceApps.get(name)?.version || '',
          destinationVersion: destinationApps.get(name)?.version || '',
          presence: sourceApps.has(name) && destinationApps.has(name) ? 'both' : sourceApps.has(name) ? 'source' : 'destination',
        })),
      );
      setSoftwareCompared(true);
      toast.success('Comparação de softwares concluída');
    } catch (err) {
      toast.error('Falha ao comparar softwares', { description: err instanceof Error ? err.message : 'Erro desconhecido' });
    } finally {
      setSoftwareLoading(false);
    }
  };

  const startCopy = async () => {
    setCopying(true);
    setCopyError('');
    try {
      const job = await apiRequest<BackupJob>('/api/backup/jobs', {
        method: 'POST',
        body: JSON.stringify({
          source: normalizeHost(source),
          destination: normalizeHost(destination),
          users: selectedProfiles,
          destination_path: destinationPath,
          exclude_patterns: ['*.ost'],
        }),
      });
      setBackupJob(job);
      toast.success('Job de migração iniciado', { description: job.id });
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Erro desconhecido';
      setCopyError(message);
      toast.error('Falha ao iniciar a cópia', { description: message });
    } finally {
      setCopying(false);
    }
  };

  useEffect(() => {
    const jobId = backupJob?.id;
    if (!jobId || !['queued', 'running'].includes(backupJob.status)) return;
    let cancelled = false;
    let timer = 0;

    const poll = async () => {
      try {
        const job = await apiRequest<BackupJob>(`/api/backup/jobs/${encodeURIComponent(jobId)}`);
        if (cancelled) return;
        setBackupJob(job);
        if (['queued', 'running'].includes(job.status)) {
          timer = window.setTimeout(poll, 1500);
        } else if (completedJobRef.current !== job.id) {
          completedJobRef.current = job.id;
          if (job.status === 'completed') {
            toast.success('Migração concluída', { description: job.summary || job.id });
            setStep(5);
          } else {
            const message = job.message || job.summary || 'O job terminou com falha.';
            setCopyError(message);
            toast.error('Migração não concluída', { description: message });
          }
        }
      } catch (err) {
        if (cancelled) return;
        setCopyError(err instanceof Error ? err.message : 'Falha ao atualizar o job.');
        timer = window.setTimeout(poll, 3000);
      }
    };

    timer = window.setTimeout(poll, 500);
    return () => {
      cancelled = true;
      window.clearTimeout(timer);
    };
  }, [backupJob?.id, backupJob?.status]);

  const requestPdf = async (endpoint: string, body: Record<string, unknown>) => {
    const token = getStoredToken();
    const response = await fetch(`${API_BASE_URL}${endpoint}`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
      },
      credentials: 'include',
      body: JSON.stringify(body),
    });
    if (!response.ok) {
      const payload = await response.json().catch(() => ({}));
      throw new Error(payload.detail || `Erro ${response.status}`);
    }
    return URL.createObjectURL(await response.blob());
  };

  const generateTerm = async () => {
    setTermLoading(true);
    try {
      const token = getStoredToken();
      const response = await fetch(`${API_BASE_URL}/api/terms/generate`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          ...(token ? { Authorization: `Bearer ${token}` } : {}),
        },
        credentials: 'include',
        body: JSON.stringify({
          wk: normalizeHost(destination),
          employee_name: employee,
          term_type: 'responsibility',
        }),
      });
      if (!response.ok) {
        const payload = await response.json().catch(() => ({}));
        throw new Error(payload.detail || `Erro ${response.status}`);
      }
      const blob = await response.blob();
      const disposition = response.headers.get('Content-Disposition') || '';
      const filename = disposition.match(/filename="?([^";]+)"?/i)?.[1] || `${normalizeHost(destination)}-responsibility.docx`;
      const document = { url: URL.createObjectURL(blob), filename, blob };
      setTermDocument((current) => {
        if (current) URL.revokeObjectURL(current.url);
        return document;
      });
      setTermGenerated(true);
      toast.success('Termo da rede carregado e pronto para edição');
    } catch (err) {
      toast.error('Falha ao gerar termo', { description: err instanceof Error ? err.message : 'Erro desconhecido' });
    } finally {
      setTermLoading(false);
    }
  };

  useEffect(() => {
    const container = termPreviewRef.current;
    const styleContainer = termStyleRef.current;
    if (!termDocument || !container || !styleContainer) return;
    let cancelled = false;
    container.innerHTML = '';
    styleContainer.innerHTML = '';
    setTermPreviewRendering(true);
    renderAsync(termDocument.blob, container, styleContainer, {
      className: 'wmt-machine-term-preview',
      ignoreFonts: false,
      ignoreHeight: false,
      ignoreWidth: false,
      inWrapper: true,
      renderFooters: true,
      renderHeaders: true,
      useBase64URL: true,
    })
      .then(() => {
        if (cancelled) return;
        container.contentEditable = 'true';
        container.spellcheck = true;
        container.querySelectorAll<HTMLElement>('.wmt-machine-term-preview-wrapper, .wmt-machine-term-preview, section').forEach((element) => {
          element.contentEditable = 'true';
        });
        setTermPreviewRendering(false);
      })
      .catch((err) => {
        if (cancelled) return;
        setTermPreviewRendering(false);
        toast.error('Falha ao renderizar o termo', { description: err instanceof Error ? err.message : 'DOCX inválido' });
      });
    return () => {
      cancelled = true;
    };
  }, [termDocument]);

  const printEditedTerm = () => {
    const container = termPreviewRef.current;
    const styleContainer = termStyleRef.current;
    if (!container?.innerHTML.trim() || !styleContainer || termPreviewRendering) return;
    const frame = window.document.createElement('iframe');
    frame.style.position = 'fixed';
    frame.style.width = '0';
    frame.style.height = '0';
    frame.style.border = '0';
    window.document.body.appendChild(frame);
    const frameDocument = frame.contentDocument;
    const frameWindow = frame.contentWindow;
    if (!frameDocument || !frameWindow) {
      frame.remove();
      return;
    }
    frameDocument.open();
    frameDocument.write(`<!doctype html><html><head><meta charset="utf-8">${styleContainer.innerHTML}<style>body{margin:0;background:#fff}.wmt-machine-term-preview-wrapper{padding:0!important;background:#fff!important}@page{margin:12mm}@media print{html,body{margin:0!important;padding:0!important}}</style></head><body>${container.innerHTML}</body></html>`);
    frameDocument.close();
    window.setTimeout(() => {
      frameWindow.focus();
      frameWindow.print();
      window.setTimeout(() => frame.remove(), 1000);
    }, 200);
  };

  const downloadPdf = (url: string, filename: string) => {
    const anchor = document.createElement('a');
    anchor.href = url;
    anchor.download = filename;
    anchor.click();
  };

  const applicationsToInstall = useMemo(
    () => softwareRows.filter((row) => row.presence === 'source' || (row.presence === 'both' && row.sourceVersion !== row.destinationVersion)),
    [softwareRows],
  );

  const generateReport = async () => {
    setReportLoading(true);
    try {
      const url = await requestPdf('/api/machine-replacement/report', {
        source: normalizeHost(source),
        destination: normalizeHost(destination),
        employee_name: employee,
        technician: user?.username || '',
        profiles: selectedProfiles,
        precheck_status: precheck?.status || '',
        precheck_message: precheck?.message || '',
        backup_job_id: backupJob?.id || '',
        backup_status: backupJob?.status || '',
        backup_summary: backupJob?.summary || backupJob?.message || '',
        validation_status: backupJob?.validation?.status || '',
        term_generated: termGenerated,
        applications: applicationsToInstall.map((row) => ({
          name: row.name,
          source_version: row.sourceVersion,
          destination_version: row.destinationVersion,
          action: row.presence === 'source' ? 'Instalar no destino' : `Atualizar para ${row.sourceVersion || 'versao da origem'}`,
        })),
      });
      if (reportPdfUrl) URL.revokeObjectURL(reportPdfUrl);
      setReportPdfUrl(url);
      toast.success('Relatório PDF gerado');
    } catch (err) {
      toast.error('Falha ao gerar relatório', { description: err instanceof Error ? err.message : 'Erro desconhecido' });
    } finally {
      setReportLoading(false);
    }
  };

  useEffect(() => {
    return () => {
      if (termDocument) URL.revokeObjectURL(termDocument.url);
    };
  }, [termDocument]);

  useEffect(() => {
    return () => {
      if (reportPdfUrl) URL.revokeObjectURL(reportPdfUrl);
    };
  }, [reportPdfUrl]);

  const softwareDifferences = useMemo(
    () => softwareRows.filter((row) => row.presence !== 'both' || row.sourceVersion !== row.destinationVersion),
    [softwareRows],
  );

  const canAdvance =
    step === 0 ? Boolean(source.trim() && destination.trim() && normalizeHost(source) !== normalizeHost(destination)) :
    step === 1 ? selectedProfiles.length > 0 :
    step === 2 ? Boolean(precheck && precheck.status !== 'blocked') :
    step === 3 ? softwareCompared :
    step === 4 ? backupJob?.status === 'completed' :
    step === 5 ? backupJob?.status === 'completed' :
    true;

  if (!user) {
    navigate('/login');
    return null;
  }

  return (
    <div className="flex h-screen bg-background">
      <Sidebar user={user.username} permissions={user.permissions} onLogout={handleLogout} />
      <main className="min-w-0 flex-1 overflow-auto">
        <div className="mx-auto w-full max-w-6xl space-y-5 p-6 lg:p-8">
          <section className="relative overflow-hidden rounded-2xl border border-primary/20 bg-gradient-to-br from-primary/12 via-card to-card p-6 shadow-sm">
            <div className="absolute -right-16 -top-20 size-64 rounded-full bg-primary/10 blur-3xl" />
            <div className="relative flex flex-col gap-4 lg:flex-row lg:items-end lg:justify-between">
              <div>
                <Badge variant="outline" className="border-primary/30 bg-background/70">Assistente operacional</Badge>
                <h1 className="mt-3 text-3xl font-semibold tracking-tight">Troca de máquina</h1>
                <p className="mt-2 max-w-2xl text-sm text-muted-foreground">Uma migração guiada, com validações rápidas e acompanhamento visível do início ao fim.</p>
              </div>
              <div className="grid grid-cols-2 gap-2 text-xs">
                <div className="rounded-xl border bg-background/75 px-4 py-3"><p className="text-muted-foreground">Origem</p><p className="mt-1 font-semibold">{normalizeHost(source) || 'A definir'}</p></div>
                <div className="rounded-xl border bg-background/75 px-4 py-3"><p className="text-muted-foreground">Destino</p><p className="mt-1 font-semibold">{normalizeHost(destination) || 'A definir'}</p></div>
              </div>
            </div>
          </section>

          <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-7">
            {steps.map(([title], index) => (
              <button key={title} onClick={() => index <= step && setStep(index)} className={`group rounded-xl border p-3 text-left transition-all ${index === step ? 'border-primary bg-primary text-primary-foreground shadow-md shadow-primary/15' : index < step ? 'border-emerald-500/40 bg-emerald-500/5 hover:bg-emerald-500/10' : 'border-border bg-card opacity-65'}`}>
                <span className={`mb-2 flex size-6 items-center justify-center rounded-full text-xs font-bold ${index === step ? 'bg-primary-foreground/20' : index < step ? 'bg-emerald-500 text-white' : 'bg-muted'}`}>{index < step ? '✓' : index + 1}</span>
                <p className="truncate text-xs font-semibold">{title}</p>
              </button>
            ))}
          </div>

          <Card className="overflow-hidden rounded-2xl border-border/70 shadow-sm">
            <CardHeader><CardTitle>{steps[step][0]}</CardTitle><p className="text-sm text-muted-foreground">{steps[step][1]}</p></CardHeader>
            <CardContent className="space-y-4">
              {step === 0 && (
                <div className="grid gap-4 md:grid-cols-2">
                  <label className="space-y-2 text-sm"><span>WKS de origem</span><Input value={source} onChange={(event) => { setSource(event.target.value.toUpperCase()); setPrecheck(null); }} placeholder="WKS048-001BR" /></label>
                  <label className="space-y-2 text-sm"><span>WKS de destino</span><Input value={destination} onChange={(event) => { setDestination(event.target.value.toUpperCase()); setPrecheck(null); }} placeholder="WKS048-002BR" /></label>
                  <label className="space-y-2 text-sm"><span>Nome do colaborador</span><Input value={employee} onChange={(event) => setEmployee(event.target.value)} placeholder="Nome completo" /></label>
                  <label className="space-y-2 text-sm"><span>Destino da migração</span><Input value={destinationPath} onChange={(event) => setDestinationPath(event.target.value)} placeholder="D:\\Backup\\Migration" /></label>
                </div>
              )}

              {step === 1 && (
                <>
                  <Button onClick={loadProfiles} disabled={profilesLoading}>{profilesLoading ? <Loader2 className="animate-spin" size={16} /> : <Users size={16} />}Identificar perfis</Button>
                  <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-3">
                    {profiles.map((profile) => (
                      <label key={profile} className="flex items-center gap-2 rounded-lg border p-3 text-sm">
                        <Checkbox checked={selectedProfiles.includes(profile)} onCheckedChange={() => setSelectedProfiles((current) => current.includes(profile) ? current.filter((item) => item !== profile) : [...current, profile])} />
                        {profile}
                      </label>
                    ))}
                    {!profiles.length && <p className="text-sm text-muted-foreground">Clique em “Identificar perfis” para consultar {normalizeHost(source)}.</p>}
                  </div>
                </>
              )}

              {step === 2 && (
                <>
                  <div className="flex flex-wrap items-center gap-3">
                    <Button onClick={runPrecheck} disabled={precheckLoading}>{precheckLoading ? <Loader2 className="animate-spin" size={16} /> : <MonitorCheck size={16} />}{precheckLoading ? 'Validando...' : 'Executar validação rápida'}</Button>
                    <span className="text-xs text-muted-foreground">Sem varredura profunda das pastas; conectividade, acesso, perfis e disco continuam sendo verificados.</span>
                  </div>
                  {precheckLoading && <div className="rounded-xl border border-blue-500/25 bg-blue-500/5 p-4"><div className="flex items-center gap-3 text-sm"><Loader2 className="animate-spin text-blue-500" size={18} /><div><p className="font-semibold">Validando origem e destino em paralelo</p><p className="text-muted-foreground">Consultando conectividade, acesso remoto e disco...</p></div></div><Progress value={75} className="mt-3" /></div>}
                  {precheck && <div className="space-y-3"><div className="flex flex-wrap items-center gap-2"><Badge variant={precheck.status === 'blocked' ? 'destructive' : 'outline'}>{precheck.status}</Badge><span className="text-sm">{precheck.quick ? 'Validação rápida' : `Estimativa: ${precheck.estimated_size}`}</span></div><div className="grid gap-3 md:grid-cols-2">{precheck.checks.map((check) => <div key={`${check.name}-${check.message}`} className="flex gap-3 rounded-xl border bg-muted/20 p-3 text-sm"><CheckCircle2 className={check.status === 'ok' ? 'text-emerald-500' : check.status === 'warning' ? 'text-amber-500' : 'text-red-500'} size={18} /><div><p className="font-semibold">{check.name}</p><p className="mt-1 text-xs text-muted-foreground">{check.message}</p></div></div>)}</div></div>}
                </>
              )}

              {step === 3 && (
                <>
                  <Button onClick={compareSoftware} disabled={softwareLoading}>{softwareLoading ? <Loader2 className="animate-spin" size={16} /> : <GitCompare size={16} />}Comparar softwares</Button>
                  <div className="max-h-[430px] overflow-auto rounded-lg border">
                    {softwareDifferences.map((row) => <div key={row.name} className="grid grid-cols-[minmax(0,1fr)_130px_130px] gap-3 border-b px-3 py-2 text-sm last:border-0"><span className="truncate font-medium">{row.name}</span><span>{row.sourceVersion || 'Não instalado'}</span><span>{row.destinationVersion || 'Não instalado'}</span></div>)}
                    {softwareCompared && !softwareDifferences.length && <p className="p-6 text-center text-sm text-muted-foreground">Os softwares das duas máquinas são equivalentes.</p>}
                  </div>
                </>
              )}

              {step === 4 && (
                <div className="space-y-4">
                  <div className="flex flex-wrap gap-2">
                    <Button onClick={startCopy} disabled={copying || ['queued', 'running'].includes(backupJob?.status || '') || precheck?.status === 'blocked'}>{copying ? <Loader2 className="animate-spin" size={16} /> : <Play size={16} />}{copying ? 'Criando job...' : backupJob ? 'Iniciar nova cópia' : 'Iniciar cópia'}</Button>
                    <Button variant="outline" onClick={() => navigate('/backup')}><RefreshCw size={16} />Abrir central de backups</Button>
                  </div>
                  {copyError && <div className="rounded-xl border border-red-500/30 bg-red-500/5 p-4 text-sm text-red-600 dark:text-red-300"><p className="font-semibold">O job encontrou um problema</p><p className="mt-1">{copyError}</p></div>}
                  {backupJob && <div className="space-y-4 rounded-xl border bg-muted/15 p-5">
                    <div className="flex flex-wrap items-start justify-between gap-3"><div><div className="flex items-center gap-2"><Badge variant={backupJob.status === 'completed' ? 'outline' : backupJob.status === 'failed' ? 'destructive' : 'default'}>{backupJob.status}</Badge><span className="font-mono text-xs text-muted-foreground">{backupJob.id}</span></div><p className="mt-2 text-sm font-semibold">{backupJob.message || 'Job registrado no backend'}</p></div><span className="text-2xl font-semibold">{backupJob.progress || 0}%</span></div>
                    <Progress value={backupJob.progress || 0} />
                    <div className="grid gap-3 text-xs sm:grid-cols-3"><div className="rounded-lg bg-background p-3"><p className="text-muted-foreground">Etapa</p><p className="mt-1 font-semibold">{backupJob.current_step || 0}/{backupJob.total_steps || '—'}</p></div><div className="rounded-lg bg-background p-3"><p className="text-muted-foreground">Atualização</p><p className="mt-1 flex items-center gap-1 font-semibold"><RefreshCw className={['queued', 'running'].includes(backupJob.status) ? 'animate-spin' : ''} size={13} />Automática a cada 1,5s</p></div><div className="rounded-lg bg-background p-3"><p className="text-muted-foreground">Tempo estimado</p><p className="mt-1 flex items-center gap-1 font-semibold"><Clock3 size={13} />{backupJob.eta_seconds ? `${Math.ceil(backupJob.eta_seconds / 60)} min` : 'Calculando'}</p></div></div>
                    {backupJob.log && <pre className="max-h-36 overflow-auto whitespace-pre-wrap rounded-lg bg-zinc-950 p-3 text-[11px] text-zinc-200">{backupJob.log.split(/\r?\n/).slice(-8).join('\n')}</pre>}
                    {backupJob.failures?.length ? <p className="text-sm text-red-500">{backupJob.failures.slice(0, 3).join(' • ')}</p> : null}
                  </div>}
                </div>
              )}

              {step === 5 && (
                <div className="space-y-4">
                  <div className="rounded-lg border border-emerald-500/40 bg-emerald-500/5 p-4"><p className="font-semibold text-emerald-700 dark:text-emerald-300">Cópia concluída</p><p className="mt-1 text-sm text-muted-foreground">{backupJob?.validation?.message || backupJob?.summary || 'A rotina terminou sem bloqueios.'}</p></div>
                  <div className="flex flex-wrap gap-2">
                    <Button onClick={generateTerm} disabled={termLoading}>{termLoading ? <Loader2 className="animate-spin" size={16} /> : <FileText size={16} />}{termGenerated ? 'Gerar novamente' : 'Gerar termo'}</Button>
                    <Button variant="outline" disabled={!termDocument} title={!termDocument ? 'Gere o termo primeiro' : 'Baixar DOCX original'} onClick={() => termDocument && downloadPdf(termDocument.url, termDocument.filename)}><Download size={16} />Baixar DOCX</Button>
                    <Button variant="outline" disabled={!termDocument || termPreviewRendering} title={!termDocument ? 'Gere o termo primeiro' : 'Imprimir conteúdo editado'} onClick={printEditedTerm}><Printer size={16} />Imprimir editado</Button>
                  </div>
                  {!termDocument && <p className="text-sm text-muted-foreground">O WMT carregará o mesmo termo de responsabilidade e aceitação configurado no módulo Terms.</p>}
                  {termDocument && <div className="overflow-hidden rounded-xl border bg-muted/20"><div className="flex flex-wrap items-center justify-between gap-2 border-b px-4 py-2 text-xs text-muted-foreground"><span>{termDocument.filename}</span><div className="flex items-center gap-2"><span>Clique no documento para editar antes de imprimir.</span><Badge variant="outline">DOCX da rede</Badge></div></div><div ref={termStyleRef} />{termPreviewRendering && <div className="flex h-40 items-center justify-center gap-2 text-sm text-muted-foreground"><Loader2 className="animate-spin" size={16} />Renderizando documento...</div>}<div className="max-h-[680px] overflow-auto bg-zinc-200 p-4 dark:bg-zinc-900"><div ref={termPreviewRef} className={termPreviewRendering ? 'hidden' : 'mx-auto max-w-[960px] cursor-text rounded bg-white p-3 text-black outline-none focus-within:ring-2 focus-within:ring-primary/40'} /></div></div>}
                </div>
              )}

              {step === 6 && (
                <div className="space-y-4">
                  <div className="rounded-xl border bg-muted/20 p-4">
                    <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
                      <div><p className="font-semibold">Relatório final da migração</p><p className="mt-1 text-sm text-muted-foreground">Inclui dados copiados, resultado do backup e {applicationsToInstall.length} aplicativo(s) que exigem instalação ou atualização.</p></div>
                      <div className="flex flex-wrap gap-2">
                        <Button onClick={generateReport} disabled={reportLoading}>{reportLoading ? <Loader2 className="animate-spin" size={16} /> : <FileText size={16} />}{reportPdfUrl ? 'Atualizar PDF' : 'Gerar PDF'}</Button>
                        <Button variant="outline" disabled={!reportPdfUrl} onClick={() => downloadPdf(reportPdfUrl, `troca-${normalizeHost(source)}-${normalizeHost(destination)}.pdf`)}><Download size={16} />Baixar</Button>
                        <Button variant="outline" disabled={!reportPdfUrl} onClick={() => reportFrameRef.current?.contentWindow?.print()}><Printer size={16} />Imprimir</Button>
                      </div>
                    </div>
                  </div>
                  {reportLoading && <div className="flex items-center justify-center gap-3 rounded-xl border py-16 text-sm text-muted-foreground"><Loader2 className="animate-spin" size={20} />Montando relatório e convertendo para PDF...</div>}
                  {reportPdfUrl && !reportLoading && <div className="overflow-hidden rounded-xl border bg-muted/20"><div className="flex items-center justify-between border-b px-4 py-2 text-xs text-muted-foreground"><span>Relatório da troca de máquina</span><Badge variant="outline">Exibido no WMT</Badge></div><iframe ref={reportFrameRef} title="Relatório da troca de máquina" src={reportPdfUrl} className="h-[720px] w-full bg-white" /></div>}
                </div>
              )}

              <div className="flex justify-between border-t pt-4">
                <Button variant="outline" onClick={() => setStep((current) => Math.max(0, current - 1))} disabled={step === 0}><ArrowLeft size={16} />Anterior</Button>
                {step < steps.length - 1 && <Button onClick={() => setStep((current) => Math.min(steps.length - 1, current + 1))} disabled={!canAdvance}>Próximo<ArrowRight size={16} /></Button>}
              </div>
            </CardContent>
          </Card>
        </div>
      </main>
    </div>
  );
}
