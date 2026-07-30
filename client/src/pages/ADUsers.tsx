import { useEffect, useRef, useState } from "react";
import { useLocation } from "wouter";
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
  Search,
  ShieldAlert,
  ShieldCheck,
  Tags,
  UserRound,
  UserX,
  UsersRound,
} from "lucide-react";
import { toast } from "sonner";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import {
  EmptyState,
  PageHero,
  PageShell,
  SectionHeading,
} from "@/components/PageLayout";
import { UniversalSearch } from "@/components/UniversalSearch";
import { apiRequest } from "@/lib/api";
import { useAuthenticatedUser } from "@/hooks/useAuth";

type ADUserStatus =
  | "active"
  | "disabled"
  | "locked"
  | "not_found"
  | "error"
  | "unknown"
  | string;

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
  active:
    "border-emerald-300 bg-emerald-50 text-emerald-700 dark:border-emerald-400/40 dark:bg-emerald-500/10 dark:text-emerald-200",
  disabled:
    "border-zinc-300 bg-zinc-50 text-zinc-700 dark:border-zinc-500/40 dark:bg-zinc-500/10 dark:text-zinc-200",
  locked:
    "border-amber-300 bg-amber-50 text-amber-700 dark:border-amber-400/40 dark:bg-amber-500/10 dark:text-amber-200",
  not_found:
    "border-red-300 bg-red-50 text-red-700 dark:border-red-400/40 dark:bg-red-500/10 dark:text-red-200",
  error:
    "border-red-300 bg-red-50 text-red-700 dark:border-red-400/40 dark:bg-red-500/10 dark:text-red-200",
  unknown: "border-border bg-muted text-muted-foreground",
};

function statusIcon(status: ADUserStatus) {
  if (status === "active") return ShieldCheck;
  if (status === "locked") return Lock;
  if (status === "disabled") return UserX;
  if (status === "not_found" || status === "error") return ShieldAlert;
  return UserRound;
}

function shortGroupName(value: string) {
  const first = String(value || "").split(",", 1)[0];
  return first.toLowerCase().startsWith("cn=")
    ? first.slice(3).replace(/\\,/g, ",")
    : first;
}

