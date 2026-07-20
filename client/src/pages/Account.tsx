import { useState } from 'react';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Badge } from '@/components/ui/badge';
import { Separator } from '@/components/ui/separator';
import { Switch } from '@/components/ui/switch';
import { Sidebar } from '@/components/Sidebar';
import { useAuth } from '@/hooks/useAuth';
import { useLanguage } from '@/contexts/LanguageContext';
import { useTheme } from '@/contexts/ThemeContext';
import { useLocation } from 'wouter';
import { useNotification } from '@/hooks/useNotification';
import { apiRequest } from '@/lib/api';
import {
  Check,
  KeyRound,
  Lock,
  LogOut,
  Languages,
  Moon,
  Palette,
  Settings,
  ShieldCheck,
  Sun,
  User,
} from 'lucide-react';

const accentOptions = [
  { value: 'blue', label: 'Blue', className: 'bg-blue-600' },
  { value: 'violet', label: 'Violet', className: 'bg-violet-600' },
  { value: 'pink', label: 'Pink', className: 'bg-pink-600' },
  { value: 'emerald', label: 'Emerald', className: 'bg-emerald-600' },
  { value: 'cyan', label: 'Cyan', className: 'bg-cyan-600' },
  { value: 'amber', label: 'Amber', className: 'bg-amber-500' },
] as const;

