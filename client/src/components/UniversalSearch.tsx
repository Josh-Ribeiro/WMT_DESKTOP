import { FormEvent, useEffect, useRef, useState } from 'react';
import { Clock3, Loader2, Monitor, Search, UserRound } from 'lucide-react';
import { useLocation } from 'wouter';
import { apiRequest } from '@/lib/api';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';

interface UniversalUser {
  sam_account_name: string;
  display_name: string;
  email: string;
  upn: string;
  employee_id: string;
  title: string;
  department: string;
  status: string;
}

interface UniversalWorkstation {
  host: string;
  ip_address: string;
  serial_number: string;
  manufacturer: string;
  model: string;
  current_user: string;
  last_seen: string;
  known: boolean;
}

interface UniversalSearchResult {
  query: string;
  users: UniversalUser[];
  workstations: UniversalWorkstation[];
  user_total: number;
  workstation_total: number;
  user_error?: string;
}

interface RecentSearch {
  type: 'user' | 'workstation';
  label: string;
  value: string;
  detail?: string;
}

const RECENT_SEARCHES_KEY = 'wmt.universalSearch.recent';
const searchCache = new Map<string, { timestamp: number; value: UniversalSearchResult }>();
const SEARCH_CACHE_TTL_MS = 60_000;

function readRecentSearches(): RecentSearch[] {
  try {
    const value = JSON.parse(window.localStorage.getItem(RECENT_SEARCHES_KEY) || '[]');
    return Array.isArray(value) ? value.slice(0, 6) : [];
  } catch {
    return [];
  }
}

interface UniversalSearchProps {
  initialValue?: string;
  onUserSelect?: (query: string) => void;
  onWorkstationSelect?: (host: string) => void;
}

