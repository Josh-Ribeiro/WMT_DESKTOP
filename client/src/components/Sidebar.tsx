import { useState } from 'react';
import { Link, useLocation } from 'wouter';
import { Button } from '@/components/ui/button';
import { useLanguage } from '@/contexts/LanguageContext';
import {
  LayoutDashboard,
  Activity,
  History,
  ListChecks,
  HardDrive,
  FileText,
  Users,
  Settings,
  LogOut,
  ChevronLeft,
  ChevronRight,
  MonitorCog,
  ArrowRightLeft,
} from 'lucide-react';

interface SidebarProps {
  user?: string;
  permissions?: string[];
  onLogout?: () => void;
}

export function Sidebar({ user = 'User', permissions = [], onLogout }: SidebarProps) {
  const [collapsed, setCollapsed] = useState(false);
  const [location] = useLocation();
  const { t } = useLanguage();

  const effectivePermissions = permissions.length ? permissions : ['dashboard', 'account'];
  const menuItems = [
    { href: '/dashboard', label: 'Dashboard', icon: LayoutDashboard, permission: 'dashboard' },
    { href: '/monitor', label: 'Monitor', icon: Activity, permission: 'monitor' },
    { href: '/tasks', label: 'Tasks', icon: ListChecks, permission: 'tasks' },
    { href: '/backup', label: 'Backup', icon: HardDrive, permission: 'backup' },
    { href: '/machine-replacement', label: 'Troca de máquina', icon: ArrowRightLeft, permission: 'backup' },
    { href: '/history', label: 'WK History', icon: History, permission: 'monitor' },
    { href: '/terms', label: 'Terms', icon: FileText, permission: 'terms' },
    { href: '/admin/users', label: 'Users', icon: Users, permission: 'users' },
    { href: '/admin/settings', label: 'Admin Settings', icon: Settings, permission: 'settings' },
    { href: '/account', label: 'Settings', icon: Settings, permission: 'account' },
  ].filter((item) => effectivePermissions.includes(item.permission));

  const isActive = (href: string) => location === href;

  return (
    <aside
      className={`flex h-screen flex-col border-r border-sidebar-border bg-sidebar/95 text-sidebar-foreground shadow-sm backdrop-blur transition-all duration-300 ${
        collapsed ? 'w-20' : 'w-64'
      }`}
    >
      <div className="flex items-center justify-between border-b border-sidebar-border p-4">
        {!collapsed && (
          <div className="flex min-w-0 items-center gap-3">
            <div className="flex size-9 shrink-0 items-center justify-center rounded-lg bg-primary text-primary-foreground shadow-sm shadow-primary/25">
              <MonitorCog size={19} />
            </div>
            <div className="min-w-0">
              <p className="truncate text-sm font-bold tracking-wide text-sidebar-foreground">WMT</p>
              <p className="truncate text-[11px] font-medium text-sidebar-foreground/60">{t('Command Center')}</p>
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

      <nav className="flex-1 overflow-y-auto p-3 space-y-2">
        {menuItems.map(({ href, label, icon: Icon }) => (
          <Link
            key={href}
            href={href}
            title={collapsed ? t(label) : undefined}
            className={`group relative flex items-center gap-3 rounded-lg px-3 py-2.5 transition-all ${
              isActive(href)
                ? 'bg-primary text-primary-foreground shadow-sm shadow-primary/20'
                : 'text-sidebar-foreground/78 hover:bg-sidebar-accent hover:text-sidebar-accent-foreground'
            }`}
          >
            {isActive(href) && !collapsed && (
              <span className="absolute -left-1 top-1/2 h-6 w-1 -translate-y-1/2 rounded-r-full bg-primary-foreground/85" />
            )}
            <Icon size={19} className="flex-shrink-0" />
            {!collapsed && <span className="text-sm font-medium">{t(label)}</span>}
          </Link>
        ))}
      </nav>

      <div className="space-y-3 border-t border-sidebar-border p-3">
        {!collapsed && (
          <div className="rounded-lg border border-sidebar-border bg-sidebar-accent/45 px-3 py-2">
            <p className="text-[11px] font-semibold uppercase tracking-wide text-sidebar-foreground/55">{t('Logged in as')}</p>
            <p className="mt-1 truncate text-sm font-semibold text-sidebar-foreground">{user}</p>
          </div>
        )}
        <Button
          variant="ghost"
          size="sm"
          onClick={onLogout}
          className="w-full justify-start text-sidebar-foreground/75 hover:bg-sidebar-accent hover:text-sidebar-accent-foreground"
        >
          <LogOut size={18} />
          {!collapsed && <span className="ml-2">{t('Logout')}</span>}
        </Button>
      </div>
    </aside>
  );
}
