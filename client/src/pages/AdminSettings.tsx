import { FormEvent, useEffect, useState } from 'react';
import { Sidebar } from '@/components/Sidebar';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { Switch } from '@/components/ui/switch';
import { useLanguage } from '@/contexts/LanguageContext';
import { useApi } from '@/hooks/useApi';
import { useAuth } from '@/hooks/useAuth';
import { apiRequest } from '@/lib/api';
import { useLocation } from 'wouter';
import { Loader2, RefreshCw, Save } from 'lucide-react';
import { toast } from 'sonner';

interface AppSettings {
  display_language: 'en-US' | 'pt-BR';
  software_center_timeout_seconds: number;
  software_center_poll_interval_seconds: number;
  update_job_timeout_minutes: number;
  backup_default_destination_path: string;
  scripts_enabled: Record<string, boolean>;
  remote_action_aliases: Record<string, string>;
}

const scriptLabels: Record<string, string> = {
  software_center: 'Software Center / SCCM Updates',
  remote_actions: 'Remote Actions',
  backup: 'Backup',
  terms: 'Terms',
};

const defaultSettings: AppSettings = {
  display_language: 'en-US',
  software_center_timeout_seconds: 180,
  software_center_poll_interval_seconds: 10,
  update_job_timeout_minutes: 120,
  backup_default_destination_path: '',
  scripts_enabled: {
    software_center: true,
    remote_actions: true,
    backup: true,
    terms: true,
  },
  remote_action_aliases: {},
};