export function UniversalSearch({
  initialValue = '',
  onUserSelect,
  onWorkstationSelect,
}: UniversalSearchProps) {
  const [, navigate] = useLocation();
  const [query, setQuery] = useState(initialValue);
  const [result, setResult] = useState<UniversalSearchResult | null>(null);
  const [recent, setRecent] = useState<RecentSearch[]>(readRecentSearches);
  const [loading, setLoading] = useState(false);
  const [focused, setFocused] = useState(false);
  const requestIdRef = useRef(0);
  const previousInitialValueRef = useRef(initialValue);

  useEffect(() => {
    if (initialValue === previousInitialValueRef.current) return;
    previousInitialValueRef.current = initialValue;
    setQuery(initialValue);
    setResult(null);
  }, [initialValue]);

  const remember = (item: RecentSearch) => {
    const next = [item, ...recent.filter((entry) => !(entry.type === item.type && entry.value === item.value))].slice(0, 6);
    setRecent(next);
    window.localStorage.setItem(RECENT_SEARCHES_KEY, JSON.stringify(next));
  };

  const openUser = (userQuery: string, label = userQuery, detail = '') => {
    remember({ type: 'user', label, value: userQuery, detail });
    setFocused(false);
    if (onUserSelect) {
      onUserSelect(userQuery);
    } else {
      navigate(`/ad-users?query=${encodeURIComponent(userQuery)}`);
    }
  };

  const openWorkstation = (host: string, detail = '') => {
    const normalized = host.trim().toUpperCase();
    remember({ type: 'workstation', label: normalized, value: normalized, detail });
    setFocused(false);
    if (onWorkstationSelect) {
      onWorkstationSelect(normalized);
    } else {
      navigate(`/monitor?host=${encodeURIComponent(normalized)}`);
    }
  };

  useEffect(() => {
    const clean = query.trim();
    setResult(null);
    if (clean.length < 2) {
      setLoading(false);
      return;
    }

    const requestId = ++requestIdRef.current;
    const timer = window.setTimeout(async () => {
      const cacheKey = clean.toLocaleLowerCase();
      const cached = searchCache.get(cacheKey);
      if (cached && Date.now() - cached.timestamp < SEARCH_CACHE_TTL_MS) {
        if (requestIdRef.current === requestId) {
          setResult(cached.value);
          setLoading(false);
        }
        return;
      }
      setLoading(true);
      try {
        const payload = await apiRequest<UniversalSearchResult>('/api/search/universal', {
          method: 'POST',
          body: JSON.stringify({ query: clean, limit: 8 }),
        });
        searchCache.set(cacheKey, { timestamp: Date.now(), value: payload });
        if (searchCache.size > 40) searchCache.delete(searchCache.keys().next().value as string);
        if (requestIdRef.current === requestId) setResult(payload);
      } catch {
        if (requestIdRef.current === requestId) setResult(null);
      } finally {
        if (requestIdRef.current === requestId) setLoading(false);
      }
    }, 450);

    return () => window.clearTimeout(timer);
  }, [query]);

  const submit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const clean = query.trim();
    if (clean.length < 2) return;

    const lower = clean.toLowerCase();
    const exactUser = result?.users.find((item) =>
      [item.sam_account_name, item.email, item.upn, item.employee_id].some((value) => value?.toLowerCase() === lower),
    );
    const exactWorkstation = result?.workstations.find((item) => item.host.toLowerCase() === lower);

    if (exactUser) {
      openUser(
        exactUser.sam_account_name || exactUser.upn || exactUser.email,
        exactUser.display_name || exactUser.sam_account_name,
        exactUser.department,
      );
    } else if (exactWorkstation?.known) {
      openWorkstation(exactWorkstation.host, exactWorkstation.current_user);
    } else if (result?.users.length) {
      openUser(clean, clean, 'Pesquisa no Active Directory');
    } else if (exactWorkstation) {
      openWorkstation(exactWorkstation.host, exactWorkstation.current_user);
    } else if (/^(?:[a-z][a-z0-9_.-]*\d[a-z0-9_.-]*|\d{1,3}(?:\.\d{1,3}){3})$/i.test(clean)) {
      openWorkstation(clean);
    } else {
      openUser(clean, clean, 'Pesquisa no Active Directory');
    }
  };

  const showPanel = focused && (loading || query.trim().length >= 2 || (!query.trim() && recent.length > 0));

  return (
    <div className="relative w-full xl:max-w-2xl">
      <form onSubmit={submit} className="grid w-full gap-2 sm:grid-cols-[minmax(0,1fr)_auto]">
        <div className="relative min-w-0">
          <Search className="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-muted-foreground" />
          <Input
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            onFocus={() => setFocused(true)}
            onBlur={() => window.setTimeout(() => setFocused(false), 160)}
            placeholder="Usuário, e-mail, matrícula, WKS, IP ou serial"
            className="min-w-0 pl-9 pr-9"
            aria-label="Busca universal"
            autoComplete="off"
          />
          {loading && <Loader2 className="absolute right-3 top-1/2 size-4 -translate-y-1/2 animate-spin text-muted-foreground" />}
        </div>
        <Button type="submit" className="min-w-32" disabled={query.trim().length < 2}>
          Pesquisar
        </Button>
      </form>

      {showPanel && (
        <div className="absolute right-0 z-50 mt-2 max-h-[min(65vh,520px)] w-full overflow-y-auto rounded-xl border border-border bg-popover p-2 text-popover-foreground shadow-xl">
          {!query.trim() && recent.length > 0 ? (
            <SearchGroup title="Pesquisas recentes" icon={Clock3}>
              {recent.map((item) => (
                <ResultButton
                  key={`${item.type}-${item.value}`}
                  icon={item.type === 'user' ? UserRound : Monitor}
                  title={item.label}
                  detail={item.detail || (item.type === 'user' ? 'Usuário' : 'Equipamento')}
                  onClick={() => (item.type === 'user' ? openUser(item.value, item.label, item.detail) : openWorkstation(item.value, item.detail))}
                />
              ))}
            </SearchGroup>
          ) : loading && !result ? (
            <div className="flex items-center gap-2 px-3 py-5 text-sm text-muted-foreground">
              <Loader2 className="animate-spin" size={16} />
              Pesquisando usuários e equipamentos...
            </div>
          ) : result && (result.users.length || result.workstations.length) ? (
            <>
              {result.users.length > 0 && (
                <SearchGroup title={`Usuários${result.user_total > result.users.length ? ` (${result.user_total})` : ''}`} icon={UserRound}>
                  {result.users.map((item) => (
                    <ResultButton
                      key={item.sam_account_name || item.upn}
                      icon={UserRound}
                      title={item.display_name || item.sam_account_name}
                      detail={[item.sam_account_name, item.employee_id && `Matrícula ${item.employee_id}`, item.department].filter(Boolean).join(' • ')}
                      meta={item.status}
                      onClick={() =>
                        openUser(
                          item.sam_account_name || item.upn || item.email,
                          item.display_name || item.sam_account_name,
                          item.department,
                        )
                      }
                    />
                  ))}
                </SearchGroup>
              )}
              {result.workstations.length > 0 && (
                <SearchGroup title="Equipamentos" icon={Monitor}>
                  {result.workstations.map((item) => (
                    <ResultButton
                      key={item.host}
                      icon={Monitor}
                      title={item.host}
                      detail={[item.ip_address, item.serial_number && `Serial ${item.serial_number}`, item.current_user].filter(Boolean).join(' • ') || (item.known ? 'Equipamento conhecido' : 'Pesquisar este equipamento')}
                      meta={item.model}
                      onClick={() => openWorkstation(item.host, item.current_user)}
                    />
                  ))}
                </SearchGroup>
              )}
            </>
          ) : !loading && query.trim().length >= 2 ? (
            <button
              type="button"
              className="flex w-full items-center gap-3 rounded-lg px-3 py-3 text-left hover:bg-muted"
              onClick={() => openWorkstation(query)}
            >
              <Monitor className="shrink-0 text-muted-foreground" size={18} />
              <span>
                <span className="block text-sm font-medium">Pesquisar “{query.trim()}” como equipamento</span>
                <span className="block text-xs text-muted-foreground">Nenhum usuário ou equipamento conhecido foi encontrado.</span>
              </span>
            </button>
          ) : null}
        </div>
      )}
    </div>
  );
}

function SearchGroup({ title, icon: Icon, children }: { title: string; icon: typeof Search; children: React.ReactNode }) {
  return (
    <section className="py-1">
      <div className="flex items-center gap-2 px-3 py-2 text-[11px] font-semibold uppercase tracking-wide text-muted-foreground">
        <Icon size={13} />
        {title}
      </div>
      <div className="space-y-1">{children}</div>
    </section>
  );
}

function ResultButton({
  icon: Icon,
  title,
  detail,
  meta,
  onClick,
}: {
  icon: typeof Search;
  title: string;
  detail: string;
  meta?: string;
  onClick: () => void;
}) {
  return (
    <button type="button" className="flex w-full items-center gap-3 rounded-lg px-3 py-2.5 text-left transition-colors hover:bg-muted" onClick={onClick}>
      <span className="flex size-9 shrink-0 items-center justify-center rounded-lg border border-border bg-background">
        <Icon size={17} />
      </span>
      <span className="min-w-0 flex-1">
        <span className="block truncate text-sm font-semibold">{title}</span>
        <span className="block truncate text-xs text-muted-foreground">{detail}</span>
      </span>
      {meta && <span className="max-w-28 truncate text-xs capitalize text-muted-foreground">{meta}</span>}
    </button>
  );
}
