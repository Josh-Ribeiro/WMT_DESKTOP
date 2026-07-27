import { useEffect, useRef, useState } from 'react';
import { useLocation } from 'wouter';
import {
  BadgeCheck,
  BriefcaseBusiness,
  Building2,
  CalendarClock,
  ChevronDown,
  ChevronRight,
  ClipboardList,
  Copy,
  GitCompare,
  History,
  IdCard,
  KeyRound,
  Loader2,
  Lock,
  Mail,
  MonitorUp,
  Phone,
  RefreshCw,
  ShieldAlert,
  ShieldCheck,
  Tags,
  UserRound,
  UserX,
  UsersRound,
} from 'lucide-react';
import { toast } from 'sonner';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { Sidebar } from '@/components/Sidebar';
import { UniversalSearch } from '@/components/UniversalSearch';
import { apiRequest } from '@/lib/api';
import { useAuth } from '@/hooks/useAuth';

type ADUserStatus = 'active' | 'disabled' | 'locked' | 'not_found' | 'error' | 'unknown' | string;

interface ADUserLookupResult {
  found: boolean;
  query: string;
  status: ADUserStatus;
  status_label: string;
  sam_account_name: string;
  display_name: string;
  email: string;
  upn: string;
  employee_id: string;
  title: string;
  department: string;
  company: string;
  office: string;
  phone: string;
  mobile: string;
  manager: string;
  enabled: boolean;
  locked: boolean;
  password_never_expires: boolean;
  cannot_change_password: boolean;
  created: string;
  changed: string;
  last_logon: string;
  last_logon_raw: string;
  last_bad_password: string;
  bad_password_count: string;
  logon_count: string;
  lockout_time: string;
  password_last_set: string;
  account_expires: string;
  distinguished_name: string;
  organizational_unit: string;
  groups: string[];
  group_count: number;
  release_groups: string[];
  office_licenses: string[];
  license_hints: string[];
  proxy_addresses: string[];
  azure_object_id: string;
  last_workstation?: {
    host: string;
    current_user: string;
    ip_address: string;
    os: string;
    timestamp: string;
    source: string;
  };
  error: string;
}

interface ADUserSearchMatch {
  sam_account_name: string;
  display_name: string;
  email: string;
  upn: string;
  title: string;
  department: string;
  company: string;
  office: string;
  status: ADUserStatus;
  last_logon: string;
  distinguished_name: string;
}

interface ADUserSearchResult {
  query: string;
  matches: ADUserSearchMatch[];
  total: number;
  truncated: boolean;
  error: string;
}

const statusStyles: Record<string, string> = {
  active: 'border-emerald-300 bg-emerald-50 text-emerald-700 dark:border-emerald-400/40 dark:bg-emerald-500/10 dark:text-emerald-200',
  disabled: 'border-zinc-300 bg-zinc-50 text-zinc-700 dark:border-zinc-500/40 dark:bg-zinc-500/10 dark:text-zinc-200',
  locked: 'border-amber-300 bg-amber-50 text-amber-700 dark:border-amber-400/40 dark:bg-amber-500/10 dark:text-amber-200',
  not_found: 'border-red-300 bg-red-50 text-red-700 dark:border-red-400/40 dark:bg-red-500/10 dark:text-red-200',
  error: 'border-red-300 bg-red-50 text-red-700 dark:border-red-400/40 dark:bg-red-500/10 dark:text-red-200',
  unknown: 'border-border bg-muted text-muted-foreground',
};

function statusIcon(status: ADUserStatus) {
  if (status === 'active') return ShieldCheck;
  if (status === 'locked') return Lock;
  if (status === 'disabled') return UserX;
  if (status === 'not_found' || status === 'error') return ShieldAlert;
  return UserRound;
}

function shortGroupName(value: string) {
  const first = String(value || '').split(',', 1)[0];
  return first.toLowerCase().startsWith('cn=') ? first.slice(3).replace(/\\,/g, ',') : first;
}

