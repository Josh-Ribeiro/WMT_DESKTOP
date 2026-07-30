import type { DashboardActivity, JobStatus } from "./types";

export const actionLabels: Record<string, string> = {
  "auth.login": "Login local",
  "auth.sso": "Windows SSO",
  "backup.create": "Backup iniciado",
  "backup.delete": "Backup removido",
  "backup.load_users": "Perfis carregados",
  "backup.open_destination": "Destino aberto",
  "remote.action": "Ação remota",
  "remote.job.create": "Tarefa remota criada",
  "remote.job.cancel": "Tarefa remota cancelada",
  "software_center.install_updates": "Updates iniciados",
  "terms.generate": "Termo DOCX",
  "terms.print": "Prévia de impressão",
  "diagnostics.run": "Diagnóstico iniciado",
  "diagnostics.job": "Diagnóstico registrado",
  "cleanup.quick": "Limpeza rápida",
};

const remoteActionLabels: Record<string, string> = {
  "remote-access": "Remote Access",
  "remote-assistance": "Remote Assistance",
  "computer-management": "Computer Management",
  "restart-spooler": "Restart Spooler",
  "renew-ip": "Renew IP",
  gpupdate: "GPUpdate",
  "force-all-actions": "Force All Actions",
  "clear-sccm-cache": "Clear SCCM Cache",
};

export const hiddenRemoteActions = new Set([
  "create-temp-c-share",
  "remove-temp-c-share",
]);

export function formatDateTime(value?: string) {
  if (!value) return "Sem data";
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return value;
  return new Intl.DateTimeFormat("pt-BR", {
    day: "2-digit",
    month: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  }).format(parsed);
}

export function greeting() {
  const hour = new Date().getHours();
  if (hour < 12) return "Bom dia";
  if (hour < 18) return "Boa tarde";
  return "Boa noite";
}

export function labelForRemoteAction(action: string) {
  return remoteActionLabels[action] || action || "Ação remota";
}

export function hostFromDetails(details?: Record<string, unknown>) {
  if (!details) return "";
  return String(
    details.host || details.wk || details.source || details.destination || ""
  ).toUpperCase();
}

export function activityDescription(activity: DashboardActivity) {
  const details = activity.details || {};
  if (activity.action.startsWith("backup.")) {
    const source = String(details.source || "");
    const destination = String(details.destination || "");
    const count = Number(details.users_count || details.count || 0);
    if (source && destination)
      return `${source} -> ${destination}${count ? `, ${count} perfil(is)` : ""}`;
    if (source) return `${source}${count ? `, ${count} perfil(is)` : ""}`;
  }
  if (activity.action.startsWith("remote.")) {
    return [
      String(details.host || ""),
      labelForRemoteAction(String(details.action || "")),
      String(details.job_id || ""),
    ]
      .filter(Boolean)
      .join(" - ");
  }
  if (activity.action === "software_center.install_updates") {
    const host = String(details.host || "");
    return host ? `Host ${host}` : "Software Center";
  }
  if (activity.action.startsWith("terms.")) {
    return (
      [String(details.wk || ""), String(details.employee_name || "")]
        .filter(Boolean)
        .join(" - ") || "Termo gerado"
    );
  }
  return actionLabels[activity.action] || activity.action;
}

export function isActiveStatus(status: JobStatus) {
  return status === "queued" || status === "running";
}
