import { useState } from "react";
import { Link, useLocation } from "wouter";
import { Button } from "@/components/ui/button";
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
  SheetTrigger,
} from "@/components/ui/sheet";
import { useLanguage } from "@/contexts/LanguageContext";
import { useAuth } from "@/hooks/useAuth";
import { NAVIGATION_ROUTES, canAccessRoute } from "@/lib/routePolicy";
import { useNestedPageLayout } from "@/contexts/LayoutContext";
import {
  Activity,
  ArrowRightLeft,
  ChevronLeft,
  ChevronRight,
  FileText,
  HardDrive,
  History,
  LayoutDashboard,
  ListChecks,
  LogOut,
  Menu,
  MonitorCog,
  Settings,
  Users,
} from "lucide-react";

interface SidebarProps {
  user?: string;
  permissions?: string[];
  onLogout?: () => void;
}

const iconByRoute = {
  dashboard: LayoutDashboard,
  monitor: Activity,
  tasks: ListChecks,
  backup: HardDrive,
  "machine-replacement": ArrowRightLeft,
  history: History,
  terms: FileText,
  "admin-users": Users,
  "admin-settings": Settings,
  account: Settings,
} as const;

export function Sidebar({
  user = "User",
  permissions = [],
  onLogout,
}: SidebarProps) {
  const [collapsed, setCollapsed] = useState(false);
  const [mobileOpen, setMobileOpen] = useState(false);
  const [location, navigate] = useLocation();
  const { t } = useLanguage();
  const auth = useAuth();
  const nestedPageLayout = useNestedPageLayout();

  if (nestedPageLayout) return null;

  const currentUser = auth.user;
  const effectiveUser = {
    role: currentUser?.role || "",
    permissions: permissions.length
      ? permissions
      : currentUser?.permissions || ["dashboard", "account"],
  };
  const menuItems = NAVIGATION_ROUTES.filter(route =>
    canAccessRoute(effectiveUser, route)
  ).map(route => ({
    href: route.path,
    label: route.label,
    icon: iconByRoute[route.id as keyof typeof iconByRoute],
  }));

  const handleLogout = async () => {
    if (onLogout) {
      onLogout();
      return;
    }
    await auth.logout();
    navigate("/login", { replace: true });
  };

  return (
    <>
      <header className="flex h-14 shrink-0 items-center justify-between border-b border-sidebar-border bg-sidebar/95 px-4 text-sidebar-foreground backdrop-blur md:hidden">
        <div className="flex min-w-0 items-center gap-3">
          <div className="flex size-8 shrink-0 items-center justify-center rounded-lg bg-primary text-primary-foreground shadow-sm shadow-primary/25">
            <MonitorCog size={17} />
          </div>
          <div className="min-w-0">
            <p className="truncate text-sm font-bold tracking-wide">WMT</p>
            <p className="truncate text-[10px] font-medium text-sidebar-foreground/60">
              {t("Command Center")}
            </p>
          </div>
        </div>

        <Sheet open={mobileOpen} onOpenChange={setMobileOpen}>
          <SheetTrigger asChild>
            <Button
              variant="ghost"
              size="icon-sm"
              aria-label="Abrir menu principal"
            >
              <Menu size={19} />
            </Button>
          </SheetTrigger>
          <SheetContent
            side="left"
            className="w-[min(88vw,20rem)] gap-0 border-sidebar-border bg-sidebar p-0 text-sidebar-foreground"
          >
            <SheetHeader className="border-b border-sidebar-border px-5 py-5 text-left">
              <SheetTitle className="flex items-center gap-3 text-sidebar-foreground">
                <span className="flex size-9 items-center justify-center rounded-lg bg-primary text-primary-foreground">
                  <MonitorCog size={19} />
                </span>
                WMT
              </SheetTitle>
              <SheetDescription>{t("Command Center")}</SheetDescription>
            </SheetHeader>

            <nav
              aria-label="Navegação principal"
              className="flex-1 space-y-1 overflow-y-auto p-3"
            >
              {menuItems.map(({ href, label, icon: Icon }) => (
                <Link
                  key={href}
                  href={href}
                  onClick={() => setMobileOpen(false)}
                  aria-current={location === href ? "page" : undefined}
                  className={`flex items-center gap-3 rounded-lg px-3 py-3 text-sm font-medium transition-colors ${
                    location === href
                      ? "bg-primary text-primary-foreground shadow-sm shadow-primary/20"
                      : "text-sidebar-foreground/78 hover:bg-sidebar-accent hover:text-sidebar-accent-foreground"
                  }`}
                >
                  <Icon size={19} className="shrink-0" />
                  {t(label)}
                </Link>
              ))}
            </nav>

            <div className="space-y-3 border-t border-sidebar-border p-4">
              <div className="rounded-lg border border-sidebar-border bg-sidebar-accent/45 px-3 py-2">
                <p className="text-[11px] font-semibold uppercase tracking-wide text-sidebar-foreground/55">
                  {t("Logged in as")}
                </p>
                <p className="mt-1 truncate text-sm font-semibold">
                  {currentUser?.username || user}
                </p>
              </div>
              <Button
                variant="ghost"
                size="sm"
                onClick={() => {
                  setMobileOpen(false);
                  void handleLogout();
                }}
                className="w-full justify-start text-sidebar-foreground/75 hover:bg-sidebar-accent hover:text-sidebar-accent-foreground"
              >
                <LogOut size={18} />
                {t("Logout")}
              </Button>
            </div>
          </SheetContent>
        </Sheet>
      </header>

      <aside
        className={`hidden h-full min-h-0 shrink-0 flex-col border-r border-sidebar-border bg-sidebar/95 text-sidebar-foreground shadow-sm backdrop-blur transition-[width] duration-300 md:flex ${
          collapsed ? "w-20" : "w-64"
        }`}
      >
        <div className="flex items-center justify-between border-b border-sidebar-border p-4">
          {!collapsed && (
            <div className="flex min-w-0 items-center gap-3">
              <div className="flex size-9 shrink-0 items-center justify-center rounded-lg bg-primary text-primary-foreground shadow-sm shadow-primary/25">
                <MonitorCog size={19} />
              </div>
              <div className="min-w-0">
                <p className="truncate text-sm font-bold tracking-wide text-sidebar-foreground">
                  WMT
                </p>
                <p className="truncate text-[11px] font-medium text-sidebar-foreground/60">
                  {t("Command Center")}
                </p>
              </div>
            </div>
          )}
          <Button
            variant="ghost"
            size="sm"
            onClick={() => setCollapsed(!collapsed)}
            className="ml-auto text-sidebar-foreground/70 hover:bg-sidebar-accent hover:text-sidebar-accent-foreground"
          >
            {collapsed ? <ChevronRight size={18} /> : <ChevronLeft size={18} />}
          </Button>
        </div>

        <nav
          aria-label="Navegação principal"
          className="flex-1 space-y-2 overflow-y-auto p-3"
        >
          {menuItems.map(({ href, label, icon: Icon }) => (
            <Link
              key={href}
              href={href}
              title={collapsed ? t(label) : undefined}
              aria-current={location === href ? "page" : undefined}
              className={`group relative flex items-center gap-3 rounded-lg px-3 py-2.5 transition-all ${
                location === href
                  ? "bg-primary text-primary-foreground shadow-sm shadow-primary/20"
                  : "text-sidebar-foreground/78 hover:bg-sidebar-accent hover:text-sidebar-accent-foreground"
              }`}
            >
              {location === href && !collapsed && (
                <span className="absolute -left-1 top-1/2 h-6 w-1 -translate-y-1/2 rounded-r-full bg-primary-foreground/85" />
              )}
              <Icon size={19} className="flex-shrink-0" />
              {!collapsed && (
                <span className="text-sm font-medium">{t(label)}</span>
              )}
            </Link>
          ))}
        </nav>

        <div className="space-y-3 border-t border-sidebar-border p-3">
          {!collapsed && (
            <div className="rounded-lg border border-sidebar-border bg-sidebar-accent/45 px-3 py-2">
              <p className="text-[11px] font-semibold uppercase tracking-wide text-sidebar-foreground/55">
                {t("Logged in as")}
              </p>
              <p className="mt-1 truncate text-sm font-semibold text-sidebar-foreground">
                {currentUser?.username || user}
              </p>
            </div>
          )}
          <Button
            variant="ghost"
            size="sm"
            onClick={() => void handleLogout()}
            className="w-full justify-start text-sidebar-foreground/75 hover:bg-sidebar-accent hover:text-sidebar-accent-foreground"
          >
            <LogOut size={18} />
            {!collapsed && <span className="ml-2">{t("Logout")}</span>}
          </Button>
        </div>
      </aside>
    </>
  );
}