function buildTicketSummary(result: ADUserLookupResult) {
  return [
    `AD User - ${result.display_name || result.query}`,
    `Status: ${result.status_label || result.status}`,
    `Login: ${result.sam_account_name || 'N/A'}`,
    `UPN: ${result.upn || 'N/A'}`,
    `Email: ${result.email || 'N/A'}`,
    `Cargo: ${result.title || 'N/A'}`,
    `Departamento: ${result.department || 'N/A'}`,
    `Empresa: ${result.company || 'N/A'}`,
    `Gestor: ${result.manager || 'N/A'}`,
    `Ultimo logon: ${result.last_logon || 'N/A'}`,
    `Senha alterada: ${result.password_last_set || 'N/A'}`,
    `Office/M365: ${result.office_licenses.length ? result.office_licenses.join(', ') : 'Sem sinal tratado no AD'}`,
    `Liberacoes: ${result.release_groups.slice(0, 12).join(', ') || 'Sem grupos listados'}`,
  ].join('\n');
}

function CopyButton({ value, label }: { value?: string; label: string }) {
  if (!value) return null;
  return (
    <button
      type="button"
      title={`Copiar ${label}`}
      className="inline-flex size-7 shrink-0 items-center justify-center rounded-md text-muted-foreground transition-colors hover:bg-muted hover:text-foreground"
      onClick={async () => {
        try {
          await navigator.clipboard.writeText(value);
          toast.success(`${label} copiado`);
        } catch {
          toast.error(`Nao foi possivel copiar ${label}`);
        }
      }}
    >
      <Copy size={14} />
    </button>
  );
}

function InfoTile({
  label,
  value,
  icon: Icon,
  copyable = false,
}: {
  label: string;
  value?: string | number | boolean;
  icon: typeof UserRound;
  copyable?: boolean;
}) {
  const text = value === true ? 'Sim' : value === false ? 'Nao' : value ? String(value) : 'N/A';
  return (
    <div className="min-w-0 rounded-lg bg-muted/35 px-4 py-3 ring-1 ring-border/40">
      <div className="flex min-w-0 items-center justify-between gap-2">
        <p className="inline-flex min-w-0 items-center gap-2 text-[11px] font-semibold uppercase tracking-wide text-muted-foreground">
          <Icon size={14} className="shrink-0" />
          <span className="truncate">{label}</span>
        </p>
        {copyable && <CopyButton value={text !== 'N/A' ? text : ''} label={label} />}
      </div>
      <p className="mt-2 min-h-5 break-words text-sm font-semibold leading-5 text-foreground">{text}</p>
    </div>
  );
}

function EmptyPanel({ text }: { text: string }) {
  return (
    <div className="rounded-lg border border-dashed border-border/80 px-4 py-8 text-center">
      <p className="text-sm text-muted-foreground">{text}</p>
    </div>
  );
}

function UserSearchResults({
  search,
  loadingUser,
  onSelect,
}: {
  search: ADUserSearchResult;
  loadingUser: boolean;
  onSelect: (match: ADUserSearchMatch) => void;
}) {
  if (search.error) {
    return (
      <div className="rounded-lg border border-red-300 bg-red-50 p-4 text-sm text-red-800 dark:border-red-400/30 dark:bg-red-500/10 dark:text-red-200">
        {search.error}
      </div>
    );
  }

  if (!search.matches.length) {
    return (
      <Card className="rounded-lg border-border/70 shadow-none">
        <CardContent className="pt-6">
          <EmptyPanel text={`Nenhum usuario encontrado para ${search.query}.`} />
        </CardContent>
      </Card>
    );
  }

  return (
    <Card className="rounded-lg border-border/70 shadow-none">
      <CardHeader>
        <div className="flex flex-col gap-2 sm:flex-row sm:items-start sm:justify-between">
          <div className="min-w-0">
            <CardTitle>Usuarios encontrados</CardTitle>
            <p className="mt-1 text-sm text-muted-foreground">
              Selecione o usuario correto para abrir o monitor completo.
            </p>
          </div>
          <Badge variant="outline">
            {search.truncated ? `${search.matches.length}+ de ${search.total}` : `${search.total} resultado(s)`}
          </Badge>
        </div>
      </CardHeader>
      <CardContent className="grid gap-3 lg:grid-cols-2">
        {search.matches.map((match) => {
          const Icon = statusIcon(match.status);
          const style = statusStyles[match.status] || statusStyles.unknown;
          return (
            <button
              key={`${match.sam_account_name}-${match.upn}-${match.distinguished_name}`}
              type="button"
              className="interactive-row min-h-32 w-full p-4 text-left"
              disabled={loadingUser}
              onClick={() => onSelect(match)}
            >
              <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
                <div className="min-w-0">
                  <div className="flex flex-wrap items-center gap-2">
                    <Badge variant="outline" className={style}>
                      <Icon size={13} />
                      {match.status}
                    </Badge>
                    {match.last_logon && <Badge variant="outline">Logon {match.last_logon}</Badge>}
                  </div>
                  <p className="mt-3 break-words text-base font-semibold text-foreground">
                    {match.display_name || match.sam_account_name || match.upn}
                  </p>
                  <p className="mt-1 break-words text-sm text-muted-foreground">
                    {[match.sam_account_name, match.title, match.department].filter(Boolean).join(' - ') || 'Usuario do AD'}
                  </p>
                  <p className="mt-2 break-words text-xs text-muted-foreground">
                    {match.email || match.upn || 'Sem email/UPN retornado'}
                  </p>
                </div>
                {loadingUser && <Loader2 className="mt-1 shrink-0 animate-spin text-muted-foreground" size={17} />}
              </div>
            </button>
          );
        })}
      </CardContent>
    </Card>
  );
}

