import { type ReactNode, useEffect } from "react";
import { ShieldAlert } from "lucide-react";
import { useLocation } from "wouter";
import { useAuth } from "@/hooks/useAuth";
import { useLanguage } from "@/contexts/LanguageContext";
import { canAccessRoute, type RoutePolicy } from "@/lib/routePolicy";

export function AuthenticationGuard({ children }: { children: ReactNode }) {
  const { loading, user } = useAuth();
  const [, navigate] = useLocation();

  useEffect(() => {
    if (!loading && !user) navigate("/login", { replace: true });
  }, [loading, navigate, user]);

  if (loading || !user) return <div className="min-h-screen bg-background" />;
  return <>{children}</>;
}

export function PermissionGuard({
  children,
  policy,
}: {
  children: ReactNode;
  policy: RoutePolicy;
}) {
  const { user } = useAuth();
  const { t } = useLanguage();

  if (!user || !canAccessRoute(user, policy)) {
    return (
      <main className="flex h-full min-h-96 items-center justify-center overflow-auto p-6">
        <div className="max-w-md rounded-xl border bg-card p-7 text-center shadow-sm">
          <ShieldAlert className="mx-auto text-destructive" size={36} />
          <h1 className="mt-4 text-xl font-semibold">
            {t("Acesso não autorizado")}
          </h1>
          <p className="mt-2 text-sm text-muted-foreground">
            {t(
              "Sua conta não possui a permissão necessária para acessar esta área."
            )}
          </p>
        </div>
      </main>
    );
  }

  return <>{children}</>;
}