export default function AdminSettings() {
  const { user, logout, loading: authLoading } = useAuth();
  const { t } = useLanguage();
  const [, navigate] = useLocation();
  const { data, loading, error, refetch } = useApi<AppSettings>('/api/settings', {
    skip: authLoading || !user,
  });
  const [form, setForm] = useState<AppSettings>(defaultSettings);
  const [aliasesText, setAliasesText] = useState('{}');
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    if (data) {
      const next = { ...defaultSettings, ...data };
      setForm(next);
      setAliasesText(JSON.stringify(next.remote_action_aliases || {}, null, 2));
    }
  }, [data]);

  const handleLogout = async () => {
    await logout();
    navigate('/login');
  };

  const updateNumber = (key: keyof AppSettings, value: string) => {
    setForm((current) => ({ ...current, [key]: Number(value) }));
  };

  const toggleScript = (key: string, value: boolean) => {
    setForm((current) => ({
      ...current,
      scripts_enabled: {
        ...current.scripts_enabled,
        [key]: value,
      },
    }));
  };

  const saveSettings = async (event: FormEvent) => {
    event.preventDefault();
    setSaving(true);
    try {
      const aliases = JSON.parse(aliasesText || '{}');
      const result = await apiRequest<AppSettings>('/api/settings', {
        method: 'PUT',
        body: JSON.stringify({
          ...form,
          remote_action_aliases: aliases,
        }),
      });
      const next = { ...defaultSettings, ...result };
      setForm(next);
      setAliasesText(JSON.stringify(next.remote_action_aliases || {}, null, 2));
      toast.success(t('Settings saved'));
      await refetch();
    } catch (err) {
      toast.error(t('Failed to save settings'), {
        description: err instanceof Error ? err.message : t('Check the fields and try again.'),
      });
    } finally {
      setSaving(false);
    }
  };

  if (authLoading) return null;
  if (!user) {
    navigate('/login');
    return null;
  }
  if (user.role !== 'admin') {
    navigate('/dashboard');
    return null;
  }

  return (
    <div className="flex h-screen bg-background">
      <Sidebar user={user.username} permissions={user.permissions} onLogout={handleLogout} />

      <main className="min-w-0 flex-1 overflow-auto">
        <form onSubmit={saveSettings} className="mx-auto flex w-full max-w-5xl flex-col gap-5 p-6 lg:p-8">
          <section className="flex flex-col gap-4 rounded-lg border border-border/70 bg-card p-5 shadow-sm md:flex-row md:items-center md:justify-between">
            <div className="min-w-0">
              <h1 className="text-2xl font-semibold tracking-normal text-foreground">{t('Admin Settings')}</h1>
              <p className="mt-1 text-sm text-muted-foreground">{t('Operational settings for WMT.')}</p>
            </div>
            <div className="flex flex-wrap gap-2">
              <Button type="button" variant="outline" onClick={() => refetch()} disabled={loading || saving}>
                {loading ? <Loader2 className="animate-spin" size={16} /> : <RefreshCw size={16} />}
                {t('Refresh')}
              </Button>
              <Button type="submit" disabled={saving}>
                {saving ? <Loader2 className="animate-spin" size={16} /> : <Save size={16} />}
                {t('Save')}
              </Button>
            </div>
          </section>

          {error && (
            <div className="rounded-lg border border-red-300 bg-red-50 p-4 text-sm text-red-800 dark:border-red-400/30 dark:bg-red-500/10 dark:text-red-200">
              {error}
            </div>
          )}

          <div className="grid gap-5 xl:grid-cols-[1fr_0.85fr]">
            <Card className="rounded-lg border-border/70 shadow-none">
              <CardHeader>
                <CardTitle>{t('Timeouts and polling')}</CardTitle>
              </CardHeader>
              <CardContent className="grid gap-4 sm:grid-cols-3">
                <label className="grid gap-2 text-sm">
                  <span className="font-medium text-foreground">SCCM timeout (s)</span>
                  <Input
                    type="number"
                    min={30}
                    max={1800}
                    value={form.software_center_timeout_seconds}
                    onChange={(event) => updateNumber('software_center_timeout_seconds', event.target.value)}
                  />
                </label>
                <label className="grid gap-2 text-sm">
                  <span className="font-medium text-foreground">SCCM polling (s)</span>
                  <Input
                    type="number"
                    min={5}
                    max={300}
                    value={form.software_center_poll_interval_seconds}
                    onChange={(event) => updateNumber('software_center_poll_interval_seconds', event.target.value)}
                  />
                </label>
                <label className="grid gap-2 text-sm">
                  <span className="font-medium text-foreground">Update timeout (min)</span>
                  <Input
                    type="number"
                    min={5}
                    max={720}
                    value={form.update_job_timeout_minutes}
                    onChange={(event) => updateNumber('update_job_timeout_minutes', event.target.value)}
                  />
                </label>
              </CardContent>
            </Card>

            <Card className="rounded-lg border-border/70 shadow-none">
              <CardHeader>
                <CardTitle>{t('Enabled scripts')}</CardTitle>
              </CardHeader>
              <CardContent className="space-y-3">
                {Object.entries(scriptLabels).map(([key, label]) => (
                  <div key={key} className="flex items-center justify-between gap-3 rounded-lg border border-border/70 px-3 py-2">
                    <span className="text-sm font-medium text-foreground">{t(label)}</span>
                    <Switch checked={form.scripts_enabled?.[key] ?? true} onCheckedChange={(value) => toggleScript(key, value)} />
                  </div>
                ))}
              </CardContent>
            </Card>
          </div>

          <Card className="rounded-lg border-border/70 shadow-none">
            <CardHeader>
              <CardTitle>Backup</CardTitle>
            </CardHeader>
            <CardContent>
              <label className="grid gap-2 text-sm">
                <span className="font-medium text-foreground">{t('Default destination path')}</span>
                <Input
                  value={form.backup_default_destination_path}
                  onChange={(event) => setForm((current) => ({ ...current, backup_default_destination_path: event.target.value }))}
                  placeholder="Example: D:\\BackupWMT or leave empty to use the default"
                />
              </label>
            </CardContent>
          </Card>

          <Card className="rounded-lg border-border/70 shadow-none">
            <CardHeader>
              <CardTitle>{t('Remote action aliases')}</CardTitle>
            </CardHeader>
            <CardContent className="space-y-2">
              <textarea
                value={aliasesText}
                onChange={(event) => setAliasesText(event.target.value)}
                className="min-h-40 w-full rounded-md border border-input bg-background px-3 py-2 font-mono text-sm text-foreground shadow-sm outline-none focus-visible:ring-2 focus-visible:ring-ring"
                spellCheck={false}
              />
              <p className="text-xs text-muted-foreground">
                {t('Simple JSON. Example:')} {"{ \"force sccm\": \"force all actions\" }"}
              </p>
            </CardContent>
          </Card>
        </form>
      </main>
    </div>
  );
}