function CollapsibleCard({
  title,
  subtitle,
  icon: Icon,
  defaultOpen = true,
  children,
}: {
  title: string;
  subtitle?: string;
  icon: typeof UserRound;
  defaultOpen?: boolean;
  children: React.ReactNode;
}) {
  const [open, setOpen] = useState(defaultOpen);
  const ToggleIcon = open ? ChevronDown : ChevronRight;

  return (
    <Card className="rounded-lg border-border/70 shadow-none">
      <CardHeader>
        <button
          type="button"
          className="flex w-full items-start justify-between gap-3 text-left"
          onClick={() => setOpen((current) => !current)}
          aria-expanded={open}
        >
          <div className="flex min-w-0 items-start gap-3">
            <div className="mt-0.5 flex size-8 shrink-0 items-center justify-center rounded-md border border-border bg-muted">
              <Icon size={16} />
            </div>
            <div className="min-w-0">
              <CardTitle>{title}</CardTitle>
              {subtitle && <p className="mt-1 text-sm text-muted-foreground">{subtitle}</p>}
            </div>
          </div>
          <ToggleIcon className="mt-1 shrink-0 text-muted-foreground" size={18} />
        </button>
      </CardHeader>
      {open && <CardContent>{children}</CardContent>}
    </Card>
  );
}

function PillList({ items, emptyText, limit = 80 }: { items: string[]; emptyText: string; limit?: number }) {
  const visible = items.slice(0, limit);
  if (!visible.length) return <EmptyPanel text={emptyText} />;

  return (
    <div className="flex flex-wrap gap-2">
      {visible.map((item) => (
        <Badge key={item} variant="outline" className="max-w-full bg-card/80">
          <span className="truncate">{shortGroupName(item)}</span>
        </Badge>
      ))}
      {items.length > limit && (
        <Badge variant="outline" className="bg-muted">
          +{items.length - limit}
        </Badge>
      )}
    </div>
  );
}

function uniqueSorted(items: string[]) {
  const byKey = new Map<string, string>();
  items.forEach((item) => {
    const clean = shortGroupName(String(item || '').trim());
    if (clean) byKey.set(clean.toLowerCase(), clean);
  });
  return Array.from(byKey.values()).sort((a, b) => a.localeCompare(b));
}

function missingFrom(reference: string[], target: string[]) {
  const targetKeys = new Set(target.map((item) => shortGroupName(item).toLowerCase()));
  return uniqueSorted(reference).filter((item) => !targetKeys.has(item.toLowerCase()));
}

function extraInTarget(reference: string[], target: string[]) {
  const referenceKeys = new Set(reference.map((item) => shortGroupName(item).toLowerCase()));
  return uniqueSorted(target).filter((item) => !referenceKeys.has(item.toLowerCase()));
}