function buildTicketSummary(result: ADUserLookupResult) {
  return [
    `AD User - ${result.display_name || result.query}`,
    `Status: ${result.status_label || result.status}`,
    `Login: ${result.sam_account_name || "N/A"}`,
    `UPN: ${result.upn || "N/A"}`,
    `Email: ${result.email || "N/A"}`,
    `Cargo: ${result.title || "N/A"}`,
    `Departamento: ${result.department || "N/A"}`,
    `Empresa: ${result.company || "N/A"}`,
    `Gestor: ${result.manager || "N/A"}`,
    `Ultimo logon: ${result.last_logon || "N/A"}`,
    `Senha alterada: ${result.password_last_set || "N/A"}`,
    `Office/M365: ${result.office_licenses.length ? result.office_licenses.join(", ") : "Sem sinal tratado no AD"}`,
    `Liberacoes: ${result.release_groups.slice(0, 12).join(", ") || "Sem grupos listados"}`,
  ].join("\n");
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
  const text =
    value === true
      ? "Sim"
      : value === false
        ? "Nao"
        : value
          ? String(value)
          : "N/A";
  return (
    <div className="min-w-0 rounded-lg bg-muted/35 px-4 py-3 ring-1 ring-border/40">
      <div className="flex min-w-0 items-center justify-between gap-2">
        <p className="inline-flex min-w-0 items-center gap-2 text-[11px] font-semibold uppercase tracking-wide text-muted-foreground">
          <Icon size={14} className="shrink-0" />
          <span className="truncate">{label}</span>
        </p>
        {copyable && (
          <CopyButton value={text !== "N/A" ? text : ""} label={label} />
        )}
      </div>
      <p className="mt-2 min-h-5 break-words text-sm font-semibold leading-5 text-foreground">
        {text}
      </p>
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

function UserLookupSkeleton() {
  return (
    <div
      className="space-y-5"
      aria-label="Carregando dados do usuário"
      aria-busy="true"
    >
      <div className="rounded-xl border border-border/70 bg-card/80 p-5">
        <div className="flex flex-col gap-5 lg:flex-row lg:items-center lg:justify-between">
          <div className="flex items-center gap-4">
            <Skeleton className="size-14 rounded-full" />
            <div className="space-y-3">
              <Skeleton className="h-5 w-48" />
              <Skeleton className="h-4 w-72 max-w-full" />
            </div>
          </div>
          <div className="grid gap-2 sm:grid-cols-3 lg:w-[560px]">
            <Skeleton className="h-20 rounded-lg" />
            <Skeleton className="h-20 rounded-lg" />
            <Skeleton className="h-20 rounded-lg" />
          </div>
        </div>
      </div>
      <div className="grid gap-5 lg:grid-cols-2">
        <Skeleton className="h-72 rounded-xl" />
        <Skeleton className="h-72 rounded-xl" />
      </div>
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
      <div
        role="alert"
        className="rounded-lg border border-red-300 bg-red-50 p-4 text-sm text-red-800 dark:border-red-400/30 dark:bg-red-500/10 dark:text-red-200"
      >
        {search.error}
      </div>
    );
  }

  if (!search.matches.length) {
    return (
      <Card className="rounded-lg border-border/70 shadow-none">
        <CardContent className="pt-6">
          <EmptyState
            icon={UserX}
            title="Nenhum usuário encontrado"
            description={`O Active Directory não retornou correspondências para “${search.query}”.`}
          />
        </CardContent>
      </Card>
    );
  }

  return (
    <Card className="rounded-lg border-border/70 shadow-none">
      <CardHeader>
        <SectionHeading
          title="Usuários encontrados"
          description="Selecione o colaborador correto para abrir o perfil completo."
          action={
            <Badge variant="outline">
              {search.truncated
                ? `${search.matches.length}+ de ${search.total}`
                : `${search.total} resultado(s)`}
            </Badge>
          }
        />
      </CardHeader>
      <CardContent className="grid gap-3 lg:grid-cols-2">
        {search.matches.map(match => {
          const Icon = statusIcon(match.status);
          const style = statusStyles[match.status] || statusStyles.unknown;
          return (
            <button
              key={`${match.sam_account_name}-${match.upn}-${match.distinguished_name}`}
              type="button"
              className="interactive-row group min-h-32 w-full p-4 text-left"
              disabled={loadingUser}
              onClick={() => onSelect(match)}
            >
              <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
                <div className="min-w-0">
                  <div className="flex flex-wrap items-center gap-2">
                    <Badge variant="outline" className={style}>
                      <Icon size={13} />
                      {match.status === "active"
                        ? "Ativo"
                        : match.status === "locked"
                          ? "Bloqueado"
                          : match.status === "disabled"
                            ? "Desabilitado"
                            : match.status}
                    </Badge>
                    {match.last_logon && (
                      <Badge variant="outline">Logon {match.last_logon}</Badge>
                    )}
                  </div>
                  <p className="mt-3 break-words text-base font-semibold text-foreground">
                    {match.display_name || match.sam_account_name || match.upn}
                  </p>
                  <p className="mt-1 break-words text-sm text-muted-foreground">
                    {[match.sam_account_name, match.title, match.department]
                      .filter(Boolean)
                      .join(" · ") || "Usuário do AD"}
                  </p>
                  <p className="mt-2 break-words text-xs text-muted-foreground">
                    {match.email || match.upn || "Sem e-mail ou UPN retornado"}
                  </p>
                </div>
                {loadingUser ? (
                  <Loader2
                    className="mt-1 shrink-0 animate-spin text-muted-foreground"
                    size={17}
                  />
                ) : (
                  <span className="flex size-8 shrink-0 items-center justify-center rounded-full border border-border bg-background text-muted-foreground transition-colors group-hover:text-primary">
                    <ChevronRight size={16} />
                  </span>
                )}
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
          onClick={() => setOpen(current => !current)}
          aria-expanded={open}
        >
          <div className="flex min-w-0 items-start gap-3">
            <div className="mt-0.5 flex size-8 shrink-0 items-center justify-center rounded-md border border-border bg-muted">
              <Icon size={16} />
            </div>
            <div className="min-w-0">
              <CardTitle>{title}</CardTitle>
              {subtitle && (
                <p className="mt-1 text-sm text-muted-foreground">{subtitle}</p>
              )}
            </div>
          </div>
          <ToggleIcon
            className="mt-1 shrink-0 text-muted-foreground"
            size={18}
          />
        </button>
      </CardHeader>
      {open && <CardContent>{children}</CardContent>}
    </Card>
  );
}

function PillList({
  items,
  emptyText,
  limit = 80,
}: {
  items: string[];
  emptyText: string;
  limit?: number;
}) {
  const visible = items.slice(0, limit);
  if (!visible.length) return <EmptyPanel text={emptyText} />;

  return (
    <div className="flex flex-wrap gap-2">
      {visible.map(item => (
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
  items.forEach(item => {
    const clean = shortGroupName(String(item || "").trim());
    if (clean) byKey.set(clean.toLowerCase(), clean);
  });
  return Array.from(byKey.values()).sort((a, b) => a.localeCompare(b));
}

function missingFrom(reference: string[], target: string[]) {
  const targetKeys = new Set(
    target.map(item => shortGroupName(item).toLowerCase())
  );
  return uniqueSorted(reference).filter(
    item => !targetKeys.has(item.toLowerCase())
  );
}

function extraInTarget(reference: string[], target: string[]) {
  const referenceKeys = new Set(
    reference.map(item => shortGroupName(item).toLowerCase())
  );
  return uniqueSorted(target).filter(
    item => !referenceKeys.has(item.toLowerCase())
  );
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
          <p className="mb-2 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
            Faltando no usuario pesquisado
          </p>
          <PillList
            items={missing}
            emptyText="Sem diferencas faltantes."
            limit={40}
          />
        </div>
        <div>
          <p className="mb-2 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
            Extra no usuario pesquisado
          </p>
          <PillList
            items={extra}
            emptyText="Sem extras relevantes."
            limit={40}
          />
        </div>
      </div>
    </div>
  );
}

function buildCompareSummary(
  base: ADUserLookupResult,
  reference: ADUserLookupResult
) {
  const missingLicenses = missingFrom(
    [...reference.office_licenses, ...reference.license_hints],
    [...base.office_licenses, ...base.license_hints]
  );
  const missingReleases = missingFrom(
    reference.release_groups,
    base.release_groups
  );
  const extraLicenses = extraInTarget(
    [...reference.office_licenses, ...reference.license_hints],
    [...base.office_licenses, ...base.license_hints]
  );
  const extraReleases = extraInTarget(
    reference.release_groups,
    base.release_groups
  );

  return [
    `Comparativo de usuários do AD`,
    `Usuario pesquisado: ${base.display_name || base.sam_account_name || base.query}`,
    `Referencia: ${reference.display_name || reference.sam_account_name || reference.query}`,
    "",
    `Office/M365 faltando: ${missingLicenses.join(", ") || "Nenhum"}`,
    `Liberacoes faltando: ${missingReleases.join(", ") || "Nenhuma"}`,
    `Office/M365 extra: ${extraLicenses.join(", ") || "Nenhum"}`,
    `Liberacoes extra: ${extraReleases.join(", ") || "Nenhuma"}`,
  ].join("\n");
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
  const missingLicenses = reference
    ? missingFrom(
        [...reference.office_licenses, ...reference.license_hints],
        [...base.office_licenses, ...base.license_hints]
      )
    : [];
  const extraLicenses = reference
    ? extraInTarget(
        [...reference.office_licenses, ...reference.license_hints],
        [...base.office_licenses, ...base.license_hints]
      )
    : [];
  const missingReleases = reference
    ? missingFrom(reference.release_groups, base.release_groups)
    : [];
  const extraReleases = reference
    ? extraInTarget(reference.release_groups, base.release_groups)
    : [];

  return (
    <Card className="rounded-lg border-border/70 shadow-none">
      <CardHeader className="flex flex-row items-start justify-between gap-3">
        <div className="min-w-0">
          <CardTitle>Comparar usuarios</CardTitle>
          <p className="mt-1 text-sm text-muted-foreground">
            Compare o usuario pesquisado com uma referencia para ver acessos e
            licencas diferentes.
          </p>
        </div>
        {reference && (
          <Button
            variant="outline"
            size="sm"
            onClick={async () => {
              try {
                await navigator.clipboard.writeText(
                  buildCompareSummary(base, reference)
                );
                toast.success("Comparativo copiado");
              } catch {
                toast.error("Nao foi possivel copiar o comparativo");
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
              onChange={event => onReferenceQueryChange(event.target.value)}
              placeholder="Usuario de referencia"
              className="pl-9"
              onKeyDown={event => {
                if (event.key === "Enter") onCompare();
              }}
            />
          </div>
          <Button
            type="button"
            variant="outline"
            disabled={referenceQuery.trim().length < 2 || loading}
            onClick={onCompare}
          >
            {loading ? (
              <Loader2 className="animate-spin" size={16} />
            ) : (
              <GitCompare size={16} />
            )}
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
              <InfoTile
                label="Usuario pesquisado"
                value={base.display_name || base.sam_account_name}
                icon={UserRound}
              />
              <InfoTile
                label="Referencia"
                value={reference.display_name || reference.sam_account_name}
                icon={UserRound}
              />
            </div>
            <CompareDiffBlock
              title="Office e M365"
              missing={missingLicenses}
              extra={extraLicenses}
            />
            <CompareDiffBlock
              title="Liberacoes"
              missing={missingReleases}
              extra={extraReleases}
            />
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
    <section
      className={`relative overflow-hidden rounded-xl border p-5 shadow-md ${
        result.status === "active"
          ? "border-emerald-500/25 bg-gradient-to-br from-emerald-500/12 via-card to-primary/8"
          : result.status === "locked"
            ? "border-amber-500/30 bg-gradient-to-br from-amber-500/12 via-card to-card"
            : "border-border/70 bg-card"
      }`}
    >
      <div
        className={`absolute inset-y-0 left-0 w-1 ${
          result.status === "active"
            ? "bg-emerald-500"
            : result.status === "locked"
              ? "bg-amber-500"
              : "bg-muted-foreground"
        }`}
      />
      <div className="flex flex-col gap-5 xl:flex-row xl:items-start xl:justify-between">
        <div className="min-w-0">
          <div className="mb-3 flex flex-wrap items-center gap-2">
            <Badge variant="outline" className={style}>
              <Icon size={14} />
              {result.status_label || result.status}
            </Badge>
            <Badge variant="outline">{result.group_count || 0} grupo(s)</Badge>
            {result.azure_object_id && (
              <Badge
                variant="outline"
                className="border-cyan-300 bg-cyan-50 text-cyan-700 dark:border-cyan-400/40 dark:bg-cyan-500/10 dark:text-cyan-200"
              >
                Vinculado ao Azure AD
              </Badge>
            )}
          </div>
          <div className="mt-4 flex min-w-0 items-center gap-3">
            <span className="flex size-12 shrink-0 items-center justify-center rounded-full border border-primary/20 bg-primary/10 text-primary shadow-sm">
              <UserRound size={22} />
            </span>
            <div className="min-w-0">
              <div className="flex min-w-0 items-start gap-2">
                <h2 className="min-w-0 break-words text-3xl font-bold tracking-tight text-foreground">
                  {result.display_name || result.query}
                </h2>
                <CopyButton value={result.display_name} label="Nome" />
              </div>
              <p className="mt-1 break-words text-sm text-muted-foreground">
                {[result.sam_account_name, result.title, result.department]
                  .filter(Boolean)
                  .join(" · ") || "Usuário do Active Directory"}
              </p>
            </div>
          </div>
        </div>

        <div className="grid w-full gap-3 xl:max-w-2xl">
          <div className="grid gap-2 sm:grid-cols-3">
            <InfoTile
              label="Login"
              value={result.sam_account_name}
              icon={IdCard}
              copyable
            />
            <InfoTile
              label="UPN"
              value={result.upn}
              icon={BadgeCheck}
              copyable
            />
            <InfoTile
              label="E-mail"
              value={result.email}
              icon={Mail}
              copyable
            />
          </div>
          {result.found && (
            <Button
              variant="outline"
              size="sm"
              className="justify-self-start bg-background/70 sm:justify-self-end"
              onClick={async () => {
                try {
                  await navigator.clipboard.writeText(
                    buildTicketSummary(result)
                  );
                  toast.success("Resumo copiado para o chamado");
                } catch {
                  toast.error("Não foi possível copiar o resumo");
                }
              }}
            >
              <ClipboardList size={15} />
              Copiar resumo para chamado
            </Button>
          )}
        </div>
      </div>
    </section>
  );
}

export default function ADUsers() {
  const user = useAuthenticatedUser();
  const [location, navigate] = useLocation();
  const [lastQuery, setLastQuery] = useState("");
  const [searchResult, setSearchResult] = useState<ADUserSearchResult | null>(
    null
  );
  const [result, setResult] = useState<ADUserLookupResult | null>(null);
  const [compareQuery, setCompareQuery] = useState("");
  const [compareResult, setCompareResult] = useState<ADUserLookupResult | null>(
    null
  );
  const [compareLoading, setCompareLoading] = useState(false);
  const [compareError, setCompareError] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const initialQueryRef = useRef("");

  const fetchAdUser = async (value: string) => {
    const clean = value.trim();
    if (clean.length < 2) return null;
    return apiRequest<ADUserLookupResult>("/api/ad-users/lookup", {
      method: "POST",
      body: JSON.stringify({ query: clean }),
    });
  };

  const searchUsers = async (value: string) => {
    const clean = value.trim();
    if (clean.length < 2) return;
    setLoading(true);
    setError("");
    setLastQuery(clean);
    setResult(null);
    setSearchResult(null);
    setCompareResult(null);
    setCompareError("");
    try {
      const payload = await apiRequest<ADUserSearchResult>(
        "/api/ad-users/search",
        {
          method: "POST",
          body: JSON.stringify({ query: clean }),
        }
      );
      setSearchResult(payload);
      if (!payload.matches.length) {
        toast.warning("Usuario nao encontrado no AD", {
          description: payload.error || clean,
        });
      }
    } catch (err) {
      const message =
        err instanceof Error ? err.message : "Falha ao consultar usuario";
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
    setError("");
    setSearchResult(null);
    setCompareResult(null);
    setCompareError("");
    try {
      const payload = await fetchAdUser(clean);
      if (!payload) return;
      setResult(payload);
      if (!payload.found) {
        toast.warning("Usuario nao encontrado no AD", {
          description: payload.error || clean,
        });
      }
    } catch (err) {
      const message =
        err instanceof Error ? err.message : "Falha ao consultar usuario";
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
    setCompareError("");
    try {
      const payload = await fetchAdUser(clean);
      if (!payload) return;
      if (!payload.found) {
        setCompareResult(null);
        setCompareError(
          payload.error || "Usuario de referencia nao encontrado."
        );
        return;
      }
      setCompareResult(payload);
    } catch (err) {
      setCompareResult(null);
      setCompareError(
        err instanceof Error ? err.message : "Falha ao comparar usuario"
      );
    } finally {
      setCompareLoading(false);
    }
  };

  useEffect(() => {
    if (!user) return;
    const initialQuery =
      new URLSearchParams(window.location.search).get("query")?.trim() || "";
    if (initialQuery.length < 2 || initialQueryRef.current === initialQuery)
      return;

    initialQueryRef.current = initialQuery;
    void searchUsers(initialQuery);
  }, [location, user]);

  return (
    <PageShell>
      <PageHero
        eyebrow="Active Directory"
        icon={UsersRound}
        title="Pesquisa de usuários"
        description="Encontre um colaborador, valide sua conta e reúna as informações necessárias para o atendimento."
        meta={
          <>
            <span className="inline-flex items-center gap-1.5 rounded-full border border-border/70 bg-background/70 px-3 py-1 text-xs font-medium text-muted-foreground">
              <ShieldCheck size={13} />
              Consulta somente leitura
            </span>
            {result?.found && (
              <span className="inline-flex items-center gap-1.5 rounded-full border border-primary/20 bg-primary/10 px-3 py-1 text-xs font-semibold text-primary">
                <UserRound size={13} />
                {result.sam_account_name}
              </span>
            )}
          </>
        }
        action={
          <div className="rounded-xl border border-primary/20 bg-background/90 p-3 shadow-lg shadow-primary/5">
            <p className="mb-2 text-xs font-semibold uppercase tracking-[0.12em] text-muted-foreground">
              Nome, login, e-mail ou matrícula
            </p>
            <UniversalSearch
              initialValue={lastQuery}
              onUserSelect={value => void searchUsers(value)}
            />
          </div>
        }
      />

      {error && (
        <div
          role="alert"
          className="flex flex-col gap-4 rounded-lg border border-red-300 bg-red-50 p-5 text-red-900 dark:border-red-400/30 dark:bg-red-500/10 dark:text-red-100 sm:flex-row sm:items-center sm:justify-between"
        >
          <div>
            <p className="text-sm font-semibold">
              Não foi possível consultar o Active Directory
            </p>
            <p className="mt-1 text-sm text-red-800/80 dark:text-red-100/75">
              {error}
            </p>
          </div>
          <Button
            variant="outline"
            size="sm"
            disabled={!lastQuery || loading}
            onClick={() => void searchUsers(lastQuery)}
          >
            <RefreshCw size={15} className={loading ? "animate-spin" : ""} />
            Tentar novamente
          </Button>
        </div>
      )}

      {loading && !result && !searchResult ? (
        <UserLookupSkeleton />
      ) : searchResult && !result ? (
        <UserSearchResults
          search={searchResult}
          loadingUser={loading}
          onSelect={match =>
            loadSelectedUser(match.sam_account_name || match.upn || match.email)
          }
        />
      ) : result ? (
        <>
          <StatusCard result={result} />

          {!result.found ? (
            <Card className="rounded-lg border-border/70 shadow-none">
              <CardContent className="pt-6">
                <EmptyState
                  icon={UserX}
                  title="Usuário não encontrado"
                  description={
                    result.error ||
                    `O Active Directory não encontrou correspondência para “${lastQuery}”.`
                  }
                />
              </CardContent>
            </Card>
          ) : (
            <>
              <div className="grid gap-5 lg:grid-cols-[minmax(0,1.15fr)_minmax(320px,0.85fr)]">
                <Card className="rounded-lg border-border/70 shadow-none">
                  <CardHeader>
                    <SectionHeading
                      title="Perfil e contato"
                      description="Informações organizacionais e meios de contato do colaborador."
                    />
                  </CardHeader>
                  <CardContent className="grid gap-3 sm:grid-cols-2">
                    <InfoTile
                      label="Matrícula"
                      value={result.employee_id}
                      icon={IdCard}
                      copyable
                    />
                    <InfoTile
                      label="Cargo"
                      value={result.title}
                      icon={BriefcaseBusiness}
                    />
                    <InfoTile
                      label="Departamento"
                      value={result.department}
                      icon={Building2}
                    />
                    <InfoTile
                      label="Empresa"
                      value={result.company}
                      icon={Building2}
                    />
                    <InfoTile
                      label="Escritório"
                      value={result.office}
                      icon={Building2}
                    />
                    <InfoTile
                      label="Gestor"
                      value={result.manager}
                      icon={UserRound}
                    />
                    <InfoTile
                      label="Telefone"
                      value={result.phone}
                      icon={Phone}
                      copyable
                    />
                    <InfoTile
                      label="Celular"
                      value={result.mobile}
                      icon={Phone}
                      copyable
                    />
                  </CardContent>
                </Card>

                <Card className="rounded-lg border-border/70 shadow-none">
                  <CardHeader>
                    <CardTitle>Estado da conta</CardTitle>
                  </CardHeader>
                  <CardContent className="grid gap-3 sm:grid-cols-2">
                    <InfoTile
                      label="Habilitada"
                      value={result.enabled}
                      icon={ShieldCheck}
                    />
                    <InfoTile
                      label="Bloqueada"
                      value={result.locked}
                      icon={Lock}
                    />
                    <InfoTile
                      label="Senha nunca expira"
                      value={result.password_never_expires}
                      icon={KeyRound}
                    />
                    <InfoTile
                      label="Não altera senha"
                      value={result.cannot_change_password}
                      icon={KeyRound}
                    />
                    <InfoTile
                      label="Criado em"
                      value={result.created}
                      icon={CalendarClock}
                    />
                    <InfoTile
                      label="Último logon"
                      value={result.last_logon}
                      icon={CalendarClock}
                    />
                    <InfoTile
                      label="Senha alterada"
                      value={result.password_last_set}
                      icon={CalendarClock}
                    />
                    <InfoTile
                      label="Expira em"
                      value={result.account_expires}
                      icon={CalendarClock}
                    />
                  </CardContent>
                </Card>
              </div>

              <div className="grid gap-5 lg:grid-cols-[minmax(0,0.9fr)_minmax(0,1.1fr)]">
                <Card className="rounded-lg border-border/70 shadow-none">
                  <CardHeader>
                    <CardTitle className="inline-flex items-center gap-2">
                      <History size={18} />
                      Histórico de login
                    </CardTitle>
                    <p className="mt-1 text-sm text-muted-foreground">
                      Sinais de autenticação disponíveis no AD sem consulta
                      direta ao Event Viewer.
                    </p>
                  </CardHeader>
                  <CardContent className="grid gap-3 sm:grid-cols-2">
                    <div className="sm:col-span-2">
                      {result.last_workstation?.host ? (
                        <button
                          type="button"
                          className="interactive-row w-full p-4 text-left"
                          onClick={() =>
                            navigate(
                              `/monitor?host=${encodeURIComponent(result.last_workstation?.host || "")}`
                            )
                          }
                        >
                          <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
                            <div className="min-w-0">
                              <p className="inline-flex items-center gap-2 text-[11px] font-semibold uppercase tracking-wide text-muted-foreground">
                                <MonitorUp size={14} />
                                Última estação vista pelo WMT
                              </p>
                              <p className="mt-2 break-words text-base font-semibold text-foreground">
                                {result.last_workstation.host}
                              </p>
                              <p className="mt-1 break-words text-sm text-muted-foreground">
                                {[
                                  result.last_workstation.current_user,
                                  result.last_workstation.ip_address,
                                  result.last_workstation.os,
                                ]
                                  .filter(Boolean)
                                  .join(" - ")}
                              </p>
                            </div>
                            <Badge variant="outline" className="w-fit">
                              {result.last_workstation.timestamp || "Sem data"}
                            </Badge>
                          </div>
                        </button>
                      ) : (
                        <div className="rounded-lg bg-muted/35 px-4 py-3 ring-1 ring-border/40">
                          <p className="inline-flex items-center gap-2 text-[11px] font-semibold uppercase tracking-wide text-muted-foreground">
                            <MonitorUp size={14} />
                            Última estação vista pelo WMT
                          </p>
                          <p className="mt-2 text-sm text-muted-foreground">
                            Nenhuma estação registrada para este usuário no
                            histórico do WMT.
                          </p>
                        </div>
                      )}
                    </div>
                    <InfoTile
                      label="Último logon conhecido"
                      value={result.last_logon}
                      icon={CalendarClock}
                    />
                    <InfoTile
                      label="Último logon no DC consultado"
                      value={result.last_logon_raw}
                      icon={CalendarClock}
                    />
                    <InfoTile
                      label="Última falha de senha"
                      value={result.last_bad_password}
                      icon={ShieldAlert}
                    />
                    <InfoTile
                      label="Falhas de senha"
                      value={result.bad_password_count}
                      icon={ShieldAlert}
                    />
                    <InfoTile
                      label="Logons registrados"
                      value={result.logon_count}
                      icon={History}
                    />
                    <InfoTile
                      label="Bloqueio registrado"
                      value={result.lockout_time}
                      icon={Lock}
                    />
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
                    <PillList
                      items={[
                        ...result.office_licenses,
                        ...result.license_hints,
                      ]}
                      emptyText="Nenhum sinal de licença Office/M365 encontrado no AD."
                    />
                    {result.proxy_addresses.length > 0 && (
                      <div>
                        <p className="mb-2 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                          Proxy addresses
                        </p>
                        <PillList
                          items={result.proxy_addresses}
                          emptyText="Sem aliases de email."
                          limit={20}
                        />
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
                  <PillList
                    items={result.release_groups}
                    emptyText="Nenhuma liberação encontrada para este usuário."
                  />
                </CollapsibleCard>
              </div>

              <Card className="rounded-lg border-border/70 shadow-none">
                <CardHeader>
                  <CardTitle>Dados do diretorio</CardTitle>
                </CardHeader>
                <CardContent className="grid gap-3 lg:grid-cols-2">
                  <InfoTile
                    label="OU"
                    value={result.organizational_unit}
                    icon={Building2}
                    copyable
                  />
                  <InfoTile
                    label="Azure object id"
                    value={result.azure_object_id}
                    icon={BadgeCheck}
                    copyable
                  />
                  <InfoTile
                    label="DN"
                    value={result.distinguished_name}
                    icon={UsersRound}
                    copyable
                  />
                  <InfoTile
                    label="Atualizado em"
                    value={result.changed}
                    icon={RefreshCw}
                  />
                </CardContent>
              </Card>
            </>
          )}
        </>
      ) : (
        <div className="grid gap-4 lg:grid-cols-[1.1fr_0.9fr]">
          <EmptyState
            icon={Search}
            title="Comece pesquisando um colaborador"
            description="Você pode usar nome, login de rede, e-mail, UPN ou número de matrícula."
            className="min-h-64 bg-card/70"
          />
          <div className="grid gap-3 sm:grid-cols-3 lg:grid-cols-1">
            {[
              {
                icon: UserRound,
                title: "Confirme a identidade",
                text: "Valide login, contato, cargo, departamento e gestor.",
              },
              {
                icon: ShieldCheck,
                title: "Verifique a conta",
                text: "Consulte bloqueio, senha, último logon e situação no AD.",
              },
              {
                icon: Tags,
                title: "Analise os acessos",
                text: "Revise grupos, liberações e sinais de licença Microsoft 365.",
              },
            ].map(({ icon: Icon, title, text }, index) => (
              <div
                key={title}
                className="flex items-start gap-3 rounded-lg border border-border/70 bg-card/80 p-4 shadow-sm"
              >
                <span className="flex size-9 shrink-0 items-center justify-center rounded-lg bg-primary/10 text-primary">
                  <Icon size={17} />
                </span>
                <div>
                  <p className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                    Etapa {index + 1}
                  </p>
                  <p className="mt-1 text-sm font-semibold text-foreground">
                    {title}
                  </p>
                  <p className="mt-1 text-xs leading-5 text-muted-foreground">
                    {text}
                  </p>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}
    </PageShell>
  );
}
