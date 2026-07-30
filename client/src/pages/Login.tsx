import { FormEvent, useEffect, useRef, useState } from "react";
import { useLocation } from "wouter";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Separator } from "@/components/ui/separator";
import { useAuth } from "@/hooks/useAuth";
import { useLanguage } from "@/contexts/LanguageContext";
import { Loader2, LogIn, RefreshCw, ShieldCheck } from "lucide-react";
import { toast } from "sonner";

export default function Login() {
  const { user, loading, login, ssoLogin } = useAuth();
  const { t } = useLanguage();
  const [, navigate] = useLocation();
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [retryingSso, setRetryingSso] = useState(false);
  const [errorMessage, setErrorMessage] = useState("");
  const autoSsoAttempted = useRef(false);

  useEffect(() => {
    if (user) {
      navigate("/dashboard");
    }
  }, [navigate, user]);

  useEffect(() => {
    if (loading || user || autoSsoAttempted.current) {
      return;
    }

    autoSsoAttempted.current = true;
    setRetryingSso(true);
    setErrorMessage("");
    ssoLogin()
      .then(() => {
        toast.success("Sessão AD detectada");
        navigate("/dashboard");
      })
      .catch(() => {
        setErrorMessage("");
      })
      .finally(() => {
        setRetryingSso(false);
      });
  }, [loading, navigate, ssoLogin, user]);

  const handleSubmit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const cleanUsername = username.trim();
    if (!cleanUsername || !password) {
      setErrorMessage("Informe usuário e senha.");
      return;
    }

    setSubmitting(true);
    setErrorMessage("");
    try {
      await login(cleanUsername, password);
      toast.success("Login realizado com sucesso");
      navigate("/dashboard");
    } catch (error) {
      const text =
        error instanceof Error ? error.message : "Falha ao autenticar";
      setErrorMessage(text);
      toast.error(text);
    } finally {
      setSubmitting(false);
    }
  };

  const handleSsoRetry = async () => {
    setRetryingSso(true);
    setErrorMessage("");
    try {
      await ssoLogin();
      toast.success("Login Windows realizado");
      navigate("/dashboard");
    } catch (error) {
      const text =
        error instanceof Error ? error.message : "Windows SSO indisponível";
      setErrorMessage(text);
      toast.error(text);
    } finally {
      setRetryingSso(false);
    }
  };

  const busy = loading || submitting || retryingSso;

  return (
    <div className="flex min-h-screen items-center justify-center bg-background p-4">
      <Card className="w-full max-w-md">
        <CardHeader className="space-y-3 text-center">
          <div className="mx-auto flex h-12 w-12 items-center justify-center rounded-lg bg-primary text-primary-foreground">
            <ShieldCheck size={26} />
          </div>
          <CardTitle className="text-2xl">WMT Desktop</CardTitle>
          <CardDescription>
            {t("Conectando com sua sessão do Active Directory")}
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-5">
          {retryingSso && (
            <div className="flex items-center gap-3 rounded-lg border border-blue-300 bg-blue-50 px-3 py-2 text-sm text-blue-800 dark:border-blue-400/30 dark:bg-blue-500/10 dark:text-blue-200">
              <Loader2 className="animate-spin" size={16} />
              {t("Detectando usuário Windows e permissões no AD...")}
            </div>
          )}

          <form className="space-y-4" onSubmit={handleSubmit}>
            <div className="space-y-2">
              <Label htmlFor="username">{t("Usuário")}</Label>
              <Input
                id="username"
                autoComplete="username"
                value={username}
                onChange={event => setUsername(event.target.value)}
                disabled={busy}
                autoFocus
              />
            </div>

            <div className="space-y-2">
              <Label htmlFor="password">{t("Senha")}</Label>
              <Input
                id="password"
                type="password"
                autoComplete="current-password"
                value={password}
                onChange={event => setPassword(event.target.value)}
                disabled={busy}
              />
            </div>

            {errorMessage && (
              <div className="rounded-md border border-destructive/30 bg-destructive/10 px-3 py-2 text-sm text-destructive">
                {errorMessage}
              </div>
            )}

            <Button className="w-full gap-2" type="submit" disabled={busy}>
              {submitting ? (
                <Loader2 className="animate-spin" size={16} />
              ) : (
                <LogIn size={16} />
              )}
              {t("Entrar")}
            </Button>
          </form>

          <Separator />

          <Button
            className="w-full gap-2"
            variant="outline"
            onClick={handleSsoRetry}
            disabled={busy}
          >
            {retryingSso ? (
              <Loader2 className="animate-spin" size={16} />
            ) : (
              <RefreshCw size={16} />
            )}
            {t("Entrar com Active Directory")}
          </Button>
        </CardContent>
      </Card>
    </div>
  );
}