function CompareDiffBlock({
  title,
  missing,
  extra,
}: {
  title: string;
  missing: string[];
  extra: string[];
}) {
  return (
    <div className="rounded-lg bg-muted/25 p-4 ring-1 ring-border/40">
      <p className="text-sm font-semibold text-foreground">{title}</p>
      <div className="mt-3 grid gap-3 lg:grid-cols-2">
        <div>
          <p className="mb-2 text-xs font-semibold uppercase tracking-wide text-muted-foreground">Faltando no usuario pesquisado</p>
          <PillList items={missing} emptyText="Sem diferencas faltantes." limit={40} />
        </div>
        <div>
          <p className="mb-2 text-xs font-semibold uppercase tracking-wide text-muted-foreground">Extra no usuario pesquisado</p>
          <PillList items={extra} emptyText="Sem extras relevantes." limit={40} />
        </div>
      </div>
    </div>
  );
}

function buildCompareSummary(base: ADUserLookupResult, reference: ADUserLookupResult) {
  const missingLicenses = missingFrom([...reference.office_licenses, ...reference.license_hints], [...base.office_licenses, ...base.license_hints]);
  const missingReleases = missingFrom(reference.release_groups, base.release_groups);
  const extraLicenses = extraInTarget([...reference.office_licenses, ...reference.license_hints], [...base.office_licenses, ...base.license_hints]);
  const extraReleases = extraInTarget(reference.release_groups, base.release_groups);

  return [
    `Comparativo AD Users`,
    `Usuario pesquisado: ${base.display_name || base.sam_account_name || base.query}`,
    `Referencia: ${reference.display_name || reference.sam_account_name || reference.query}`,
    '',
    `Office/M365 faltando: ${missingLicenses.join(', ') || 'Nenhum'}`,
    `Liberacoes faltando: ${missingReleases.join(', ') || 'Nenhuma'}`,
    `Office/M365 extra: ${extraLicenses.join(', ') || 'Nenhum'}`,
    `Liberacoes extra: ${extraReleases.join(', ') || 'Nenhuma'}`,
  ].join('\n');
}

function UserComparePanel({
  base,
  reference,
  referenceQuery,
  loading,
  error,
  onReferenceQueryChange,
  onCompare,
}: {
  base: ADUserLookupResult;
  reference: ADUserLookupResult | null;
  referenceQuery: string;
  loading: boolean;
  error: string;
  onReferenceQueryChange: (value: string) => void;
  onCompare: () => void;
}) {
  const missingLicenses = reference ? missingFrom([...reference.office_licenses, ...reference.license_hints], [...base.office_licenses, ...base.license_hints]) : [];
  const extraLicenses = reference ? extraInTarget([...reference.office_licenses, ...reference.license_hints], [...base.office_licenses, ...base.license_hints]) : [];
  const missingReleases = reference ? missingFrom(reference.release_groups, base.release_groups) : [];
  const extraReleases = reference ? extraInTarget(reference.release_groups, base.release_groups) : [];

  return (
    <Card className="rounded-lg border-border/70 shadow-none">
      <CardHeader className="flex flex-row items-start justify-between gap-3">
        <div className="min-w-0">
          <CardTitle>Comparar usuarios</CardTitle>
          <p className="mt-1 text-sm text-muted-foreground">Compare o usuario pesquisado com uma referencia para ver acessos e licencas diferentes.</p>
        </div>
        {reference && (
          <Button
            variant="outline"
            size="sm"
            onClick={async () => {
              try {
                await navigator.clipboard.writeText(buildCompareSummary(base, reference));
                toast.success('Comparativo copiado');
              } catch {
                toast.error('Nao foi possivel copiar o comparativo');
              }
            }}
          >
            <ClipboardList size={15} />
            Copiar
          </Button>
        )}
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="grid gap-2 sm:grid-cols-[minmax(0,1fr)_auto]">
          <div className="relative min-w-0">
            <GitCompare className="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-muted-foreground" />
            <Input
              value={referenceQuery}
              onChange={(event) => onReferenceQueryChange(event.target.value)}
              placeholder="Usuario de referencia"
              className="pl-9"
              onKeyDown={(event) => {
                if (event.key === 'Enter') onCompare();
              }}
            />
          </div>
          <Button type="button" variant="outline" disabled={referenceQuery.trim().length < 2 || loading} onClick={onCompare}>
            {loading ? <Loader2 className="animate-spin" size={16} /> : <GitCompare size={16} />}
            Comparar
          </Button>
        </div>

        {error && (
          <div className="rounded-lg border border-red-300 bg-red-50 p-3 text-sm text-red-800 dark:border-red-400/30 dark:bg-red-500/10 dark:text-red-200">
            {error}
          </div>
        )}

        {reference ? (
          <div className="space-y-4">
            <div className="grid gap-3 md:grid-cols-2">
              <InfoTile label="Usuario pesquisado" value={base.display_name || base.sam_account_name} icon={UserRound} />
              <InfoTile label="Referencia" value={reference.display_name || reference.sam_account_name} icon={UserRound} />
            </div>
            <CompareDiffBlock title="Office e M365" missing={missingLicenses} extra={extraLicenses} />
            <CompareDiffBlock title="Liberacoes" missing={missingReleases} extra={extraReleases} />
          </div>
        ) : (
          <EmptyPanel text="Informe um usuario de referencia para comparar acessos." />
        )}
      </CardContent>
    </Card>
  );
}