export default function Account() {
  const { user, logout } = useAuth();
  const { theme, setTheme, accentColor, setAccentColor } = useTheme();
  const { language, setLanguage, t } = useLanguage();
  const [, navigate] = useLocation();
  const { success, error } = useNotification();
  const [oldPassword, setOldPassword] = useState('');
  const [newPassword, setNewPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');

  const handleLogout = async () => {
    await logout();
    navigate('/login');
  };

  const handleChangePassword = async () => {
    if (!oldPassword || !newPassword || !confirmPassword) {
      error(t('Please fill in all password fields'));
      return;
    }

    if (newPassword !== confirmPassword) {
      error(t('New passwords do not match'));
      return;
    }

    if (newPassword.length < 8) {
      error(t('Password must be at least 8 characters long'));
      return;
    }

    try {
      await apiRequest('/api/account/change-password', {
        method: 'POST',
        body: JSON.stringify({
          old_password: oldPassword,
          new_password: newPassword,
        }),
      });

      success(t('Password changed successfully'));
      setOldPassword('');
      setNewPassword('');
      setConfirmPassword('');
    } catch (err) {
      error(err instanceof Error ? err.message : t('Failed to change password'));
    }
  };

  if (!user) {
    navigate('/login');
    return null;
  }

  const isWindowsSession = user.auth_source === 'windows';
  const displayName = user.display_name || user.username;

  return (
    <div className="flex h-screen bg-background">
      <Sidebar user={user.username} permissions={user.permissions} onLogout={handleLogout} />

      <main className="flex-1 overflow-auto">
        <div className="mx-auto flex w-full max-w-6xl flex-col gap-6 p-6 lg:p-8">
          <section className="flex flex-col gap-4 rounded-lg border border-border/70 bg-card p-6 shadow-sm md:flex-row md:items-center md:justify-between">
            <div className="flex min-w-0 items-center gap-4">
              <div className="flex size-12 shrink-0 items-center justify-center rounded-lg bg-primary text-primary-foreground">
                <Settings size={22} />
              </div>
              <div className="min-w-0">
                <h1 className="text-2xl font-semibold tracking-normal text-foreground">{t('Settings')}</h1>
                <p className="mt-1 text-sm text-muted-foreground">
                  {t('Account details, access profile and WMT appearance preferences.')}
                </p>
              </div>
            </div>
            <div className="flex flex-wrap gap-2">
              <Badge variant="outline" className="capitalize">{user.role}</Badge>
              <Badge variant="outline" className={isWindowsSession ? 'border-blue-200 bg-blue-50 text-blue-700 dark:border-blue-400/30 dark:bg-blue-500/10 dark:text-blue-200' : ''}>
                {isWindowsSession ? 'Windows SSO' : t('Local account')}
              </Badge>
            </div>
          </section>

          <div className="grid grid-cols-1 gap-6 xl:grid-cols-[0.9fr_1.1fr]">
            <div className="flex flex-col gap-6">
              <Card className="rounded-lg border-border/70 shadow-none">
                <CardHeader>
                  <CardTitle className="flex items-center gap-2">
                    <User size={19} />
                    {t('Profile')}
                  </CardTitle>
                  <CardDescription>{t('Current identity used by WMT.')}</CardDescription>
                </CardHeader>
                <CardContent className="space-y-5">
                  <div>
                    <p className="text-xs font-semibold uppercase text-muted-foreground">{t('Display name')}</p>
                    <p className="mt-1 text-lg font-semibold text-foreground">{displayName}</p>
                  </div>
                  <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
                    <div className="rounded-lg border border-border/70 p-3">
                      <p className="text-xs font-semibold uppercase text-muted-foreground">{t('Username')}</p>
                      <p className="mt-1 truncate text-sm font-medium text-foreground">{user.username}</p>
                    </div>
                    <div className="rounded-lg border border-border/70 p-3">
                      <p className="text-xs font-semibold uppercase text-muted-foreground">{t('Domain')}</p>
                      <p className="mt-1 truncate text-sm font-medium text-foreground">{user.domain || t('Local')}</p>
                    </div>
                    <div className="rounded-lg border border-border/70 p-3 sm:col-span-2">
                      <p className="text-xs font-semibold uppercase text-muted-foreground">E-mail</p>
                      <p className="mt-1 truncate text-sm font-medium text-foreground">{user.email || t('Not available')}</p>
                    </div>
                  </div>

                  <Separator />

                  <div>
                    <p className="text-xs font-semibold uppercase text-muted-foreground">{t('Permissions')}</p>
                    <div className="mt-3 flex flex-wrap gap-2">
                      {user.permissions?.length ? (
                        user.permissions.map((perm) => (
                          <Badge key={perm} variant="secondary" className="capitalize">
                            {perm}
                          </Badge>
                        ))
                      ) : (
                        <span className="text-sm text-muted-foreground">{t('No explicit permissions loaded.')}</span>
                      )}
                    </div>
                  </div>
                </CardContent>
              </Card>

              <Card className="rounded-lg border-border/70 shadow-none">
                <CardHeader>
                  <CardTitle className="flex items-center gap-2">
                    <ShieldCheck size={19} />
                    {t('Session')}
                  </CardTitle>
                  <CardDescription>{t('Current authentication state.')}</CardDescription>
                </CardHeader>
                <CardContent className="space-y-4">
                  <div className="rounded-lg border border-border/70 bg-muted/40 p-4">
                    <p className="text-sm font-medium text-foreground">
                      {isWindowsSession ? t('Authenticated with your Windows account.') : t('Authenticated with a local WMT account.')}
                    </p>
                    <p className="mt-1 text-sm text-muted-foreground">
                      {t('Access is controlled by your role and available permissions.')}
                    </p>
                  </div>
                  <Button variant="destructive" onClick={handleLogout} className="w-full gap-2">
                    <LogOut size={18} />
                    {t('Logout')}
                  </Button>
                </CardContent>
              </Card>
            </div>

            <div className="flex flex-col gap-6">
              <Card className="rounded-lg border-border/70 shadow-none">
                <CardHeader>
                  <CardTitle className="flex items-center gap-2">
                    <Palette size={19} />
                    {t('Appearance')}
                  </CardTitle>
                  <CardDescription>{t('Choose how WMT should look on this workstation.')}</CardDescription>
                </CardHeader>
                <CardContent className="space-y-6">
                  <div className="flex flex-col gap-4 rounded-lg border border-border/70 p-4 sm:flex-row sm:items-center sm:justify-between">
                    <div className="flex items-center gap-3">
                      <div className="flex size-10 items-center justify-center rounded-md bg-muted text-foreground">
                        <Languages size={18} />
                      </div>
                      <div>
                        <p className="font-medium text-foreground">{t('Interface language')}</p>
                        <p className="text-sm text-muted-foreground">{t('Choose the language used by WMT on this workstation.')}</p>
                      </div>
                    </div>
                    <select
                      value={language}
                      onChange={(event) => setLanguage(event.target.value as 'en-US' | 'pt-BR')}
                      className="h-10 min-w-40 rounded-md border border-input bg-background px-3 text-sm text-foreground shadow-sm outline-none focus-visible:ring-2 focus-visible:ring-ring"
                    >
                      <option value="en-US">{t('English')}</option>
                      <option value="pt-BR">{t('Portuguese')}</option>
                    </select>
                  </div>

                  <div className="flex flex-col gap-4 rounded-lg border border-border/70 p-4 sm:flex-row sm:items-center sm:justify-between">
                    <div className="flex items-center gap-3">
                      <div className="flex size-10 items-center justify-center rounded-md bg-muted text-foreground">
                        {theme === 'dark' ? <Moon size={18} /> : <Sun size={18} />}
                      </div>
                      <div>
                        <p className="font-medium text-foreground">{t('Dark mode')}</p>
                        <p className="text-sm text-muted-foreground">{t('Use a darker interface for low-light environments.')}</p>
                      </div>
                    </div>
                    <Switch
                      checked={theme === 'dark'}
                      onCheckedChange={(checked) => setTheme(checked ? 'dark' : 'light')}
                    />
                  </div>

                  <div>
                    <div className="mb-3">
                      <p className="font-medium text-foreground">{t('Accent color')}</p>
                      <p className="text-sm text-muted-foreground">{t('This changes buttons, selected navigation and focus color.')}</p>
                    </div>
                    <div className="grid grid-cols-2 gap-3 sm:grid-cols-3">
                      {accentOptions.map((option) => {
                        const selected = accentColor === option.value;
                        return (
                          <button
                            key={option.value}
                            type="button"
                            onClick={() => setAccentColor(option.value)}
                            className={`flex items-center gap-3 rounded-lg border p-3 text-left transition-colors ${
                              selected ? 'border-primary bg-primary/10' : 'border-border hover:bg-muted'
                            }`}
                          >
                            <span className={`flex size-8 shrink-0 items-center justify-center rounded-md ${option.className} text-white`}>
                              {selected && <Check size={16} />}
                            </span>
                            <span className="text-sm font-medium text-foreground">{t(option.label)}</span>
                          </button>
                        );
                      })}
                    </div>
                  </div>

                  <div className="rounded-lg border border-border/70 bg-muted/30 p-4">
                    <p className="text-sm font-medium text-foreground">{t('Preview')}</p>
                    <div className="mt-3 flex flex-wrap items-center gap-2">
                      <Button size="sm">{t('Primary action')}</Button>
                      <Button size="sm" variant="outline">{t('Secondary')}</Button>
                      <Badge>{t('Selected')}</Badge>
                    </div>
                  </div>
                </CardContent>
              </Card>

              <Card className="rounded-lg border-border/70 shadow-none">
                <CardHeader>
                  <CardTitle className="flex items-center gap-2">
                    <Lock size={19} />
                    {t('Security')}
                  </CardTitle>
                  <CardDescription>
                    {isWindowsSession
                      ? t('Password is managed by Active Directory for this session.')
                      : t('Manage your local WMT password.')}
                  </CardDescription>
                </CardHeader>
                <CardContent>
                  {isWindowsSession ? (
                    <div className="flex gap-3 rounded-lg border border-blue-200 bg-blue-50 p-4 text-blue-800 dark:border-blue-400/30 dark:bg-blue-500/10 dark:text-blue-200">
                      <KeyRound className="mt-0.5 shrink-0" size={18} />
                      <div>
                        <p className="text-sm font-medium">{t('Windows account security')}</p>
                        <p className="mt-1 text-sm">
                          {t('Password changes should be done through Windows/Active Directory policies.')}
                        </p>
                      </div>
                    </div>
                  ) : (
                    <div className="space-y-4">
                      <div>
                        <label className="text-sm font-medium text-foreground">{t('Current Password')}</label>
                        <Input
                          type="password"
                          value={oldPassword}
                          onChange={(e) => setOldPassword(e.target.value)}
                          placeholder={t('Enter current password')}
                          className="mt-1"
                        />
                      </div>

                      <div>
                        <label className="text-sm font-medium text-foreground">{t('New Password')}</label>
                        <Input
                          type="password"
                          value={newPassword}
                          onChange={(e) => setNewPassword(e.target.value)}
                          placeholder={t('Enter new password')}
                          className="mt-1"
                        />
                      </div>

                      <div>
                        <label className="text-sm font-medium text-foreground">{t('Confirm Password')}</label>
                        <Input
                          type="password"
                          value={confirmPassword}
                          onChange={(e) => setConfirmPassword(e.target.value)}
                          placeholder={t('Confirm new password')}
                          className="mt-1"
                        />
                      </div>

                      <Button onClick={handleChangePassword} className="w-full">
                        {t('Update Password')}
                      </Button>
                    </div>
                  )}
                </CardContent>
              </Card>
            </div>
          </div>
        </div>
      </main>
    </div>
  );
}
