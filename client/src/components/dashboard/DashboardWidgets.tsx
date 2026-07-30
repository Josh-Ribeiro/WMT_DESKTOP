import type { ComponentType } from "react";
import { Loader2 } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import type { JobStatus } from "./types";
import { isActiveStatus } from "./dashboardUtils";

const statusStyles: Record<string, string> = {
  queued:
    "border-zinc-300 bg-zinc-50 text-zinc-700 dark:border-zinc-500/40 dark:bg-zinc-500/10 dark:text-zinc-200",
  running:
    "border-blue-300 bg-blue-50 text-blue-700 dark:border-blue-400/40 dark:bg-blue-500/10 dark:text-blue-200",
  completed:
    "border-emerald-300 bg-emerald-50 text-emerald-700 dark:border-emerald-400/40 dark:bg-emerald-500/10 dark:text-emerald-200",
  failed:
    "border-red-300 bg-red-50 text-red-700 dark:border-red-400/40 dark:bg-red-500/10 dark:text-red-200",
  canceled:
    "border-amber-300 bg-amber-50 text-amber-700 dark:border-amber-400/40 dark:bg-amber-500/10 dark:text-amber-200",
};

const statusLabels: Record<string, string> = {
  queued: "Na fila",
  running: "Em execução",
  completed: "Concluído",
  failed: "Falhou",
  canceled: "Cancelado",
};

export function StatusBadge({ status }: { status: JobStatus }) {
  return (
    <Badge
      variant="outline"
      className={statusStyles[status] || "border-border"}
    >
      {isActiveStatus(status) && <Loader2 className="animate-spin" size={13} />}
      {statusLabels[status] || status}
    </Badge>
  );
}

export function KpiTile({
  label,
  value,
  helper,
  icon: Icon,
  tone,
}: {
  label: string;
  value: number;
  helper: string;
  icon: ComponentType<{ size?: number }>;
  tone: string;
}) {
  return (
    <div className="relative overflow-hidden rounded-lg border border-border/70 bg-card/95 px-4 py-3 shadow-sm backdrop-blur">
      <div
        className={`absolute inset-x-0 top-0 h-1 ${tone.split(" ").find(item => item.startsWith("bg-")) || "bg-primary"}`}
      />
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <p className="text-[11px] font-semibold uppercase tracking-wide text-muted-foreground">
            {label}
          </p>
          <p className="mt-2 text-2xl font-semibold text-foreground">{value}</p>
        </div>
        <div className={`rounded-md border p-2 shadow-sm ${tone}`}>
          <Icon size={17} />
        </div>
      </div>
      <p className="mt-3 line-clamp-2 text-xs text-muted-foreground">
        {helper}
      </p>
    </div>
  );
}

export function DashboardSkeleton() {
  return (
    <div
      className="space-y-5"
      aria-label="Carregando Dashboard"
      aria-busy="true"
    >
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-5">
        {Array.from({ length: 5 }, (_, index) => (
          <div
            key={index}
            className="rounded-lg border border-border/70 bg-card/80 p-4"
          >
            <div className="flex items-start justify-between gap-3">
              <div className="space-y-3">
                <Skeleton className="h-3 w-20" />
                <Skeleton className="h-8 w-14" />
              </div>
              <Skeleton className="size-9 rounded-md" />
            </div>
            <Skeleton className="mt-4 h-3 w-4/5" />
          </div>
        ))}
      </div>
      <div className="grid gap-5 xl:grid-cols-[minmax(0,1.35fr)_minmax(320px,0.65fr)]">
        <Skeleton className="h-80 rounded-lg" />
        <Skeleton className="h-80 rounded-lg" />
      </div>
    </div>
  );
}