function StatusCard({ result }: { result: ADUserLookupResult }) {
  const Icon = statusIcon(result.status);
  const style = statusStyles[result.status] || statusStyles.unknown;

  return (
    <section className="surface-hero overflow-hidden p-5">
      <div className="flex flex-col gap-5 xl:flex-row xl:items-start xl:justify-between">
        <div className="min-w-0">
          <div className="mb-3 flex flex-wrap items-center gap-2">
            <Badge variant="outline" className={style}>
              <Icon size={14} />
              {result.status_label || result.status}
            </Badge>
            <Badge variant="outline">
              {result.group_count || 0} grupo(s)
            </Badge>
            {result.azure_object_id && (
              <Badge variant="outline" className="border-cyan-300 bg-cyan-50 text-cyan-700 dark:border-cyan-400/40 dark:bg-cyan-500/10 dark:text-cyan-200">
                Azure AD linked
              </Badge>
            )}
          </div>
          <div className="flex min-w-0 items-start gap-2">
            <h1 className="min-w-0 break-words text-2xl font-semibold tracking-normal text-foreground">
              {result.display_name || result.query}
            </h1>
            <CopyButton value={result.display_name} label="Nome" />
          </div>
          <p className="mt-1 break-words text-sm text-muted-foreground">
            {[result.sam_account_name, result.title, result.department].filter(Boolean).join(' - ') || 'Usuario do Active Directory'}
          </p>
        </div>

        <div className="grid w-full gap-2 sm:grid-cols-3 xl:max-w-2xl">
          <InfoTile label="Login" value={result.sam_account_name} icon={IdCard} copyable />
          <InfoTile label="UPN" value={result.upn} icon={BadgeCheck} copyable />
          <InfoTile label="Email" value={result.email} icon={Mail} copyable />
        </div>
      </div>
    </section>
  );
}

