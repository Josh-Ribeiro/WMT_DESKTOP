import type { ReactNode } from "react";
import type { LucideIcon } from "lucide-react";
import { cn } from "@/lib/utils";

interface PageShellProps {
  children: ReactNode;
  className?: string;
  contentClassName?: string;
}

export function PageShell({
  children,
  className,
  contentClassName,
}: PageShellProps) {
  return (
    <main
      className={cn(
        "min-h-0 min-w-0 flex-1 overflow-auto overscroll-contain",
        className
      )}
    >
      <div
        className={cn(
          "mx-auto flex min-w-0 w-full max-w-[1440px] flex-col gap-5 p-4 sm:p-6 lg:gap-6 lg:p-8",
          contentClassName
        )}
      >
        {children}
      </div>
    </main>
  );
}

interface PageHeroProps {
  title: ReactNode;
  description?: ReactNode;
  eyebrow?: ReactNode;
  icon?: LucideIcon;
  meta?: ReactNode;
  action?: ReactNode;
  className?: string;
}

export function PageHero({
  title,
  description,
  eyebrow,
  icon: Icon,
  meta,
  action,
  className,
}: PageHeroProps) {
  return (
    <header
      className={cn(
        "wmt-header relative z-30 overflow-visible rounded-xl border p-4 text-slate-100 shadow-lg sm:p-5 lg:p-6",
        className
      )}
    >
      <div className="flex flex-col gap-5 xl:flex-row xl:items-end xl:justify-between">
        <div className="min-w-0">
          {(eyebrow || Icon) && (
            <div className="mb-3 flex items-center gap-2 text-xs font-semibold uppercase tracking-[0.12em] text-blue-300">
              {Icon && (
                <span
                  className="flex size-7 items-center justify-center rounded-md bg-blue-400/10"
                  aria-hidden="true"
                >
                  <Icon size={15} />
                </span>
              )}
              {eyebrow}
            </div>
          )}
          <h1 className="text-balance text-2xl font-semibold tracking-tight text-white sm:text-3xl">
            {title}
          </h1>
          {description && (
            <p className="mt-2 max-w-3xl text-sm leading-6 text-slate-400 sm:text-[15px]">
              {description}
            </p>
          )}
          {meta && (
            <div className="mt-4 flex flex-wrap items-center gap-2">{meta}</div>
          )}
        </div>
        {action && (
          <div className="w-full min-w-0 shrink-0 xl:max-w-2xl">{action}</div>
        )}
      </div>
    </header>
  );
}

interface SectionHeadingProps {
  title: ReactNode;
  description?: ReactNode;
  action?: ReactNode;
  className?: string;
}

export function SectionHeading({
  title,
  description,
  action,
  className,
}: SectionHeadingProps) {
  return (
    <div
      className={cn(
        "flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between",
        className
      )}
    >
      <div className="min-w-0">
        <h2 className="text-base font-semibold tracking-tight text-foreground">
          {title}
        </h2>
        {description && (
          <p className="mt-1 text-sm leading-5 text-muted-foreground">
            {description}
          </p>
        )}
      </div>
      {action && <div className="min-w-0 max-w-full shrink-0">{action}</div>}
    </div>
  );
}

interface EmptyStateProps {
  icon?: LucideIcon;
  title: ReactNode;
  description?: ReactNode;
  action?: ReactNode;
  className?: string;
}

export function EmptyState({
  icon: Icon,
  title,
  description,
  action,
  className,
}: EmptyStateProps) {
  return (
    <div
      className={cn(
        "flex min-h-36 flex-col items-center justify-center rounded-lg border border-dashed border-border/80 bg-muted/20 px-5 py-8 text-center",
        className
      )}
    >
      {Icon && (
        <span className="mb-3 flex size-10 items-center justify-center rounded-full border border-border bg-card text-muted-foreground shadow-sm">
          <Icon size={18} aria-hidden="true" />
        </span>
      )}
      <p className="text-sm font-medium text-foreground">{title}</p>
      {description && (
        <p className="mt-1 max-w-md text-sm text-muted-foreground">
          {description}
        </p>
      )}
      {action && <div className="mt-4">{action}</div>}
    </div>
  );
}