export default function ADUsers() {
  const { user, logout } = useAuth();
  const [location, navigate] = useLocation();
  const [lastQuery, setLastQuery] = useState('');
  const [searchResult, setSearchResult] = useState<ADUserSearchResult | null>(null);
  const [result, setResult] = useState<ADUserLookupResult | null>(null);
  const [compareQuery, setCompareQuery] = useState('');
  const [compareResult, setCompareResult] = useState<ADUserLookupResult | null>(null);
  const [compareLoading, setCompareLoading] = useState(false);
  const [compareError, setCompareError] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const initialQueryRef = useRef('');

  const handleLogout = async () => {
    await logout();
    navigate('/login');
  };

  const fetchAdUser = async (value: string) => {
    const clean = value.trim();
    if (clean.length < 2) return null;
    return apiRequest<ADUserLookupResult>('/api/ad-users/lookup', {
      method: 'POST',
      body: JSON.stringify({ query: clean }),
    });
  };

  const searchUsers = async (value: string) => {
    const clean = value.trim();
    if (clean.length < 2) return;
    setLoading(true);
    setError('');
    setLastQuery(clean);
    setResult(null);
    setSearchResult(null);
    setCompareResult(null);
    setCompareError('');
    try {
      const payload = await apiRequest<ADUserSearchResult>('/api/ad-users/search', {
        method: 'POST',
        body: JSON.stringify({ query: clean }),
      });
      setSearchResult(payload);
      if (!payload.matches.length) {
        toast.warning('Usuario nao encontrado no AD', {
          description: payload.error || clean,
        });
      }
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Falha ao consultar usuario';
      setError(message);
      setResult(null);
    } finally {
      setLoading(false);
    }
  };

  const loadSelectedUser = async (value: string) => {
    const clean = value.trim();
    if (clean.length < 2) return;
    setLoading(true);
    setError('');
    setCompareResult(null);
    setCompareError('');
    try {
      const payload = await fetchAdUser(clean);
      if (!payload) return;
      setResult(payload);
      if (!payload.found) {
        toast.warning('Usuario nao encontrado no AD', {
          description: payload.error || clean,
        });
      }
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Falha ao consultar usuario';
      setError(message);
      setResult(null);
    } finally {
      setLoading(false);
    }
  };

  const compareUser = async () => {
    const clean = compareQuery.trim();
    if (clean.length < 2) return;
    setCompareLoading(true);
    setCompareError('');
    try {
      const payload = await fetchAdUser(clean);
      if (!payload) return;
      if (!payload.found) {
        setCompareResult(null);
        setCompareError(payload.error || 'Usuario de referencia nao encontrado.');
        return;
      }
      setCompareResult(payload);
    } catch (err) {
      setCompareResult(null);
      setCompareError(err instanceof Error ? err.message : 'Falha ao comparar usuario');
    } finally {
      setCompareLoading(false);
    }
  };

  useEffect(() => {
    if (!user) return;
    const initialQuery = new URLSearchParams(window.location.search).get('query')?.trim() || '';
    if (initialQuery.length < 2 || initialQueryRef.current === initialQuery) return;

    initialQueryRef.current = initialQuery;
    void searchUsers(initialQuery);
  }, [location, user]);

  if (!user) {
    navigate('/login');
    return null;
  }

  return (
    <div className="flex h-screen bg-background">
      <Sidebar user={user.username} permissions={user.permissions} onLogout={handleLogout} />

      <main className="min-w-0 flex-1 overflow-auto">
        <div className="mx-auto flex w-full max-w-7xl flex-col gap-5 p-6 lg:p-8">
          <section className="relative z-30 overflow-visible rounded-lg border border-border/70 bg-card/95 p-5 shadow-sm backdrop-blur">
            <div className="flex flex-col gap-5 xl:flex-row xl:items-end xl:justify-between">
              <div className="min-w-0">
                <div className="mb-3 flex flex-wrap items-center gap-2">
                  <Badge variant="outline" className="border-blue-300 bg-blue-50 text-blue-700 dark:border-blue-400/40 dark:bg-blue-500/10 dark:text-blue-200">
                    Active Directory
                  </Badge>
                  <span className="inline-flex items-center gap-1 text-xs text-muted-foreground">
                    <UsersRound size={13} />
                    Monitor de usuarios
                  </span>
                </div>
                <h1 className="text-2xl font-semibold tracking-normal text-foreground">AD Users</h1>
                <p className="mt-1 max-w-3xl text-sm text-muted-foreground">
                  Consulta tratada de usuario, status, grupos de liberacao e sinais de licenca Office/M365.
                </p>
              </div>

              <UniversalSearch initialValue={lastQuery} onUserSelect={(value) => void searchUsers(value)} />
            </div>
          </section>

          {error && (
            <div className="rounded-lg border border-red-300 bg-red-50 p-4 text-sm text-red-800 dark:border-red-400/30 dark:bg-red-500/10 dark:text-red-200">
              {error}
            </div>
          )}

          {loading && !result && !searchResult ? (
            <div className="flex items-center justify-center py-20">
              <Loader2 className="animate-spin text-muted-foreground" size={32} />
            </div>
          ) : searchResult && !result ? (
            <UserSearchResults
              search={searchResult}
              loadingUser={loading}
              onSelect={(match) => loadSelectedUser(match.sam_account_name || match.upn || match.email)}
            />
          ) : result ? (
            <>
              <StatusCard result={result} />

              {!result.found ? (
                <Card className="rounded-lg border-border/70 shadow-none">
                  <CardContent className="pt-6">
                    <EmptyPanel text={result.error || `Nenhum usuario encontrado para ${lastQuery}.`} />
                  </CardContent>
                </Card>
              ) : (
                <>
                  <div className="grid gap-5 lg:grid-cols-[minmax(0,1.15fr)_minmax(320px,0.85fr)]">
                    <Card className="rounded-lg border-border/70 shadow-none">
                      <CardHeader className="flex flex-row items-start justify-between gap-3">
                        <CardTitle>Perfil e contato</CardTitle>
                        <Button
                          variant="outline"
                          size="sm"
                          onClick={async () => {
                            try {
                              await navigator.clipboard.writeText(buildTicketSummary(result));
                              toast.success('Resumo copiado para ticket');
                            } catch {
                              toast.error('Nao foi possivel copiar o resumo');
                            }
                          }}
                        >
                          <ClipboardList size={15} />
                          Copiar resumo
                        </Button>
                      </CardHeader>
                      <CardContent className="grid gap-3 sm:grid-cols-2">
                        <InfoTile label="Matricula" value={result.employee_id} icon={IdCard} copyable />
                        <InfoTile label="Cargo" value={result.title} icon={BriefcaseBusiness} />
                        <InfoTile label="Departamento" value={result.department} icon={Building2} />
                        <InfoTile label="Empresa" value={result.company} icon={Building2} />
                        <InfoTile label="Escritorio" value={result.office} icon={Building2} />
                        <InfoTile label="Gestor" value={result.manager} icon={UserRound} />
                        <InfoTile label="Telefone" value={result.phone} icon={Phone} copyable />
                        <InfoTile label="Mobile" value={result.mobile} icon={Phone} copyable />
                      </CardContent>
                    </Card>

                    <Card className="rounded-lg border-border/70 shadow-none">
                      <CardHeader>
                        <CardTitle>Estado da conta</CardTitle>
                      </CardHeader>
                      <CardContent className="grid gap-3 sm:grid-cols-2">
                        <InfoTile label="Habilitada" value={result.enabled} icon={ShieldCheck} />
                        <InfoTile label="Bloqueada" value={result.locked} icon={Lock} />
                        <InfoTile label="Senha nunca expira" value={result.password_never_expires} icon={KeyRound} />
                        <InfoTile label="Nao altera senha" value={result.cannot_change_password} icon={KeyRound} />
                        <InfoTile label="Criado em" value={result.created} icon={CalendarClock} />
                        <InfoTile label="Ultimo logon" value={result.last_logon} icon={CalendarClock} />
                        <InfoTile label="Senha alterada" value={result.password_last_set} icon={CalendarClock} />
                        <InfoTile label="Expira em" value={result.account_expires} icon={CalendarClock} />
                      </CardContent>
                    </Card>
                  </div>

                  <div className="grid gap-5 lg:grid-cols-[minmax(0,0.9fr)_minmax(0,1.1fr)]">
                    <Card className="rounded-lg border-border/70 shadow-none">
                      <CardHeader>
                        <CardTitle className="inline-flex items-center gap-2">
                          <History size={18} />
                          Historico de login
                        </CardTitle>
                        <p className="mt-1 text-sm text-muted-foreground">Sinais de autenticacao disponiveis no AD sem consulta direta ao Event Viewer.</p>
                      </CardHeader>
                      <CardContent className="grid gap-3 sm:grid-cols-2">
                        <div className="sm:col-span-2">
                          {result.last_workstation?.host ? (
                            <button
                              type="button"
                              className="interactive-row w-full p-4 text-left"
                              onClick={() => navigate(`/monitor?host=${encodeURIComponent(result.last_workstation?.host || '')}`)}
                            >
                              <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
                                <div className="min-w-0">
                                  <p className="inline-flex items-center gap-2 text-[11px] font-semibold uppercase tracking-wide text-muted-foreground">
                                    <MonitorUp size={14} />
                                    Ultima WKS vista pelo WMT
                                  </p>
                                  <p className="mt-2 break-words text-base font-semibold text-foreground">
                                    {result.last_workstation.host}
                                  </p>
                                  <p className="mt-1 break-words text-sm text-muted-foreground">
                                    {[result.last_workstation.current_user, result.last_workstation.ip_address, result.last_workstation.os].filter(Boolean).join(' - ')}
                                  </p>
                                </div>
                                <Badge variant="outline" className="w-fit">
                                  {result.last_workstation.timestamp || 'Sem data'}
                                </Badge>
                              </div>
                            </button>
                          ) : (
                            <div className="rounded-lg bg-muted/35 px-4 py-3 ring-1 ring-border/40">
                              <p className="inline-flex items-center gap-2 text-[11px] font-semibold uppercase tracking-wide text-muted-foreground">
                                <MonitorUp size={14} />
                                Ultima WKS vista pelo WMT
                              </p>
                              <p className="mt-2 text-sm text-muted-foreground">
                                Sem workstation registrada para este usuario no historico do WMT.
                              </p>
                            </div>
                          )}
                        </div>
                        <InfoTile label="Ultimo logon conhecido" value={result.last_logon} icon={CalendarClock} />
                        <InfoTile label="Ultimo logon no DC consultado" value={result.last_logon_raw} icon={CalendarClock} />
                        <InfoTile label="Ultima falha de senha" value={result.last_bad_password} icon={ShieldAlert} />
                        <InfoTile label="Falhas de senha" value={result.bad_password_count} icon={ShieldAlert} />
                        <InfoTile label="Logons registrados" value={result.logon_count} icon={History} />
                        <InfoTile label="Bloqueio registrado" value={result.lockout_time} icon={Lock} />
                      </CardContent>
                    </Card>

                    <UserComparePanel
                      base={result}
                      reference={compareResult}
                      referenceQuery={compareQuery}
                      loading={compareLoading}
                      error={compareError}
                      onReferenceQueryChange={setCompareQuery}
                      onCompare={compareUser}
                    />
                  </div>

                  <div className="grid gap-5 lg:grid-cols-[minmax(0,0.9fr)_minmax(0,1.1fr)]">
                    <CollapsibleCard
                      title="Office e M365"
                      subtitle="Sinais tratados por grupos e atributos sincronizados no AD."
                      icon={Tags}
                      defaultOpen={false}
                    >
                      <div className="space-y-4">
                        <PillList items={[...result.office_licenses, ...result.license_hints]} emptyText="Nenhum sinal de licenca Office/M365 encontrado no AD." />
                        {result.proxy_addresses.length > 0 && (
                          <div>
                            <p className="mb-2 text-xs font-semibold uppercase tracking-wide text-muted-foreground">Proxy addresses</p>
                            <PillList items={result.proxy_addresses} emptyText="Sem aliases de email." limit={20} />
                          </div>
                        )}
                      </div>
                    </CollapsibleCard>

                    <CollapsibleCard
                      title="Liberacoes"
                      subtitle="Grupos de acesso retornados pelo AD, excluindo sinais de licenca."
                      icon={UsersRound}
                      defaultOpen={false}
                    >
                        <PillList items={result.release_groups} emptyText="Nenhuma liberacao encontrada para este usuario." />
                    </CollapsibleCard>
                  </div>

                  <Card className="rounded-lg border-border/70 shadow-none">
                    <CardHeader>
                      <CardTitle>Dados do diretorio</CardTitle>
                    </CardHeader>
                    <CardContent className="grid gap-3 lg:grid-cols-2">
                      <InfoTile label="OU" value={result.organizational_unit} icon={Building2} copyable />
                      <InfoTile label="Azure object id" value={result.azure_object_id} icon={BadgeCheck} copyable />
                      <InfoTile label="DN" value={result.distinguished_name} icon={UsersRound} copyable />
                      <InfoTile label="Atualizado em" value={result.changed} icon={RefreshCw} />
                    </CardContent>
                  </Card>
                </>
              )}
            </>
          ) : (
            <Card className="rounded-lg border-border/70 shadow-none">
              <CardContent className="pt-6">
                <EmptyPanel text="Pesquise um usuario para carregar o monitor do AD." />
              </CardContent>
            </Card>
          )}
        </div>
      </main>
    </div>
  );
}
